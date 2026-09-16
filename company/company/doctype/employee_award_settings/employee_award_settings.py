# Copyright (c) 2026, Innoblitz and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _

class EmployeeAwardSettings(Document):
	def validate(self):
		self.validate_weights()

	def validate_weights(self):
		total = (
			(self.attendance_weight or 0) +
			(self.personality_weight or 0) +
			(self.login_time_weight or 0) +
			(self.overtime_weight or 0) +
			(self.leave_penalty_weight or 0)
		)
		if total != 100:
			frappe.throw(_("Total of scoring weights must be exactly 100%. Current total: {0}%").format(total))
