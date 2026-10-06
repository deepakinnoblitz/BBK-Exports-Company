# -*- coding: utf-8 -*-
# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

class CanteenEntry(Document):
	def validate(self):
		if not self.canteen_date:
			frappe.throw("Canteen Date is required")
		if not self.employee:
			frappe.throw("Employee is required")
		if not self.meal_count or self.meal_count < 1:
			self.meal_count = 1
		if not self.meal_type:
			self.meal_type = "Lunch"
		if not self.status:
			self.status = "Availed"

		# Auto fill employee details if missing
		if not self.employee_name or not self.department:
			emp = frappe.db.get_value("Employee", self.employee, ["employee_name", "department", "designation"], as_dict=1)
			if emp:
				if not self.employee_name:
					self.employee_name = emp.employee_name
				if not self.department:
					self.department = emp.department
				if not self.designation:
					self.designation = emp.designation
