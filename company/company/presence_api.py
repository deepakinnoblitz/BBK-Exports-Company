import re
import time
import frappe
from frappe import _
from frappe.utils import now_datetime, time_diff_in_seconds, flt, today
from frappe.exceptions import TimestampMismatchError

DEFAULT_STATUS_MESSAGES = {
    "Busy": "In a meeting",
    "Do Not Disturb": "Do not disturb",
    "Break": "On a break",
    "Away": "Stepped away",
}

def format_duration_hms(seconds):
    """
    Format duration into 'X mins Y Sec' or 'X Sec'.
    """
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} Sec"
    
    mins = seconds // 60
    secs = seconds % 60
    
    if decimal_secs := seconds % 60:
         return f"{mins} mins {secs} Sec"
    return f"{mins} mins"

@frappe.whitelist()
def update_presence(status, employee=None, status_message=None, source="Manual", start_time=None):
    """
    Update employee presence and handle session/break logic.
    """
    if not employee:
        employee = frappe.db.get_value("Employee", {"user": frappe.session.user}, "name")
    
    if not employee:
        frappe.throw(_("Employee not found for current user"))

    now = now_datetime()
    
    # Parse start_time if provided as ISO string
    if start_time and isinstance(start_time, str):
        from frappe.utils import get_datetime, convert_utc_to_system_timezone
        parsed = get_datetime(start_time)
        # MySQL DATETIME uses local server time (no timezone).
        # The frontend sends UTC (ISO 8601 with Z), so we must convert UTC → local time
        # before stripping tzinfo. Using .replace(tzinfo=None) directly would keep the
        # UTC value, making it look earlier than all local-time interval rows.
        if parsed.tzinfo is not None:
            parsed = convert_utc_to_system_timezone(parsed).replace(tzinfo=None)
        start_time = parsed

    # Get or create current presence record
    if not frappe.db.exists("Employee Presence", employee):
        presence = frappe.get_doc({
            "doctype": "Employee Presence",
            "employee": employee,
            "status": "Offline",
            "last_updated": now
        })
        presence.insert(ignore_permissions=True)
    else:
        presence = frappe.get_doc("Employee Presence", employee)
    
    old_status = presence.status
    old_last_updated = presence.last_updated
    
    if old_status == status:
        return {"status": "No change"}

    # Handle Session Logic
    active_session = get_active_session(employee)
    
    # Resolution: For system-triggered offline transitions (cleanup), 
    # use the last confirmed activity time for the session closure.
    effective_now = now
    if status == "Offline" and source == "System":
        last_confirmed_time = frappe.db.get_value("Employee Presence", employee, "last_updated")
        if last_confirmed_time:
            effective_now = last_confirmed_time

    # Close session if going Offline
    if status == "Offline" and active_session:
        close_session(active_session, effective_now)
    else:
        # Update Presence status and timestamp
        presence.status = status
        presence.last_updated = now

        if not active_session:
            active_session = create_session(employee, now, status=status)
        else:
            active_session.last_seen = now

    # Handle Break logic
    if status == "Break":
        if active_session:
            actual_source = source if source != "Manual" else "Manual"
            
            # Use start_time for retroactive breaks
            break_start = start_time if (start_time and source in ("Idle", "Away")) else now
            create_break(active_session.name, break_start, source=actual_source, reason=status_message)
            
            # Retroactively close/trim intervals that are now covered by the break period.
            if break_start:
                rows_to_remove = []
                for interval in active_session.intervals:
                    overlaps = (not interval.to_time) or (interval.to_time > break_start)
                    if overlaps:
                        if interval.from_time < break_start:
                            # Truncate the interval to end at break_start
                            interval.to_time = break_start
                            interval.duration_seconds = time_diff_in_seconds(break_start, interval.from_time)
                        else:
                            # Interval started AFTER break_start → fully covered by break, delete it
                            rows_to_remove.append(interval)
                
                # Use Frappe's proper child-row removal
                for row in rows_to_remove:
                    active_session.remove(row)
    else:
        # If we are coming BACK from a break (Break or Away was the old logic)
        # We need to close the active break.
        # Resolve resumption message duration before closing break
        resumed_duration = 0
        if old_status in ("Break", "Away"):
            active_break_name = frappe.db.get_value("Employee Break", {"session": active_session.name if active_session else None, "break_end": ["is", "not set"]}, "name")
            if active_break_name:
                brk_start = frappe.db.get_value("Employee Break", active_break_name, "break_start")
                resumed_duration = time_diff_in_seconds(now, brk_start)
            elif active_session and active_session.intervals:
                # If no break record (Away status), use the start of the current interval
                resumed_duration = time_diff_in_seconds(now, active_session.intervals[-1].from_time)
            else:
                # Fallback to the previous last_updated
                resumed_duration = time_diff_in_seconds(now, old_last_updated)

            close_active_break(active_session.name if active_session else None, now)
            
            # Send resumption message if moving back to Available (Only for Automated transitions)
            if status == "Available" and source != "Manual":
                notify_auto_resume(employee, resumed_duration)

    # Resolve status message
    final_status_message = ""
    if status in ("Available", "Offline"):
        final_status_message = ""
    elif status_message is not None:
        final_status_message = status_message
    else:
        final_status_message = DEFAULT_STATUS_MESSAGES.get(status, "")

    # Update Presence status message and save with retry
    for i in range(3):
        try:
            # Re-fetch to ensure we have the latest timestamp before the final save
            presence = frappe.get_doc("Employee Presence", employee)
            if status == "Offline":
                presence.status = status
                presence.last_updated = now
            else:
                presence.status = status
                presence.last_updated = now
            
            presence.status_message = final_status_message
            presence.save(ignore_permissions=True)
            break
        except TimestampMismatchError:
            if i == 2: raise
            time.sleep(0.05)
    
    # Send automated Away message if triggered by inactivity
    if status == "Away" and source == "Idle":
        notify_auto_status_change(employee, "Away")
    
    # Publish real-time update for Chat UI
    user_id = frappe.db.get_value("Employee", employee, "user")
    if user_id:
        frappe.publish_realtime('presence_update', {
            "user_id": user_id,
            "status": status,
            "status_message": final_status_message,
            "last_active": now.isoformat()
        }, after_commit=True)

    # ── Interval Handling ──
    if active_session and status not in ("Offline", "Break"):
        last_interval = active_session.intervals[-1] if active_session.intervals else None
        
        if last_interval and not last_interval.to_time:
            # We have an open interval
            if old_status not in ("Offline", "Break"):
                # Normal transition between active statuses: split
                last_interval.to_time = now
                last_interval.duration_seconds = time_diff_in_seconds(now, last_interval.from_time)
                active_session.append("intervals", {
                    "from_time": now,
                    "status": status
                })
            else:
                # Resuming from a non-active status: just update the status of the open interval
                last_interval.status = status
        else:
            # No open interval (e.g. after retroactive cleanup or first login of session)
            active_session.append("intervals", {
                "from_time": now,
                "status": status
            })
            
    # Update live totals before saving
    if active_session:
        # Calculate Total Working Hours based on active segments only (excl. Offline, Break, Away)
        total_active_seconds = sum(flt(i.duration_seconds) for i in active_session.intervals if i.duration_seconds and i.status not in ("Offline", "Break", "Away"))
        active_session.total_work_hours = max(0, flt(total_active_seconds) / 3600.0)
        
        # Calculate Total Break Hours
        total_break_seconds = get_live_break_seconds(active_session)
        active_session.total_break_hours = flt(total_break_seconds) / 3600.0

    # Single save for the active session at the end with retry logic
    if active_session:
        for i in range(3):
            try:
                # If we're retrying, we need the latest session doc 
                # but we MUST preserve the changes we just made (intervals, etc.)
                # In most cases, a simple save(ignore_permissions) is enough 
                # if we reload properly or handle pings via db_set.
                active_session.save(ignore_permissions=True)
                break
            except TimestampMismatchError:
                if i == 2: raise
                time.sleep(0.05)
                # Re-fetch and re-apply basic fields, intervals are more complex 
                # but usually the conflict is just the 'modified' timestamp from a ping
                new_session = frappe.get_doc("Employee Session", active_session.name)
                # Transfer our local changes to the new session object
                new_session.last_seen = active_session.last_seen
                new_session.intervals = active_session.intervals
                new_session.status = active_session.status
                active_session = new_session

    frappe.db.commit()

    # Immediate check for reminders after status change
    try:
        from company.company.employee_remainder_api import check_and_enqueue_reminders
        check_and_enqueue_reminders()
    except Exception:
        pass

    return {"status": "success", "message": f"Status updated to {status}"}

