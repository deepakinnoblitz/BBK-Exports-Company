import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_first_day, get_last_day, add_days, now_datetime
from company.company.doctype.employee_monthly_award.employee_monthly_award import (
    calculate_attendance_score,
    calculate_leave_penalty,
    calculate_monthly_awards
)

class TestEmployeeMonthlyAward(FrappeTestCase):
    def setUp(self):
        # Generate a unique ID to avoid duplicates across test runs
        unique = str(now_datetime().timestamp()).replace(".", "")
        
        # 1. Create User
        self.user = frappe.get_doc({
            "doctype": "User",
            "email": f"test_{unique}@example.com",
            "first_name": "Test User",
            "enabled": 1
        }).insert(ignore_permissions=True)
        
        # 2. Create Employee
        self.emp = frappe.get_doc({
            "doctype": "Employee",
            "employee_id": f"TEST-{unique}",
            "employee_name": "Test Employee",
            "email": self.user.email,
            "user": self.user.name,
            "date_of_joining": "2025-01-01",
            "status": "Active",
            "company": "_Test Company"
        }).insert(ignore_permissions=True)
        
        self.employee_id = self.emp.name

        # 3. Ensure Leave Type and Allocation
        if not frappe.db.exists("Leave Type", "Unpaid Leave"):
            frappe.get_doc({
                "doctype": "Leave Type",
                "leave_type_name": "Unpaid Leave",
                "is_lwp": 1
            }).insert(ignore_permissions=True)

        # Submit Allocation so it's active
        la = frappe.get_doc({
            "doctype": "Leave Allocation",
            "employee": self.employee_id,
            "leave_type": "Unpaid Leave",
            "from_date": "2026-01-01",
            "to_date": "2026-12-31",
            "new_leaves_allocated": 10
        })
        la.insert(ignore_permissions=True)
        la.submit()

        # 4. Setup Award Settings
        settings = frappe.get_single("Employee Award Settings")
        settings.attendance_weight = 30
        settings.personality_weight = 30
        settings.login_time_weight = 20
        settings.overtime_weight = 10
        settings.leave_penalty_weight = 20
        settings.leave_penalty_per_day = 5.0
        settings.daily_working_hours = 8
        settings.save()

    def test_attendance_score(self):
        month = "2026-03-01"
        start_date = get_first_day(month)
        end_date = get_last_day(month)
        working_days = 20
        settings = frappe.get_single("Employee Award Settings")

        # Mock 10 days present - MUST SUBMIT for some validations
        for i in range(10):
            att = frappe.get_doc({
                "doctype": "Attendance",
                "employee": self.employee_id,
                "attendance_date": add_days(start_date, i),
                "status": "Present"
            })
            att.insert(ignore_permissions=True)
            att.submit()

        score, log = calculate_attendance_score(self.employee_id, start_date, end_date, working_days, settings)
        # (10/20) * 30 = 15
        self.assertEqual(score, 15.0)
        self.assertIn("10/20 days", log)

    def test_leave_penalty(self):
        month = "2026-03-01"
        start_date = get_first_day(month)
        end_date = get_last_day(month)
        settings = frappe.get_single("Employee Award Settings")

        # Mock 1 day leave
        leave = frappe.get_doc({
            "doctype": "Leave Application",
            "employee": self.employee_id,
            "leave_type": "Unpaid Leave",
            "from_date": add_days(start_date, 15),
            "to_date": add_days(start_date, 15),
            "workflow_state": "Approved", # Manually set to skip workflow
            "company": self.emp.company,
            "follow_via_email": 0
        })
        # Use insert() then manually set docstatus to skip validation if needed, 
        # or just submit() if balance is fixed
        leave.insert(ignore_permissions=True)
        leave.submit()

        penalty_score, log = calculate_leave_penalty(self.employee_id, start_date, end_date, settings)
        # 20 - (1 * 5) = 15
        self.assertEqual(penalty_score, 15.0)
        self.assertIn("1 leaves", log)

    def test_overtime_score(self):
        month = "2026-03-01"
        start_date = get_first_day(month)
        end_date = get_last_day(month)
        working_days = 20 # Mocked
        settings = frappe.get_single("Employee Award Settings")
        
        # Standard: 8 * 20 = 160 hrs
        # Mock 176 hours (10% overtime)
        frappe.get_doc({
            "doctype": "Employee Session",
            "employee": self.employee_id,
            "login_date": start_date,
            "total_work_hours": 176
        }).insert(ignore_permissions=True)
        
        score, log = calculate_overtime_score(self.employee_id, start_date, end_date, working_days, settings)
        # (16/160) * 10 = 1.0 point
        self.assertEqual(score, 1.0)
        self.assertIn("16.0 hrs", log)

    def test_monthly_award_generation(self):
        month = "2026-03-01"
        start_date = get_first_day(month)
        
        # Ensure at least one attendance so employee is picked up if logic filters by activity
        frappe.get_doc({
            "doctype": "Attendance",
            "employee": self.employee_id,
            "attendance_date": start_date,
            "status": "Present"
        }).insert(ignore_permissions=True).submit()

        # Clear existing awards for the month in TEST DB
        frappe.db.delete("Employee Monthly Award", {"month": month})
        
        # Run generator
        calculate_monthly_awards(month)
        
        # Check if record created
        award = frappe.db.exists("Employee Monthly Award", {"employee": self.employee_id, "month": month})
        self.assertTrue(award)

    def tearDown(self):
        # Transaction is rolled back automatically by FrappeTestCase
        pass