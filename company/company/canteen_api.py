# -*- coding: utf-8 -*-
# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import json
import calendar
from datetime import datetime, date
import frappe
from frappe.utils import getdate, now_datetime, cint, flt

# ----------------------------------------------------------------------
# 1. MONTHLY CANTEEN ROSTER / MUSTER ROLL
# ----------------------------------------------------------------------

@frappe.whitelist()
def get_monthly_canteen(month=None, year=None, department=None, employee=None, meal_type=None, start=0, limit=50, order_by=None):
	"""
	Returns the monthly canteen roster matrix, including holidays from existing Holiday List.
	"""
	today = getdate()
	m = cint(month) if month else today.month
	y = cint(year) if year else today.year
	start = cint(start)
	limit = cint(limit) if limit else 50
	if limit > 200:
		limit = 200

	num_days = calendar.monthrange(y, m)[1]
	start_date = date(y, m, 1)
	end_date = date(y, m, num_days)

	start_str = start_date.strftime("%Y-%m-%d")
	end_str = end_date.strftime("%Y-%m-%d")

	# 1. Pre-fetch Holidays for the month from Holiday List
	month_holidays = frappe.db.sql(
		"""
		SELECT holiday_date, description
		FROM `tabHolidays`
		WHERE holiday_date BETWEEN %s AND %s
		  AND is_working_day = 0
		""",
		(start_str, end_str),
		as_dict=True
	)
	holiday_map = {getdate(h.holiday_date): (h.description or "Holiday") for h in month_holidays}

	# 2. Generate Days list for the month
	days_list = []
	for day_idx in range(1, num_days + 1):
		d = date(y, m, day_idx)
		d_str = d.strftime("%Y-%m-%d")
		is_wo = d.weekday() == 6  # Sunday
		is_h = d in holiday_map
		h_name = holiday_map.get(d, "")

		days_list.append({
			"date": d_str,
			"day": day_idx,
			"day_name": d.strftime("%a"),
			"is_weekend": is_wo,
			"is_holiday": is_h,
			"holiday_name": h_name
		})

	# 3. Build Employee Filters & SQL
	emp_filters = {"status": "Active"}
	where_clauses = ["e.status = 'Active'"]
	values = {}

	if department and department != "all":
		emp_filters["department"] = department
		where_clauses.append("e.department = %(department)s")
		values["department"] = department

	if employee and employee != "all":
		if isinstance(employee, list):
			emp_filters["name"] = ["in", employee]
			where_clauses.append("e.name IN %(emp_list)s")
			values["emp_list"] = tuple(employee)
		elif isinstance(employee, str) and (employee.startswith("[") or "," in employee):
			try:
				parsed = json.loads(employee)
				if isinstance(parsed, list):
					emp_filters["name"] = ["in", parsed]
					where_clauses.append("e.name IN %(emp_list)s")
					values["emp_list"] = tuple(parsed)
				else:
					emp_filters["name"] = employee
					where_clauses.append("e.name = %(employee)s")
					values["employee"] = employee
			except Exception:
				parsed = [x.strip() for x in employee.split(",") if x.strip()]
				if parsed:
					emp_filters["name"] = ["in", parsed]
					where_clauses.append("e.name IN %(emp_list)s")
					values["emp_list"] = tuple(parsed)
		else:
			emp_filters["name"] = employee
			where_clauses.append("e.name = %(employee)s")
			values["employee"] = employee

	# Calculate Total Count for pagination
	total_count = frappe.db.count("Employee", filters=emp_filters)

	where_str = " AND ".join(where_clauses)
	values["limit"] = limit
	values["start"] = start

	# Determine Employee Order By
	join_ce = False
	if not order_by or order_by in ["employee_id_asc", "employee_asc", "name_asc", "employee_id asc", "name asc", "employee asc"]:
		sql_order = "e.name ASC"
	elif order_by in ["employee_id_desc", "employee_desc", "name_desc", "employee_id desc", "name desc", "employee desc"]:
		sql_order = "e.name DESC"
	elif order_by in ["modified_desc", "modified desc"]:
		join_ce = True
		sql_order = "CASE WHEN MAX(ce.modified) IS NOT NULL THEN 0 ELSE 1 END, MAX(ce.modified) DESC, e.name ASC"
	elif order_by in ["modified_asc", "modified asc"]:
		join_ce = True
		sql_order = "CASE WHEN MIN(ce.modified) IS NOT NULL THEN 0 ELSE 1 END, MIN(ce.modified) ASC, e.name ASC"
	elif order_by in ["employee_name_asc", "employee_name asc"]:
		sql_order = "e.employee_name ASC, e.name ASC"
	elif order_by in ["employee_name_desc", "employee_name desc"]:
		sql_order = "e.employee_name DESC, e.name ASC"
	elif order_by in ["department_asc", "department asc"]:
		sql_order = "e.department ASC, e.name ASC"
	elif order_by in ["department_desc", "department desc"]:
		sql_order = "e.department DESC, e.name ASC"
	else:
		sql_order = f"e.{order_by}"

	# Fetch Page of Employees
	if join_ce:
		employees_data = frappe.db.sql(f"""
			SELECT 
				e.name, e.employee_name, e.department, e.designation
			FROM `tabEmployee` e
			LEFT JOIN `tabCanteen Entry` ce ON ce.employee = e.name
			WHERE {where_str}
			GROUP BY e.name, e.employee_name, e.department, e.designation
			ORDER BY {sql_order}
			LIMIT %(limit)s OFFSET %(start)s
		""", values, as_dict=True)
	else:
		employees_data = frappe.db.sql(f"""
			SELECT 
				e.name, e.employee_name, e.department, e.designation
			FROM `tabEmployee` e
			WHERE {where_str}
			ORDER BY {sql_order}
			LIMIT %(limit)s OFFSET %(start)s
		""", values, as_dict=True)

	emp_ids = [e.name for e in employees_data]
	emp_entries = {}
	daily_totals = {d["date"]: 0 for d in days_list}
	grand_total = 0

	# 4. Fetch Canteen Entries for these employees
	if emp_ids:
		entry_conditions = [
			"employee IN %(emp_ids)s",
			"canteen_date BETWEEN %(start_str)s AND %(end_str)s",
			"status = 'Availed'"
		]
		entry_values = {
			"emp_ids": tuple(emp_ids),
			"start_str": start_str,
			"end_str": end_str
		}
		if meal_type and meal_type != "all":
			entry_conditions.append("meal_type = %(meal_type)s")
			entry_values["meal_type"] = meal_type

		entries = frappe.db.sql(
			f"""
			SELECT 
				name, employee, employee_name, canteen_date, meal_type, meal_count, status, source, remarks
			FROM `tabCanteen Entry`
			WHERE {" AND ".join(entry_conditions)}
			""",
			entry_values,
			as_dict=True
		)
		for entry in entries:
			d_str = str(entry.canteen_date)
			existing_rec = emp_entries.setdefault(entry.employee, {}).get(d_str)
			count = entry.meal_count or 1
			if existing_rec:
				existing_rec["meal_count"] += count
				current_types = existing_rec.get("meal_types", [existing_rec.get("meal_type")])
				current_types.append(entry.meal_type or "Lunch")
				existing_rec["meal_types"] = current_types
				existing_rec["meal_type"] = ", ".join(list(dict.fromkeys(current_types)))
			else:
				emp_entries.setdefault(entry.employee, {})[d_str] = {
					"name": entry.name,
					"meal_count": count,
					"meal_type": entry.meal_type or "Lunch",
					"meal_types": [entry.meal_type or "Lunch"],
					"status": entry.status,
					"source": entry.source,
					"remarks": entry.remarks
				}
			if d_str in daily_totals:
				daily_totals[d_str] += count
				grand_total += count

	# 5. Assemble Employee Matrix
	matrix_employees = []
	for emp in employees_data:
		records = emp_entries.get(emp.name, {})
		emp_total = sum((rec.get("meal_count") or 1) for rec in records.values())

		days_map = {}
		for d in days_list:
			d_str = d["date"]
			rec = records.get(d_str)
			if rec:
				days_map[d_str] = {
					"availed": True,
					"meal_count": rec.get("meal_count", 1),
					"meal_type": rec.get("meal_type", "Lunch"),
					"entry_id": rec.get("name"),
					"source": rec.get("source", "Manual"),
					"is_holiday": d["is_holiday"],
					"is_weekend": d["is_weekend"],
					"holiday_name": d["holiday_name"]
				}
			else:
				days_map[d_str] = {
					"availed": False,
					"meal_count": 0,
					"is_holiday": d["is_holiday"],
					"is_weekend": d["is_weekend"],
					"holiday_name": d["holiday_name"]
				}

		matrix_employees.append({
			"employee": emp.name,
			"employee_name": emp.employee_name or emp.name,
			"department": emp.department or "",
			"designation": emp.designation or "",
			"entries": days_map,
			"total_meals": emp_total
		})

	month_names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
	month_name = f"{month_names[m - 1]} {y}"

	return {
		"month": m,
		"year": y,
		"month_name": month_name,
		"days": days_list,
		"employees": matrix_employees,
		"daily_totals": daily_totals,
		"grand_total": grand_total,
		"total_count": total_count,
		"has_more": (start + len(matrix_employees)) < total_count
	}


