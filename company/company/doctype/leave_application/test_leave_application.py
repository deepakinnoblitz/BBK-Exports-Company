# Copyright (c) 2025, deepak and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, add_days, now_datetime
from unittest.mock import patch

class TestLeaveApplicationTiming(FrappeTestCase):
    def setUp(self):
        # Generate a unique ID to avoid duplicates across test runs
        unique = str(now_datetime().timestamp()).replace(".", "")
        
        # 1. Create User
        self.user = frappe.get_doc({
            "doctype": "User",
            "email": f"test_leave_{unique}@example.com",
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

        la = frappe.get_doc({
            "doctype": "Leave Allocation",
            "employee": self.employee_id,
            "leave_type": "Unpaid Leave",
            "from_date": "2026-01-01",
            "to_date": "2026-12-31",
            "new_leaves_allocated": 10,
            "total_leaves_allocated": 10,
            "status": "Approved"
        })
        la.insert(ignore_permissions=True)
        la.submit()

        # 4. Ensure Evaluation Point "Disagree" exists
        if not frappe.db.exists("Evaluation Point", "Disagree"):
            frappe.get_doc({
                "doctype": "Evaluation Point",
                "point_name": "Disagree",
                "default_score": -5
            }).insert(ignore_permissions=True)

        # 5. Ensure Evaluation Trait "Attendance" exists
        if not frappe.db.exists("Evaluation Trait", "Attendance"):
            frappe.get_doc({
                "doctype": "Evaluation Trait",
                "trait_name": "Attendance"
            }).insert(ignore_permissions=True)

        # 6. Ensure Workflow States exist
        for ws in ["Pending Approval", "Approved", "Clarification Requested", "Rejected"]:
            if not frappe.db.exists("Workflow State", ws):
                frappe.get_doc({
                    "doctype": "Workflow State",
                    "workflow_state_name": ws
                }).insert(ignore_permissions=True)

        # 7. Create Evaluation Automation Rule for a specific day (Wednesday)
        frappe.db.delete("Evaluation Automation Rule", {"event_type": "Specific Day Leave", "specific_day": "Wednesday"})
        self.rule = frappe.get_doc({
            "doctype": "Evaluation Automation Rule",
            "rule_name": f"Test Rule {unique}",
            "event_type": "Specific Day Leave",
            "specific_day": "Wednesday",
            "enabled": 1,
            "trait": "Attendance",
            "evaluation_point": "Disagree"
        }).insert(ignore_permissions=True)

    def test_leave_evaluation_timing(self):
        # Find the next Wednesday's date
        today_date = getdate()
        days_ahead = 2 - today_date.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        wednesday = add_days(today_date, days_ahead)

        # Create a Leave Application for Wednesday (Pending Approval status)
        leave = frappe.get_doc({
            "doctype": "Leave Application",
            "employee": self.employee_id,
            "leave_type": "Unpaid Leave",
            "from_date": wednesday,
            "to_date": wednesday,
            "workflow_state": "Pending Approval",
            "company": self.emp.company,
            "follow_via_email": 0,
            "reson": "Test Reason"
        })

        with patch('frappe.model.document.Document.validate_workflow'):
            with patch('company.company.evaluation_automation._create_automated_evaluation') as mock_create:
                # 1. On insert / auto-submit, workflow_state is "Pending Approval" -> Should NOT trigger evaluation
                leave.insert(ignore_permissions=True)
                if leave.docstatus == 0:
                    leave.submit()

                mock_create.assert_not_called()

                # 2. Update to "Clarification Requested" -> Should NOT trigger evaluation
                leave.workflow_state = "Clarification Requested"
                leave.save(ignore_permissions=True)
                mock_create.assert_not_called()

                # 3. Update to "Approved" -> SHOULD trigger evaluation
                leave.workflow_state = "Approved"
                leave.save(ignore_permissions=True)
                mock_create.assert_called_once()
