# Copyright (c) 2026, Innoblitz and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import now_datetime, get_datetime, get_time, getdate, add_days
from datetime import datetime


def trigger_evaluation_automation(employee, event_type, reference_doctype=None, reference_name=None, remarks=None):
    """
    Finds enabled automation rules for an event and creates evaluations.
    Called from event handlers like handle_attendance_automation or handle_task_automation.
    """
    rules = frappe.get_all("Evaluation Automation Rule", filters={
        "event_type": event_type,
        "enabled": 1
    }, fields=["name", "trait", "evaluation_point", "auto_submit", "how_to_improve"])

    for rule in rules:
        _create_automated_evaluation(employee, rule, event_type, reference_doctype, reference_name, remarks)


def _create_automated_evaluation(employee, rule, event_type, reference_doctype, reference_name, remarks, evaluation_date=None):
    """
    Creates an Employee Evaluation record based on a rule.
    Prevents duplicate evaluations for the same reference document.
    """
    ref_tag = f"Reference: {reference_doctype}/{reference_name}" if reference_doctype and reference_name else ""

    # Prevent duplicates for the same reference + trait + point
    if ref_tag:
        existing = frappe.db.exists("Employee Evaluation", {
            "employee": employee,
            "trait": rule["trait"],
            "evaluation_type": rule["evaluation_point"],
            "remarks": ["like", f"%Auto: {rule['name']}%{ref_tag}%"]
        })
        if existing:
            frappe.log_error(
                f"Skipping duplicate evaluation for {employee} [{event_type}] on {reference_name}",
                "Evaluation Automation - Duplicate Skip"
            )
            return

    full_remarks = " | ".join(filter(None, [remarks, f"Auto: {rule['name']}", ref_tag]))

    try:
        evaluation = frappe.get_doc({
            "doctype": "Employee Evaluation",
            "employee": employee,
            "trait": rule["trait"],
            "evaluation_type": rule["evaluation_point"],
            "evaluation_date": evaluation_date or now_datetime().date(),
            "remarks": full_remarks,
            "how_to_improve": rule.get("how_to_improve"),
            "auto_submit": rule.get("auto_submit", 0),
            "hr_user": "Administrator"
        })
        evaluation.insert(ignore_permissions=True)

    except Exception as e:
        frappe.log_error(
            f"Failed to create evaluation for {employee} [{event_type}]: {str(e)}",
            "Evaluation Automation - Error"
        )


# ─── Attendance Event Handler ────────────────────────────────────────────────

def handle_attendance_automation(doc, method=None):
    """
    Hook: Attendance on_update / after_insert
    Checks Late Login and Early Exit rules.
    """
    if not doc.employee:
        return

    _check_late_login(doc)
    _check_early_exit(doc)


def _check_late_login(doc):
    """
    Triggers 'Late Login' evaluation if in_time exceeds the threshold configured in the rule.
    """
    if not doc.in_time:
        return

    late_rules = frappe.get_all("Evaluation Automation Rule", filters={
        "event_type": "Late Login",
        "enabled": 1
    }, fields=["name", "trait", "evaluation_point", "auto_submit", "late_login_after", "how_to_improve"])

    for rule in late_rules:
        threshold = rule.get("late_login_after")
        if not threshold:
            continue

        try:
            threshold_time = get_time(threshold)
            actual_time = get_time(str(doc.in_time))

            if actual_time > threshold_time:
                _create_automated_evaluation(
                    employee=doc.employee,
                    rule=rule,
                    event_type="Late Login",
                    reference_doctype="Attendance",
                    reference_name=doc.name,
                    remarks=f"Login at {doc.in_time}, threshold {threshold}",
                    evaluation_date=doc.attendance_date
                )
        except Exception as e:
            frappe.log_error(
                f"Late Login check error for {doc.employee} on {doc.name}: {str(e)}",
                "Evaluation Automation - Late Login Error"
            )


