# Copyright (c) 2026, Innoblitz and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

class EmployeeEvaluation(Document):
	def autoname(self):
		# Better naming using a standard series to avoid collisions after deletions
		self.name = frappe.model.naming.make_autoname(f"EE-{self.employee}-.#####")

	def before_insert(self):
		if not self.hr_user:
			self.hr_user = frappe.session.user

	def validate(self):
		self.calculate_score_change()

	def on_submit(self):
		frappe.log_error(f"On Submit Triggered for {self.name}", "Employee Evaluation Debug")
		self.update_employee_score()

	def on_cancel(self):
		self.revert_employee_score()

	def calculate_score_change(self):
		if not self.trait or not self.evaluation_type:
			return
			
		trait = frappe.get_doc("Evaluation Trait", self.trait)
		
		# 1. Check for trait-specific override in child table
		score = None
		for row in trait.evaluation_scores:
			if row.evaluation_point == self.evaluation_type:
				score = row.score
				break
		
		# 2. Fall back to master default score if no override exists
		if score is None:
			point = frappe.get_doc("Evaluation Point", self.evaluation_type)
			score = point.default_score or 0
			
		self.score_change = score

	def update_employee_score(self):
		if getattr(self, "_score_log_created", False):
			return
		
		# Prevent duplicate runs in the same request context
		flag_key = f"score_log_created_{self.name}"
		if frappe.flags.get(flag_key):
			return

		# Robust database check to prevent duplicate logs for the same event
		if frappe.db.exists("Employee Evaluation Score Log", {"employee_evaluation": self.name}):
			return
		
		frappe.flags[flag_key] = True

		employee = frappe.get_doc("Employee", self.employee)
		current_score = employee.evaluation_score if employee.evaluation_score is not None else 100
		new_score = current_score + (self.score_change or 0)

		if new_score > 100:
			new_score = 100
		if new_score < 0:
			new_score = 0

		# Update Employee
		frappe.db.set_value("Employee", self.employee, {
			"evaluation_score": new_score,
			"evaluation_status": self.get_status_for_score(new_score)
		})

		# Create Log
		log = frappe.get_doc({
			"doctype": "Employee Evaluation Score Log",
			"employee": self.employee,
			"previous_score": current_score,
			"change": self.score_change,
			"new_score": new_score,
			"reason": f"{self.evaluation_type} on {self.trait}{': ' + self.remarks if self.remarks else ''}",
			"employee_evaluation": self.name,
			"date": now_datetime()
		})
		log.insert(ignore_permissions=True)
		self._score_log_created = True

	def revert_employee_score(self):
		flag_key = f"score_log_reverted_{self.name}"
		if frappe.flags.get(flag_key):
			return

		frappe.flags[flag_key] = True

		employee = frappe.get_doc("Employee", self.employee)
		current_score = employee.evaluation_score if employee.evaluation_score is not None else 100
		
		# Revert the change (subtract what was added, add what was subtracted)
		new_score = current_score - (self.score_change or 0)

		if new_score > 100:
			new_score = 100
		if new_score < 0:
			new_score = 0

		# Update Employee
		frappe.db.set_value("Employee", self.employee, {
			"evaluation_score": new_score,
			"evaluation_status": self.get_status_for_score(new_score)
		})

		# Create Log
		log = frappe.get_doc({
			"doctype": "Employee Evaluation Score Log",
			"employee": self.employee,
			"previous_score": current_score,
			"change": -(self.score_change or 0),
			"new_score": new_score,
			"reason": f"CANCELLED: {self.evaluation_type} on {self.trait}{': ' + self.remarks if self.remarks else ''}",
			"employee_evaluation": self.name,
			"date": now_datetime()
		})
		log.insert(ignore_permissions=True)

	def get_status_for_score(self, score):
		if score >= 90:
			return "Excellent"
		elif score >= 75:
			return "Good"
		elif score >= 60:
			return "Average"
		else:
			return "Needs Improvement"

@frappe.whitelist()
def reset_employee_scores(password, employees=None):
	# Verify against Administrator password
	from frappe.utils.password import check_password
	try:
		check_password("Administrator", password)
	except frappe.AuthenticationError:
		frappe.throw("Incorrect Administrator Password")
	
	if isinstance(employees, str):
		import json
		employees = json.loads(employees)
		
	filters = {"status": "Active"}
	if employees:
		filters["name"] = ["in", employees]
		
	employees_list = frappe.get_all("Employee", filters=filters, fields=["name", "employee_name", "evaluation_score"])
	
	results = []
	for emp in employees_list:
		prev_score = emp.evaluation_score if emp.evaluation_score is not None else 100
		
		# If specific employees are provided, we reset even if they are at 100 to ensure consistency.
		# If no employees provided (Reset All), we skip those who are already at 100.
		if not employees and prev_score == 100:
			continue
			
		# Update Employee
		frappe.db.set_value("Employee", emp.name, {
			"evaluation_score": 100,
			"evaluation_status": "Excellent"
		})
		
		# Create Log
		log = frappe.get_doc({
			"doctype": "Employee Evaluation Score Log",
			"employee": emp.name,
			"previous_score": prev_score,
			"change": 100 - prev_score,
			"new_score": 100,
			"reason": "Administrative Reset to 100" if not employees else f"Administrative Reset for {emp.employee_name} to 100",
			"date": now_datetime()
		})
		log.insert(ignore_permissions=True)
		
		results.append({
			"employee": emp.name,
			"employee_name": emp.employee_name,
			"previous_score": prev_score,
			"new_score": 100
		})
	
	return results
	
@frappe.whitelist()
def hard_delete_evaluation(name):
	# Check for delete permission
	if not frappe.has_permission("Employee Evaluation", ptype="delete", doc=name):
		frappe.throw("You do not have permission to delete this Evaluation.", frappe.PermissionError)
	
	# Force delete ignoring links for the main doc
	frappe.delete_doc("Employee Evaluation", name, force=True, ignore_permissions=False)
	
	# Clean up orphaned score logs for this name
	frappe.db.delete("Employee Evaluation Score Log", {"employee_evaluation": name})
	
	return "Successfully deleted"
