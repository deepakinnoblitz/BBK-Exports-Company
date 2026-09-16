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
                ("task_manager", "Task Manager"),
                ("employee", "Employee List"),
                ("employee", "Users List"),
                ("attendance_list", "Attendance List"),
                ("daily_log", "Daily Log"),
                ("wfh_attendance", "WFH Attendance"),
                ("leaves", "Leave Application"),
                ("leaves", "Leave Allocate"),
                ("requests", "Request List"),
                ("timesheets", "Timesheets"),
                ("salary_slips", "Salary Slips"),
                ("holidays", "Holidays List"),
                ("announcements", "Announcements"),
                ("asset_list", "Asset List"),
                ("asset_assignments", "Asset Assignments"),
                ("asset_requests", "Asset Requests"),
                ("expense_tracker", "Expense Tracker"),
                ("reimbursement_claims", "Reimbursement Claim List"),
                ("employee_evaluation", "Employee Evaluation"),
                ("badges", "Badges"),
                ("employee_monthly_award", "Employee Monthly Award"),
                ("job_openings", "Job Opening List"),
                ("job_applicants", "Job Applicant List"),
                ("interviews", "Interview List"),
                ("employee_referrals", "Employee Referral List"),
                ("hr_document_templates", "Document Templates"),
                ("hr_document_templates", "Document Generation"),
                ("report_attendance", "Attendance Report"),
                ("report_daily_log", "Daily Log Report"),
                ("report_task", "Task Report"),
                ("report_timesheet", "Timesheet Report"),
                ("report_leave_allocation", "Leave Allocation Report"),
                ("report_employee_overall", "Employee Overall Report"),
                ("report_salary_slip", "Salary Slip Report"),
                ("master_department", "Department"),
                ("master_project", "Project"),
                ("master_activity_type", "Activity Type"),
                ("master_claim_type", "Claim Type"),
                ("master_bank_account", "Bank Account"),
                ("master_asset_category", "Asset Category"),
                ("master_criteria_category", "Criteria Category"),
                ("master_designation", "Designation"),
                ("master_salary_component", "Salary Component"),
                ("master_leave_type", "Leave Type"),
                ("master_blood_group", "Blood Group"),
                ("reminders", "Reminders")
            ]
        elif role == "Employee":
            modules_list = [
                ("dashboard", "Employee Dashboard"),
                ("profile", "My Profile"),
                ("tasks", "My Tasks"),
                ("attendance_list", "My Attendance"),
                ("daily_log", "My Daily Log"),
                ("leaves", "My Leave Application"),
                ("requests", "My Request List"),
                ("timesheets", "My Timesheet"),
                ("wfh_attendance", "My WFH Attendance"),
                ("salary_slips", "My Salary Slip"),
                ("reimbursement_claims", "My Reimbursement Claim"),
                ("asset_list", "My Asset List"),
                ("asset_requests", "My Asset Requests"),
                ("employee_referrals", "Refer a Friend"),
                ("report_attendance", "My Attendance Report"),
                ("report_daily_log", "My Daily Log Report"),
                ("report_timesheet", "My Timesheet Report")
            ]
        elif role in ("CRM And Sales", "Sales", "CRM User"):
            modules_list = [
                ("dashboard", "Dashboard"),
                ("lead", "Leads"),
                ("clients", "Clients"),
                ("company", "Company"),
                ("proposal", "Proposal"),
                ("prospects", "Prospects"),
                ("estimation", "Estimations"),
                ("invoice", "Invoices"),
                ("invoice_collection", "Invoice Collections"),
                ("purchase", "Purchases"),
                ("purchase_collection", "Purchase Collections"),
                ("sales_target_entry", "Sales Target Entry"),
                ("crm_expenses", "CRM Expense Tracker"),
                ("events", "Calendar"),
                ("email_templates", "Email Templates"),
                ("email_campaigns", "Email Campaigns"),
                ("email_automations", "Email Automations"),
                ("email_settings", "Email Settings"),
                ("whatsapp_templates", "WhatsApp Templates"),
                ("whatsapp_campaigns", "WhatsApp Campaigns"),
                ("whatsapp_automations", "WhatsApp Automations"),
                ("whatsapp_settings", "WhatsApp Settings"),
                ("meta_account", "Meta Account"),
                ("meta_apps", "Meta Apps"),
                ("meta_pages", "Meta Pages"),
                ("meta_forms", "Meta Forms"),
                ("meta_leads", "Meta Leads"),
                ("webhook_logs", "Webhook Logs"),
                ("meta_queue", "Meta Queue"),
                ("master_lead_from", "Lead From"),
                ("master_call_status", "Call Status"),
                ("master_meeting_status", "Meeting Status"),
                ("master_service", "Service"),
                ("master_item", "Item"),
                ("master_payment_terms", "Payment Terms"),
                ("master_payment_type", "Payment Type"),
                ("master_tax_types", "Tax Types"),
                ("master_company_bank_account", "Company Bank Account"),
                ("master_email_template_category", "Email Template Category"),
                ("master_whatsapp_template_category", "WhatsApp Template Category"),
                ("report_lead", "Lead Report"),
                ("report_clients", "Clients Report"),
                ("report_company", "Company Report"),
                ("report_calls", "Calls Report"),
                ("report_meeting", "Meeting Report"),
                ("report_proposal", "Proposal Report"),
                ("report_prospects", "Prospects Report"),
                ("report_estimation", "Estimation Report"),
                ("report_invoice", "Invoice Report"),
                ("report_purchase", "Purchase Report"),
                ("report_invoice_collection", "Invoice Collection Summary"),
                ("report_purchase_settlement", "Purchase Settlement Report")
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

