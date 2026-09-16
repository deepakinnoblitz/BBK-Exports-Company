# Copyright (c) 2026, Innoblitz and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_first_day, get_last_day, add_days, getdate, flt
import calendar

class EmployeeMonthlyAward(Document):
	def validate(self):
		# Mutual Exclusivity: if manual is checked, uncheck auto
		if self.manually_selected:
			self.is_auto_generated = 0
			
			# Ensure only one manual selection per month
			duplicate = frappe.db.exists("Employee Monthly Award", {
				"month": self.month,
				"manually_selected": 1,
				"name": ["!=", self.name]
			})
			if duplicate:
				other_emp = frappe.db.get_value("Employee Monthly Award", duplicate, "employee")
				from frappe.utils import format_date
				formatted_month = format_date(self.month, "MMMM YYYY")
				frappe.throw(f"Another employee ({other_emp}) is already manually selected for {formatted_month}. Please deselect them first.")
		elif self.is_auto_generated:
			self.manually_selected = 0


@frappe.whitelist()
def calculate_monthly_awards(month=None):

	"""
	Calculates awards for the given month. Default is previous month.
	"""
	if not month:
		# Default to previous month
		today = getdate()
		first_day_this_month = get_first_day(today)
		last_day_prev_month = add_days(first_day_this_month, -1)
		month = get_first_day(last_day_prev_month)
	else:
		month = getdate(month)

	# Check if awards already generated for this month
	first_day = get_first_day(month)
	existing_award = frappe.db.exists("Employee Monthly Award", {
		"month": first_day,
	})

	if existing_award:
		return "Already Generated"

	settings = frappe.get_doc("Employee Award Settings")
	
	employees = frappe.get_all("Employee", filters={"status": "Active"}, fields=["name", "evaluation_score"])
	
	awards = []
	
	# 2. Calculate Working Days (Exclude Sun, 2/4 Sat, and Holidays)
	from calendar import monthrange
	first_day = get_first_day(month)
	last_day = get_last_day(month)
	num_days = monthrange(month.year, month.month)[1]
	
	# Fetch specific holidays for this month
	holiday_list = frappe.get_all("Holiday List",
		filters={"year": str(month.year), "month_year": str(month.month)},
		fields=["name"]
	)
	holiday_dates = []
	if holiday_list:
		holiday_doc = frappe.get_doc("Holiday List", holiday_list[0].name)
		holiday_dates = [getdate(h.holiday_date) for h in holiday_doc.holidays if not h.is_working_day]

	working_days = 0
	saturday_count = 0
	for day in range(1, num_days + 1):
		d = getdate(f"{month.year}-{month.month:02d}-{day:02d}")
		weekday = d.weekday()  # Monday=0, Sunday=6
		
		is_holiday = False
		if weekday == 6: # Sunday
			is_holiday = True
		elif weekday == 5: # Saturday
			saturday_count += 1
			if saturday_count in [2, 4]:
				is_holiday = True
		
		# Check if this date is in the specific holiday list
		if d in holiday_dates:
			is_holiday = True
			
		if not is_holiday:
			working_days += 1

	for emp in employees:
		try:
			# 1. Attendance
			att_score, att_log = calculate_attendance_score(emp.name, first_day, last_day, working_days, settings)
			
			# 2. Personality
			pers_score = (flt(emp.evaluation_score) / 100.0) * flt(settings.personality_weight)
			pers_log = f"Evaluation: {emp.evaluation_score}% of {settings.personality_weight} pts = {pers_score:.2f}"
			
			# 3. Login Time
			login_score, login_log = calculate_login_score(emp.name, first_day, last_day, working_days, settings)
			
			# 3b. Overtime
			ot_score, ot_log = calculate_overtime_score(emp.name, first_day, last_day, working_days, settings)
			
			# 4. Leave Penalty
			leave_score, leave_log = calculate_leave_penalty(emp.name, first_day, last_day, settings)
			
			total_score = att_score + pers_score + login_score + ot_score + leave_score
			
			# Detailed Calculation Log
			full_log = (
				"--- Score Breakdown ---\n"
				f"1. {att_log}\n"
				f"2. {pers_log}\n"
				f"3. {login_log}\n"
				f"4. {ot_log}\n"
				f"5. {leave_log}\n"
				f"Total Score: {total_score:.3f}"
			)
			
			# Check if record already exists for this month/employee
			existing = frappe.db.get_value("Employee Monthly Award", {"employee": emp.name, "month": first_day}, "name")
			
			if existing:
				award = frappe.get_doc("Employee Monthly Award", existing)
				if award.manually_selected:
					continue # Skip manual entries
			else:
				award = frappe.new_doc("Employee Monthly Award")
				award.employee = emp.name
				award.month = first_day
				award.is_auto_generated = 1

			award.attendance_score = att_score
			award.personality_score = pers_score
			award.login_score = login_score
			award.overtime_score = ot_score
			award.leave_penalty = leave_score
			award.total_score = total_score
			award.calculation_log = full_log
			
			if settings.auto_publish:
				award.published = 1
				
			award.save(ignore_permissions=True)
			awards.append(award)
			
		except Exception as e:
			frappe.log_error(f"Error calculating EOM for {emp.name}: {str(e)}", "EOM Calculation Error")
			continue

	# Rank awards (only for active employees, though they should be the only ones here)
	# Use total_score DESC then personality_score DESC as tie-breaker
	awards.sort(key=lambda x: (flt(x.total_score), flt(x.personality_score)), reverse=True)
	
	for i, award in enumerate(awards):
		award.rank = i + 1
		award.save(ignore_permissions=True)

	return len(awards)

