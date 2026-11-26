# -*- coding: utf-8 -*-
import frappe
from frappe.model.document import Document

class PermissionManagement(Document):
    def validate(self):
        # Auto populate child mapping rows if empty
        self.populate_default_permissions()

        # Validate that if any action is allowed, View is also enabled
        for perm in self.permissions:
            if (perm.add_permission or perm.edit_permission or perm.delete_permission or perm.export_permission or perm.get("import_permission")):
                perm.view_permission = 1

    @frappe.whitelist()
    def populate_default_permissions(self):
        # Always build or sync permissions when backend_master_role is selected
        if not self.backend_master_role:
            return

        # Map backend master roles to their corresponding modules & screen registry list
        role = self.backend_master_role.strip()
        modules_list = []

        if role == "HR":
            modules_list = [
                ("dashboard", "HR Dashboard"),
                ("employee", "Employee List"),
                ("employee", "Users List"),
                ("attendance_list", "Attendance List"),
                ("shift_roster", "Employee Shift Assignment"),
                ("shift_roster", "Monthly Shift Roster"),
                ("shift_rotation", "Shift Rotation"),
                ("line_roster", "Employee Line Assignment"),
                ("line_roster", "Monthly Line Roster"),
                ("line_rotation", "Line Rotation"),
                ("leaves", "Leave Application"),
                ("leaves", "Leave Allocate"),
                ("salary_slips", "Salary Slips"),
                ("holidays", "Holidays List"),
                ("canteen", "Canteen"),
                ("asset_list", "Asset List"),
                ("asset_assignments", "Asset Assignments"),
                ("asset_requests", "Asset Requests"),
                ("expense_tracker", "Company Expenses"),
                ("reimbursement_claims", "Reimbursement Claim List"),
                ("job_openings", "Job Opening List"),
                ("job_applicants", "Job Applicant List"),
                ("employee_referrals", "Employee Referral List"),
                ("hr_document_templates", "Document Templates"),
                ("hr_document_templates", "Document Generation"),
                ("report_attendance", "Attendance Report"),
                ("report_canteen", "Canteen Report"),
                ("report_shift", "Shift Report"),
                ("report_line", "Line Report"),
                ("report_leave_allocation", "Leave Allocation Report"),
                ("report_employee_overall", "Employee Overall Report"),
                ("report_salary_slip", "Salary Slip Report"),
                ("report_salary_reconciliation", "Salary Reconciliation"),
                ("master_department", "Department"),
                ("master_designation", "Designation"),
                ("master_employee_type", "Employee Type"),
                ("master_line_order", "Line"),
                ("master_shift", "Shift"),
                ("master_skill", "Skill"),
                ("master_bus_travel_route", "Bus - Travel Route"),
                ("master_claim_type", "Claim Type"),
                ("master_bank_account", "Bank Account"),
                ("master_asset_category", "Asset Category"),
                ("master_criteria_category", "Criteria Category"),
                ("master_blood_group", "Blood Group"),
                ("master_salary_component", "Salary Component"),
                ("master_leave_type", "Leave Type"),
                ("master_hr_document_category", "HR Document Category")
            ]
        elif role == "Employee":
            modules_list = [
                ("dashboard", "Employee Dashboard"),
                ("profile", "My Profile"),
                ("attendance_list", "My Attendance"),
                ("leaves", "My Leave Application"),
                ("shift_roster", "Monthly Shift Roster"),
                ("line_roster", "Monthly Line Roster"),
                ("canteen", "Canteen"),
                ("salary_slips", "My Salary Slip"),
                ("reimbursement_claims", "My Reimbursement Claim"),
                ("asset_list", "My Asset List"),
                ("asset_requests", "My Asset Requests"),
                ("employee_referrals", "Refer a Friend"),
                ("report_attendance", "My Attendance Report"),
                ("report_canteen", "My Canteen Report"),
                ("report_shift", "My Shift Report"),
                ("report_line", "My Line Report")
            ]

        # Populate rows if the child permissions table is empty
        if not self.permissions and modules_list:
            for module, screen in modules_list:
                self.append("permissions", {
                    "module_id": module,
                    "screen_id": screen,
                    "add_permission": 0,
                    "edit_permission": 0,
                    "view_permission": 1 if "Dashboard" in screen or screen == "Dashboard" else 0,
                    "delete_permission": 0,
                    "export_permission": 0,
                    "import_permission": 0
                })
        return self.permissions

