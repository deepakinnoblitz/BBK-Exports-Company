import frappe
from frappe.model.document import Document

from frappe.utils import getdate

class Employee(Document):
	def validate(self):
		self.validate_duplicate_components()
		self.validate_status_and_dol()

	def validate_status_and_dol(self):
		if self.status == "Active":
			self.date_of_leaving = None
		elif self.status == "Inactive":
			if self.date_of_leaving and self.date_of_joining:
				if getdate(self.date_of_leaving) < getdate(self.date_of_joining):
					frappe.throw("Date of Leaving cannot be before Date of Joining")

	def validate_duplicate_components(self):
		components = []
		for table in ["earnings", "deductions"]:
			for row in self.get(table):
				if row.component_name in components:
					frappe.throw(f"Duplicate component name: {row.component_name}")
				components.append(row.component_name)

	def on_update(self):
		if self.user:
			frappe.db.set_value("User", self.user, "user_image", self.profile_picture)
		
		self.manage_user_permissions()

	def on_trash(self):
		self.delete_user_permissions()

	def manage_user_permissions(self):
		old_doc = self.get_doc_before_save()
		old_user = old_doc.user if old_doc else None

		if old_user and old_user != self.user:
			# User changed or cleared, delete old permission
			frappe.db.delete("User Permission", {
				"user": old_user,
				"allow": "Employee",
				"for_value": self.name
			})

		if self.user:
			# Create or ensure new permission exists
			if not frappe.db.exists("User Permission", {"user": self.user, "allow": "Employee", "for_value": self.name}):
				frappe.get_doc({
					"doctype": "User Permission",
					"user": self.user,
					"allow": "Employee",
					"for_value": self.name
				}).insert(ignore_permissions=True)

	def delete_user_permissions(self):
		frappe.db.delete("User Permission", {
			"allow": "Employee",
			"for_value": self.name
		})