@frappe.whitelist()
def get_latest_published_eom():
    from frappe.utils import get_first_day, get_last_day, add_months, nowdate

    # ✅ Previous month range
    prev_month_date = add_months(nowdate(), -1)
    start_date = get_first_day(prev_month_date)
    end_date = get_last_day(prev_month_date)

    awards = frappe.get_list(
        "Employee Monthly Award",
        filters={
            "published": 1,
            "month": ["between", [start_date, end_date]]
        },
        fields=["*"],
        order_by="manually_selected desc, rank asc",
        limit=1,
        ignore_permissions=True
    )

    if not awards:
        return None

    award = awards[0]

    emp = frappe.db.get_value(
        "Employee",
        award.employee,
        ["employee_name", "designation", "profile_picture"],
        as_dict=1
    )

    if emp:
        award.update(emp)

    award.display_days = frappe.db.get_single_value("Employee Award Settings", "display_days") or 5
    return award

def calculate_attendance_score(employee, start_date, end_date, working_days, settings):
	attendances = frappe.get_all("Attendance", filters={
		"employee": employee,
		"attendance_date": ["between", [start_date, end_date]],
		"status": ["in", ["Present", "Half Day"]]
	}, fields=["status"], ignore_permissions=True)
	
	score_val = 0
	for att in attendances:
		if att.status == "Present":
			score_val += 1.0
		elif att.status == "Half Day":
			score_val += 0.5
			
	weight = flt(settings.attendance_weight)
	if working_days == 0: 
		return 0, f"Attendance: 0/{working_days} days = 0 pts"
	
	final_score = (score_val / working_days) * weight
	log = f"Attendance: {score_val}/{working_days} days = {final_score:.2f} pts"
	return final_score, log

def calculate_login_score(employee, start_date, end_date, working_days, settings):
	sessions = frappe.get_all("Employee Session", filters={
		"employee": employee,
		"login_date": ["between", [start_date, end_date]]
	}, fields=["total_work_hours"], ignore_permissions=True)
	
	total_hours = sum(flt(s.total_work_hours) for s in sessions)
	daily_std = flt(settings.daily_working_hours) or 8.0
	standard = daily_std * working_days
	
	weight = flt(settings.login_time_weight)
	if standard == 0:
		score = 0
		log = f"Login Time: {total_hours:.1f}/0.0 hrs = 0.00 pts"
	else:
		score = min(weight, (total_hours / standard) * weight)
		log = f"Login Time: {total_hours:.1f}/{standard:.1f} hrs = {score:.2f} pts"
	return score, log

def calculate_overtime_score(employee, start_date, end_date, working_days, settings):
	sessions = frappe.get_all("Employee Session", filters={
		"employee": employee,
		"login_date": ["between", [start_date, end_date]]
	}, fields=["total_work_hours"], ignore_permissions=True)
	
	total_hours = sum(flt(s.total_work_hours) for s in sessions)
	daily_std = flt(settings.daily_working_hours) or 8.0
	standard = daily_std * working_days
	
	overtime_hours = max(0, total_hours - standard)
	weight = flt(settings.overtime_weight)
	
	if standard == 0 or overtime_hours == 0:
		score = 0
		log = f"Overtime: {overtime_hours:.1f} hrs = 0.00 pts"
	else:
		# Overtime score is relative to how many extra hours worked vs standard
		score = min(weight, (overtime_hours / standard) * weight)
		log = f"Overtime: {overtime_hours:.1f} hrs (above {standard:.1f}) = {score:.2f} pts"
	return score, log

def calculate_leave_penalty(employee, start_date, end_date, settings):
	leaves = frappe.get_all("Leave Application", filters={
		"employee": employee,
		"workflow_state": "Approved",
		"from_date": ["<=", end_date],
		"to_date": [">=", start_date]
	}, fields=["from_date", "to_date", "total_days"], ignore_permissions=True)
	
	total_leave_days = sum(flt(leave.total_days) for leave in leaves)
		
	weight = flt(settings.leave_penalty_weight)
	penalty_per_day = flt(settings.leave_penalty_per_day) or 5.0
	
	score = max(0, weight - (total_leave_days * penalty_per_day))
	log = f"Leave Penalty: {total_leave_days} leaves (-{total_leave_days * penalty_per_day} pts) = {score:.2f} pts"
	return score, log
