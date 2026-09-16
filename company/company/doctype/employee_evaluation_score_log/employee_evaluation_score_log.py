# Copyright (c) 2026, Innoblitz and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class EmployeeEvaluationScoreLog(Document):
	def autoname(self):
		count = frappe.db.count("Employee Evaluation Score Log", {"employee": self.employee})
		self.name = f"PSL-{self.employee}-{count + 1}"
