import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime


class Proposal(Document):

    def validate(self):
        self.set_default_status()
        self.validate_dates()
        self.populate_attachment_metadata()
        self.set_total_attachments()
        self.validate_send_stage_requirements()

    def autoname(self):
        """Set document name = reference_no"""
        if self.reference_no:
            self.name = self.reference_no

    def before_insert(self):
        if not self.created_by:
            self.created_by = frappe.session.user

        """Generate Proposal reference_no before inserting"""
        if not self.reference_no:
            today = getdate()
            year = today.year

            # Financial Year (April → March)
            if today.month < 4:
                start_year = year - 1
                end_year = year
            else:
                start_year = year
                end_year = year + 1

            fy = f"{str(start_year)[-2:]}-{str(end_year)[-2:]}"  # e.g., 25-26

            # Get last Proposal in this FY
            last = frappe.db.sql("""
                SELECT reference_no FROM `tabProposal`
                WHERE reference_no LIKE %s
                ORDER BY creation DESC LIMIT 1
            """, (f"IB-P/{fy}/%",), as_dict=True)

            if last:
                try:
                    last_num = int(last[0].reference_no.split("/")[-1])
                    next_num = last_num + 1
                except ValueError:
                    next_num = 1
            else:
                next_num = 1

            # Assign reference_no
            self.reference_no = f"IB-P/{fy}/{str(next_num).zfill(3)}"

            # Also set document name
            self.name = self.reference_no

    def before_save(self):
        self.set_total_attachments()

    def on_update(self):
        pass

    def set_default_status(self):
        """Default status to Draft for new documents."""
        if not self.status:
            self.status = "Draft"

    def validate_dates(self):
        """Validate that valid_until is not earlier than proposal_date."""
        if self.valid_until and self.proposal_date:
            if getdate(self.valid_until) < getdate(self.proposal_date):
                frappe.throw(
                    "Valid Until date ({0}) cannot be earlier than Proposal Date ({1}).".format(
                        self.valid_until, self.proposal_date
                    )
                )

    def populate_attachment_metadata(self):
        """Auto-fill metadata fields for each attachment row."""
        current_user = frappe.session.user
        current_datetime = now_datetime()

        for row in (self.attachments_table or []):
            if row.attachment:
                # Extract file name from the attachment URL/path
                if not row.file_name:
                    file_path = row.attachment or ""
                    row.file_name = file_path.split("/")[-1] if "/" in file_path else file_path

                # Set uploaded_on if not already set
                if not row.uploaded_on:
                    row.uploaded_on = current_datetime

                # Set uploaded_by if not already set
                if not row.uploaded_by:
                    row.uploaded_by = current_user

                # Optionally fetch file size from File doctype
                if not row.file_size and row.attachment:
                    try:
                        file_doc = frappe.get_doc("File", {"file_url": row.attachment})
                        if file_doc:
                            size_bytes = file_doc.file_size or 0
                            if size_bytes > 0:
                                # Format human-readable
                                if size_bytes < 1024:
                                    row.file_size = f"{size_bytes} B"
                                elif size_bytes < 1024 * 1024:
                                    row.file_size = f"{size_bytes / 1024:.1f} KB"
                                else:
                                    row.file_size = f"{size_bytes / (1024 * 1024):.1f} MB"
                    except Exception:
                        pass

    def set_total_attachments(self):
        """Count non-empty attachment rows."""
        count = sum(1 for row in (self.attachments_table or []) if row.attachment)
        self.total_attachments = count

    def validate_send_stage_requirements(self):
        """Require at least one attachment before moving to Send stage."""
        if self.status == "Sent" and self.total_attachments < 1:
            frappe.throw("At least one attachment is required before marking the proposal as Sent.")
