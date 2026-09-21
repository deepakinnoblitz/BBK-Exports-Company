# -*- coding: utf-8 -*-
# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import json
import calendar
from datetime import datetime, date, timedelta
import frappe
from frappe.utils import getdate, now_datetime, cint, flt

# ----------------------------------------------------------------------
# 1. CENTRAL SHIFT RESOLVER
# ----------------------------------------------------------------------

@frappe.whitelist()
def get_applicable_shift(employee, attendance_date):
	"""
	Central resolver to determine an employee's applicable shift for a given date.
	Resolution Order:
	  1. Date-specific Employee Shift Roster assignment (Active)
	  2. Shift Rotation schedule assignment (Active)
	  3. Employee's Default Shift from Employee record
	"""
	if not employee or not attendance_date:
		return None

	target_date = getdate(attendance_date)
	date_str = target_date.strftime("%Y-%m-%d")

	# 1. Check Date-specific Employee Shift Roster
	roster = frappe.db.sql("""
		SELECT name, shift, shift_name, assignment_type, effective_from, effective_to
		FROM `tabEmployee Shift Roster`
		WHERE employee = %(employee)s
		  AND status = 'Active'
		  AND effective_from <= %(date_str)s
		  AND (effective_to IS NULL OR effective_to >= %(date_str)s)
		ORDER BY modified DESC
		LIMIT 1
	""", {"employee": employee, "date_str": date_str}, as_dict=1)

	if roster and roster[0].shift:
		r = roster[0]
		shift_details = get_shift_metadata(r.shift)
		return {
			"shift": r.shift,
			"shift_name": r.shift_name or (shift_details.get("shift_name") if shift_details else r.shift),
			"source": "ROSTER",
			"roster_id": r.name,
			"assignment_type": r.assignment_type,
			"details": shift_details
		}

	# 2. Check Active Shift Rotation
	rotations = frappe.db.sql("""
		SELECT r.name, r.rotation_name, r.frequency, r.start_date, r.end_date,
		       r.exclude_holidays, r.exclude_weekly_offs, r.department
		FROM `tabShift Rotation` r
		INNER JOIN `tabShift Rotation Assignee` a ON a.parent = r.name
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
				FROM `tabShift Rotation`
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
			SELECT step_number, shift, shift_name
			FROM `tabShift Rotation Sequence`
			WHERE parent = %(parent)s
			ORDER BY step_number ASC
		""", {"parent": rot.name}, as_dict=1)

		if not sequences:
			continue

		seq_count = len(sequences)
		start = getdate(rot.start_date)
		days_diff = (target_date - start).days

		if days_diff < 0:
			continue

		freq = (rot.frequency or "Weekly").lower()
		if freq == "daily":
			step_idx = days_diff % seq_count
		elif freq == "bi-weekly":
			step_idx = (days_diff // 14) % seq_count
		elif freq == "monthly":
			months_diff = (target_date.year - start.year) * 12 + (target_date.month - start.month)
			step_idx = months_diff % seq_count
		else:  # Weekly default
			step_idx = (days_diff // 7) % seq_count

		selected_seq = sequences[step_idx]
		shift_details = get_shift_metadata(selected_seq.shift)
		return {
			"shift": selected_seq.shift,
			"shift_name": selected_seq.shift_name or (shift_details.get("shift_name") if shift_details else selected_seq.shift),
			"source": "ROTATION",
			"rotation_name": rot.rotation_name,
			"step_number": selected_seq.step_number,
			"details": shift_details
		}

	# 3. Fallback: Employee Default Shift
	default_shift = frappe.db.get_value("Employee", employee, "shift")
	if default_shift:
		shift_details = get_shift_metadata(default_shift)
		return {
			"shift": default_shift,
			"shift_name": shift_details.get("shift_name") if shift_details else default_shift,
			"source": "DEFAULT",
			"details": shift_details
		}

	return None


def get_shift_metadata(shift_id):
	"""Fetches Shift doc fields for timing and break hours."""
	if not shift_id:
		return {}
	data = frappe.db.get_value(
		"Shift",
		shift_id,
		["shift_name", "start_time", "end_time", "lunch_hours", "break_hours", "allow_overtime", "overtime_hours", "min_overtime_minutes"],
		as_dict=1
	)
	return data or {}


def is_holiday_for_date(target_date):
	"""Check if the given date is listed in any company Holiday List."""
	date_str = target_date.strftime("%Y-%m-%d")
	return frappe.db.exists("Holidays", {"holiday_date": date_str})


def record_roster_history(roster_id, employee, employee_name, effective_from, effective_to, previous_shift, new_shift, changed_by, reason, source):
	"""Creates an audit log entry in Employee Shift Roster History."""
	try:
		hist = frappe.new_doc("Employee Shift Roster History")
		hist.roster_id = roster_id or ""
		hist.employee = employee
		hist.employee_name = employee_name or frappe.db.get_value("Employee", employee, "employee_name")
		hist.effective_from = effective_from
		hist.effective_to = effective_to or effective_from
		hist.previous_shift = previous_shift
		hist.new_shift = new_shift
		hist.changed_by = changed_by or frappe.session.user
		hist.changed_at = now_datetime()
		hist.reason = reason or "Shift assignment updated"
		hist.source = (source or "MANUAL").upper()
		hist.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(f"Failed to record shift roster history: {str(e)}", "Shift Roster History")


# ----------------------------------------------------------------------
# 2. CONFLICT CHECKING & CRUD APIS
# ----------------------------------------------------------------------

@frappe.whitelist()
def check_roster_conflict(employee, effective_from, effective_to=None, exclude_name=None):
	"""Returns any active overlapping roster assignments for the employee."""
	if not employee or not effective_from:
		return []

	eff_from = effective_from
	eff_to = effective_to or effective_from

	query = """
		SELECT name, shift, shift_name, effective_from, effective_to, assignment_type
		FROM `tabEmployee Shift Roster`
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
	"""Creates a new Employee Shift Roster assignment."""
	if isinstance(data, str):
		data = json.loads(data)

	employee = data.get("employee")
	shift = data.get("shift")
	effective_from = data.get("effective_from")
	effective_to = data.get("effective_to") or effective_from
	assignment_type = data.get("assignment_type", "Manual")
	reason = data.get("reason", "")
	status = data.get("status", "Active")

	if not employee or not shift or not effective_from:
		frappe.throw("Employee, Shift, and Effective From are required.")

	# If assignment type is Override, cancel conflicting active records first
	if assignment_type == "Override":
		conflicts = check_roster_conflict(employee, effective_from, effective_to)
		for c in conflicts:
			frappe.db.set_value("Employee Shift Roster", c.name, {
				"status": "Cancelled",
				"reason": f"Overridden by new assignment for {shift} ({effective_from} to {effective_to})"
			})
			record_roster_history(
				roster_id=c.name,
				employee=employee,
				employee_name=None,
				effective_from=c.effective_from,
				effective_to=c.effective_to,
				previous_shift=c.shift,
				new_shift=None,
				changed_by=frappe.session.user,
				reason="Overridden by new shift assignment",
				source="OVERRIDE"
			)

	doc = frappe.new_doc("Employee Shift Roster")
	doc.employee = employee
	doc.shift = shift
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
	"""Updates an existing Employee Shift Roster assignment."""
	if isinstance(data, str):
		data = json.loads(data)

	if not frappe.db.exists("Employee Shift Roster", name):
		frappe.throw(f"Employee Shift Roster record {name} not found.")

	doc = frappe.get_doc("Employee Shift Roster", name)
	prev_shift = doc.shift

	if "employee" in data:
		doc.employee = data["employee"]
	if "shift" in data:
		doc.shift = data["shift"]
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
	"""Cancels or permanently deletes a shift roster assignment."""
	if not frappe.db.exists("Employee Shift Roster", name):
		frappe.throw(f"Employee Shift Roster {name} not found.")

	doc = frappe.get_doc("Employee Shift Roster", name)

	if delete_permanently:
		record_roster_history(
			roster_id=doc.name,
			employee=doc.employee,
			employee_name=doc.employee_name,
			effective_from=doc.effective_from,
			effective_to=doc.effective_to,
			previous_shift=doc.shift,
			new_shift=None,
			changed_by=frappe.session.user,
			reason=reason or "Deleted permanently",
			source="MANUAL"
		)
		doc.delete()
	else:
		doc.status = "Cancelled"
		doc.reason = reason or "Cancelled by user"
		doc.save()
		record_roster_history(
			roster_id=doc.name,
			employee=doc.employee,
			employee_name=doc.employee_name,
			effective_from=doc.effective_from,
			effective_to=doc.effective_to,
			previous_shift=doc.shift,
			new_shift=None,
			changed_by=frappe.session.user,
			reason=reason or "Cancelled assignment",
			source="MANUAL"
		)

	frappe.db.commit()
	return {"success": True, "name": name}


# ----------------------------------------------------------------------
# 3. BULK ASSIGNMENT & PREVIEW
# ----------------------------------------------------------------------

@frappe.whitelist()
def preview_bulk_assign_shifts(employees, shift, effective_from, effective_to, exclude_weekly_offs=True, exclude_holidays=True):
	"""
	Simulates a bulk shift assignment and returns preview details and conflict warnings.
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
		emp = frappe.db.get_value("Employee", emp_id, ["name", "employee_name", "department", "designation", "shift"], as_dict=1)
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
			"current_default_shift": emp.shift,
			"new_shift": shift,
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
def bulk_assign_shifts(employees, shift, effective_from, effective_to, assignment_type="Bulk", reason="", exclude_weekly_offs=True, exclude_holidays=True, override_conflicts=False):
	"""
	Performs atomic bulk assignment of shifts to multiple employees.
	"""
	if isinstance(employees, str):
		employees = json.loads(employees)

	exclude_weekly_offs = cint(exclude_weekly_offs)
	exclude_holidays = cint(exclude_holidays)
	override_conflicts = cint(override_conflicts)

	start_dt = getdate(effective_from)
	end_dt = getdate(effective_to) if effective_to else start_dt

	if not employees or not shift or not effective_from:
		frappe.throw("Employees list, Shift, and Effective From date are required.")

	created_count = 0
	skipped_count = 0
	errors = []

	for emp_id in employees:
		try:
			conflicts = check_roster_conflict(emp_id, effective_from, effective_to)
			if conflicts:
				if override_conflicts:
					for c in conflicts:
						frappe.db.set_value("Employee Shift Roster", c.name, {
							"status": "Cancelled",
							"reason": f"Overridden by bulk assignment for {shift} ({effective_from} to {effective_to})"
						})
						record_roster_history(
							roster_id=c.name,
							employee=emp_id,
							employee_name=None,
							effective_from=c.effective_from,
							effective_to=c.effective_to,
							previous_shift=c.shift,
							new_shift=None,
							changed_by=frappe.session.user,
							reason="Overridden by bulk assignment",
							source="OVERRIDE"
						)
				else:
					skipped_count += 1
					errors.append(f"Employee {emp_id} skipped due to conflict.")
					continue

			doc = frappe.new_doc("Employee Shift Roster")
			doc.employee = emp_id
			doc.shift = shift
			doc.effective_from = effective_from
			doc.effective_to = effective_to
			doc.assignment_type = assignment_type or "Bulk"
			doc.reason = reason or "Bulk shift assignment"
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
def get_monthly_roster(month, year, department=None, employee=None):
	"""
	Returns workforce roster matrix: all employees as rows, month days as columns.
	Each cell contains the resolved shift, source, timing, and day attributes.
	"""
	m = cint(month)
	y = cint(year)
	if not m or not y:
		today = date.today()
		m = today.month
		y = today.year

	num_days = calendar.monthrange(y, m)[1]
	start_date = date(y, m, 1)
	end_date = date(y, m, num_days)

	start_str = start_date.strftime("%Y-%m-%d")
	end_str = end_date.strftime("%Y-%m-%d")

	# 1. Generate Days list for the month
	days_list = []
	for day_idx in range(1, num_days + 1):
		d = date(y, m, day_idx)
		d_str = d.strftime("%Y-%m-%d")
		is_wo = d.weekday() == 6
		is_h = is_holiday_for_date(d)
		h_name = ""
		if is_h:
			h_doc = frappe.db.get_value("Holidays", {"holiday_date": d_str}, "description")
			h_name = h_doc or "Holiday"

		days_list.append({
			"date": d_str,
			"day": day_idx,
			"day_name": d.strftime("%a"),
			"is_weekend": is_wo,
			"is_holiday": is_h,
			"holiday_name": h_name
		})

	# 2. Get Employees list
	emp_filters = {"status": "Active"}
	if department and department != "all":
		emp_filters["department"] = department
	if employee and employee != "all":
		if isinstance(employee, list):
			emp_filters["name"] = ["in", employee]
		elif isinstance(employee, str) and (employee.startswith("[") or "," in employee):
			try:
				import json
				parsed = json.loads(employee)
				if isinstance(parsed, list):
					emp_filters["name"] = ["in", parsed]
				else:
					emp_filters["name"] = employee
			except Exception:
				emp_filters["name"] = ["in", [x.strip() for x in employee.split(",") if x.strip()]]
		else:
			emp_filters["name"] = employee

	employees_data = frappe.db.get_all(
		"Employee",
		filters=emp_filters,
		fields=["name", "employee_name", "department", "designation", "shift"],
		order_by="employee_name asc",
		limit=200
	)

	# 3. Pre-fetch all active Shift Master records for quick code lookup
	all_shifts = frappe.db.get_all(
		"Shift",
		filters={"status": "Active"},
		fields=["name", "shift_name", "start_time", "end_time"]
	)
	shift_lookup = {s.name: s for s in all_shifts}

	# 4. Fetch all active roster assignments for the entire month
	# This avoids querying DB inside daily loops
	roster_records = frappe.db.sql(
		"""
		SELECT 
			name, employee, shift, shift_name, effective_from, effective_to, assignment_type, modified
		FROM `tabEmployee Shift Roster`
		WHERE status = 'Active'
		  AND (effective_from <= %s AND (effective_to >= %s OR effective_to IS NULL OR effective_to = ''))
		ORDER BY modified ASC
		""",
		(end_str, start_str),
		as_dict=True
	)

	# Group roster assignments by employee
	emp_rosters = {}
	for r in roster_records:
		emp_rosters.setdefault(r.employee, []).append(r)

	# 5. Build Employee Matrix
	matrix = []
	for emp in employees_data:
		e_id = emp.name
		r_list = emp_rosters.get(e_id, [])

		emp_shifts = {}
		for day_info in days_list:
			d_str = day_info["date"]
			d_obj = getdate(d_str)

			# A. Check Date-specific Roster
			assigned_roster = None
			for r in r_list:
				r_from = getdate(r.effective_from)
				r_to = getdate(r.effective_to) if r.effective_to else r_from
				if r_from <= d_obj <= r_to:
					assigned_roster = r
					# Continue loop to take latest modified if multiple

			if assigned_roster:
				s_name = assigned_roster.shift
				s_meta = shift_lookup.get(s_name, {})
				emp_shifts[d_str] = {
					"shift": s_name,
					"shift_name": assigned_roster.shift_name or s_meta.get("shift_name", s_name),
					"source": "ROSTER",
					"roster_id": assigned_roster.name,
					"assignment_type": assigned_roster.assignment_type,
					"start_time": str(s_meta.get("start_time") or ""),
					"end_time": str(s_meta.get("end_time") or ""),
					"is_weekly_off": day_info["is_weekend"],
					"is_holiday": day_info["is_holiday"]
				}
			else:
				# B. Central resolver for rotation / default
				resolved = get_applicable_shift(e_id, d_str)
				if resolved:
					s_name = resolved["shift"]
					s_meta = shift_lookup.get(s_name, {})
					emp_shifts[d_str] = {
						"shift": s_name,
						"shift_name": resolved.get("shift_name", s_name),
						"source": resolved.get("source", "DEFAULT"),
						"roster_id": resolved.get("roster_id"),
						"start_time": str(s_meta.get("start_time") or ""),
						"end_time": str(s_meta.get("end_time") or ""),
						"is_weekly_off": day_info["is_weekend"],
						"is_holiday": day_info["is_holiday"]
					}
				else:
					emp_shifts[d_str] = {
						"shift": None,
						"shift_name": "Unassigned",
						"source": "NONE",
						"is_weekly_off": day_info["is_weekend"],
						"is_holiday": day_info["is_holiday"]
					}

		matrix.append({
			"employee": emp.name,
			"employee_name": emp.employee_name,
			"department": emp.department or "-",
			"designation": emp.designation or "-",
			"default_shift": emp.shift or "-",
			"shifts": emp_shifts
		})

	return {
		"month": m,
		"year": y,
		"month_name": calendar.month_name[m],
		"days": days_list,
		"employees": matrix,
		"shifts": all_shifts
	}


@frappe.whitelist()
def get_calendar_roster(start_date, end_date, employee=None, department=None):
	"""
	Returns calendar events for FullCalendar view.
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
				import json
				parsed = json.loads(employee)
				if isinstance(parsed, list):
					emp_filters["name"] = ["in", parsed]
				else:
					emp_filters["name"] = employee
			except Exception:
				emp_filters["name"] = ["in", [x.strip() for x in employee.split(",") if x.strip()]]
		else:
			emp_filters["name"] = employee

	employees_data = frappe.db.get_all("Employee", filters=emp_filters, fields=["name", "employee_name", "shift"])
	start_dt = getdate(start_date)
	end_dt = getdate(end_date)

	events = []
	curr = start_dt
	while curr <= end_dt:
		d_str = curr.strftime("%Y-%m-%d")
		for emp in employees_data:
			shift_info = get_applicable_shift(emp.name, d_str)
			if shift_info and shift_info.get("shift"):
				timing_str = ""
				meta = shift_info.get("details") or {}
				st = meta.get("start_time")
				et = meta.get("end_time")
				if st and et:
					timing_str = f" ({str(st)[:5]} - {str(et)[:5]})"

				events.append({
					"id": f"{emp.name}_{d_str}",
					"title": f"{emp.employee_name} - {shift_info['shift_name']}{timing_str}",
					"employee": emp.name,
					"employee_name": emp.employee_name,
					"shift": shift_info["shift"],
					"shift_name": shift_info["shift_name"],
					"source": shift_info.get("source"),
					"start": d_str,
					"end": d_str,
					"allDay": True,
					"roster_id": shift_info.get("roster_id")
				})
		curr += timedelta(days=1)

	return events


# ----------------------------------------------------------------------
# 5. SHIFT ROTATION GENERATION & AUDIT HISTORY
# ----------------------------------------------------------------------

@frappe.whitelist()
def generate_rotation_assignments(rotation_name):
	"""
	Generates concrete Employee Shift Roster entries from a Shift Rotation doc.
	"""
	if not frappe.db.exists("Shift Rotation", rotation_name):
		frappe.throw(f"Shift Rotation {rotation_name} not found.")

	rot = frappe.get_doc("Shift Rotation", rotation_name)
	if not rot.sequences:
		frappe.throw("Shift Rotation has no shift sequences configured.")

	assignees = [a.employee for a in rot.assignees]
	if not assignees and rot.department:
		assignees = frappe.db.get_all("Employee", filters={"department": rot.department, "status": "Active"}, pluck="name")

	if not assignees:
		frappe.throw("No employees assigned to this Shift Rotation.")

	start_dt = getdate(rot.start_date)
	end_dt = getdate(rot.end_date)
	seq_count = len(rot.sequences)
	freq = (rot.frequency or "Weekly").lower()

	created = 0
	curr = start_dt
	while curr <= end_dt:
		d_str = curr.strftime("%Y-%m-%d")
		is_wo = curr.weekday() == 6
		is_h = is_holiday_for_date(curr)

		if rot.exclude_weekly_offs and is_wo:
			curr += timedelta(days=1)
			continue
		if rot.exclude_holidays and is_h:
			curr += timedelta(days=1)
			continue

		days_diff = (curr - start_dt).days
		if freq == "daily":
			step_idx = days_diff % seq_count
		elif freq == "bi-weekly":
			step_idx = (days_diff // 14) % seq_count
		elif freq == "monthly":
			months_diff = (curr.year - start_dt.year) * 12 + (curr.month - start_dt.month)
			step_idx = months_diff % seq_count
		else:
			step_idx = (days_diff // 7) % seq_count

		selected_shift = rot.sequences[step_idx].shift

		for emp_id in assignees:
			# Check if explicit override exists or create assignment
			conflicts = check_roster_conflict(emp_id, d_str, d_str)
			if not conflicts:
				doc = frappe.new_doc("Employee Shift Roster")
				doc.employee = emp_id
				doc.shift = selected_shift
				doc.effective_from = d_str
				doc.effective_to = d_str
				doc.assignment_type = "Rotation"
				doc.reason = f"Generated from Rotation: {rot.rotation_name}"
				doc.status = "Active"
				doc.insert(ignore_permissions=True)
				created += 1

		curr += timedelta(days=1)

	frappe.db.commit()
	return {"success": True, "created_records": created, "rotation_name": rotation_name}


@frappe.whitelist()
def get_roster_history(roster_id=None, employee=None):
	"""Returns audit history records for shift roster assignments."""
	filters = {}
	if roster_id:
		filters["roster_id"] = roster_id
	if employee:
		filters["employee"] = employee

	return frappe.db.get_all(
		"Employee Shift Roster History",
		filters=filters,
		fields=["name", "roster_id", "employee", "employee_name", "effective_from", "effective_to", "previous_shift", "new_shift", "source", "changed_by", "changed_at", "reason"],
		order_by="changed_at desc",
		limit=100
	)


# ----------------------------------------------------------------------
# 6. SHIFT ROTATION CRUD APIS
# ----------------------------------------------------------------------

@frappe.whitelist()
def get_shift_rotation_doc(name):
	"""Returns complete Shift Rotation doc with sequences and assignees."""
	if not frappe.db.exists("Shift Rotation", name):
		frappe.throw(f"Shift Rotation '{name}' not found.")
	doc = frappe.get_doc("Shift Rotation", name)
	return doc.as_dict()


@frappe.whitelist()
def create_shift_rotation_doc(doc):
	"""Creates a new Shift Rotation with sequences and assignees child tables."""
	if isinstance(doc, str):
		doc = json.loads(doc)

	rot_name = (doc.get("rotation_name") or "").strip()
	if not rot_name:
		frappe.throw("Rotation Name is required.")

	if frappe.db.exists("Shift Rotation", rot_name):
		frappe.throw(f"Shift Rotation '{rot_name}' already exists.")

	rotation = frappe.new_doc("Shift Rotation")
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
			"shift": s.get("shift"),
			"shift_name": s.get("shift_name") or s.get("shift"),
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
def update_shift_rotation_doc(name, doc):
	"""Updates existing Shift Rotation and replaces child tables cleanly."""
	if isinstance(doc, str):
		doc = json.loads(doc)

	if not frappe.db.exists("Shift Rotation", name):
		frappe.throw(f"Shift Rotation '{name}' not found.")

	target_name = name
	new_rot_name = (doc.get("rotation_name") or "").strip()

	# Handle rename if name changed
	if new_rot_name and new_rot_name != name:
		if frappe.db.exists("Shift Rotation", new_rot_name):
			frappe.throw(f"Shift Rotation '{new_rot_name}' already exists.")
		frappe.rename_doc("Shift Rotation", name, new_rot_name, ignore_permissions=True)
		target_name = new_rot_name

	rotation = frappe.get_doc("Shift Rotation", target_name)
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
			"shift": s.get("shift"),
			"shift_name": s.get("shift_name") or s.get("shift"),
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
def delete_shift_rotation_doc(name):
	"""Deletes Shift Rotation doc."""
	if not frappe.db.exists("Shift Rotation", name):
		frappe.throw(f"Shift Rotation '{name}' not found.")
	frappe.delete_doc("Shift Rotation", name, ignore_permissions=True)
	frappe.db.commit()
	return {"success": True}

