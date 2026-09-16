import frappe
from frappe.model.document import Document

class JobApplicant(Document):

    def after_insert(self):
        self.notify_hr_on_creation()

    def notify_hr_on_creation(self):
        """Send email to HR when a new Job Applicant is created"""

        from company.company.api import is_hrms_notification_enabled
        if not is_hrms_notification_enabled("job_notification"):
            return

        # Fetch HR email settings
        hr_settings = frappe.get_all(
            "Company Email Settings",
            fields=["hr_email", "hr_cc_emails"],
            limit=1
        )

        if not hr_settings:
            frappe.msgprint("⚠️ No HR Email Settings found in 'Company Email Settings'.")
            return

        hr_email = hr_settings[0].get("hr_email")
        cc_emails = hr_settings[0].get("hr_cc_emails")

        if not hr_email:
            frappe.msgprint("⚠️ HR Email (To) is not configured in 'Company Email Settings'.")
            return

        recipients = [hr_email]
        cc_list = []

        if cc_emails:
            cc_list = [
                email.strip() 
                for email in cc_emails.replace("\n", ",").split(",") 
                if email.strip()
            ]

        # Email HTML Template
        message = f"""
        <div style="font-family:'Poppins','Segoe UI',Arial,sans-serif;background:#e7f6ed;padding:40px;">
            <div style="max-width:600px;margin:auto;background:white;border-radius:14px;
                        box-shadow:0 4px 12px rgba(25,135,84,0.2);overflow:hidden;">

                <div style="background:#198754;color:white;padding:20px 26px;font-size:18px;font-weight:600;">
                    📝 New Job Application Received
                </div>

                <div style="padding:26px;color:#333;font-size:14px;line-height:1.6;">
                    <p>Dear HR,</p>
                    <p>A new job application has been submitted. Below are the details:</p>

                    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:18px;
                                   border-radius:8px;overflow:hidden;">

                        <tr style="background:#eaf9f0;">
                            <td style="padding:10px 12px;font-weight:600;width:160px;">Applicant Name</td>
                            <td style="padding:10px 12px;">{self.applicant_name or '-'}</td>
                        </tr>

                        <tr style="background:#f4fcf7;">
                            <td style="padding:10px 12px;font-weight:600;">Email</td>
                            <td style="padding:10px 12px;">{self.email_id or '-'}</td>
                        </tr>

                        <tr style="background:#eaf9f0;">
                            <td style="padding:10px 12px;font-weight:600;">Phone</td>
                            <td style="padding:10px 12px;">{self.phone_number or '-'}</td>
                        </tr>

                        <tr style="background:#f4fcf7%;">
                            <td style="padding:10px 12px;font-weight:600;">Job Opening</td>
                            <td style="padding:10px 12px;">{self.job_title or '-'}</td>
                        </tr>

                        <tr style="background:#eaf9f0;">
                            <td style="padding:10px 12px;font-weight:600;">Status</td>
                            <td style="padding:10px 12px;">{self.status or '-'}</td>
                        </tr>

                        <tr style="background:#f4fcf7;">
                            <td style="padding:10px 12px;font-weight:600;">Location</td>
                            <td style="padding:10px 12px;">
                                {self.city or '-'}, {self.state or '-'}, {self.country or '-'}
                            </td>
                        </tr>

                        <tr style="background:#eaf9f0;">
                            <td style="padding:10px 12px;font-weight:600;">Resume</td>
                            <td style="padding:10px 12px;">
                                <a href="{self.resume_attachment}" target="_blank">Download Resume</a>
                            </td>
                        </tr>

                    </table>

                    <div style="text-align:center;margin-top:28px;">
                        <a href="{frappe.utils.get_url('/app/job-applicant/' + self.name)}"
                           style="background:#198754;color:white;padding:12px 24px;text-decoration:none;
                                  border-radius:8px;font-size:14px;font-weight:500;">
                            View in ERP
                        </a>
                    </div>
                </div>

                <div style="background:#c9e9d4;padding:12px 20px;text-align:center;
                            font-size:12px;color:#0f5132;">
                    This is an automated message from your ERP system.
                </div>
            </div>
        </div>
        """

        frappe.sendmail(
            recipients=recipients,
            cc=cc_list,
            subject=f"📝 New Job Application - {self.applicant_name}",
            message=message,
            reference_doctype=self.doctype,
            reference_name=self.name,
        )
