# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import json
from datetime import datetime, date
import frappe
from frappe import _
from frappe.utils import getdate, cint


def execute(filters: dict | None = None):
	"""Return columns and data for the Canteen Report."""
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns() -> list[dict]:
	"""Return columns for the Canteen Report."""
	return [
		{"label": _("Date"), "fieldname": "canteen_date", "fieldtype": "Date", "width": 120},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 150},
		{"label": _("Designation"), "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 150},
		{"label": _("Meal Type"), "fieldname": "meal_type", "fieldtype": "Select", "width": 120},
		{"label": _("Meal Count"), "fieldname": "meal_count", "fieldtype": "Int", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Select", "width": 110},
		{"label": _("Source"), "fieldname": "source", "fieldtype": "Select", "width": 120},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Small Text", "width": 180},
		{"label": _("Name"), "fieldname": "name", "fieldtype": "Data", "width": 150},
	]


def get_data(filters: dict | None) -> list[dict]:
	"""Return Canteen entries for the selected date range and filters."""
	try:
		if isinstance(filters, str):
			filters = json.loads(filters)
		filters = filters or {}

		today = getdate()
		from_date = filters.get("from_date")
		to_date = filters.get("to_date")

		if not from_date:
			from_date = frappe.utils.get_first_day(today)
		else:
			from_date = getdate(from_date)

		if not to_date:
			to_date = frappe.utils.get_last_day(today)
		else:
			to_date = getdate(to_date)

		if to_date < from_date:
			return []

		selected_employee = filters.get("employee")
		if isinstance(selected_employee, str) and (selected_employee.startswith("[") or selected_employee.startswith("{")):
			try:
				selected_employee = json.loads(selected_employee)
			except Exception:
				pass

		if not selected_employee or selected_employee == "all" or selected_employee == "":
			selected_employee = None
		elif isinstance(selected_employee, str) and "," in selected_employee:
			selected_employee = [x.strip() for x in selected_employee.split(",") if x.strip()]

		meal_type_filter = filters.get("meal_type")
		if meal_type_filter in ["all", "", None]:
			meal_type_filter = None

		status_filter = filters.get("status")
		if status_filter in ["all", "", None]:
			status_filter = None

		dept_filter = filters.get("department")
		if dept_filter in ["all", "", None]:
			dept_filter = None

		# 1. Fetch Active Employees Map
		emp_filters = {"status": "Active"}
		if selected_employee:
			if isinstance(selected_employee, list):
				if len(selected_employee) == 1:
					emp_filters["name"] = selected_employee[0]
				elif len(selected_employee) > 1:
					emp_filters["name"] = ["in", selected_employee]
			else:
				emp_filters["name"] = selected_employee

		if dept_filter:
			emp_filters["department"] = dept_filter

		employees = frappe.get_all(
			"Employee",
			fields=["name", "employee_name", "department", "designation", "date_of_joining", "status"],
			filters=emp_filters,
			order_by="name asc"
		)

		if not employees:
			return []

		emp_map = {e.name: e for e in employees}
		emp_list = list(emp_map.keys())

		# 2. Build Query Conditions for Canteen Entry
		where_conditions = [
			"ce.canteen_date BETWEEN %(from_date)s AND %(to_date)s",
			"ce.employee IN %(emp_list)s"
		]
		params = {
			"from_date": str(from_date),
			"to_date": str(to_date),
			"emp_list": tuple(emp_list)
		}

		if meal_type_filter:
			where_conditions.append("ce.meal_type = %(meal_type)s")
			params["meal_type"] = meal_type_filter

		if status_filter:
			where_conditions.append("ce.status = %(status)s")
			params["status"] = status_filter

		where_str = " AND ".join(where_conditions)

		entries = frappe.db.sql(f"""
			SELECT 
				ce.name,
				ce.employee,
				ce.employee_name,
				ce.department,
				ce.designation,
				ce.canteen_date,
				ce.meal_type,
				ce.meal_count,
				ce.status,
				ce.source,
				ce.remarks,
				ce.creation,
				ce.modified
			FROM `tabCanteen Entry` ce
			WHERE {where_str}
			ORDER BY ce.canteen_date DESC, ce.employee_name ASC, ce.meal_type ASC
		""", params, as_dict=True)

		# 3. Format & Enrich
		final_data = []
		for entry in entries:
			emp_info = emp_map.get(entry.employee) or {}
			final_data.append({
				"name": entry.name,
				"canteen_date": str(entry.canteen_date),
				"employee": entry.employee,
				"employee_name": entry.employee_name or emp_info.get("employee_name") or entry.employee,
				"department": entry.department or emp_info.get("department") or "",
				"designation": entry.designation or emp_info.get("designation") or "",
				"meal_type": entry.meal_type or "Lunch",
				"meal_count": cint(entry.meal_count) or 1,
				"status": entry.status or "Availed",
				"source": entry.source or "Manual",
				"remarks": entry.remarks or "",
				"creation": str(entry.creation) if entry.creation else "",
				"modified": str(entry.modified) if entry.modified else ""
			})

		return final_data

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Canteen Report Error")
		return []