@frappe.whitelist()
def check_today_timesheet(employee=None):
    """
    Check if the employee has a timesheet for today.
    """
    if not employee:
        employee = frappe.db.get_value("Employee", {"user": frappe.session.user}, "name")
    
    if not employee:
        return {"has_timesheet": False}

    has_timesheet = frappe.db.exists("Timesheet", {
        "employee": employee,
        "timesheet_date": frappe.utils.today()
    })

    return {"has_timesheet": bool(has_timesheet)}

@frappe.whitelist()
def ping_presence(employee=None):
    """
    Periodic ping to keep session alive.
    """
    if not employee:
        employee = frappe.db.get_value("Employee", {"user": frappe.session.user}, "name")
    
    if not employee:
        return {"status": "error", "message": "Employee not found"}

    now = now_datetime()
    
    # Update Presence last_updated
    frappe.db.set_value("Employee Presence", employee, "last_updated", now)
    
    # Update Active Session last_seen using db_set with update_modified=False to prevent conflicts with manual edits
    active_session = get_active_session(employee)
    if active_session:
        active_session.db_set("last_seen", now, update_modified=False)
        return {"status": "success", "session": active_session.name}
    
    return {"status": "no_active_session"}

@frappe.whitelist()
def get_presence(employee=None):
    """
    Get current presence and session info.
    """
    if not employee:
        employee = frappe.db.get_value("Employee", {"user": frappe.session.user}, "name")
    
    if not employee:
        return {"status": "error", "message": "Employee not found"}

    presence = frappe.db.get_value("Employee Presence", employee, ["status", "last_updated", "status_message"], as_dict=True)
    if not presence:
        presence = {"status": "Offline", "last_updated": None, "status_message": ""}
    
    active_session = get_active_session(employee)
    
    active_break = None
    total_active_seconds = 0
    if active_session:
        total_active_seconds = get_live_active_seconds(active_session)
        active_break = frappe.db.get_value("Employee Break", 
            {"session": active_session.name, "break_end": ["is", "not set"]}, 
            ["name", "break_start"], as_dict=True)

    return {
        "presence": presence,
        "session": {
            "name": active_session.name if active_session else None,
            "login_time": active_session.login_time if active_session else None,
            "total_active_seconds": total_active_seconds,
            "total_break_seconds": get_live_break_seconds(active_session) if active_session else 0
        },
        "break": active_break
    }