# ----------------------------------------------------------------------
# 2. CALENDAR VIEW EVENTS
# ----------------------------------------------------------------------

@frappe.whitelist()
def get_calendar_canteen(start_date, end_date, employee=None, department=None, meal_type=None):
	"""
	Returns calendar events for Canteen entries and Holidays in range.
	"""
	if not start_date or not end_date:
		return []

	filters = [
		["canteen_date", ">=", start_date],
		["canteen_date", "<=", end_date],
		["status", "=", "Availed"]
	]
	if employee and employee != "all":
		if isinstance(employee, list):
			if len(employee) == 1:
				filters.append(["employee", "=", employee[0]])
			else:
				filters.append(["employee", "in", employee])
		elif isinstance(employee, str) and (employee.startswith("[") or "," in employee):
			try:
				parsed = json.loads(employee)
				if isinstance(parsed, list):
					if len(parsed) == 1:
						filters.append(["employee", "=", parsed[0]])
					else:
						filters.append(["employee", "in", parsed])
				else:
					filters.append(["employee", "=", str(parsed)])
			except Exception:
				parsed = [x.strip() for x in employee.split(",") if x.strip()]
				if len(parsed) == 1:
					filters.append(["employee", "=", parsed[0]])
				elif len(parsed) > 1:
					filters.append(["employee", "in", parsed])
		else:
			filters.append(["employee", "=", employee])

	if department and department != "all":
		filters.append(["department", "=", department])

	if meal_type and meal_type != "all":
		filters.append(["meal_type", "=", meal_type])

	entries = frappe.get_all(
		"Canteen Entry",
		filters=filters,
		fields=["name", "employee", "employee_name", "department", "canteen_date", "meal_type", "meal_count", "source", "status", "remarks"]
	)

	events = []
	for e in entries:
		d_str = str(e.canteen_date)
		events.append({
			"id": e.name,
			"title": f"{e.employee_name} ({e.meal_type} x{e.meal_count})",
			"start": d_str,
			"end": d_str,
			"allDay": True,
			"backgroundColor": "#059669",
			"borderColor": "#047857",
			"textColor": "#ffffff",
			"extendedProps": {
				"entry_id": e.name,
				"employee": e.employee,
				"employee_name": e.employee_name,
				"department": e.department,
				"canteen_date": d_str,
				"meal_type": e.meal_type,
				"meal_count": e.meal_count,
				"source": e.source,
				"remarks": e.remarks
			}
		})

	# Also add holidays to calendar
	holidays = frappe.db.sql(
		"""
		SELECT holiday_date, description
		FROM `tabHolidays`
		WHERE holiday_date BETWEEN %s AND %s
		  AND is_working_day = 0
		""",
		(start_date, end_date),
		as_dict=True
	)
	for h in holidays:
		d_str = str(h.holiday_date)
		events.append({
			"id": f"holiday-{d_str}",
			"title": f"Holiday: {h.description or 'Holiday'}",
			"start": d_str,
			"end": d_str,
			"allDay": True,
			"backgroundColor": "#ef4444",
			"borderColor": "#dc2626",
			"textColor": "#ffffff",
			"extendedProps": {
				"is_holiday": True,
				"holiday_name": h.description or "Holiday"
			}
		})

	return events


