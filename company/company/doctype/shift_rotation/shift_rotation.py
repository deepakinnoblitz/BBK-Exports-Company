# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

class ShiftRotation(Document):
	def validate(self):
		if not self.rotation_name:
			frappe.throw("Rotation Name is required")
		if not self.start_date or not self.end_date:
			frappe.throw("Start Date and End Date are required")
		if getdate(self.end_date) < getdate(self.start_date):
			frappe.throw("End Date cannot be earlier than Start Date")
		if not self.sequences:
			frappe.throw("Please add at least one shift in the Sequence Table")

	def on_trash(self):
		pass
