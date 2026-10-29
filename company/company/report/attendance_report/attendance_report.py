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
	user_roles = frappe.get_roles(frappe.session.user)
	is_system_manager = any(r in ["System Manager", "Administrator"] for r in user_roles)

	columns = [
		{"label": _("Date"), "fieldname": "attendance_date", "fieldtype": "Date", "width": 120},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 200},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Select", "width": 100},
		{"label": _("In Time"), "fieldname": "in_time", "fieldtype": "Time", "width": 100},
		{"label": _("Out Time"), "fieldname": "out_time", "fieldtype": "Time", "width": 100},
		{"label": _("Working Hours"), "fieldname": "working_hours_display", "fieldtype": "Data", "width": 120},
		{"label": _("Overtime"), "fieldname": "official_overtime", "fieldtype": "Data", "width": 130},
	]

	if is_system_manager:
		columns.append({"label": _("Extra Overtime"), "fieldname": "unofficial_overtime", "fieldtype": "Data", "width": 150})

	columns.extend([
		{"label": _("Manual"), "fieldname": "manual", "fieldtype": "Check", "width": 80},
		{"label": _("Name"), "fieldname": "name", "fieldtype": "Data", "width": 120},
	])
	return columns


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
				"in_time", "out_time", "working_hours_display", "official_overtime",
				"unofficial_overtime", "manual", "name", "docstatus"
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
							"official_overtime": None,
							"unofficial_overtime": None,
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
						"official_overtime": None,
						"unofficial_overtime": None,
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


def format_time_val(val):
	if not val:
		return ""
	if isinstance(val, str):
		parts = val.split(":")
		if len(parts) >= 2:
			return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
		return val
	try:
		total_seconds = int(val.total_seconds())
		hours = total_seconds // 3600
		minutes = (total_seconds % 3600) // 60
		return f"{hours:02d}:{minutes:02d}"
	except Exception:
		return str(val)[:5]


def calc_stats(items):
	s = len(items)
	p = sum(1 for x in items if x.get("is_present"))
	a = s - p
	pct = round((a / s) * 100, 1) if s > 0 else 0.0
	return {"str": s, "pre": p, "abs": a, "abs_pct": pct}


def sum_stats(stats_list):
	s = sum(x["str"] for x in stats_list)
	p = sum(x["pre"] for x in stats_list)
	a = s - p
	pct = round((a / s) * 100, 1) if s > 0 else 0.0
	return {"str": s, "pre": p, "abs": a, "abs_pct": pct}


def combine_group_stats(items):
	existing_items = [x for x in items if not x.get("is_new_join") and not x.get("is_north_indian")]
	new_join_items = [x for x in items if x.get("is_new_join")]
	north_indian_items = [x for x in items if x.get("is_north_indian") and not x.get("is_new_join")]
	
	return {
		"existing": calc_stats(existing_items),
		"new_join": calc_stats(new_join_items),
		"north_indian": calc_stats(north_indian_items),
		"total": calc_stats(items)
	}


def sum_group_stats(group_stats_list):
	return {
		"existing": sum_stats([x["existing"] for x in group_stats_list]),
		"new_join": sum_stats([x["new_join"] for x in group_stats_list]),
		"north_indian": sum_stats([x["north_indian"] for x in group_stats_list]),
		"total": sum_stats([x["total"] for x in group_stats_list])
	}


