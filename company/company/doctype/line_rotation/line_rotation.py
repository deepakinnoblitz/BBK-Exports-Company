# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

class LineRotation(Document):
	def validate(self):
		if not self.rotation_name:
			frappe.throw("Rotation Name is required")
		if self.start_date and self.end_date and getdate(self.end_date) < getdate(self.start_date):
			frappe.throw("End Date cannot be earlier than Start Date")
		if not self.sequences:
			frappe.throw("At least one line sequence step is required")
