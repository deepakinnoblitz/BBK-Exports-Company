# Copyright (c) 2025, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Department(Document):
	def validate(self):
		self.validate_department_name()
		self.validate_department_code()

	def validate_department_name(self):
		name = (self.department_name or "").strip()
		if len(name) > 140 or len(self.department_name or "") > 140:
			frappe.throw(_("Maximum character limit is 140 characters for Department Name."))

	def validate_department_code(self):
		code = (self.department_code or "").strip()
		if code:
			self.department_code = code

			# Check if another Department already has this department_code (case-insensitive)
			is_existing = not self.is_new() and bool(frappe.db.exists("Department", self.name))
			if is_existing:
				existing = frappe.db.sql(
					"""
					SELECT name, department_name
					FROM `tabDepartment`
					WHERE LOWER(TRIM(department_code)) = LOWER(%s)
					AND name != %s
					LIMIT 1
					""",
					(code, self.name),
					as_dict=True,
				)
			else:
				existing = frappe.db.sql(
					"""
					SELECT name, department_name
					FROM `tabDepartment`
					WHERE LOWER(TRIM(department_code)) = LOWER(%s)
					LIMIT 1
					""",
					(code,),
					as_dict=True,
				)

			if existing:
				existing_doc = existing[0]
				existing_title = existing_doc.get("department_name") or existing_doc.get("name")
				frappe.throw(
					_("Department Code '{0}' already exists for Department '{1}'. Department Code must be unique.").format(
						code, existing_title
					)
				)
		else:
			self.department_code = ""

