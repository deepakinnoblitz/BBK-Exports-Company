# -*- coding: utf-8 -*-
# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HRDocumentTemplate(Document):
	pass


@frappe.whitelist()
def get_document_template_variables(document_for="Employee"):
	"""
	Returns available variables for the selected document_for target (default: Employee).
	Reads metadata dynamically without hardcoding field names.
	"""
	target_doctype = document_for or "Employee"

	exclude_fields = {
		"name",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"idx",
		"_assign",
		"_comments",
		"_liked_by",
		"_seen",
		"_user_tags",
		"amended_from",
		"parent",
		"parentfield",
		"parenttype",
	}

	ignore_fieldtypes = {
		"Section Break",
		"Column Break",
		"Tab Break",
		"HTML",
		"Button",
		"Table",
		"Table MultiSelect",
		"Image",
		"Attach",
		"Attach Image",
		"Fold",
		"Heading",
	}

	try:
		meta = frappe.get_meta(target_doctype)
	except Exception as e:
		frappe.throw(f"Invalid DocType: {target_doctype}")

	variables = []
	seen = set()

	for df in meta.fields:
		if (
			df.fieldname
			and df.fieldname not in exclude_fields
			and df.fieldtype not in ignore_fieldtypes
		):
			var_name = df.fieldname
			if var_name not in seen:
				seen.add(var_name)
				variables.append({
					"label": df.label or df.fieldname,
					"fieldname": df.fieldname,
					"variable": f"{{{{ {df.fieldname} }}}}",
					"fieldtype": df.fieldtype,
				})

	return sorted(variables, key=lambda x: x["label"])
