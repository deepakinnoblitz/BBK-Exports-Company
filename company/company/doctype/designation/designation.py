# Copyright (c) 2025, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Designation(Document):
	def validate(self):
		self.validate_designation_code()

	def validate_designation_code(self):
		code = (self.designation_code or "").strip()
		if code:
			self.designation_code = code

			# Check if another Designation already has this designation_code (case-insensitive)
			is_existing = not self.is_new() and bool(frappe.db.exists("Designation", self.name))
			if is_existing:
				existing = frappe.db.sql(
					"""
					SELECT name, designation_name
					FROM `tabDesignation`
					WHERE LOWER(TRIM(designation_code)) = LOWER(%s)
					AND name != %s
					LIMIT 1
					""",
					(code, self.name),
					as_dict=True,
				)
			else:
				existing = frappe.db.sql(
					"""
					SELECT name, designation_name
					FROM `tabDesignation`
					WHERE LOWER(TRIM(designation_code)) = LOWER(%s)
					LIMIT 1
					""",
					(code,),
					as_dict=True,
				)

			if existing:
				existing_doc = existing[0]
				existing_title = existing_doc.get("designation_name") or existing_doc.get("name")
				frappe.throw(
					_("Designation Code '{0}' already exists for Designation '{1}'. Designation Code must be unique.").format(
						code, existing_title
					)
				)
		else:
			self.designation_code = ""