@frappe.whitelist()
def get_all_presences():
    """
    Get current presence status for all employees, mapped by user email.
    """
    data = frappe.db.sql("""
        SELECT 
            e.user as user_id,
            p.status,
            p.status_message,
            p.last_updated
        FROM `tabEmployee Presence` p
        JOIN `tabEmployee` e ON p.employee = e.name
    """, as_dict=True)
    
    return { d.user_id: d for d in data if d.user_id }

def get_live_active_seconds(session):
    if not session:
        return 0
    
    now = now_datetime()
    # 1. Sum up all completed intervals (excluding Offline, Break, Away)
    total_seconds = sum(flt(i.duration_seconds) for i in session.intervals if i.to_time and i.status not in ("Offline", "Break", "Away"))
    
    # 2. Add current interval if it's open (excluding Offline/Break)
    if session.intervals and not session.intervals[-1].to_time:
        last = session.intervals[-1]
        if last.status not in ("Offline", "Break", "Away"):
            total_seconds += time_diff_in_seconds(now, last.from_time)
    
    return total_seconds

def get_live_status_seconds(session, status):
    if not session:
        return 0
    
    now = now_datetime()
    # 1. Sum up all completed intervals with this status
    total_seconds = sum(flt(i.duration_seconds) for i in session.intervals if i.to_time and i.status == status)
    
    # 2. Add current interval if it matches status and is open
    if session.intervals and not session.intervals[-1].to_time:
        last = session.intervals[-1]
        if last.status == status:
            total_seconds += time_diff_in_seconds(now, last.from_time)
            
    return total_seconds

def get_live_break_seconds(session):
    if not session:
        return 0
    
    now = now_datetime()
    # 1. Sum up all completed breaks for this session
    breaks = frappe.get_all("Employee Break", 
        filters={"session": session.name}, 
        fields=["break_duration", "break_start", "break_end"])
    
    total_seconds = 0
    for b in breaks:
        if b.break_end:
            total_seconds += flt(b.break_duration) * 60.0
        else:
            # Current active break
            total_seconds += time_diff_in_seconds(now, b.break_start)
            
    return total_seconds

