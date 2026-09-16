import frappe
from frappe.model.document import Document
from frappe import _

class EmployeeReferral(Document):
    @frappe.whitelist()
    def create_job_applicant(self):
        """
        HR action to create a Job Applicant from this referral.
        """
        if self.job_applicant:
            frappe.throw(_("A Job Applicant has already been created for this referral."))

        if self.status == "Rejected":
            frappe.throw(_("Cannot create a Job Applicant for a rejected referral."))

        # Create new Job Applicant
        applicant = frappe.get_doc({
            "doctype": "Job Applicant",
            "applicant_name": self.candidate_name,
            "email_id": self.candidate_email,
            "phone_number": self.candidate_phone,
            "job_title": self.job_opening,
            "source": "Employee Referral",
            "resume_attachment": self.resume,
            "status": "Received"
        })
        
        applicant.insert(ignore_permissions=True)
        
        # Link applicant to referral
        self.job_applicant = applicant.name
        self.status = "Accepted"
        self.save()
        
        frappe.msgprint(_("Job Applicant {0} created successfully.").format(applicant.name))
        return applicant.name

    def on_update(self):
        # Additional logic can be added here (e.g. status sync if needed)
        pass
