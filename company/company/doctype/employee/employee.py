import json
import frappe
from frappe.model.document import Document
from frappe.utils import getdate, flt

class Employee(Document):
	def validate(self):
		self.validate_duplicate_components()
		self.validate_status_and_dol()
		self.calculate_totals()

	def calculate_totals(self):
		from frappe.utils import flt
		self.total_earnings = round(sum(flt(e.amount) for e in self.get("earnings", [])), 2)
		self.total_deductions = round(sum(flt(d.amount) for d in self.get("deductions", [])), 2)
		self.net_salary = round(self.total_earnings - self.total_deductions, 2)

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
		self.log_history_changes()

	def log_history_changes(self):
		old_doc = self.get_doc_before_save()
		user = frappe.session.user or "Administrator"
		user_name = frappe.db.get_value("User", user, "full_name") or user

		if not old_doc:
			# If this is newly created and has skill, create initial log entry
			if self.skill:
				frappe.get_doc({
					"doctype": "Employee Skill History",
					"employee": self.name,
					"employee_name": self.employee_name,
					"from_skill": None,
					"to_skill": self.skill,
					"changed_by": user,
					"changed_by_name": user_name,
					"changed_at": frappe.utils.now_datetime(),
					"reason": getattr(self.flags, "skill_change_reason", None) or "Initial Skill Assignment"
				}).insert(ignore_permissions=True)
			if flt(self.ctc) > 0:
				frappe.get_doc({
					"doctype": "Employee Salary History",
					"employee": self.name,
					"employee_name": self.employee_name,
					"previous_ctc": 0,
					"new_ctc": flt(self.ctc),
					"previous_net_salary": 0,
					"new_net_salary": flt(self.net_salary),
					"changed_by": user,
					"changed_by_name": user_name,
					"changed_at": frappe.utils.now_datetime(),
					"reason": getattr(self.flags, "salary_change_reason", None) or "Initial CTC Setup"
				}).insert(ignore_permissions=True)
			return

		# 1. Track Skill Change
		if (old_doc.skill or "") != (self.skill or ""):
			frappe.get_doc({
				"doctype": "Employee Skill History",
				"employee": self.name,
				"employee_name": self.employee_name,
				"from_skill": old_doc.skill,
				"to_skill": self.skill,
				"changed_by": user,
				"changed_by_name": user_name,
				"changed_at": frappe.utils.now_datetime(),
				"reason": getattr(self.flags, "skill_change_reason", None) or "Skill updated"
			}).insert(ignore_permissions=True)

		# 2. Track Salary Change
		changes = []
		old_earnings = {row.component_name: flt(row.amount) for row in (old_doc.earnings or []) if row.component_name}
		new_earnings = {row.component_name: flt(row.amount) for row in (self.earnings or []) if row.component_name}

		old_deductions = {row.component_name: flt(row.amount) for row in (old_doc.deductions or []) if row.component_name}
		new_deductions = {row.component_name: flt(row.amount) for row in (self.deductions or []) if row.component_name}

		has_ctc_change = flt(old_doc.ctc) != flt(self.ctc)
		has_net_change = flt(old_doc.net_salary) != flt(self.net_salary)
		has_component_change = False

		# Compare earnings
		all_earning_names = list(dict.fromkeys(list(old_earnings.keys()) + list(new_earnings.keys())))
		for comp in all_earning_names:
			old_val = old_earnings.get(comp, 0.0)
			new_val = new_earnings.get(comp, 0.0)
			if comp not in old_earnings:
				changes.append({
					"component": comp,
					"category": "Earning",
					"change_type": "added",
					"old_amount": 0.0,
					"new_amount": new_val,
					"diff": new_val
				})
				has_component_change = True
			elif comp not in new_earnings:
				changes.append({
					"component": comp,
					"category": "Earning",
					"change_type": "removed",
					"old_amount": old_val,
					"new_amount": 0.0,
					"diff": -old_val
				})
				has_component_change = True
			elif old_val != new_val:
				changes.append({
					"component": comp,
					"category": "Earning",
					"change_type": "modified",
					"old_amount": old_val,
					"new_amount": new_val,
					"diff": new_val - old_val
				})
				has_component_change = True

		# Compare deductions
		all_deduction_names = list(dict.fromkeys(list(old_deductions.keys()) + list(new_deductions.keys())))
		for comp in all_deduction_names:
			old_val = old_deductions.get(comp, 0.0)
			new_val = new_deductions.get(comp, 0.0)
			if comp not in old_deductions:
				changes.append({
					"component": comp,
					"category": "Deduction",
					"change_type": "added",
					"old_amount": 0.0,
					"new_amount": new_val,
					"diff": new_val
				})
				has_component_change = True
			elif comp not in new_deductions:
				changes.append({
					"component": comp,
					"category": "Deduction",
					"change_type": "removed",
					"old_amount": old_val,
					"new_amount": 0.0,
					"diff": -old_val
				})
				has_component_change = True
			elif old_val != new_val:
				changes.append({
					"component": comp,
					"category": "Deduction",
					"change_type": "modified",
					"old_amount": old_val,
					"new_amount": new_val,
					"diff": new_val - old_val
				})
				has_component_change = True

		if has_ctc_change or has_net_change or has_component_change:
			summary_items = []
			if has_ctc_change:
				summary_items.append(f"CTC: ₹{flt(old_doc.ctc):,.2f} ➔ ₹{flt(self.ctc):,.2f}")
			if has_net_change:
				summary_items.append(f"Net Salary: ₹{flt(old_doc.net_salary):,.2f} ➔ ₹{flt(self.net_salary):,.2f}")
			for ch in changes:
				if ch["change_type"] == "added":
					summary_items.append(f"+{ch['component']}: ₹{ch['new_amount']:,.2f}")
				elif ch["change_type"] == "removed":
					summary_items.append(f"-{ch['component']}: ₹{ch['old_amount']:,.2f}")
				else:
					summary_items.append(f"{ch['component']}: ₹{ch['old_amount']:,.2f} ➔ ₹{ch['new_amount']:,.2f}")

			changed_components_summary = ", ".join(summary_items)

			frappe.get_doc({
				"doctype": "Employee Salary History",
				"employee": self.name,
				"employee_name": self.employee_name,
				"previous_ctc": flt(old_doc.ctc),
				"new_ctc": flt(self.ctc),
				"previous_net_salary": flt(old_doc.net_salary),
				"new_net_salary": flt(self.net_salary),
				"changed_components": changed_components_summary,
				"component_details": json.dumps(changes),
				"changed_by": user,
				"changed_by_name": user_name,
				"changed_at": frappe.utils.now_datetime(),
				"reason": getattr(self.flags, "salary_change_reason", None) or "Salary revised"
			}).insert(ignore_permissions=True)


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
