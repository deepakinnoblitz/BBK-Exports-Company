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

    def validate(self):
        self.validate_resume()

    def validate_resume(self):
        if not self.resume:
            return
        video_extensions = (
            ".webm", ".mp4", ".mkv", ".mov", ".avi", ".flv",
            ".wmv", ".m4v", ".3gp", ".ogg", ".ogv", ".ts", ".mpg", ".mpeg"
        )
        url_clean = self.resume.lower().split("?")[0].strip()
        if any(url_clean.endswith(ext) for ext in video_extensions):
            frappe.throw(_("Video files are not allowed for resume attachment. Please upload a valid document (PDF, DOC, DOCX, JPG, PNG)."))

        file_size = frappe.db.get_value("File", {"file_url": self.resume}, "file_size")
        if file_size and file_size > 5 * 1024 * 1024:
            frappe.throw(_("Resume attachment file size exceeds 5MB limit. Please upload a file smaller than 5MB."))

    def on_update(self):
        # Additional logic can be added here (e.g. status sync if needed)
        pass