def update_session_break_hours(doc, method=None):
    if doc.session:
        # Define filters: only exclude the current record if we are deleting it
        filters = {"session": doc.session}
        if method == "on_trash":
            filters["name"] = ["!=", doc.name]
            
        # Re-calculate total from relevant breaks in DB
        breaks = frappe.get_all("Employee Break", 
            filters=filters, 
            fields=["break_duration", "break_start", "break_end"]
        )
        
        total_seconds = 0
        now = now_datetime()
        for b in breaks:
            if b.break_end:
                # Use break_duration if available, else calculate from start/end
                if b.break_duration:
                    total_seconds += flt(b.break_duration) * 60.0
                else:
                    total_seconds += time_diff_in_seconds(b.break_end, b.break_start)
            else:
                # Current active break
                total_seconds += time_diff_in_seconds(now, b.break_start)
        
        # Update modified=False to avoid conflicts with manual edits in progress
        frappe.db.set_value("Employee Session", doc.session, "total_break_hours", flt(total_seconds) / 3600.0, update_modified=False)

def get_active_session(employee):
    session_name = frappe.db.get_value("Employee Session", {"employee": employee, "status": "Active"}, "name")
    if session_name:
        return frappe.get_doc("Employee Session", session_name)
    return None

def create_session(employee, now, status=None):
    today_date = today()
    existing_session_name = frappe.db.get_value("Employee Session", {"employee": employee, "login_date": today_date}, "name")
    
    if existing_session_name:
        doc = frappe.get_doc("Employee Session", existing_session_name)
        doc.status = "Active"
        doc.logout_time = None
        doc.last_seen = now
    else:
        doc = frappe.get_doc({
            "doctype": "Employee Session",
            "employee": employee,
            "login_time": now,
            "login_date": today_date,
            "last_seen": now,
            "status": "Active",
            "intervals": []
        })
    
    if not status:
        # Get current status to set on the initial interval
        status = frappe.db.get_value("Employee Presence", employee, "status") or "Available"
    
    # Close any open Offline interval from a previous session on the same day
    if doc.intervals and not doc.intervals[-1].to_time and doc.intervals[-1].status == "Offline":
        doc.intervals[-1].to_time = now
        doc.intervals[-1].duration_seconds = time_diff_in_seconds(now, doc.intervals[-1].from_time)

    doc.append("intervals", {
        "from_time": now,
        "status": status
    })
    doc.save(ignore_permissions=True)
    
    # Publish session update
    user_id = frappe.db.get_value("Employee", employee, "user")
    if user_id:
        frappe.publish_realtime('session_update', {"user_id": user_id, "name": doc.name}, after_commit=True)
        
    return doc

def close_session(session, now):
    # Close any open breaks first
    close_active_break(session.name, now)
    
    session.logout_time = now
    session.status = "Inactive"
    
    # Update the last interval
    if session.intervals:
        last_interval = session.intervals[-1]
        if not last_interval.to_time:
            last_interval.to_time = now
            last_interval.duration_seconds = time_diff_in_seconds(now, last_interval.from_time)
            # Ensure status is set if it was missing (for old records)
            if not last_interval.status:
                last_interval.status = frappe.db.get_value("Employee Presence", session.employee, "status") or "Available"
        
    # Append Offline interval to track time until next login
    session.append("intervals", {
        "from_time": now,
        "status": "Offline"
    })
    
    # Calculate Total Working Hours based on active segments only (excl. Offline, Break, Away)
    total_active_seconds = sum(flt(i.duration_seconds) for i in session.intervals if i.status not in ("Offline", "Break", "Away"))
    
    session.total_work_hours = max(0, flt(total_active_seconds) / 3600.0)
    
    # Calculate Total Break Hours
    total_break_seconds = get_live_break_seconds(session)
    session.total_break_hours = flt(total_break_seconds) / 3600.0
    
    session.save(ignore_permissions=True)
    
    # Publish session update
    user_id = frappe.db.get_value("Employee", session.employee, "user")
    if user_id:
        frappe.publish_realtime('session_update', {"user_id": user_id, "name": session.name}, after_commit=True)

def notify_auto_status_change(employee, status):
    """
    Send automated chat message when user goes Idle.
    """
    try:
        receiver_email = frappe.db.get_value("Employee", employee, "user")
        employee_name = frappe.db.get_value("Employee", employee, "employee_name")
        
        if receiver_email:
            from company.company.api import send_automated_chat_message, send_chat_notification_to_user
            
            # Fetch the threshold that actually triggered this status
            settings = frappe.get_single("Employee Presence Settings")
            if status == "Away":
                threshold_s = settings.away_threshold or 300
            elif status == "Break":
                threshold_s = settings.break_threshold or 900
            else:
                threshold_s = settings.idle_threshold or 60
                
            threshold_display = format_duration_hms(threshold_s)
            
            content = f"""Hi {employee_name} 👋<br><br>
We noticed no activity for the last {threshold_display}, so your status has been automatically set to 'Break'.<br><br>
⏱️ Inactive Time: {threshold_display}<br>
Status: Active<br><br>
We'll switch you back to 'Available' as soon as you're active again."""
            
            if send_automated_chat_message(None, receiver_email, content):
                send_chat_notification_to_user(receiver_email, "Break Notification", content)
    except Exception as e:
        frappe.log_error(f"Error sending auto status message: {str(e)}", "Auto Status Notification Error")

