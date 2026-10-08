# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import json
import calendar
from datetime import datetime, date, timedelta
import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, cint, flt


def execute(filters: dict | None = None):
	"""Return columns and data for the Line Report."""
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns() -> list[dict]:
	"""Return columns for the Line Report."""
	return [
		{"label": _("Date"), "fieldname": "line_date", "fieldtype": "Date", "width": 120},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 150},
		{"label": _("Designation"), "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 150},
		{"label": _("Line Order"), "fieldname": "line_order", "fieldtype": "Link", "options": "Line Order", "width": 160},
		{"label": _("Line Name"), "fieldname": "line_name", "fieldtype": "Data", "width": 160},
		{"label": _("Assignment Type"), "fieldname": "assignment_type", "fieldtype": "Data", "width": 130},
		{"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 110},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Select", "width": 100},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Small Text", "width": 180},
		{"label": _("Name"), "fieldname": "name", "fieldtype": "Data", "width": 120},
	]


def get_data(filters: dict | None) -> list[dict]:
	"""Return resolved Line assignments for each employee across date range."""
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

		line_filter = filters.get("line") or filters.get("line_order")
		if line_filter in ["all", "", None]:
			line_filter = None

		status_filter = filters.get("status")
		if status_filter in ["all", "", None]:
			status_filter = None

		dept_filter = filters.get("department")
		if dept_filter in ["all", "", None]:
			dept_filter = None

		# 1. Fetch Master Lines
		lines_raw = frappe.get_all(
			"Line Order",
			fields=["name", "line_name", "status", "description"]
		)
		line_meta_map = {}
		for l in lines_raw:
			line_meta_map[l.name] = {
				"line_order": l.name,
				"line_name": l.line_name or l.name,
				"status": l.status or "Active",
				"description": l.description or "",
			}

		# 2. Fetch Active Employees
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
			fields=["name", "employee_name", "department", "designation", "date_of_joining", "status", "line_order"],
			filters=emp_filters,
			order_by="name asc"
		)

		if not employees:
			return []

		emp_list = [e.name for e in employees]

		# 3. Pre-fetch Date-specific Employee Line Roster records
		roster_records = frappe.db.sql("""
			SELECT name, employee, employee_name, department, designation, line_order, line_name,
			       effective_from, effective_to, assignment_type, status, reason
			FROM `tabEmployee Line Roster`
			WHERE employee IN %(emp_list)s
			  AND status = 'Active'
			  AND effective_from <= %(to_date)s
			  AND (effective_to IS NULL OR effective_to >= %(from_date)s)
			ORDER BY modified DESC
		""", {
			"emp_list": tuple(emp_list),
			"from_date": str(from_date),
			"to_date": str(to_date)
		}, as_dict=True)

		# Group roster records by employee
		emp_rosters = {}
		for r in roster_records:
			emp_rosters.setdefault(r.employee, []).append(r)

		# 4. Pre-fetch Active Line Rotations
		rotations = frappe.db.sql("""
			SELECT r.name, r.rotation_name, r.frequency, r.start_date, r.end_date,
			       r.exclude_holidays, r.exclude_weekly_offs, r.department, a.employee
			FROM `tabLine Rotation` r
			INNER JOIN `tabLine Rotation Assignee` a ON a.parent = r.name
			WHERE a.employee IN %(emp_list)s
			  AND r.status = 'Active'
			  AND r.start_date <= %(to_date)s
			  AND r.end_date >= %(from_date)s
			ORDER BY r.modified DESC
		""", {
			"emp_list": tuple(emp_list),
			"from_date": str(from_date),
			"to_date": str(to_date)
		}, as_dict=True)

		emp_rotations = {}
		rotation_names = set()
		for rot in rotations:
			emp_rotations.setdefault(rot.employee, []).append(rot)
			rotation_names.add(rot.name)

		# Fetch Rotation Sequences
		seq_map = {}
		if rotation_names:
			seq_records = frappe.db.sql("""
				SELECT parent, step_number, line_order, line_name
				FROM `tabLine Rotation Sequence`
				WHERE parent IN %(rot_names)s
				ORDER BY step_number ASC
			""", {"rot_names": tuple(rotation_names)}, as_dict=True)
			for s in seq_records:
				seq_map.setdefault(s.parent, []).append(s)

		# 5. Pre-fetch Holidays from Holiday List
		relevant_years = list(set([from_date.year, to_date.year]))
		holiday_lists = frappe.get_all("Holiday List", fields=["name"], filters={"year": ["in", relevant_years]})
		holiday_list_names = [hl.name for hl in holiday_lists]
		holiday_map = {}
		if holiday_list_names:
			holidays = frappe.get_all(
				"Holidays",
				fields=["parent", "holiday_date", "description", "is_working_day"],
				filters={
					"parent": ["in", holiday_list_names],
					"holiday_date": ["between", [str(from_date), str(to_date)]]
				}
			)
			for h in holidays:
				holiday_map[str(h.holiday_date)] = h

		# 6. Generate Daily Resolved Records across Date Range
		final_data = []
		curr_date_ptr = to_date

		while curr_date_ptr >= from_date:
			date_str = str(curr_date_ptr)
			is_sunday = curr_date_ptr.weekday() == 6
			is_holiday = date_str in holiday_map and not holiday_map[date_str].is_working_day
			holiday_desc = holiday_map[date_str].description if (date_str in holiday_map and not holiday_map[date_str].is_working_day) else ""

			for emp in employees:
				if emp.date_of_joining and curr_date_ptr < getdate(emp.date_of_joining):
					continue

				resolved_line = None
				source = "DEFAULT"
				assignment_type = "Default"
				reason = ""
				roster_name = ""

				# Check Roster Override
				if emp.name in emp_rosters:
					for r in emp_rosters[emp.name]:
						r_from = getdate(r.effective_from)
						r_to = getdate(r.effective_to) if r.effective_to else None
						if r_from <= curr_date_ptr and (r_to is None or r_to >= curr_date_ptr):
							resolved_line = r.line_order
							source = "ROSTER"
							assignment_type = r.assignment_type or "Manual"
							reason = r.reason or ""
							roster_name = r.name
							break

				# Check Rotation if not in Roster
				if not resolved_line and emp.name in emp_rotations:
					for rot in emp_rotations[emp.name]:
						if rot.exclude_weekly_offs and is_sunday:
							continue
						if rot.exclude_holidays and is_holiday:
							continue
						sequences = seq_map.get(rot.name, [])
						if not sequences:
							continue
						rot_start = getdate(rot.start_date)
						days_diff = (curr_date_ptr - rot_start).days
						if days_diff < 0:
							continue
						freq = (rot.frequency or "Weekly").lower()
						seq_count = len(sequences)
						if freq == "daily":
							step_idx = days_diff % seq_count
						elif freq == "bi-weekly":
							step_idx = (days_diff // 14) % seq_count
						elif freq == "monthly":
							months_diff = (curr_date_ptr.year - rot_start.year) * 12 + (curr_date_ptr.month - rot_start.month)
							step_idx = months_diff % seq_count
						else:
							step_idx = (days_diff // 7) % seq_count
						selected_seq = sequences[step_idx]
						resolved_line = selected_seq.line_order
						source = "ROTATION"
						assignment_type = "Rotation"
						reason = f"Rotation: {rot.rotation_name}"
						break

				# Check Default Line
				if not resolved_line:
					resolved_line = emp.line_order
					source = "DEFAULT"
					assignment_type = "Default"

				# Determine Status
				status = "Active"
				if is_holiday:
					status = "Holiday"
				elif is_sunday:
					status = "Weekly Off"

				meta = line_meta_map.get(resolved_line, {})
				line_name_display = meta.get("line_name") or resolved_line or "Unassigned"

				row = {
					"line_date": date_str,
					"employee": emp.name,
					"employee_name": emp.employee_name or emp.name,
					"department": emp.department or "",
					"designation": emp.designation or "",
					"line_order": resolved_line or "",
					"line_name": line_name_display,
					"assignment_type": assignment_type,
					"source": source,
					"status": status,
					"reason": reason or holiday_desc,
					"name": roster_name or f"LINE-{emp.name}-{date_str}",
				}

				# Apply filters
				if line_filter and row["line_order"] != line_filter and row["line_name"] != line_filter:
					continue
				if status_filter and status_filter != "all" and row["status"] != status_filter:
					continue

				final_data.append(row)

			curr_date_ptr = frappe.utils.add_days(curr_date_ptr, -1)
			if isinstance(curr_date_ptr, str):
				curr_date_ptr = getdate(curr_date_ptr)

		return final_data
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Line Report Error")
		return []