def _check_early_exit(doc):
    """
    Triggers 'Early Exit' evaluation if out_time is before the threshold configured in the rule.
    """
    if not doc.out_time:
        return

    early_rules = frappe.get_all("Evaluation Automation Rule", filters={
        "event_type": "Early Exit",
        "enabled": 1
    }, fields=["name", "trait", "evaluation_point", "auto_submit", "early_exit_before", "how_to_improve"])

    for rule in early_rules:
        threshold = rule.get("early_exit_before")
        if not threshold:
            continue

        try:
            threshold_time = get_time(threshold)
            actual_time = get_time(str(doc.out_time))

            if actual_time < threshold_time:
                _create_automated_evaluation(
                    employee=doc.employee,
                    rule=rule,
                    event_type="Early Exit",
                    reference_doctype="Attendance",
                    reference_name=doc.name,
                    remarks=f"Exit at {doc.out_time}, threshold {threshold}",
                    evaluation_date=doc.attendance_date
                )
        except Exception as e:
            frappe.log_error(
                f"Early Exit check error for {doc.employee} on {doc.name}: {str(e)}",
                "Evaluation Automation - Early Exit Error"
            )



def _hhmm_to_float(hhmm):
    if not hhmm:
        return 0.0
    try:
        parts = hhmm.split(':')
        if len(parts) != 2:
            return 0.0
        h, m = map(int, parts)
        return h + (m / 60.0)
    except (ValueError, TypeError):
        return 0.0


# ─── Task Manager Event Handler ───────────────────────────────────────────────

def handle_task_automation(doc, method=None):
    """
    Hook: Task Manager on_update
    Triggers 'Task Delayed' when a task is Completed after its due_date
    or if actual hours worked exceed the estimated hours.
    Triggers 'Milestone Achieved' when completed on time / within estimate.
    """
    if doc.status != "Completed" or not doc.closed_on:
        return

    # Only run when status transitions to Completed
    before = doc.get_doc_before_save()
    if before and before.status == "Completed":
        return

    try:
        closed_date = get_datetime(doc.closed_on).date()
        due_date = doc.due_date

        # Get all assignees from the child table
        assignees = frappe.get_all(
            "Task Manager Assignee",
            filters={"parent": doc.name},
            fields=["employee"]
        )

        if not assignees:
            return

        # Calculate actual hours from history Closed events
        actual_hours = 0.0
        for h in doc.history:
            if h.event == "Closed" and h.hours_spent:
                actual_hours = _hhmm_to_float(h.hours_spent)

        estimated_hours = doc.estimated_time or 0.0

        is_delayed = False
        if due_date and closed_date > due_date:
            is_delayed = True
        elif estimated_hours > 0 and actual_hours > estimated_hours:
            is_delayed = True

        event_type = "Task Delayed" if is_delayed else "Milestone Achieved"

        if due_date and closed_date > due_date and (estimated_hours > 0 and actual_hours > estimated_hours):
            remarks = f"Task '{doc.title}' closed on {closed_date} (due {due_date}) and actual hours {actual_hours} > estimated {estimated_hours}"
        elif due_date and closed_date > due_date:
            remarks = f"Task '{doc.title}' closed on {closed_date}, due {due_date}"
        elif estimated_hours > 0 and actual_hours > estimated_hours:
            remarks = f"Task '{doc.title}' closed on {closed_date}, actual hours {actual_hours} > estimated {estimated_hours}"
        else:
            remarks = f"Task '{doc.title}' closed on {closed_date}, due {due_date}"

        for row in assignees:
            if not row.employee:
                continue
            trigger_evaluation_automation(
                employee=row.employee,
                event_type=event_type,
                reference_doctype="Task Manager",
                reference_name=doc.name,
                remarks=remarks
            )

    except Exception as e:
        frappe.log_error(
            f"Task automation error for {doc.name}: {str(e)}",
            "Evaluation Automation - Task Error"
        )