def notify_auto_resume(employee, duration_seconds):
    """
    Send welcome back message when user becomes active.
    """
    try:
        receiver_email = frappe.db.get_value("Employee", employee, "user")
        employee_name = frappe.db.get_value("Employee", employee, "employee_name")
        
        if receiver_email:
            from company.company.api import send_automated_chat_message, send_chat_notification_to_user
            
            duration_display = format_duration_hms(duration_seconds)
            now = now_datetime()
            end_time = now.strftime("%I:%M %p")
            
            content = f"""Welcome back, {employee_name}!<br><br>
Your status is now 'Available'.<br><br>
⏱️ Inactive Duration: {duration_display}<br>
🕒 Resumed At: {end_time}<br><br>
Your activity has been successfully resumed."""
            
            if send_automated_chat_message(None, receiver_email, content):
                send_chat_notification_to_user(receiver_email, "Welcome Back", content)
    except Exception as e:
        frappe.log_error(f"Error sending auto resume message: {str(e)}", "Auto Resume Notification Error")

def create_break(session_name, now, source="Manual", reason=""):
    # Ensure no other active break exists
    existing = frappe.db.get_value("Employee Break", {"session": session_name, "break_end": ["is", "not set"]}, "name")
    if not existing:
        doc = frappe.get_doc({
            "doctype": "Employee Break",
            "session": session_name,
            "break_start": now,
            "source": source,
            "reason": reason
        })
        doc.insert(ignore_permissions=True)

        # Publish session update (for break tracking)
        user_id = frappe.db.get_value("Employee", frappe.db.get_value("Employee Session", session_name, "employee"), "user")
        if user_id:
            frappe.publish_realtime('session_update', {"user_id": user_id, "name": session_name}, after_commit=True)

def close_active_break(session_name, now):
    if not session_name:
        return
    
    active_break_name = frappe.db.get_value("Employee Break", 
        {"session": session_name, "break_end": ["is", "not set"]}, "name")
    
    if active_break_name:
        brk = frappe.get_doc("Employee Break", active_break_name)
        brk.break_end = now
        
        # Calculate duration in minutes
        diff_seconds = time_diff_in_seconds(now, brk.break_start)
        brk.break_duration = diff_seconds / 60.0
        brk.save(ignore_permissions=True)

        # Publish session update (for break tracking)
        user_id = frappe.db.get_value("Employee", frappe.db.get_value("Employee Session", session_name, "employee"), "user")
        if user_id:
            frappe.publish_realtime('session_update', {"user_id": user_id, "name": session_name}, after_commit=True)