# ----------------------------------------------------------------------
# 3. CRUD & BULK OPERATIONS
# ----------------------------------------------------------------------

@frappe.whitelist()
def create_canteen_entry(data):
	"""Create a new canteen entry (or update if already exists for same employee, date, meal_type)"""
	if isinstance(data, str):
		data = json.loads(data)

	emp = data.get("employee")
	c_date = data.get("canteen_date")
	m_type = data.get("meal_type") or "Lunch"
	m_count = cint(data.get("meal_count")) or 1

	existing = frappe.db.get_value(
		"Canteen Entry",
		{"employee": emp, "canteen_date": c_date, "meal_type": m_type},
		"name"
	)

	if existing:
		doc = frappe.get_doc("Canteen Entry", existing)
		doc.meal_count = m_count
		doc.status = data.get("status") or "Availed"
		doc.remarks = data.get("remarks") or doc.remarks
		doc.save(ignore_permissions=True)
		return doc.as_dict()

	doc = frappe.get_doc({
		"doctype": "Canteen Entry",
		"employee": emp,
		"canteen_date": c_date,
		"meal_type": m_type,
		"meal_count": m_count,
		"status": data.get("status") or "Availed",
		"source": data.get("source") or "Manual",
		"remarks": data.get("remarks")
	})
	doc.insert(ignore_permissions=True)
	return doc.as_dict()