# ─── Daily Log Event Handler ────────────────────────────────────────────────

def handle_daily_log_automation(doc, method=None):
    """
    Hook: Employee Session after_insert
    Triggers 'Daily Log Submission' evaluations based on thresholds (Late, Early, Long Break).
    If no threshold is set, triggers for every submission.
    """
    if not doc.employee:
        return

    rules = frappe.get_all("Evaluation Automation Rule", filters={
        "event_type": "Daily Log Submission",
        "enabled": 1
    }, fields=["name", "trait", "evaluation_point", "auto_submit", "late_login_after", "early_exit_before", "break_duration_after", "how_to_improve"])

    for rule in rules:
        should_trigger = True
        conditions_met = []

        # 1. Late Login Check (Time part of login_time)
        if rule.get("late_login_after") and doc.login_time:
            threshold_time = get_time(rule["late_login_after"])
            actual_time = get_time(doc.login_time)
            if actual_time > threshold_time:
                conditions_met.append(f"Late Login ({actual_time} > {threshold_time})")
            else:
                should_trigger = False

        # 2. Early Exit Check (Time part of logout_time)
        if should_trigger and rule.get("early_exit_before") and doc.logout_time:
            threshold_time = get_time(rule["early_exit_before"])
            actual_time = get_time(doc.logout_time)
            if actual_time < threshold_time:
                conditions_met.append(f"Early Exit ({actual_time} < {threshold_time})")
            else:
                should_trigger = False

        # 3. Long Break Check
        if should_trigger and rule.get("break_duration_after"):
            total_break = doc.total_break_hours or 0
            if total_break > rule["break_duration_after"]:
                conditions_met.append(f"Long Break ({total_break}h > {rule['break_duration_after']}h)")
            else:
                should_trigger = False

        if should_trigger:
            remarks = " | ".join(conditions_met) if conditions_met else "Regular Submission"
            _create_automated_evaluation(
                employee=doc.employee,
                rule=rule,
                event_type="Daily Log Submission",
                reference_doctype="Employee Session",
                reference_name=doc.name,
                remarks=remarks,
                evaluation_date=doc.login_date
            )


# ─── Leave Application Event Handler ──────────────────────────────────────────

def handle_leave_automation(doc, method=None):
    """
    Hook: Leave Application on_submit
    Checks if leave falls on a 'Specific Day' configured in rules.
    """
    if not doc.employee:
        return

    # Trigger for Specific Day/Date Leave
    rules = frappe.get_all("Evaluation Automation Rule", filters={
        "event_type": ["in", ["Specific Day Leave", "Specific Date Leave"]],
        "enabled": 1
    }, fields=["name", "trait", "evaluation_point", "auto_submit", "specific_day", "specific_date", "event_type", "how_to_improve"])

    if not rules:
        return

    try:
        start = getdate(doc.from_date)
        end = getdate(doc.to_date)
        
        # Check each day of the leave period
        current = start
        while current <= end:
            day_name = current.strftime("%A")
            for rule in rules:
                is_match = False
                remarks = ""

                if rule.event_type == "Specific Day Leave" and rule.specific_day == day_name:
                    is_match = True
                    remarks = f"Leave on {day_name} ({current.strftime('%Y-%m-%d')})"
                elif rule.event_type == "Specific Date Leave" and rule.specific_date and getdate(rule.specific_date) == current:
                    is_match = True
                    remarks = f"Leave on specific date: {current.strftime('%Y-%m-%d')}"

                if is_match:
                    _create_automated_evaluation(
                        employee=doc.employee,
                        rule=rule,
                        event_type=rule.event_type,
                        reference_doctype="Leave Application",
                        reference_name=doc.name,
                        remarks=remarks
                    )
            current = add_days(current, 1)

    except Exception as e:
        frappe.log_error(
            f"Leave automation error for {doc.name}: {str(e)}",
            "Evaluation Automation - Leave Error"
        )