@frappe.whitelist()
def get_detailed_sessions(employee=None, limit_start=0, limit_page_length=20, date_search="", status="all", sort_by="login_date_desc", day=None, date=None, from_date=None, to_date=None):
    """
    Fetch sessions with their child intervals and related breaks.
    """
    is_hr_or_admin = "HR" in frappe.get_roles() or "Administrator" in frappe.get_roles()

    if not is_hr_or_admin:
        # Non-HR/Admin users MUST be restricted to their own ID
        employee = frappe.db.get_value("Employee", {"user": frappe.session.user}, "name")
        if not employee:
            return {"data": [], "total_count": 0}
    # For HR/Admin, 'employee' is already either None (all) or from param (specific)
    
    # Map sort_by to SQL order by
    order_by_sql = "s.login_date desc"
    if sort_by == "login_date_asc":
        order_by_sql = "s.login_date asc"
    elif sort_by == "working_hours_desc":
        order_by_sql = "s.total_work_hours desc"
    elif sort_by == "working_hours_asc":
        order_by_sql = "s.total_work_hours asc"

    # Build SQL based on filters
    query_filters = []
    values = {}
    
    if date_search:
        # Check if it looks like a date (DD-MM-YYYY or DD/MM/YYYY)
        if re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}$", date_search.strip()):
            try:
                parts = re.split(r"[-/]", date_search.strip())
                if len(parts) == 3:
                     # Add equality check for the date
                     # We use an OR because we want to match either the login_date strictly
                     # or fallback to string search if the name contains these numbers (unlikely but safe)
                     formatted_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                     query_filters.append("(s.login_date = %(formatted_date)s OR s.employee LIKE %(search)s OR e.employee_name LIKE %(search)s)")
                     values["formatted_date"] = formatted_date
                     values["search"] = f"%{date_search}%"
                else:
                     query_filters.append("(s.employee LIKE %(search)s OR e.employee_name LIKE %(search)s OR s.login_date LIKE %(search)s)")
                     values["search"] = f"%{date_search}%"
            except Exception:
                query_filters.append("(s.employee LIKE %(search)s OR e.employee_name LIKE %(search)s OR s.login_date LIKE %(search)s)")
                values["search"] = f"%{date_search}%"
        else:
            # Not a specific date format, search name or ID or login_date string
            query_filters.append("(s.employee LIKE %(search)s OR e.employee_name LIKE %(search)s OR s.login_date LIKE %(search)s)")
            values["search"] = f"%{date_search}%"
        
    if status and status != "all":
        query_filters.append("s.status = %(status)s")
        values["status"] = status

    if day and day != "all":
        query_filters.append("DAYNAME(s.login_date) = %(day)s")
        values["day"] = day

    if date:
        query_filters.append("s.login_date = %(date)s")
        values["date"] = date
        
    if from_date and to_date:
        query_filters.append("s.login_date BETWEEN %(from_date)s AND %(to_date)s")
        values["from_date"] = from_date
        values["to_date"] = to_date
    elif from_date:
        query_filters.append("s.login_date >= %(from_date)s")
        values["from_date"] = from_date
    elif to_date:
        query_filters.append("s.login_date <= %(to_date)s")
        values["to_date"] = to_date

    if employee and employee != "all":
        import json
        selected_employees = []
        if isinstance(employee, list):
            selected_employees = employee
        elif isinstance(employee, str):
            if employee.startswith("[") and employee.endswith("]"):
                try:
                    selected_employees = json.loads(employee)
                except Exception:
                    selected_employees = [employee]
            elif "," in employee:
                selected_employees = [x.strip() for x in employee.split(",") if x.strip()]
            else:
                selected_employees = [employee]
        
        if selected_employees:
            placeholders = []
            for idx, emp_id in enumerate(selected_employees):
                key = f"emp_filter_{idx}"
                placeholders.append(f"%({key})s")
                values[key] = emp_id
            query_filters.append(f"s.employee IN ({', '.join(placeholders)})")

    where_clause = f"WHERE {' AND '.join(query_filters)}" if query_filters else ""
    
    sessions = frappe.db.sql(f"""
        SELECT 
            s.name, s.employee, e.employee_name, s.login_time, s.login_date, s.logout_time, s.total_work_hours, s.total_break_hours, s.status
        FROM 
            `tabEmployee Session` s
        LEFT JOIN 
            `tabEmployee` e ON s.employee = e.name
        {where_clause}
        ORDER BY 
            {order_by_sql}
        LIMIT 
            %(limit_start)s, %(limit_page_length)s
    """, {
        **values,
        "limit_start": int(limit_start),
        "limit_page_length": int(limit_page_length)
    }, as_dict=True)
    
    # Get count using the same where_clause
    count_res = frappe.db.sql(f"""
        SELECT COUNT(*)
        FROM `tabEmployee Session` s
        LEFT JOIN `tabEmployee` e ON s.employee = e.name
        {where_clause}
    """, values)
    total_count = count_res[0][0] if count_res else 0

    for s in sessions:
        # Get intervals (child table of Session)
        s.intervals = frappe.get_all("Employee Session Interval",
            filters={"parent": s.name},
            fields=["from_time", "to_time", "status", "duration_seconds"],
            order_by="from_time asc"
        )
        # Get breaks (separate DocType linked to Session)
        s.breaks = frappe.get_all("Employee Break",
            filters={"session": s.name},
            fields=["break_start", "break_end", "break_duration", "source", "reason"],
            order_by="break_start asc"
        )

    return {"data": sessions, "total_count": total_count}