@frappe.whitelist()
def get_daily_attendance_summary(date, load_all=0):
	"""
	Computes all 3 Daily Report components for a single date:
	1. attendance_by_department (Grouped biometric logs with in/out times and status)
	2. head_count (Staff and Worker breakdown with Manpower, Present, Absent, Absent %)
	3. line_wise (Line and Section breakdown across Existing, New Join, North Indian, Total)
	"""
	try:
		d = frappe.utils.getdate(date)
		today = frappe.utils.getdate()

		# 1. Fetch Active Employees
		employees = frappe.get_all(
			"Employee",
			fields=[
				"name", "employee_name", "department", "designation",
				"employee_type", "line_order",
				"production_type", "date_of_joining", "date_of_leaving"
			],
			filters={"status": "Active"},
			order_by="name asc"
		)

		valid_employees = []
		for emp in employees:
			if emp.date_of_joining and emp.date_of_joining > d:
				continue
			if emp.date_of_leaving and emp.date_of_leaving < d:
				continue
			valid_employees.append(emp)

		emp_names = [e.name for e in valid_employees]

		# 2. Fetch Attendance for this day
		attendance_rows = []
		if emp_names:
			attendance_rows = frappe.get_all(
				"Attendance",
				fields=[
					"employee", "status", "in_time", "out_time",
					"working_hours_display", "name"
				],
				filters={
					"attendance_date": d,
					"employee": ["in", emp_names]
				}
			)
		att_map = {r.employee: r for r in attendance_rows}

		# Check Holiday
		holiday = frappe.db.get_value(
			"Holidays",
			{"holiday_date": d, "is_working_day": 0},
			"description"
		)

		# 3. Classify each employee
		processed_emps = []
		for emp in valid_employees:
			att = att_map.get(emp.name)
			raw_status = att.status if att else ("Holiday" if holiday else ("Absent" if d <= today else "-"))
			in_t = format_time_val(att.in_time) if att else ""
			out_t = format_time_val(att.out_time) if att else ""
			is_present = bool(raw_status in ["Present", "Half Day", "Work From Home"] or in_t)

			emp_type_cat = f"{emp.employee_type or ''} {getattr(emp, 'employee_category', '') or ''}".lower()
			dept_str = (emp.department or "").lower()
			desig_str = (emp.designation or "").lower()
			line_str = (emp.line_order or "").lower()

			is_north_indian = "north indian" in emp_type_cat
			is_staff = "staff" in emp_type_cat or any(
				x in dept_str for x in ["accounts", "human resources", "hr", "it", "merchandising", "sourcing"]
			)
			is_new_join = False
			if emp.date_of_joining and emp.date_of_joining <= d:
				diff = (d - emp.date_of_joining).days
				# NEW JOIN means Working In One month (<= 31 days or joined in the same calendar month)
				if 0 <= diff <= 31 or (d.year == emp.date_of_joining.year and d.month == emp.date_of_joining.month):
					is_new_join = True

			prod_type = (getattr(emp, "production_type", None) or "").strip()
			if prod_type:
				is_production = (prod_type.lower() == "production")
			else:
				is_production = (not is_staff) and any(
					x in dept_str for x in ["sewing", "cutting", "finishing", "washing", "ironing", "embroidery", "sampling"]
				)

			disp_status = "Present" if is_present else ("Holiday" if raw_status == "Holiday" else "Absent")
			if is_present and in_t and not out_t:
				disp_status = "MP"  # Biometric punch in without punch out (Missing Punch)

			processed_emps.append({
				"attendance_name": att.name if att else None,
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"department": emp.department or "General",
				"designation": emp.designation or ("Staff" if is_staff else "Worker"),
				"in_time": in_t,
				"out_time": out_t,
				"status": disp_status,
				"raw_status": raw_status,
				"is_present": is_present,
				"is_staff": is_staff,
				"is_production": is_production,
				"production_type": prod_type or ("Production" if is_production else "Non Production"),
				"is_north_indian": is_north_indian,
				"is_new_join": is_new_join,
				"line_order": emp.line_order or "",
				"dept_str": dept_str,
				"desig_str": desig_str,
				"emp_type_cat": emp_type_cat
			})

		# ----------------------------------------------------
		# REPORT 1: Attendance with Department
		# ----------------------------------------------------
		# Sort by Department asc, Designation asc, Employee Name asc
		attendance_by_department = sorted(
			[
				{
					"employee": e["employee"],
					"employee_name": e["employee_name"],
					"department": e["department"],
					"designation": e["designation"],
					"in_time": e["in_time"],
					"out_time": e["out_time"],
					"status": e["status"],
					"is_present": e["is_present"],
					"is_staff": e["is_staff"],
					"is_production": e["is_production"],
					"production_type": e["production_type"],
					"is_new_join": e["is_new_join"],
					"is_north_indian": e["is_north_indian"],
					"line_order": e["line_order"]
				}
				for e in processed_emps
			],
			key=lambda x: (x["department"], x["designation"], x["employee_name"])
		)

		# ----------------------------------------------------
		# REPORT 2: Head Count Report (Fully Dynamic)
		# ----------------------------------------------------
		staff_emps = [e for e in processed_emps if e["is_staff"]]
		worker_emps = [e for e in processed_emps if not e["is_staff"]]

		def build_dynamic_headcount_groups(emps, group_field="department", sub_field="designation"):
			groups = {}
			for e in emps:
				main_val = e.get(group_field) or "Unassigned"
				sub_val = e.get(sub_field) or "Unassigned"
				if main_val not in groups:
					groups[main_val] = {"items": [], "sub_map": {}}
				groups[main_val]["items"].append(e)
				if sub_val not in groups[main_val]["sub_map"]:
					groups[main_val]["sub_map"][sub_val] = []
				groups[main_val]["sub_map"][sub_val].append(e)

			rows = []
			for main_val, g_data in sorted(groups.items(), key=lambda x: -len(x[1]["items"])):
				st = calc_stats(g_data["items"])
				sub_rows = []
				for sub_val, sub_items in sorted(g_data["sub_map"].items(), key=lambda x: -len(x[1])):
					sub_st = calc_stats(sub_items)
					sub_rows.append({
						sub_field: sub_val,
						"category": sub_val,
						"manpower": sub_st["str"],
						"present": sub_st["pre"],
						"absent": sub_st["abs"],
						"absent_pct": sub_st["abs_pct"]
					})
				rows.append({
					group_field: main_val,
					"category": main_val,
					"manpower": st["str"],
					"present": st["pre"],
					"absent": st["abs"],
					"absent_pct": st["abs_pct"],
					"sub_items": sub_rows
				})
			return rows

		staff_departments = build_dynamic_headcount_groups(staff_emps, "department", "designation")
		staff_designations = build_dynamic_headcount_groups(staff_emps, "designation", "department")

		worker_departments = build_dynamic_headcount_groups(worker_emps, "department", "designation")
		worker_designations = build_dynamic_headcount_groups(worker_emps, "designation", "department")

		staff_total_st = calc_stats(staff_emps)
		staff_total = {
			"category": "Staff Total",
			"manpower": staff_total_st["str"],
			"present": staff_total_st["pre"],
			"absent": staff_total_st["abs"],
			"absent_pct": staff_total_st["abs_pct"]
		}

		workers_total_st = calc_stats(worker_emps)
		workers_total = {
			"category": "Worker's Total",
			"manpower": workers_total_st["str"],
			"present": workers_total_st["pre"],
			"absent": workers_total_st["abs"],
			"absent_pct": workers_total_st["abs_pct"]
		}

		factory_total_st = calc_stats(processed_emps)
		factory_total = {
			"category": "Factory Total",
			"manpower": factory_total_st["str"],
			"present": factory_total_st["pre"],
			"absent": factory_total_st["abs"],
			"absent_pct": factory_total_st["abs_pct"]
		}

		head_count = {
			"staff": staff_departments,
			"staff_departments": staff_departments,
			"staff_designations": staff_designations,
			"staff_total": staff_total,
			"workers": worker_departments,
			"worker_departments": worker_departments,
			"worker_designations": worker_designations,
			"workers_total": workers_total,
			"factory_total": factory_total
		}

		# ----------------------------------------------------
		# REPORT 3: Line Wise Report (Dynamic Sections & Lines)
		# ----------------------------------------------------
		import re

		def natural_sort_key(s):
			return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", str(s or ""))]

		# 1. Fetch active Line Orders from DocType and any line_order present on active employees
		db_lines = frappe.get_all("Line Order", filters={"status": "Active"}, order_by="name asc", pluck="name")
		emp_lines = set(e["line_order"] for e in processed_emps if e.get("line_order"))
		all_line_names = sorted(list(set(db_lines) | emp_lines), key=natural_sort_key)

		# Dynamic production classification based on Employee.production_type field
		prod_line_emps = [e for e in processed_emps if e.get("is_production")]
		non_prod_emps = [e for e in processed_emps if not e.get("is_production")]

		line_allocated = set()
		production_sections = []

		# List all production lines directly without pairing
		sec_lines = []
		for l_name in all_line_names:
			matched = [e for e in prod_line_emps if e.get("line_order") == l_name]
			for e in matched:
				line_allocated.add(e["employee"])
			sec_lines.append({
				"line_name": l_name,
				**combine_group_stats(matched)
			})
		if sec_lines:
			sec_total = sum_group_stats(sec_lines)
			production_sections.append({
				"section_name": "PRODUCTION",
				"lines": sec_lines,
				"total": {
					"line_name": "TOTAL",
					**sec_total
				}
			})

		# Floor workers in production departments not allocated to a line
		unassigned_prod_workers = [
			e for e in prod_line_emps
			if e["employee"] not in line_allocated
		]
		if unassigned_prod_workers:
			for e in unassigned_prod_workers:
				line_allocated.add(e["employee"])
			extra_line = {
				"line_name": "Support & Floor Preparation",
				**combine_group_stats(unassigned_prod_workers)
			}
			production_sections.append({
				"section_name": "SUPPORT",
				"lines": [extra_line],
				"total": {
					"line_name": "TOTAL",
					**extra_line
				}
			})

		# Production Grand Total
		prod_grand_total = sum_group_stats([s["total"] for s in production_sections]) if production_sections else combine_group_stats([])

		# Dynamic Non-Production Section
		# Group all non_prod_emps dynamically by their actual department
		non_prod_dept_map = {}
		for e in non_prod_emps:
			dept = e.get("department") or "Other"
			non_prod_dept_map.setdefault(dept, []).append(e)

		non_prod_lines = []
		sorted_non_prod_depts = sorted(non_prod_dept_map.keys(), key=lambda d: len(non_prod_dept_map[d]), reverse=True)
		for dept_name in sorted_non_prod_depts:
			dept_emps = non_prod_dept_map[dept_name]
			non_prod_lines.append({
				"line_name": dept_name,
				**combine_group_stats(dept_emps)
			})

		non_prod_total = sum_group_stats(non_prod_lines) if non_prod_lines else combine_group_stats([])

		# Factory Grand Total
		factory_grand_total = sum_group_stats([prod_grand_total, non_prod_total])

		line_wise = {
			"production_sections": production_sections,
			"production_grand_total": {
				"line_name": "Grand Total of Production",
				**prod_grand_total
			},
			"non_production_section": {
				"section_name": "Non production",
				"lines": non_prod_lines,
				"total": {
					"line_name": "TOTAL",
					**non_prod_total
				}
			},
			"factory_grand_total": {
				"line_name": "GRAND TOTAL OF FACTORY",
				**factory_grand_total
			}
		}

		# Build department summaries
		dept_summary_map = {}
		for e in processed_emps:
			dept = e.get("department") or "Unassigned"
			if dept not in dept_summary_map:
				dept_summary_map[dept] = {"department": dept, "total": 0, "present": 0, "absent": 0}
			dept_summary_map[dept]["total"] += 1
			if e.get("is_present"):
				dept_summary_map[dept]["present"] += 1
			else:
				dept_summary_map[dept]["absent"] += 1

		department_summaries = sorted(list(dept_summary_map.values()), key=lambda x: x["department"])

		load_all_val = frappe.parse_json(load_all) if isinstance(load_all, str) else bool(load_all)
		first_dept = department_summaries[0]["department"] if department_summaries else None
		if not load_all_val and first_dept:
			final_attendance = [e for e in attendance_by_department if e["department"] == first_dept]
		else:
			final_attendance = attendance_by_department

		# Meta
		meta = {
			"date": str(d),
			"total_employees": factory_total["manpower"],
			"total_present": factory_total["present"],
			"total_absent": factory_total["absent"],
			"present_pct": round((factory_total["present"] / factory_total["manpower"]) * 100, 1) if factory_total["manpower"] > 0 else 0.0
		}

		return {
			"status": "success",
			"department_summaries": department_summaries,
			"attendance_by_department": final_attendance,
			"head_count": head_count,
			"line_wise": line_wise,
			"meta": meta
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Daily Attendance Summary Error")
		return {
			"status": "error",
			"message": str(e)
		}


@frappe.whitelist()
def get_daily_attendance_by_department(date, department):
	"""
	Fast on-demand endpoint that returns employee attendance list for a single department.
	"""
	try:
		d = frappe.utils.getdate(date)
		today = frappe.utils.getdate()

		# Check Holiday
		holiday = frappe.db.get_value(
			"Holidays",
			{"holiday_date": d, "is_working_day": 0},
			"description"
		)

		employees = frappe.get_all(
			"Employee",
			fields=[
				"name", "employee_name", "department", "designation",
				"employee_type", "line_order",
				"production_type", "date_of_joining", "date_of_leaving"
			],
			filters={"status": "Active", "department": department},
			order_by="name asc"
		)

		valid_employees = []
		for emp in employees:
			if emp.date_of_joining and emp.date_of_joining > d:
				continue
			if emp.date_of_leaving and emp.date_of_leaving < d:
				continue
			valid_employees.append(emp)

		emp_names = [e.name for e in valid_employees]
		attendance_rows = []
		if emp_names:
			attendance_rows = frappe.get_all(
				"Attendance",
				fields=["name", "employee", "status", "in_time", "out_time"],
				filters={"attendance_date": d, "employee": ("in", emp_names), "docstatus": ("!=", 2)}
			)
		att_map = {a.employee: a for a in attendance_rows}

		processed_emps = []
		for emp in valid_employees:
			att = att_map.get(emp.name)
			raw_status = att.status if att else ("Holiday" if holiday else ("Absent" if d <= today else "-"))
			in_t = format_time_val(att.in_time) if att else ""
			out_t = format_time_val(att.out_time) if att else ""
			is_present = bool(raw_status in ["Present", "Half Day", "Work From Home"] or in_t)

			emp_type_cat = f"{emp.employee_type or ''} {getattr(emp, 'employee_category', '') or ''}".lower()
			dept_str = (emp.department or "").lower()
			desig_str = (emp.designation or "").lower()

			is_north_indian = "north indian" in emp_type_cat or "north indian" in desig_str
			is_staff = "staff" in emp_type_cat or any(
				x in dept_str for x in ["accounts", "human resources", "hr", "it", "merchandising", "sourcing"]
			)
			is_new_join = False
			if emp.date_of_joining and emp.date_of_joining <= d:
				diff = (d - emp.date_of_joining).days
				if 0 <= diff <= 31 or (d.year == emp.date_of_joining.year and d.month == emp.date_of_joining.month):
					is_new_join = True

			prod_type = (getattr(emp, "production_type", None) or "").strip()
			if prod_type:
				is_production = (prod_type.lower() == "production")
			else:
				is_production = (not is_staff) and any(
					x in dept_str for x in ["sewing", "cutting", "finishing", "washing", "ironing", "embroidery", "sampling"]
				)

			disp_status = "Present" if is_present else ("Holiday" if raw_status == "Holiday" else "Absent")
			if is_present and in_t and not out_t:
				disp_status = "MP"

			processed_emps.append({
				"attendance_name": att.name if att else None,
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"department": emp.department or "General",
				"designation": emp.designation or ("Staff" if is_staff else "Worker"),
				"in_time": in_t,
				"out_time": out_t,
				"status": disp_status,
				"is_present": is_present,
				"is_staff": is_staff,
				"is_production": is_production,
				"production_type": prod_type or ("Production" if is_production else "Non Production"),
				"is_new_join": is_new_join,
				"is_north_indian": is_north_indian,
				"line_order": emp.line_order or ""
			})

		return {
			"status": "success",
			"department": department,
			"employees": sorted(processed_emps, key=lambda x: (x["designation"], x["employee_name"]))
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Daily Attendance Department Error")
		return {
			"status": "error",
			"message": str(e)
		}


def calc_row_stats(items):
	st = calc_stats(items)
	return {
		"manpower": st["str"],
		"present": st["pre"],
		"absent": st["abs"],
		"absent_pct": st["abs_pct"]
	}