@frappe.whitelist()
def update_canteen_entry(name, data):
	"""Update an existing canteen entry"""
	if isinstance(data, str):
		data = json.loads(data)

	doc = frappe.get_doc("Canteen Entry", name)
	if "meal_count" in data:
		doc.meal_count = cint(data["meal_count"])
	if "meal_type" in data:
		doc.meal_type = data["meal_type"]
	if "status" in data:
		doc.status = data["status"]
	if "remarks" in data:
		doc.remarks = data["remarks"]
	if "canteen_date" in data:
		doc.canteen_date = data["canteen_date"]
	if "employee" in data:
		doc.employee = data["employee"]

	doc.save(ignore_permissions=True)
	return doc.as_dict()


@frappe.whitelist()
def delete_canteen_entry(name):
	"""Delete a canteen entry"""
	frappe.delete_doc("Canteen Entry", name, ignore_permissions=True)
	return True


@frappe.whitelist()
def bulk_delete_canteen_entries(names):
	"""Bulk delete canteen entries"""
	if isinstance(names, str):
		names = json.loads(names)

	for name in names:
		frappe.delete_doc("Canteen Entry", name, ignore_permissions=True)
	return True


# ----------------------------------------------------------------------
# 4. EXCEL BULK IMPORT API
# ----------------------------------------------------------------------

@frappe.whitelist()
def bulk_import_canteen_entries(month, year, rows, meal_type="Lunch"):
	"""
	Import parsed Excel rows for Canteen.
	rows format: [
		{
			"emp_number": "BEPL0002",
			"employee_name": "Sivakumar D S",
			"days": { "1": 1, "4": 1, "8": 2, ... }
		}
	]
	"""
	m = cint(month)
	y = cint(year)
	if isinstance(rows, str):
		rows = json.loads(rows)

	if not m or not y or not rows:
		frappe.throw("Month, Year and Rows are required for import")

	# Pre-fetch all active employees for matching by ID, employee_id, or name
	all_employees = frappe.db.get_all(
		"Employee",
		fields=["name", "employee_id", "employee_name", "department", "designation"]
	)
	emp_by_id = {}
	for e in all_employees:
		if e.name:
			emp_by_id[e.name.strip().upper()] = e
		if e.employee_id:
			emp_by_id[e.employee_id.strip().upper()] = e
	emp_by_name = {e.employee_name.strip().lower(): e for e in all_employees if e.employee_name}

	created_count = 0
	updated_count = 0
	total_meals = 0
	errors = []

	num_days = calendar.monthrange(y, m)[1]

	for r_idx, row in enumerate(rows):
		raw_emp_id = str(row.get("emp_number") or row.get("employee") or row.get("employee_id") or "").strip()
		raw_emp_name = str(row.get("employee_name") or row.get("name") or "").strip()
		days_data = row.get("days") or {}

		# Match employee
		emp = None
		if raw_emp_id:
			emp = emp_by_id.get(raw_emp_id.upper())
		if not emp and raw_emp_name:
			emp = emp_by_name.get(raw_emp_name.lower())

		if not emp:
			errors.append(f"Row {r_idx + 1}: Employee '{raw_emp_id}' ('{raw_emp_name}') not found in system")
			continue

		for day_str, count_val in days_data.items():
			try:
				day_num = cint(day_str)
				if day_num < 1 or day_num > num_days:
					continue

				meal_count = cint(count_val)
				if meal_count <= 0:
					continue

				c_date = date(y, m, day_num).strftime("%Y-%m-%d")

				existing = frappe.db.get_value(
					"Canteen Entry",
					{"employee": emp.name, "canteen_date": c_date, "meal_type": meal_type},
					["name", "meal_count"],
					as_dict=True
				)

				if existing:
					frappe.db.set_value("Canteen Entry", existing.name, {
						"meal_count": meal_count,
						"status": "Availed",
						"source": "Excel Import"
					})
					updated_count += 1
				else:
					doc = frappe.get_doc({
						"doctype": "Canteen Entry",
						"employee": emp.name,
						"employee_name": emp.employee_name,
						"department": emp.department,
						"designation": emp.designation,
						"canteen_date": c_date,
						"meal_type": meal_type,
						"meal_count": meal_count,
						"status": "Availed",
						"source": "Excel Import"
					})
					doc.insert(ignore_permissions=True)
					created_count += 1

				total_meals += meal_count

			except Exception as ex:
				errors.append(f"Row {r_idx + 1}, Day {day_str}: {str(ex)}")

	frappe.db.commit()

	return {
		"success": True,
		"created_count": created_count,
		"updated_count": updated_count,
		"total_meals": total_meals,
		"error_count": len(errors),
		"errors": errors[:20]  # First 20 errors if any
	}