@frappe.whitelist()
def update_detailed_session(name, login_time=None, logout_time=None, intervals=None, breaks=None):
    """
    Update a session with its intervals and breaks.
    Only accessible by HR or Admin.
    """
    is_hr_or_admin = "HR" in frappe.get_roles() or "Administrator" in frappe.get_roles()
    if not is_hr_or_admin:
        frappe.throw(_("Only HR or Admin can update session logs"))

    if isinstance(intervals, str):
        import json
        intervals = json.loads(intervals)
    if isinstance(breaks, str):
        import json
        breaks = json.loads(breaks)

    session = frappe.get_doc("Employee Session", name)
    
    if login_time:
        session.login_time = login_time
    if logout_time:
        session.logout_time = logout_time
        session.status = "Inactive" 
    
    if intervals is not None:
        session.set("intervals", [])
        for i in intervals:
            f_time = i.get("from_time")
            t_time = i.get("to_time")
            dur = i.get("duration_seconds")
            if t_time and not dur:
                dur = time_diff_in_seconds(t_time, f_time)
            
            session.append("intervals", {
                "from_time": f_time,
                "to_time": t_time,
                "status": i.get("status"),
                "duration_seconds": dur or 0
            })
            
    if breaks is not None:
        # Use db.delete to avoid triggering hooks during bulk update, 
        # as we re-calculate totals manually at the end of this function.
        frappe.db.delete("Employee Break", {"session": name})
            
        for b in breaks:
            b_start = b.get("break_start")
            b_end = b.get("break_end")
            b_dur = b.get("break_duration")
            if b_end and not b_dur:
                b_dur = time_diff_in_seconds(b_end, b_start) / 60.0

            doc = frappe.get_doc({
                "doctype": "Employee Break",
                "session": name,
                "break_start": b_start,
                "break_end": b_end,
                "source": b.get("source") or "Manual",
                "reason": b.get("reason"),
                "break_duration": b_dur or 0
            })
            doc.insert(ignore_permissions=True)
            
    # Re-calculate totals before final save
    total_active_seconds = sum(flt(i.duration_seconds) for i in session.intervals if i.status not in ("Offline", "Break", "Away"))
    session.total_work_hours = max(0, flt(total_active_seconds) / 3600.0)
    
    total_break_seconds = get_live_break_seconds(session)
    session.total_break_hours = flt(total_break_seconds) / 3600.0

    # Single save for the active session at the end with retry logic to handle background updates
    for i in range(3):
        try:
            session.save(ignore_permissions=True)
            break
        except frappe.exceptions.TimestampMismatchError:
            if i == 2: raise
            time.sleep(0.05)
            # Re-fetch only the metadata while keeping our local changes to children/totals
            latest_modified = frappe.db.get_value("Employee Session", name, "modified")
            session.modified = latest_modified

    frappe.db.commit()
    
    return {"status": "success"}

@frappe.whitelist()
def get_session_detail(name):
    """
    Fetch a single session with its intervals and breaks.
    """
    session = frappe.db.get_value("Employee Session", name, 
        ["name", "employee", "login_time", "login_date", "logout_time", "total_work_hours", "total_break_hours", "status"], 
        as_dict=True)
    
    if not session:
        return None

    # Get employee name
    session.employee_name = frappe.db.get_value("Employee", session.employee, "employee_name")

    # Get intervals
    session.intervals = frappe.get_all("Employee Session Interval",
        filters={"parent": session.name},
        fields=["from_time", "to_time", "status", "duration_seconds"],
        order_by="from_time asc"
    )

    # Get breaks
    session.breaks = frappe.get_all("Employee Break",
        filters={"session": session.name},
        fields=["break_start", "break_end", "break_duration", "source", "reason"],
        order_by="break_start asc"
    )

    return session

def daily_reset():
    """
    Force close all active sessions and reset all statuses to Offline.
    To be called by a daily cron job at midnight.
    """
    now = now_datetime()
    
    # 1. Close all active sessions
    active_sessions = frappe.get_all("Employee Session", filters={"status": "Active"}, fields=["name"])
    for s in active_sessions:
        doc = frappe.get_doc("Employee Session", s.name)
        close_session(doc, now)
    
    # 2. Reset all presence records to Offline
    frappe.db.sql("UPDATE `tabEmployee Presence` SET status = 'Offline', last_updated = %s", now)
    
    frappe.db.commit()

