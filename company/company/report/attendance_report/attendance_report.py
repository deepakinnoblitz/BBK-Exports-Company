# Copyright (c) 2025, deepak and contributors
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
		{"label": _("Date"), "fieldname": "attendance_date", "fieldtype": "Date", "width": 120},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 200},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Select", "width": 100},
		{"label": _("In Time"), "fieldname": "in_time", "fieldtype": "Time", "width": 100},
		{"label": _("Out Time"), "fieldname": "out_time", "fieldtype": "Time", "width": 100},
		{"label": _("Working Hours"), "fieldname": "working_hours_display", "fieldtype": "Data", "width": 120},
		{"label": _("Overtime"), "fieldname": "overtime_display", "fieldtype": "Data", "width": 120},
		{"label": _("Manual"), "fieldname": "manual", "fieldtype": "Check", "width": 80},
		{"label": _("Name"), "fieldname": "name", "fieldtype": "Data", "width": 120},
	]


def get_data(filters: dict | None) -> list[dict]:
	"""Return data for the report with gap analysis for Holidays and Missing attendance."""
	try:
		# Robust Filter Parsing
		if isinstance(filters, str):
			import json
			filters = json.loads(filters)
		
		today = frappe.utils.getdate()
		from_date = filters.get("from_date")
		to_date = filters.get("to_date")
		
		if not from_date: from_date = frappe.utils.get_first_day(today)
		else: from_date = frappe.utils.getdate(from_date)
			
		if not to_date: to_date = frappe.utils.get_last_day(today)
		else: to_date = frappe.utils.getdate(to_date)
		
		# Ensure we handle 'all' or empty filters consistently
		selected_employee = filters.get("employee")
		if not selected_employee or selected_employee == "all" or selected_employee == "":
			selected_employee = None
			
		status_filter = filters.get("status")
		if status_filter in ["all", "", None]:
			status_filter = None

		# 1. Fetch Employees
		emp_filters = {"status": "Active"} 
		if selected_employee:
			if isinstance(selected_employee, list):
				emp_filters["name"] = ["in", selected_employee]
			else:
				emp_filters["name"] = selected_employee

		employees = frappe.get_all(
			"Employee",
			fields=["name", "employee_name", "date_of_joining", "status"],
			filters=emp_filters
		)
		
		if not employees:
			return []
			
		emp_map = {e.name: e for e in employees}
		emp_list = list(emp_map.keys())

		# 2. Fetch Existing Attendance
		attendance_conditions = {
			"attendance_date": ["between", [from_date, to_date]],
			"employee": ["in", emp_list],
		}
		
		existing_attendance = frappe.get_all(
			"Attendance",
			fields=[
				"attendance_date", "employee", "employee_name", "status",
				"in_time", "out_time", "working_hours_display", "overtime_display",
				"manual", "name", "docstatus"
			],
			filters=attendance_conditions,
			order_by="attendance_date desc"
		)
		
		# Map: employee -> date -> record
		attendance_map = {}
		for row in existing_attendance:
			e = row.employee
			d = str(row.attendance_date)
			if e not in attendance_map: attendance_map[e] = {}
			attendance_map[e][d] = row

		# 3. Fetch Holidays from "Holiday List"
		# Strategy: Get lists matching the Year(s).
		relevant_years = list(set([from_date.year, to_date.year]))
		
		holiday_lists = frappe.get_all(
			"Holiday List",
			fields=["name"],
			filters={"year": ["in", relevant_years]}
		)
		
		holiday_list_names = [hl.name for hl in holiday_lists]
		
		holiday_map = {} # date -> description
		
		if holiday_list_names:
			holidays = frappe.get_all(
				"Holidays",
				fields=["parent", "holiday_date", "description", "is_working_day"],
				filters={
					"parent": ["in", holiday_list_names],
					"holiday_date": ["between", [from_date, to_date]]
				}
			)
			
			for h in holidays:
				holiday_map[str(h.holiday_date)] = h

		# 4. Gap Analysis
		final_data = []
		
		# Iterate dates from to_date down to from_date (descending)
		curr_date_ptr = to_date
		
		while curr_date_ptr >= from_date:
			date_str = str(curr_date_ptr)
			
			for emp in employees:
				# Skip if before joining or after relieving
				if emp.date_of_joining and curr_date_ptr < emp.date_of_joining:
					continue

				row = None
				
				# Check if attendance exists
				if emp.name in attendance_map and date_str in attendance_map[emp.name]:
					row = attendance_map[emp.name][date_str]
				
				# If no attendance, check for Holiday (Global check)
				elif date_str in holiday_map:
					h_record = holiday_map[date_str]
					if not h_record.is_working_day:
						row = {
							"attendance_date": curr_date_ptr,
							"employee": emp.name,
							"employee_name": emp.employee_name,
							"status": "Holiday",
							"in_time": None,
							"out_time": None,
							"working_hours_display": h_record.description, # Show description here
							"overtime_display": None,
							"name": "",
							"manual": 0
						}
				
				# If still no row, check if Missing (Past/Today + Not Sunday?)
				# Filter out weekends (Sunday) logic could go here if requested.
				# For 'Missing', strict logic: non-attendance on non-holiday is Missing.
				elif curr_date_ptr <= today:
					# Simple check: If not found and not future, it's Missing
					row = {
						"attendance_date": curr_date_ptr,
						"employee": emp.name,
						"employee_name": emp.employee_name,
						"status": "Missing",
						"in_time": None,
						"out_time": None,
						"working_hours_display": "00:00",
						"overtime_display": None,
						"name": "",
						"manual": 0
					}
				
				# Add to result if matches status filter
				if row:
					if not status_filter or status_filter == "all" or row.get("status") == status_filter:
						final_data.append(row)
			
			curr_date_ptr = frappe.utils.add_days(curr_date_ptr, -1)
			if isinstance(curr_date_ptr, str):
				curr_date_ptr = frappe.utils.getdate(curr_date_ptr)
		
		return final_data
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Attendance Report Error")
		return []


def get_conditions(filters: dict | None) -> dict:
	"""Deprecated: Logic moved to get_data."""
	return {}
