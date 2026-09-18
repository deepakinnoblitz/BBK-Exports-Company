# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EmployeeType(Document):
	def autoname(self):
		emp_type = (self.employee_type or "").strip()
		cat_type = (self.category_type or "").strip()

		if cat_type and cat_type != "General":
			# Append category if not already in employee_type
			if not emp_type.lower().endswith(f"- {cat_type}".lower()) and not emp_type.lower().endswith(f"({cat_type})".lower()):
				generated = f"{emp_type} - {cat_type}"
			else:
				generated = emp_type
		else:
			generated = emp_type

		self.name = generated
		self.employee_type = generated