def process_auto_breaks():
    """
    Background job to identify inactive users and move them to Away or Break status.
    Uses settings from Employee Presence Settings.
    """
    from frappe.utils import add_seconds
    
    settings = frappe.get_single("Employee Presence Settings")
    
    # 1. Skip if auto-status is disabled globally
    if not settings.enable_auto_status:
        return
        
    now = now_datetime()
    
    # 2. Get thresholds
    away_threshold = settings.away_threshold or 300
    break_threshold = settings.break_threshold or 900
    offline_threshold = getattr(settings, "offline_threshold", 3600) or 3600
    
    # 3. Find active presences that haven't been updated for > away_threshold
    # Transition Available -> Away
    away_time = add_seconds(now, -away_threshold)
    inactive_productive = frappe.get_all("Employee Presence", 
        filters={
            "status": ["not in", ["Offline", "Break", "Away"]],
            "last_updated": ["<", away_time]
        },
        fields=["employee", "status"]
    )
    
    for p in inactive_productive:
        frappe.enqueue("company.company.presence_api.update_presence", 
                       status="Away", employee=p.employee, source="Idle")
    
    # 4. Find Away presences that haven't been updated for > break_threshold
    # Transition Away -> Break
    break_time = add_seconds(now, -break_threshold)
    inactive_away = frappe.get_all("Employee Presence",
        filters={
            "status": "Away",
            "last_updated": ["<", break_time]
        },
        fields=["employee", "status"]
    )
    
    for p in inactive_away:
        frappe.enqueue("company.company.presence_api.update_presence", 
                       status="Break", employee=p.employee, source="Idle")
        
    # 5. Find any non-offline presences that haven't been updated for > offline_threshold
    # Transition -> Offline (Computer shutdown/restart case)
    offline_time = add_seconds(now, -offline_threshold)
    inactive_any = frappe.get_all("Employee Presence",
        filters={
            "status": ["!=", "Offline"],
            "last_updated": ["<", offline_time]
        },
        fields=["employee", "status"]
    )
    
    for p in inactive_any:
        frappe.enqueue("company.company.presence_api.update_presence", 
                       status="Offline", employee=p.employee, source="System")
    
    if inactive_productive or inactive_away or inactive_any:
        frappe.db.commit()

@frappe.whitelist()
def force_offline_all():
    """
    Cron job to set all employees to Offline at the end of the day.
    Uses last_updated as the effective logout time for accuracy.
    """
    active_presences = frappe.get_all("Employee Presence",
        filters={"status": ["!=", "Offline"]},
        fields=["employee"]
    )
    
    for p in active_presences:
        # source="System" ensures update_presence uses last_updated for session closure
        update_presence(status="Offline", employee=p.employee, source="System")
        
    frappe.db.commit()

@frappe.whitelist()
def log_location(latitude, longitude, accuracy=None, status=None, source=None, device_type=None, ip_address=None):
    settings = frappe.get_single("Employee Presence Settings")
    if not settings.enable_location_tracking:
        return {"status": "ignored", "message": "Location tracking is disabled globally."}

    employee = frappe.db.get_value("Employee", {"user": frappe.session.user}, "name")
    if not employee:
        frappe.throw(_("Employee not found for current user"))

    target = getattr(settings, "location_tracking_target", "All Employees") or "All Employees"
    if target == "Selected Employees":
        tracked_raw = getattr(settings, "tracked_employees", "[]") or "[]"
        tracked_list = frappe.parse_json(tracked_raw) if isinstance(tracked_raw, str) else (tracked_raw or [])
        if employee not in tracked_list:
            return {"status": "ignored", "message": f"Location tracking is disabled for employee {employee}."}

    active_session = get_active_session(employee)
    session_name = active_session.name if active_session else None

    if not session_name and source == "Logout":
        session_name = frappe.db.get_value("Employee Session", {"employee": employee}, "name", order_by="modified desc")

    # Get details if not provided
    if not device_type and hasattr(frappe, "request") and frappe.request:
        device_type = frappe.request.headers.get("User-Agent")
    if not ip_address and hasattr(frappe, "local") and frappe.local:
        ip_address = frappe.local.request_ip

    doc = frappe.get_doc({
        "doctype": "Employee Location Log",
        "employee": employee,
        "session": session_name,
        "status": status,
        "source": source,
        "latitude": flt(latitude),
        "longitude": flt(longitude),
        "accuracy": flt(accuracy) if accuracy is not None else None,
        "logged_at": now_datetime(),
        "device_type": device_type,
        "ip_address": ip_address
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "success", "name": doc.name}

@frappe.whitelist()
def get_location_logs(employee=None, session=None, from_date=None, to_date=None, status=None, source=None):
    is_hr_or_admin = "HR" in frappe.get_roles() or "Administrator" in frappe.get_roles()
    if not is_hr_or_admin:
        employee = frappe.db.get_value("Employee", {"user": frappe.session.user}, "name")
        if not employee:
            return []

    filters = {}
    if employee:
        filters["employee"] = employee
    if session:
        filters["session"] = session
    if status and status != "all":
        filters["status"] = status
    if source and source != "all":
        filters["source"] = source

    logs = frappe.get_all("Employee Location Log",
        filters=filters,
        fields=["name", "employee", "session", "status", "source", "latitude", "longitude", "accuracy", "logged_at", "device_type", "ip_address"],
        order_by="logged_at asc"
    )
    return logs
