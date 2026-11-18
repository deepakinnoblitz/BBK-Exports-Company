# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EmployeeType(Document):
	def autoname(self):
		emp_type = (self.employee_type or "").strip()
		cat_type = (self.category_type or "").strip()

		# Only Staff supports categories (CTC / Non CTC)
		if emp_type.lower() == "staff" or emp_type.lower().startswith("staff -"):
			if cat_type in ["CTC", "Non CTC"]:
				generated = f"Staff - {cat_type}"
			elif " - " in emp_type:
				generated = emp_type
			else:
				generated = f"Staff - {cat_type}" if cat_type and cat_type != "General" else "Staff - CTC"
		else:
			# Non-Staff (Workers, Drivers, Contractor, etc.) - No category
			generated = emp_type
			self.category_type = "General"

		self.name = generated
		self.employee_type = generated

	def validate(self):
		emp_type = (self.employee_type or "").strip()
		if emp_type.lower() != "staff" and not emp_type.lower().startswith("staff -"):
			self.category_type = "General"
