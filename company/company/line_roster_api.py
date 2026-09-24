# -*- coding: utf-8 -*-
# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import json
import calendar
from datetime import datetime, date, timedelta
import frappe
from frappe.utils import getdate, now_datetime, cint, flt

# ----------------------------------------------------------------------
# 1. CENTRAL LINE RESOLVER
# ----------------------------------------------------------------------

@frappe.whitelist()
def get_applicable_line(employee, attendance_date):
	"""
	Central resolver to determine an employee's applicable line for a given date.
	Resolution Order:
	  1. Date-specific Employee Line Roster assignment (Active)
	  2. Line Rotation schedule assignment (Active)
	  3. Employee's Default Line (line_order) from Employee record
	"""
	if not employee or not attendance_date:
		return None

	target_date = getdate(attendance_date)
	date_str = target_date.strftime("%Y-%m-%d")

	# 1. Check Date-specific Employee Line Roster
	roster = frappe.db.sql("""
		SELECT name, line_order, line_name, assignment_type, effective_from, effective_to
		FROM `tabEmployee Line Roster`
		WHERE employee = %(employee)s
		  AND status = 'Active'
		  AND effective_from <= %(date_str)s
		  AND (effective_to IS NULL OR effective_to >= %(date_str)s)
		ORDER BY modified DESC
		LIMIT 1
	""", {"employee": employee, "date_str": date_str}, as_dict=1)

	if roster and roster[0].line_order:
		r = roster[0]
		line_details = get_line_metadata(r.line_order)
		return {
			"line_order": r.line_order,
			"line_name": r.line_name or (line_details.get("line_name") if line_details else r.line_order),
			"source": "ROSTER",
			"roster_id": r.name,
			"assignment_type": r.assignment_type,
			"details": line_details
		}

	# 2. Check Active Line Rotation
	rotations = frappe.db.sql("""
		SELECT r.name, r.rotation_name, r.frequency, r.start_date, r.end_date,
		       r.exclude_holidays, r.exclude_weekly_offs, r.department
		FROM `tabLine Rotation` r
		INNER JOIN `tabLine Rotation Assignee` a ON a.parent = r.name
		WHERE a.employee = %(employee)s
		  AND r.status = 'Active'
		  AND r.start_date <= %(date_str)s
		  AND r.end_date >= %(date_str)s
		ORDER BY r.modified DESC
	""", {"employee": employee, "date_str": date_str}, as_dict=1)

	if not rotations:
		# Also check department level rotation
		emp_dept = frappe.db.get_value("Employee", employee, "department")
		if emp_dept:
			rotations = frappe.db.sql("""
				SELECT name, rotation_name, frequency, start_date, end_date,
				       exclude_holidays, exclude_weekly_offs, department
				FROM `tabLine Rotation`
				WHERE department = %(department)s
				  AND status = 'Active'
				  AND start_date <= %(date_str)s
				  AND end_date >= %(date_str)s
				ORDER BY modified DESC
			""", {"department": emp_dept, "date_str": date_str}, as_dict=1)

	for rot in rotations:
		# Check if today is a weekly-off or holiday and rotation excludes it
		is_weekly_off = target_date.weekday() == 6  # Sunday by default
		if rot.exclude_weekly_offs and is_weekly_off:
			continue

		if rot.exclude_holidays and is_holiday_for_date(target_date):
			continue

		# Calculate sequence index
		sequences = frappe.db.sql("""
			SELECT step_number, line_order, line_name
			FROM `tabLine Rotation Sequence`
			WHERE parent = %(parent)s
			ORDER BY step_number ASC
		""", {"parent": rot.name}, as_dict=1)

		if not sequences:
			continue

		start_dt = getdate(rot.start_date)
		seq_count = len(sequences)
		frequency = (rot.frequency or "Weekly").lower()

		days_diff = (target_date - start_dt).days
		if days_diff < 0:
			continue

		if frequency == "daily":
			step_idx = days_diff % seq_count
		elif frequency == "bi-weekly":
			step_idx = (days_diff // 14) % seq_count
		elif frequency == "monthly":
			months_diff = (target_date.year - start_dt.year) * 12 + (target_date.month - start_dt.month)
			step_idx = months_diff % seq_count
		else:  # weekly
			step_idx = (days_diff // 7) % seq_count

		selected_line = sequences[step_idx].line_order
		line_details = get_line_metadata(selected_line)
		return {
			"line_order": selected_line,
			"line_name": sequences[step_idx].line_name or (line_details.get("line_name") if line_details else selected_line),
			"source": "ROTATION",
			"rotation_name": rot.rotation_name,
			"details": line_details
		}

	# 3. Fallback to Employee's Default Line (line_order)
	default_line = frappe.db.get_value("Employee", employee, "line_order")
	if default_line:
		line_details = get_line_metadata(default_line)
		return {
			"line_order": default_line,
			"line_name": line_details.get("line_name") if line_details else default_line,
			"source": "DEFAULT",
			"details": line_details
		}

	return None


def get_line_metadata(line_order):
	"""Returns cached Line Order master metadata."""
	if not line_order:
		return None
	line = frappe.db.get_value("Line Order", line_order, ["name", "line_name", "status", "description"], as_dict=1)
	return line


def is_holiday_for_date(target_date):
	"""Checks if given date is a non-working holiday in Holiday List."""
	d_str = target_date.strftime("%Y-%m-%d") if isinstance(target_date, (date, datetime)) else str(target_date)
	return frappe.db.exists("Holidays", {"holiday_date": d_str, "is_working_day": 0}) is not None


def record_roster_history(roster_id, employee, employee_name, effective_from, effective_to, previous_line, new_line, changed_by, reason, source="MANUAL"):
	"""Creates an immutable audit log entry in Employee Line Roster History."""
	try:
		if not employee_name and employee:
			employee_name = frappe.db.get_value("Employee", employee, "employee_name")

		history = frappe.new_doc("Employee Line Roster History")
		history.roster_id = roster_id or ""
		history.employee = employee
		history.employee_name = employee_name or employee
		history.effective_from = effective_from
		history.effective_to = effective_to or effective_from
		history.previous_line = previous_line
		history.new_line = new_line
		history.source = (source or "MANUAL").upper()
		history.changed_by = changed_by or frappe.session.user
		history.changed_at = now_datetime()
		history.reason = reason or "Roster assignment changed"
		history.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(f"Failed to record line roster history: {str(e)}", "Line Roster History")


# ----------------------------------------------------------------------
# 2. CONFLICT CHECKING & CRUD APIS
# ----------------------------------------------------------------------

@frappe.whitelist()
def check_roster_conflict(employee, effective_from, effective_to=None, exclude_name=None):
	"""Returns any active overlapping line roster assignments for the employee."""
	if not employee or not effective_from:
		return []

	eff_from = effective_from
	eff_to = effective_to or effective_from

	query = """
		SELECT name, line_order, line_name, effective_from, effective_to, assignment_type
		FROM `tabEmployee Line Roster`
		WHERE employee = %(employee)s
		  AND status = 'Active'
		  AND (%(exclude_name)s IS NULL OR name != %(exclude_name)s)
		  AND (
			(effective_to IS NOT NULL AND effective_from <= %(eff_to)s AND effective_to >= %(eff_from)s)
			OR
			(effective_to IS NULL AND effective_from >= %(eff_from)s AND effective_from <= %(eff_to)s)
		  )
	"""
	return frappe.db.sql(query, {
		"employee": employee,
		"eff_from": eff_from,
		"eff_to": eff_to,
		"exclude_name": exclude_name or None
	}, as_dict=1)


@frappe.whitelist()
def create_roster_assignment(data):
	"""Creates a new Employee Line Roster assignment."""
	if isinstance(data, str):
		data = json.loads(data)

	employee = data.get("employee")
	line_order = data.get("line_order") or data.get("line")
	effective_from = data.get("effective_from")
	effective_to = data.get("effective_to") or effective_from
	assignment_type = data.get("assignment_type", "Manual")
	reason = data.get("reason", "")
	status = data.get("status", "Active")

	if not employee or not line_order or not effective_from:
		frappe.throw("Employee, Line Order, and Effective From are required.")

	# If assignment type is Override, cancel conflicting active records first
	if assignment_type == "Override":
		conflicts = check_roster_conflict(employee, effective_from, effective_to)
		for c in conflicts:
			frappe.db.set_value("Employee Line Roster", c.name, {
				"status": "Cancelled",
				"reason": f"Overridden by new assignment for {line_order} ({effective_from} to {effective_to})"
			})
			record_roster_history(
				roster_id=c.name,
				employee=employee,
				employee_name=None,
				effective_from=c.effective_from,
				effective_to=c.effective_to,
				previous_line=c.line_order,
				new_line=None,
				changed_by=frappe.session.user,
				reason="Overridden by new line assignment",
				source="OVERRIDE"
			)

	doc = frappe.new_doc("Employee Line Roster")
	doc.employee = employee
	doc.line_order = line_order
	doc.effective_from = effective_from
	doc.effective_to = effective_to
	doc.assignment_type = assignment_type
	doc.reason = reason
	doc.status = status
	doc.insert()
	frappe.db.commit()

	return doc.as_dict()


@frappe.whitelist()
def update_roster_assignment(name, data):
	"""Updates an existing Employee Line Roster assignment."""
	if isinstance(data, str):
		data = json.loads(data)

	if not frappe.db.exists("Employee Line Roster", name):
		frappe.throw(f"Employee Line Roster record {name} not found.")

	doc = frappe.get_doc("Employee Line Roster", name)

	if "employee" in data:
		doc.employee = data["employee"]
	if "line_order" in data or "line" in data:
		doc.line_order = data.get("line_order") or data.get("line")
	if "effective_from" in data:
		doc.effective_from = data["effective_from"]
	if "effective_to" in data:
		doc.effective_to = data["effective_to"]
	if "assignment_type" in data:
		doc.assignment_type = data["assignment_type"]
	if "reason" in data:
		doc.reason = data["reason"]
	if "status" in data:
		doc.status = data["status"]

	doc.save()
	frappe.db.commit()

	return doc.as_dict()


@frappe.whitelist()
def delete_or_cancel_roster_assignment(name, reason=None, delete_permanently=False):
	"""Cancels or permanently deletes a line roster assignment."""
	if not frappe.db.exists("Employee Line Roster", name):
		frappe.throw(f"Employee Line Roster {name} not found.")

	is_delete = cint(delete_permanently) == 1 or str(delete_permanently).lower() in ("true", "1")
	doc = frappe.get_doc("Employee Line Roster", name)

	if is_delete:
		record_roster_history(
			roster_id=doc.name,
			employee=doc.employee,
			employee_name=doc.employee_name,
			effective_from=doc.effective_from,
			effective_to=doc.effective_to,
			previous_line=doc.line_order,
			new_line=None,
			changed_by=frappe.session.user,
			reason=reason or "Deleted permanently",
			source="MANUAL"
		)
		doc.delete()
	else:
		if doc.status != "Cancelled":
			doc.status = "Cancelled"
			doc.reason = reason or "Cancelled by user"
			doc.save()

	frappe.db.commit()
	return {"success": True, "name": name}


# ----------------------------------------------------------------------
# 3. BULK ASSIGNMENT & PREVIEW
# ----------------------------------------------------------------------

@frappe.whitelist()
def preview_bulk_assign_lines(employees, line_order, effective_from, effective_to, exclude_weekly_offs=True, exclude_holidays=True):
	"""
	Simulates a bulk line assignment and returns preview details and conflict warnings.
	"""
	if isinstance(employees, str):
		employees = json.loads(employees)

	exclude_weekly_offs = cint(exclude_weekly_offs)
	exclude_holidays = cint(exclude_holidays)

	start_dt = getdate(effective_from)
	end_dt = getdate(effective_to) if effective_to else start_dt

	if end_dt < start_dt:
		frappe.throw("Effective To cannot be earlier than Effective From.")

	# Generate dates list
	dates_to_assign = []
	curr = start_dt
	while curr <= end_dt:
		is_wo = curr.weekday() == 6
		is_h = is_holiday_for_date(curr)

		if exclude_weekly_offs and is_wo:
			curr += timedelta(days=1)
			continue
		if exclude_holidays and is_h:
			curr += timedelta(days=1)
			continue

		dates_to_assign.append(curr.strftime("%Y-%m-%d"))
		curr += timedelta(days=1)

	preview_items = []
	conflict_count = 0

	for emp_id in employees:
		emp = frappe.db.get_value("Employee", emp_id, ["name", "employee_name", "department", "designation", "line_order"], as_dict=1)
		if not emp:
			continue

		conflicts = check_roster_conflict(emp_id, effective_from, effective_to)
		has_conflict = len(conflicts) > 0
		if has_conflict:
			conflict_count += 1

		preview_items.append({
			"employee": emp.name,
			"employee_name": emp.employee_name,
			"department": emp.department,
			"designation": emp.designation,
			"current_default_line": emp.line_order,
			"new_line": line_order,
			"effective_from": effective_from,
			"effective_to": effective_to,
			"assigned_days_count": len(dates_to_assign),
			"has_conflict": has_conflict,
			"conflicts": conflicts
		})

	return {
		"total_employees": len(employees),
		"applicable_dates_count": len(dates_to_assign),
		"conflict_employees_count": conflict_count,
		"preview": preview_items
	}


@frappe.whitelist()
def bulk_assign_lines(employees, line_order, effective_from, effective_to, assignment_type="Bulk", reason="", exclude_weekly_offs=True, exclude_holidays=True, override_conflicts=False):
	"""
	Performs atomic bulk assignment of lines to multiple employees.
	"""
	if isinstance(employees, str):
		employees = json.loads(employees)

	exclude_weekly_offs = cint(exclude_weekly_offs)
	exclude_holidays = cint(exclude_holidays)
	override_conflicts = cint(override_conflicts)

	start_dt = getdate(effective_from)
	end_dt = getdate(effective_to) if effective_to else start_dt

	if not employees or not line_order or not effective_from:
		frappe.throw("Employees list, Line Order, and Effective From date are required.")

	created_count = 0
	skipped_count = 0
	errors = []

	for emp_id in employees:
		try:
			conflicts = check_roster_conflict(emp_id, effective_from, effective_to)
			if conflicts:
				if override_conflicts:
					for c in conflicts:
						frappe.db.set_value("Employee Line Roster", c.name, {
							"status": "Cancelled",
							"reason": f"Overridden by bulk assignment for {line_order} ({effective_from} to {effective_to})"
						})
						record_roster_history(
							roster_id=c.name,
							employee=emp_id,
							employee_name=None,
							effective_from=c.effective_from,
							effective_to=c.effective_to,
							previous_line=c.line_order,
							new_line=None,
							changed_by=frappe.session.user,
							reason="Overridden by bulk assignment",
							source="OVERRIDE"
						)
				else:
					skipped_count += 1
					errors.append(f"Employee {emp_id} skipped due to conflict.")
					continue

			doc = frappe.new_doc("Employee Line Roster")
			doc.employee = emp_id
			doc.line_order = line_order
			doc.effective_from = effective_from
			doc.effective_to = effective_to
			doc.assignment_type = assignment_type or "Bulk"
			doc.reason = reason or "Bulk line assignment"
			doc.status = "Active"
			doc.insert()
			created_count += 1

		except Exception as e:
			skipped_count += 1
			errors.append(f"Error for {emp_id}: {str(e)}")

	frappe.db.commit()

	return {
		"created_count": created_count,
		"skipped_count": skipped_count,
		"errors": errors
	}


# ----------------------------------------------------------------------
# 4. MONTHLY ROSTER MATRIX & CALENDAR FEED
# ----------------------------------------------------------------------

@frappe.whitelist()
def get_monthly_roster(month=None, year=None, department=None, employee=None, search=None, start=0, limit=50):
	"""
	Returns workforce line roster matrix: all employees as rows, month days as columns.
	Supports pagination (start, limit) and search for high-performance instant rendering.
	"""
	m = cint(month)
	y = cint(year)
	if not m or not y:
		today = date.today()
		m = today.month
		y = today.year

	start = cint(start) if start is not None else 0
	limit = cint(limit) if limit is not None else 50
	if limit <= 0:
		limit = 50

	num_days = calendar.monthrange(y, m)[1]
	start_date = date(y, m, 1)
	end_date = date(y, m, num_days)

	start_str = start_date.strftime("%Y-%m-%d")
	end_str = end_date.strftime("%Y-%m-%d")

	# 1. Pre-fetch Holidays for the month once
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
		is_wo = d.weekday() == 6
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

	# 3. Build Employee Filters
	emp_filters = {"status": "Active"}
	if department and department != "all":
		emp_filters["department"] = department
	if employee and employee != "all":
		if isinstance(employee, list):
			emp_filters["name"] = ["in", employee]
		elif isinstance(employee, str) and (employee.startswith("[") or "," in employee):
			try:
				parsed = json.loads(employee)
				if isinstance(parsed, list):
					emp_filters["name"] = ["in", parsed]
				else:
					emp_filters["name"] = employee
			except Exception:
				emp_filters["name"] = ["in", [x.strip() for x in employee.split(",") if x.strip()]]
		else:
			emp_filters["name"] = employee

	# Calculate Total Count for pagination
	total_count = frappe.db.count("Employee", filters=emp_filters)

	# Fetch Page of Employees
	employees_data = frappe.db.get_all(
		"Employee",
		filters=emp_filters,
		fields=["name", "employee_name", "department", "designation", "line_order"],
		order_by="employee_name asc",
		start=start,
		page_length=limit
	)

	# 4. Pre-fetch all active Line Order records for lookup
	all_lines = frappe.db.get_all(
		"Line Order",
		filters={"status": "Active"},
		fields=["name", "line_name", "description"]
	)
	line_lookup = {l.name: l for l in all_lines}

	# 5. Fetch all active line roster assignments for THIS page of employees
	emp_ids = [e.name for e in employees_data]
	emp_rosters = {}
	if emp_ids:
		roster_records = frappe.db.sql(
			"""
			SELECT 
				name, employee, line_order, line_name, effective_from, effective_to, assignment_type, modified
			FROM `tabEmployee Line Roster`
			WHERE status = 'Active'
			  AND employee IN %(emp_ids)s
			  AND (effective_from <= %(end_str)s AND (effective_to >= %(start_str)s OR effective_to IS NULL OR effective_to = ''))
			ORDER BY modified ASC
			""",
			{"emp_ids": tuple(emp_ids), "start_str": start_str, "end_str": end_str},
			as_dict=True
		)
		for r in roster_records:
			emp_rosters.setdefault(r.employee, []).append(r)

	# 6. Pre-fetch active Line Rotations (if any)
	rotations_emp = {}
	rotations_dept = {}
	rotation_seqs = {}
	active_rotations = frappe.db.sql(
		"""
		SELECT r.name, r.rotation_name, r.frequency, r.start_date, r.end_date,
		       r.exclude_holidays, r.exclude_weekly_offs, r.department,
		       a.employee
		FROM `tabLine Rotation` r
		LEFT JOIN `tabLine Rotation Assignee` a ON a.parent = r.name
		WHERE r.status = 'Active'
		  AND r.start_date <= %(end_str)s
		  AND r.end_date >= %(start_str)s
		ORDER BY r.modified DESC
		""",
		{"start_str": start_str, "end_str": end_str},
		as_dict=True
	)
	if active_rotations:
		rot_names = list({r.name for r in active_rotations})
		seq_records = frappe.db.sql(
			"""
			SELECT parent, step_number, line_order, line_name
			FROM `tabLine Rotation Sequence`
			WHERE parent IN %(rot_names)s
			ORDER BY step_number ASC
			""",
			{"rot_names": tuple(rot_names)},
			as_dict=True
		)
		for s in seq_records:
			rotation_seqs.setdefault(s.parent, []).append(s)

		for r in active_rotations:
			if r.employee:
				rotations_emp.setdefault(r.employee, []).append(r)
			elif r.department:
				rotations_dept.setdefault(r.department, []).append(r)

	# Helper to resolve rotation in-memory without ANY SQL queries
	def resolve_rotation_in_memory(emp_id, emp_dept, target_d, d_str):
		rots = (rotations_emp.get(emp_id) or (rotations_dept.get(emp_dept) if emp_dept else None) or [])
		is_wo = target_d.weekday() == 6
		is_h = target_d in holiday_map

		for rot in rots:
			if getdate(rot.start_date) <= target_d <= getdate(rot.end_date):
				if rot.exclude_weekly_offs and is_wo:
					continue
				if rot.exclude_holidays and is_h:
					continue
				seqs = rotation_seqs.get(rot.name, [])
				if not seqs:
					continue
				diff_days = (target_d - getdate(rot.start_date)).days
				freq = (rot.frequency or "Daily").lower()
				if "week" in freq:
					step_idx = (diff_days // 7) % len(seqs)
				elif "month" in freq:
					step_idx = ((target_d.year - rot.start_date.year) * 12 + target_d.month - rot.start_date.month) % len(seqs)
				else:
					step_idx = diff_days % len(seqs)
				matched = seqs[step_idx]
				return {
					"line_order": matched.line_order,
					"line_name": matched.line_name or matched.line_order,
					"source": "ROTATION",
					"roster_id": rot.name
				}
		return None

	# 7. Build Employee Matrix
	matrix = []
	for emp in employees_data:
		e_id = emp.name
		r_list = emp_rosters.get(e_id, [])

		emp_lines = {}
		for day_info in days_list:
			d_str = day_info["date"]
			d_obj = getdate(d_str)

			assigned_roster = None
			for r in r_list:
				r_from = getdate(r.effective_from)
				r_to = getdate(r.effective_to) if r.effective_to else r_from
				if r_from <= d_obj <= r_to:
					assigned_roster = r

			if assigned_roster:
				l_name = assigned_roster.line_order
				l_meta = line_lookup.get(l_name, {})
				emp_lines[d_str] = {
					"line_order": l_name,
					"line_name": assigned_roster.line_name or l_meta.get("line_name", l_name),
					"source": "ROSTER",
					"roster_id": assigned_roster.name,
					"assignment_type": assigned_roster.assignment_type,
					"is_weekly_off": day_info["is_weekend"],
					"is_holiday": day_info["is_holiday"]
				}
			else:
				# Resolve rotation or default line in-memory (0 database queries!)
				rot_match = resolve_rotation_in_memory(e_id, emp.department, d_obj, d_str)
				if rot_match:
					l_name = rot_match["line_order"]
					l_meta = line_lookup.get(l_name, {})
					emp_lines[d_str] = {
						"line_order": l_name,
						"line_name": rot_match.get("line_name") or l_meta.get("line_name", l_name),
						"source": "ROTATION",
						"roster_id": rot_match.get("roster_id"),
						"is_weekly_off": day_info["is_weekend"],
						"is_holiday": day_info["is_holiday"]
					}
				elif emp.line_order:
					l_name = emp.line_order
					l_meta = line_lookup.get(l_name, {})
					emp_lines[d_str] = {
						"line_order": l_name,
						"line_name": l_meta.get("line_name", l_name),
						"source": "DEFAULT",
						"roster_id": None,
						"is_weekly_off": day_info["is_weekend"],
						"is_holiday": day_info["is_holiday"]
					}
				else:
					emp_lines[d_str] = {
						"line_order": None,
						"line_name": "Unassigned",
						"source": "NONE",
						"is_weekly_off": day_info["is_weekend"],
						"is_holiday": day_info["is_holiday"]
					}

		matrix.append({
			"employee": emp.name,
			"employee_name": emp.employee_name,
			"department": emp.department or "-",
			"designation": emp.designation or "-",
			"default_line": emp.line_order or "-",
			"lines": emp_lines
		})

	return {
		"month": m,
		"year": y,
		"month_name": calendar.month_name[m],
		"days": days_list,
		"employees": matrix,
		"total_count": total_count,
		"has_more": (start + len(matrix)) < total_count,
		"lines": all_lines
	}


@frappe.whitelist()
def get_calendar_roster(start_date, end_date, employee=None, department=None):
	"""
	Returns calendar events for Line schedule FullCalendar view.
	"""
	if not start_date or not end_date:
		today = date.today()
		start_date = today.strftime("%Y-%m-01")
		end_date = (today + timedelta(days=31)).strftime("%Y-%m-%d")

	emp_filters = {"status": "Active"}
	if department and department != "all":
		emp_filters["department"] = department
	if employee and employee != "all":
		if isinstance(employee, list):
			emp_filters["name"] = ["in", employee]
		elif isinstance(employee, str) and (employee.startswith("[") or "," in employee):
			try:
				parsed = json.loads(employee)
				if isinstance(parsed, list):
					emp_filters["name"] = ["in", parsed]
				else:
					emp_filters["name"] = employee
			except Exception:
				emp_filters["name"] = ["in", [x.strip() for x in employee.split(",") if x.strip()]]
		else:
			emp_filters["name"] = employee

	employees_data = frappe.db.get_all("Employee", filters=emp_filters, fields=["name", "employee_name", "line_order"])
	start_dt = getdate(start_date)
	end_dt = getdate(end_date)

	events = []
	curr = start_dt
	while curr <= end_dt:
		d_str = curr.strftime("%Y-%m-%d")
		for emp in employees_data:
			line_info = get_applicable_line(emp.name, d_str)
			if line_info and line_info.get("line_order"):
				events.append({
					"id": f"{emp.name}_{d_str}",
					"title": f"{emp.employee_name} - {line_info['line_name']}",
					"employee": emp.name,
					"employee_name": emp.employee_name,
					"line_order": line_info["line_order"],
					"line_name": line_info["line_name"],
					"source": line_info.get("source"),
					"start": d_str,
					"end": d_str,
					"allDay": True,
					"roster_id": line_info.get("roster_id")
				})
		curr += timedelta(days=1)

	return events


# ----------------------------------------------------------------------
# 5. LINE ROTATION GENERATION & AUDIT HISTORY
# ----------------------------------------------------------------------

@frappe.whitelist()
def generate_rotation_assignments(rotation_name=None, employees=None, start_date=None, end_date=None, exclude_weekly_offs=1, exclude_holidays=1, override_conflicts=0, data=None):
	"""
	Generates concrete Employee Line Roster entries from a Line Rotation template,
	for the selected employees and specified date range.
	"""
	if data:
		if isinstance(data, str):
			data = json.loads(data)
		rotation_name = data.get("rotation_name", rotation_name)
		employees = data.get("employees", employees)
		start_date = data.get("start_date", start_date)
		end_date = data.get("end_date", end_date)
		exclude_weekly_offs = data.get("exclude_weekly_offs", exclude_weekly_offs)
		exclude_holidays = data.get("exclude_holidays", exclude_holidays)
		override_conflicts = data.get("override_conflicts", override_conflicts)

	if isinstance(employees, str):
		try:
			employees = json.loads(employees)
		except Exception:
			employees = [e.strip() for e in employees.split(",") if e.strip()]

	if not rotation_name:
		frappe.throw("Line Rotation is required.")

	if not frappe.db.exists("Line Rotation", rotation_name):
		frappe.throw(f"Line Rotation '{rotation_name}' not found.")

	rot = frappe.get_doc("Line Rotation", rotation_name)
	if not rot.sequences:
		frappe.throw("Line Rotation has no line sequences configured.")

	target_employees = employees or []
	if not target_employees and getattr(rot, "assignees", None):
		target_employees = [a.employee for a in rot.assignees if a.employee]
	if not target_employees and getattr(rot, "department", None):
		target_employees = frappe.db.get_all("Employee", filters={"department": rot.department, "status": "Active"}, pluck="name")

	if not target_employees:
		frappe.throw("Please select at least one employee to generate rosters for.")

	eff_start = getdate(start_date or getattr(rot, "start_date", None) or frappe.utils.nowdate())
	eff_end = getdate(end_date or getattr(rot, "end_date", None) or eff_start)
	if eff_end < eff_start:
		frappe.throw("End Date cannot be earlier than Start Date.")

	seq_count = len(rot.sequences)
	freq = (rot.frequency or "Weekly").lower()
	exclude_wo = cint(exclude_weekly_offs)
	exclude_h = cint(exclude_holidays)
	override = cint(override_conflicts)

	created = 0
	skipped = 0
	overridden = 0

	curr = eff_start
	while curr <= eff_end:
		d_str = curr.strftime("%Y-%m-%d")
		is_wo = curr.weekday() == 6
		is_h = is_holiday_for_date(curr)

		if exclude_wo and is_wo:
			curr += timedelta(days=1)
			continue
		if exclude_h and is_h:
			curr += timedelta(days=1)
			continue

		days_diff = (curr - eff_start).days
		if freq == "daily":
			step_idx = days_diff % seq_count
		elif freq == "bi-weekly":
			step_idx = (days_diff // 14) % seq_count
		elif freq == "monthly":
			months_diff = (curr.year - eff_start.year) * 12 + (curr.month - eff_start.month)
			step_idx = months_diff % seq_count
		else:
			step_idx = (days_diff // 7) % seq_count

		selected_line = rot.sequences[step_idx].line_order

		for emp_id in target_employees:
			conflicts = check_roster_conflict(emp_id, d_str, d_str)
			if conflicts:
				if override:
					for c in conflicts:
						frappe.db.set_value("Employee Line Roster", c.name, {
							"status": "Cancelled",
							"reason": f"Overridden by Rotation '{rot.rotation_name}' generation for {selected_line}"
						})
						record_roster_history(
							roster_id=c.name,
							employee=emp_id,
							employee_name=None,
							effective_from=c.effective_from,
							effective_to=c.effective_to,
							previous_line=c.line_order,
							new_line=selected_line,
							changed_by=frappe.session.user,
							reason=f"Overridden by Rotation: {rot.rotation_name}",
							source="ROTATION"
						)
						overridden += 1
					doc = frappe.new_doc("Employee Line Roster")
					doc.employee = emp_id
					doc.line_order = selected_line
					doc.effective_from = d_str
					doc.effective_to = d_str
					doc.assignment_type = "Rotation"
					doc.reason = f"Generated from Rotation: {rot.rotation_name}"
					doc.status = "Active"
					doc.insert(ignore_permissions=True)
					created += 1
				else:
					skipped += 1
			else:
				doc = frappe.new_doc("Employee Line Roster")
				doc.employee = emp_id
				doc.line_order = selected_line
				doc.effective_from = d_str
				doc.effective_to = d_str
				doc.assignment_type = "Rotation"
				doc.reason = f"Generated from Rotation: {rot.rotation_name}"
				doc.status = "Active"
				doc.insert(ignore_permissions=True)
				created += 1

		curr += timedelta(days=1)

	frappe.db.commit()
	msg = f"Generated {created} line roster entries for {len(target_employees)} employees."
	if skipped > 0:
		msg += f" {skipped} dates skipped due to existing active assignments."
	if overridden > 0:
		msg += f" {overridden} conflicting assignments overridden."

	return {
		"success": True,
		"created_records": created,
		"skipped_records": skipped,
		"overridden_records": overridden,
		"rotation_name": rotation_name,
		"message": msg
	}


@frappe.whitelist()
def get_roster_history(roster_id=None, employee=None):
	"""Returns audit history records for line roster assignments."""
	filters = {}
	if roster_id:
		filters["roster_id"] = roster_id
	if employee:
		filters["employee"] = employee

	return frappe.db.get_all(
		"Employee Line Roster History",
		filters=filters,
		fields=["name", "roster_id", "employee", "employee_name", "effective_from", "effective_to", "previous_line", "new_line", "source", "changed_by", "changed_at", "reason", "creation"],
		order_by="changed_at desc, creation desc",
		limit=100
	)


# ----------------------------------------------------------------------
# 6. LINE ROTATION CRUD APIS
# ----------------------------------------------------------------------

@frappe.whitelist()
def get_line_rotation_doc(name):
	"""Returns complete Line Rotation doc with sequences and assignees."""
	if not frappe.db.exists("Line Rotation", name):
		frappe.throw(f"Line Rotation '{name}' not found.")
	doc = frappe.get_doc("Line Rotation", name)
	return doc.as_dict()


@frappe.whitelist()
def create_line_rotation_doc(doc):
	"""Creates a new Line Rotation with sequences and assignees child tables."""
	if isinstance(doc, str):
		doc = json.loads(doc)

	rot_name = (doc.get("rotation_name") or "").strip()
	if not rot_name:
		frappe.throw("Rotation Name is required.")

	if frappe.db.exists("Line Rotation", rot_name):
		frappe.throw(f"Line Rotation '{rot_name}' already exists.")

	rotation = frappe.new_doc("Line Rotation")
	rotation.rotation_name = rot_name
	rotation.frequency = doc.get("frequency", "Weekly")
	rotation.status = doc.get("status", "Active")
	rotation.department = doc.get("department") or None
	rotation.start_date = doc.get("start_date")
	rotation.end_date = doc.get("end_date")
	rotation.exclude_holidays = 1 if doc.get("exclude_holidays") else 0
	rotation.exclude_weekly_offs = 1 if doc.get("exclude_weekly_offs") else 0
	rotation.description = doc.get("description") or ""

	for idx, s in enumerate(doc.get("sequences", [])):
		rotation.append("sequences", {
			"step_number": s.get("step_number") or (idx + 1),
			"line_order": s.get("line_order") or s.get("line"),
			"line_name": s.get("line_name") or s.get("line_order") or s.get("line"),
		})

	for a in doc.get("assignees", []):
		rotation.append("assignees", {
			"employee": a.get("employee"),
			"employee_name": a.get("employee_name"),
			"department": a.get("department"),
			"designation": a.get("designation"),
		})

	rotation.insert(ignore_permissions=True)
	frappe.db.commit()
	return rotation.as_dict()


@frappe.whitelist()
def update_line_rotation_doc(name, doc):
	"""Updates existing Line Rotation and replaces child tables cleanly."""
	if isinstance(doc, str):
		doc = json.loads(doc)

	if not frappe.db.exists("Line Rotation", name):
		frappe.throw(f"Line Rotation '{name}' not found.")

	target_name = name
	new_rot_name = (doc.get("rotation_name") or "").strip()

	# Handle rename if name changed
	if new_rot_name and new_rot_name != name:
		if frappe.db.exists("Line Rotation", new_rot_name):
			frappe.throw(f"Line Rotation '{new_rot_name}' already exists.")
		frappe.rename_doc("Line Rotation", name, new_rot_name, ignore_permissions=True)
		target_name = new_rot_name

	rotation = frappe.get_doc("Line Rotation", target_name)
	rotation.rotation_name = new_rot_name or rotation.rotation_name
	rotation.frequency = doc.get("frequency", rotation.frequency)
	rotation.status = doc.get("status", rotation.status)
	rotation.department = doc.get("department") or None
	rotation.start_date = doc.get("start_date", rotation.start_date)
	rotation.end_date = doc.get("end_date", rotation.end_date)
	rotation.exclude_holidays = 1 if doc.get("exclude_holidays") else 0
	rotation.exclude_weekly_offs = 1 if doc.get("exclude_weekly_offs") else 0
	rotation.description = doc.get("description") or ""

	# Replace sequences child table
	rotation.set("sequences", [])
	for idx, s in enumerate(doc.get("sequences", [])):
		rotation.append("sequences", {
			"step_number": s.get("step_number") or (idx + 1),
			"line_order": s.get("line_order") or s.get("line"),
			"line_name": s.get("line_name") or s.get("line_order") or s.get("line"),
		})

	# Replace assignees child table
	rotation.set("assignees", [])
	for a in doc.get("assignees", []):
		rotation.append("assignees", {
			"employee": a.get("employee"),
			"employee_name": a.get("employee_name"),
			"department": a.get("department"),
			"designation": a.get("designation"),
		})

	rotation.save(ignore_permissions=True)
	frappe.db.commit()
	return rotation.as_dict()


@frappe.whitelist()
def delete_line_rotation_doc(name):
	"""Deletes Line Rotation doc."""
	if not frappe.db.exists("Line Rotation", name):
		frappe.throw(f"Line Rotation '{name}' not found.")
	frappe.delete_doc("Line Rotation", name, ignore_permissions=True)
	frappe.db.commit()
	return {"success": True}


# ----------------------------------------------------------------------
# 7. HIGH-VOLUME EMPLOYEE SELECTOR
# ----------------------------------------------------------------------

@frappe.whitelist()
def get_filtered_employees(department=None, shift=None, line_order=None, search=None, page=1, page_size=25, status="Active"):
	"""
	Optimized paginated employee query supporting multi-dimensional filters
	for Department, Shift, and Line Order in enterprise HRMS.
	"""
	page = cint(page) or 1
	page_size = cint(page_size) or 25
	start = (page - 1) * page_size

	conditions = []
	values = {}

	if status and status != "all":
		conditions.append("status = %(status)s")
		values["status"] = status
	else:
		conditions.append("status NOT IN ('Left', 'Inactive')")

	if department and department != "all":
		conditions.append("department = %(department)s")
		values["department"] = department

	if shift and shift != "all":
		conditions.append("shift = %(shift)s")
		values["shift"] = shift

	if line_order and line_order != "all":
		conditions.append("line_order = %(line_order)s")
		values["line_order"] = line_order

	if search:
		conditions.append("(name LIKE %(search)s OR employee_name LIKE %(search)s OR designation LIKE %(search)s)")
		values["search"] = f"%{search}%"

	where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

	# Total count
	total_res = frappe.db.sql(f"SELECT COUNT(name) as total FROM `tabEmployee` {where_clause}", values, as_dict=1)
	total = total_res[0].total if total_res else 0

	# Paginated data
	values["limit"] = page_size
	values["offset"] = start
	employees = frappe.db.sql(f"""
		SELECT name, employee_name, department, shift, line_order, designation, status
		FROM `tabEmployee`
		{where_clause}
		ORDER BY employee_name ASC, name ASC
		LIMIT %(limit)s OFFSET %(offset)s
	""", values, as_dict=1)

	return {
		"employees": employees,
		"total": total,
		"page": page,
		"page_size": page_size
	}


@frappe.whitelist()
def get_filtered_employee_ids(department=None, shift=None, line_order=None, search=None, status="Active"):
	"""
	Returns a lightweight list of employee IDs matching the active filter criteria.
	"""
	conditions = []
	values = {}

	if status and status != "all":
		conditions.append("status = %(status)s")
		values["status"] = status
	else:
		conditions.append("status NOT IN ('Left', 'Inactive')")

	if department and department != "all":
		conditions.append("department = %(department)s")
		values["department"] = department

	if shift and shift != "all":
		conditions.append("shift = %(shift)s")
		values["shift"] = shift

	if line_order and line_order != "all":
		conditions.append("line_order = %(line_order)s")
		values["line_order"] = line_order

	if search:
		conditions.append("(name LIKE %(search)s OR employee_name LIKE %(search)s OR designation LIKE %(search)s)")
		values["search"] = f"%{search}%"

	where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

	ids = frappe.db.sql(f"SELECT name FROM `tabEmployee` {where_clause} ORDER BY employee_name ASC", values, pluck="name")
	return ids
