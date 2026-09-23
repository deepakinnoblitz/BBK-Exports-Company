# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

class EmployeeLineRoster(Document):
	def validate(self):
		self.validate_dates()
		self.fetch_employee_and_line_details()
		self.validate_conflicts()

	def validate_dates(self):
		if not self.effective_from:
			frappe.throw("Effective From date is required")
		if self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw("Effective To date cannot be earlier than Effective From date")

	def fetch_employee_and_line_details(self):
		if self.employee:
			emp = frappe.db.get_value("Employee", self.employee, ["employee_name", "department", "designation"], as_dict=1)
			if emp:
				self.employee_name = emp.employee_name
				self.department = emp.department
				self.designation = emp.designation

		if self.line_order:
			line_name = frappe.db.get_value("Line Order", self.line_order, "line_name")
			if line_name:
				self.line_name = line_name

	def validate_conflicts(self):
		if self.status != "Active":
			return

		eff_from = self.effective_from
		eff_to = self.effective_to or self.effective_from

		# Find overlapping active assignments
		overlap_query = """
			SELECT name, line_order, effective_from, effective_to
			FROM `tabEmployee Line Roster`
			WHERE employee = %(employee)s
			  AND status = 'Active'
			  AND name != %(current_name)s
			  AND (
				(effective_to IS NOT NULL AND effective_from <= %(eff_to)s AND effective_to >= %(eff_from)s)
				OR
				(effective_to IS NULL AND effective_from >= %(eff_from)s AND effective_from <= %(eff_to)s)
			  )
		"""
		conflicts = frappe.db.sql(overlap_query, {
			"employee": self.employee,
			"current_name": self.name or "",
			"eff_from": eff_from,
			"eff_to": eff_to
		}, as_dict=1)

		if conflicts and self.assignment_type != "Override":
			conflict_list = ", ".join([f"{c.name} (Line: {c.line_order}, {c.effective_from} to {c.effective_to or c.effective_from})" for c in conflicts])
			frappe.throw(
				f"Line conflict detected for Employee {self.employee_name or self.employee}. Overlaps with: {conflict_list}. Use Override assignment type if you want to replace existing assignments."
			)

	def on_update(self):
		doc_before_save = self.get_doc_before_save()
		is_new_doc = doc_before_save is None

		from company.company.line_roster_api import record_roster_history

		if is_new_doc:
			default_line = frappe.db.get_value("Employee", self.employee, "line_order")
			record_roster_history(
				roster_id=self.name,
				employee=self.employee,
				employee_name=self.employee_name,
				effective_from=self.effective_from,
				effective_to=self.effective_to or self.effective_from,
				previous_line=default_line,
				new_line=self.line_order if self.status == "Active" else None,
				changed_by=frappe.session.user,
				reason=self.reason or "Line roster assignment updated",
				source=self.assignment_type or "MANUAL"
			)
		else:
			status_changed = self.status != doc_before_save.status
			line_changed = self.line_order != doc_before_save.line_order

			if status_changed or line_changed:
				if self.status == "Cancelled":
					cancel_reason = self.reason if (self.reason and self.reason not in ("Assignment cancelled", "Line roster assignment updated")) else "Cancelled by user"
					record_roster_history(
						roster_id=self.name,
						employee=self.employee,
						employee_name=self.employee_name,
						effective_from=self.effective_from,
						effective_to=self.effective_to or self.effective_from,
						previous_line=doc_before_save.line_order or self.line_order,
						new_line=None,
						changed_by=frappe.session.user,
						reason=cancel_reason,
						source=self.assignment_type or "MANUAL"
					)
				else:
					update_reason = self.reason if (self.reason and self.reason not in ("Line roster assignment updated", "Assignment cancelled", "Cancelled by user")) else "Line roster assignment updated"
					record_roster_history(
						roster_id=self.name,
						employee=self.employee,
						employee_name=self.employee_name,
						effective_from=self.effective_from,
						effective_to=self.effective_to or self.effective_from,
						previous_line=doc_before_save.line_order,
						new_line=self.line_order,
						changed_by=frappe.session.user,
						reason=update_reason,
						source=self.assignment_type or "MANUAL"
					)
