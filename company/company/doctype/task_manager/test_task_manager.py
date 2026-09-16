# Copyright (c) 2026, deepak and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, add_days, now_datetime
from company.company.doctype.task_manager.task_manager import close_task

class TestTaskManagerDelayed(FrappeTestCase):
    def setUp(self):
        # Generate a unique ID to avoid duplicates across test runs
        unique = str(now_datetime().timestamp()).replace(".", "")
        
        # 1. Create User
        self.user = frappe.get_doc({
            "doctype": "User",
            "email": f"test_task_{unique}@example.com",
            "first_name": "Test Task User",
            "enabled": 1
        }).insert(ignore_permissions=True)
        
        # 2. Create Employee
        self.emp = frappe.get_doc({
            "doctype": "Employee",
            "employee_id": f"TEST-T-{unique}",
            "employee_name": "Test Task Employee",
            "email": self.user.email,
            "user": self.user.name,
            "date_of_joining": "2025-01-01",
            "status": "Active",
            "company": "_Test Company",
            "evaluation_score": 100
        }).insert(ignore_permissions=True)
        
        self.employee_id = self.emp.name

        # 3. Ensure Evaluation Point "Disagree" exists with -5 score
        if frappe.db.exists("Evaluation Point", "Disagree"):
            frappe.db.set_value("Evaluation Point", "Disagree", "default_score", -5)
        else:
            frappe.get_doc({
                "doctype": "Evaluation Point",
                "point_name": "Disagree",
                "default_score": -5
            }).insert(ignore_permissions=True)

        # 4. Ensure Evaluation Trait "Attendance" exists
        if not frappe.db.exists("Evaluation Trait", "Attendance"):
            frappe.get_doc({
                "doctype": "Evaluation Trait",
                "trait_name": "Attendance"
            }).insert(ignore_permissions=True)

        # Clear any trait-specific score overrides for Disagree to avoid interference
        trait = frappe.get_doc("Evaluation Trait", "Attendance")
        trait.evaluation_scores = []
        trait.save(ignore_permissions=True)

        # 5. Create Evaluation Automation Rule for "Task Delayed"
        frappe.db.delete("Evaluation Automation Rule", {"event_type": "Task Delayed"})
        self.rule = frappe.get_doc({
            "doctype": "Evaluation Automation Rule",
            "rule_name": f"Task Delayed Rule {unique}",
            "event_type": "Task Delayed",
            "enabled": 1,
            "trait": "Attendance",
            "evaluation_point": "Disagree"
        }).insert(ignore_permissions=True)

        # 6. Ensure Project exists
        if not frappe.db.exists("Project", "Test Project"):
            frappe.get_doc({
                "doctype": "Project",
                "project": "Test Project"
            }).insert(ignore_permissions=True)

    def test_task_delayed_by_hours(self):
        # Create a task estimated for 1 hour, due in the future
        task = frappe.get_doc({
            "doctype": "Task Manager",
            "title": "Delayed Task Test",
            "project": "Test Project",
            "due_date": add_days(getdate(), 5),
            "estimated_time": 1.0,
            "status": "Open",
            "assignees": [{
                "employee": self.employee_id,
                "user": self.user.name
            }]
        })
        task.insert(ignore_permissions=True)

        score_before = frappe.db.get_value("Employee", self.employee_id, "evaluation_score")
        print(f"\n--- SCORE BEFORE CLOSE: {score_before} ---")

        # Close the task spent 2 hours (2:00) -> Should trigger Task Delayed
        close_task(task.name, "02:00", "Took longer than expected")

        # Verify Employee Evaluation was created and submitted
        evals = frappe.get_all("Employee Evaluation", filters={
            "employee": self.employee_id,
            "evaluation_type": "Disagree",
            "docstatus": 1
        })
        self.assertEqual(len(evals), 1)

        # Print all score logs in the system, no limit, no filters
        logs = frappe.db.get_all("Employee Evaluation Score Log", fields=["*"], limit=1000)
        print("\n=== ALL SCORE LOGS IN SYSTEM ===")
        for log in logs:
            if log.employee == self.employee_id or log.employee_evaluation == evals[0]["name"]:
                print(f"MATCH: {log.name} - employee: {log.employee} - change: {log.change} - reason: {log.reason} - eval: {log.employee_evaluation}")
            else:
                print(f"Other: {log.name} - employee: {log.employee} - change: {log.change}")
        print("====================================")

        # Verify Employee score reduced by 5 points (from 100 to 95)
        score = frappe.db.get_value("Employee", self.employee_id, "evaluation_score")
        print(f"--- SCORE AFTER CLOSE: {score} ---")
        self.assertEqual(score, 95)

        # Verify duplicate evaluation is NOT created upon resaving/updating
        task_doc = frappe.get_doc("Task Manager", task.name)
        task_doc.description = "Updated description"
        task_doc.save(ignore_permissions=True)

        evals_after = frappe.get_all("Employee Evaluation", filters={
            "employee": self.employee_id,
            "evaluation_type": "Disagree",
            "docstatus": 1
        })
        self.assertEqual(len(evals_after), 1)

    def test_task_on_time_by_hours(self):
        # Create a task estimated for 2 hours, due in the future
        task = frappe.get_doc({
            "doctype": "Task Manager",
            "title": "On Time Task Test",
            "project": "Test Project",
            "due_date": add_days(getdate(), 5),
            "estimated_time": 2.0,
            "status": "Open",
            "assignees": [{
                "employee": self.employee_id,
                "user": self.user.name
            }]
        })
        task.insert(ignore_permissions=True)

        # Close the task spent 1.5 hours (1:30) -> Should NOT trigger Task Delayed
        close_task(task.name, "01:30", "Completed quickly")

        # Verify NO Employee Evaluation was created for "Disagree"
        evals = frappe.get_all("Employee Evaluation", filters={
            "employee": self.employee_id,
            "evaluation_type": "Disagree"
        })
        self.assertEqual(len(evals), 0)

        # Verify employee score remains 100
        score = frappe.db.get_value("Employee", self.employee_id, "evaluation_score")
        self.assertEqual(score, 100)
