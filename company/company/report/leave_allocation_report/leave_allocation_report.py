# Copyright (c) 2026, Innoblitz and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters: dict | None = None):
	"""Return columns and data for the report."""
	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns() -> list[dict]:
	"""Return columns for the report."""
	return [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
		{"label": _("Leave Type"), "fieldname": "leave_type", "fieldtype": "Link", "options": "Leave Type", "width": 150},
		{"label": _("Allocated Days"), "fieldname": "total_leaves_allocated", "fieldtype": "Float", "width": 120},
		{"label": _("Used Days"), "fieldname": "total_leaves_taken", "fieldtype": "Float", "width": 120},
		{"label": _("Balance Days"), "fieldname": "balance_leaves", "fieldtype": "Float", "width": 120},
		{"label": _("Carry Forward"), "fieldname": "carry_forward", "fieldtype": "Check", "width": 100},
		{"label": _("Expiry Date"), "fieldname": "to_date", "fieldtype": "Date", "width": 120},
		{"label": _("From Date"), "fieldname": "from_date", "fieldtype": "Date", "width": 120},
	]


def get_data(filters: dict | None) -> list[dict]:
	"""Return data for the report based on leave allocations and type master."""
	try:
		if isinstance(filters, str):
			import json
			filters = json.loads(filters)

		conditions = []
		values = {}

		# Date filter parsing
		from_date = filters.get("from_date")
		to_date = filters.get("to_date")
		if from_date:
			conditions.append("la.from_date >= %(from_date)s")
			values["from_date"] = from_date
		if to_date:
			conditions.append("la.to_date <= %(to_date)s")
			values["to_date"] = to_date

		# Employee filter parsing
		employee = filters.get("employee")
		if employee and employee != "all" and employee != "":
			if isinstance(employee, list):
				if len(employee) > 0:
					conditions.append("la.employee in %(employee)s")
					values["employee"] = tuple(employee)
			else:
				conditions.append("la.employee = %(employee)s")
				values["employee"] = employee

		# Leave Type filter parsing
		leave_type = filters.get("leave_type")
		if leave_type and leave_type != "all" and leave_type != "":
			conditions.append("la.leave_type = %(leave_type)s")
			values["leave_type"] = leave_type

		conditions.append("la.docstatus < 2")  # Exclude cancelled

		where_clause = " AND ".join(conditions)
		if where_clause:
			where_clause = "WHERE " + where_clause

		query = f"""
			SELECT
				la.name,
				la.employee,
				la.employee_name,
				la.leave_type,
				la.total_leaves_allocated,
				la.total_leaves_taken,
				(la.total_leaves_allocated - la.total_leaves_taken) as balance_leaves,
				COALESCE(lt.carry_forward, 0) as carry_forward,
				la.from_date,
				la.to_date
			FROM `tabLeave Allocation` la
			LEFT JOIN `tabLeave Type` lt ON la.leave_type = lt.name
			{where_clause}
			ORDER BY la.creation DESC
		"""

		data = frappe.db.sql(query, values, as_dict=True)
		return data

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Leave Allocation Report Error")
		return []
