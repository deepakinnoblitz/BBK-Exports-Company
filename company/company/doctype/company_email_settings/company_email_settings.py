# Copyright (c) 2025, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import validate_email_address


class CompanyEmailSettings(Document):
	def validate(self):
		if self.hr_email:
			self.hr_email = self.hr_email.strip()
			validate_email_address(self.hr_email, throw=True)

		if self.hr_cc_emails:
			valid_emails = []
			for email in self.hr_cc_emails.split(","):
				clean_email = email.strip()
				if clean_email:
					validate_email_address(clean_email, throw=True)
					valid_emails.append(clean_email)
			self.hr_cc_emails = ", ".join(valid_emails)

