# Copyright (c) 2025, deepak and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

class Lead(Document):

    def on_update(self):
        self.date_and_time = now_datetime()

    def calculate_lead_score(self):
        score = 0
        max_score = 30  # total possible score

        # Email available
        if self.email:
            score += 10

        # Phone available
        if self.phone_number:
            score += 10

        # Company Name available
        if self.company_name:
            score += 5

        # GSTIN available
        if self.gstin:
            score += 5

        # Convert to percentage
        self.lead_score = (score / max_score) * 100

    def validate_phone_and_email(self):
        # Automatically populate child tables from main fields if child tables are empty
        if self.phone_number and not self.get("phone_numbers"):
            self.append("phone_numbers", {
                "phone": self.phone_number.strip()
            })

        if self.email and not self.get("emails"):
            self.append("emails", {
                "email": self.email.strip()
            })

        # Validate that at least one phone number exists
        if not self.get("phone_numbers"):
            frappe.throw("At least one Phone Number is required")
        
        # Check first phone number value
        first_phone = self.get("phone_numbers")[0].phone
        if not first_phone or not first_phone.strip():
            frappe.throw("Phone Number in the first row is mandatory")

        # Synchronize first phone to the main phone_number field
        self.phone_number = first_phone.strip()

        # Synchronize first email (if any) to the main email field
        if self.get("emails") and self.get("emails")[0].email:
            self.email = self.get("emails")[0].email.strip()
        else:
            self.email = None

    def before_save(self):
        self.validate_phone_and_email()
        self.calculate_lead_score()
        self.validate_proposal_exists()
        self.log_pipeline_timeline()

    def validate_proposal_exists(self):
        if self.is_new():
            return
            
        old_state = frappe.db.get_value(
            "Lead",
            self.name,
            "workflow_state"
        )
        new_state = self.workflow_state
        
        # Check if transitioning to "Proposal Sent"
        if new_state == "Proposal Sent" and old_state != "Proposal Sent":
            has_proposal = frappe.db.exists("Proposal", {"lead": self.name})
            if not has_proposal:
                frappe.throw("You must create at least one Proposal for this Lead before moving it to the 'Proposal Sent' stage.")

    def log_pipeline_timeline(self):
        # New document → no previous state
        if self.is_new():
            return

        # Get previous workflow_state
        old_state = frappe.db.get_value(
            "Lead",
            self.name,
            "workflow_state"
        )

        new_state = self.workflow_state


        # If no change → do nothing
        if not old_state or old_state == new_state:
            return

        # Append child table row
        self.append("converted_pipeline_timeline", {
            "state_from": old_state,
            "state_to": new_state,
            "date_and_time": now_datetime(),
            "change_by": frappe.session.user
        })