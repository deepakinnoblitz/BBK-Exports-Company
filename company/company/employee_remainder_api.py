import frappe
import json
from frappe import _
from frappe.utils import (
    now_datetime, 
    getdate, 
    get_time, 
    add_to_date, 
    nowdate, 
    get_datetime,
    get_link_to_form
)
from datetime import datetime
from company.company.presence_api import get_live_active_seconds, get_live_break_seconds, get_live_status_seconds

@frappe.whitelist()
def get_my_reminders():
    """Fetch manual reminders for the current employee."""
    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user": user}, "name")
    
    if not employee:
        return []

    return frappe.get_all(
        "Employee Remainder",
        filters={"employee": employee},
        fields=["name", "type", "message", "repeat", "date", "time", "day", "status"],
        order_by="creation desc"
    )

@frappe.whitelist()
def save_remainder(data):
    """Save or update a manual reminder."""
    if isinstance(data, str):
        data = frappe.parse_json(data)

    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user": user}, "name")
    
    if not employee:
        frappe.throw(_("Employee record not found for the current user."))

    if data.get("time") and len(data["time"].split(":")) >= 2:
        parts = data["time"].split(":")
        data["time"] = f"{parts[0]}:{parts[1]}:00"

    if data.get("name"):
        doc = frappe.get_doc("Employee Remainder", data["name"])
        doc.update(data)
        doc.save(ignore_permissions=True)
    else:
        data["employee"] = employee
        data["doctype"] = "Employee Remainder"
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True)
        
    frappe.db.commit()
    
    # Immediately sync the queue for this specific reminder today
    if doc.name:
        frappe.db.sql("""
            DELETE FROM `tabEmployee Remainder Queue` 
            WHERE status = 'Pending' 
            AND remainder = %s
            AND scheduled_time >= %s
        """, (doc.name, nowdate()))
    
    # Trigger the enqueuing logic to create the Pending entry immediately
    check_and_enqueue_reminders()
    
    # Process if it's already due
    process_remainder_queue()
    
    return doc

def check_and_enqueue_reminders(hr_reminder_name=None):
    """Scheduler function to enqueue active recurring reminders and HR reminders."""
    now = now_datetime()
    current_date = now.strftime('%Y-%m-%d')
    current_day = now.strftime("%A")
    advance_window = 3600 # 1 hour
    grace_period = -3600 # 1 hour grace for past/missed reminders
    
    # 1. Process Recurring Individual (Manual) Reminders
    try:
        active_reminders = frappe.get_all(
            "Employee Remainder",
            filters={"status": "Active", "repeat": ["in", ["Single", "Daily", "Weekly"]]},
            fields=["name", "employee", "message", "repeat", "date", "time", "day", "type"]
        )

        for r in active_reminders:
            # For Single reminders, only process if the date is today
            if r.repeat == "Single" and str(r.date) != current_date:
                continue
                
            # For Weekly reminders, only process if the day is today
            if r.repeat == "Weekly" and r.day != current_day:
                continue
                
            trigger_dt = get_datetime(f"{current_date} {r.time}")
            time_diff = (trigger_dt - now).total_seconds()
            
            # If it's within the 1-hour advance window OR 1-hour grace period
            if time_diff <= advance_window and time_diff >= grace_period:
                # Check if this specific time is already enqueued
                if not is_already_enqueued_today(r.name, r.employee, scheduled_time=trigger_dt):
                    enqueue_remainder(r.name, r.employee, r.message or f"Reminder: {r.type}", custom_scheduled_time=trigger_dt)
    except Exception:
        frappe.log_error(title="check_and_enqueue_reminders manual error", message=frappe.get_traceback())

    # 2. Process HR Organizational Reminders
    try:
        settings = frappe.get_single("Employee Remainder Settings")
        if settings.enable_hr_reminders:
            # Fetch all active configurations from the new Doctype
            hr_configs = frappe.get_all("HR Remainder Configuration", fields=["name", "message", "trigger_time", "is_global"])
            
            all_active_employees = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name")
            
            for hr_rem in hr_configs:
                trigger_time = hr_rem.trigger_time
                if not trigger_time:
                    continue
                    
                trigger_dt = get_datetime(f"{current_date} {trigger_time}")
                time_diff = (trigger_dt - now).total_seconds()
                
                # Use the robust range check (1 hour advance window)
                if time_diff <= advance_window and time_diff >= grace_period:
                    employees = []
                    
                    if hr_rem.is_global:
                        employees = all_active_employees
                    else:
                        # Fetch selected employees from child table
                        selected_rows = frappe.get_all("HR Remainder Selected Employee", 
                            filters={"parent": hr_rem.name, "parenttype": "HR Remainder Configuration"}, 
                            fields=["employee"]
                        )
                        employees = [e.employee for e in selected_rows if e.employee]

                    for emp in employees:
                        hr_id = f"HR-{hr_rem.name}"
                        if not is_already_enqueued_today(None, emp, hr_id, scheduled_time=trigger_dt):
                            enqueue_remainder(None, emp, hr_rem.message, hr_id, custom_scheduled_time=trigger_dt)
    except Exception:
        frappe.log_error(title="check_and_enqueue_reminders HR error", message=frappe.get_traceback())

    # 3. Process Automated System Reminders (Lunch/Break)
    try:
        if settings.enable_break_reminders or settings.enable_lunch_reminders:
            # Get employees who have an active session TODAY
            employees_with_session = frappe.get_all(
                "Employee Session",
                filters={"status": "Active", "login_date": current_date},
                pluck="employee"
            )
            
            for session_emp in employees_with_session:
                # A. Lunch Start Reminder
                if settings.enable_lunch_reminders and settings.get("enable_lunch_start_reminder") and settings.lunch_start_time:
                    lunch_time = get_datetime(f"{current_date} {settings.lunch_start_time}")
                    time_diff = (lunch_time - now).total_seconds()
                    
                    if time_diff <= advance_window and time_diff >= grace_period:
                        hr_id = "AUTO-LUNCH-START"
                        if not is_already_enqueued_today(None, session_emp, hr_id, scheduled_time=lunch_time):
                            enqueue_remainder(None, session_emp, settings.lunch_reminder_message or "It's lunch time! 🍴", hr_id, custom_scheduled_time=lunch_time)

                # A2. Lunch End Reminder
                if settings.enable_lunch_reminders and settings.get("enable_lunch_end_reminder") and settings.lunch_end_time:
                    lunch_end_time = get_datetime(f"{current_date} {settings.lunch_end_time}")
                    time_diff = (lunch_end_time - now).total_seconds()
                    
                    if time_diff <= advance_window and time_diff >= grace_period:
                        hr_id = "AUTO-LUNCH-END"
                        if not is_already_enqueued_today(None, session_emp, hr_id, scheduled_time=lunch_end_time):
                            enqueue_remainder(None, session_emp, settings.lunch_end_reminder_message or "Lunch break has ended. Time to resume work! 💻", hr_id, custom_scheduled_time=lunch_end_time)
    except Exception:
        frappe.log_error(title="check_and_enqueue_reminders automated error", message=frappe.get_traceback())

    # 4. Real-time Monitoring for Duration Alerts (Break/Lunch)
    # These MUST have a session to be calculated
    try:
        active_sessions = frappe.get_all(
            "Employee Session",
            filters={"status": "Active", "login_date": current_date},
            fields=["name", "employee"]
        )
        for session in active_sessions:
            # B. Break Reminder (Max Duration) -> Monitors 'Away' status
                if settings.get("enable_max_break_reminders") and settings.max_break_duration_threshold:
                    presence_status = frappe.db.get_value("Employee Presence", session.employee, "status")
                    if presence_status == "Away":
                        # Calculate Live Away duration
                        session_doc = frappe.get_doc("Employee Session", session.name)
                        away_seconds = get_live_status_seconds(session_doc, "Away")
                        away_mins = away_seconds / 60.0
                        
                        if away_mins >= settings.max_break_duration_threshold:
                            hr_id = "MAX-BREAK"
                            last_sent = get_last_enqueued_time(session.employee, hr_id)
                            
                            frequency = settings.break_reminder_frequency or 60
                            # Add a 0.1 minute buffer to account for scheduler jitter
                            if not last_sent or (now - last_sent).total_seconds() / 60 >= (frequency - 0.1):
                                 # Use a new queue doc directly to avoid any hidden 'is_already_enqueued' checks
                                 frappe.get_doc({
                                     "doctype": "Employee Remainder Queue",
                                     "employee": session.employee,
                                     "content": settings.max_break_reminder_message or f"Your break has exceeded {int(settings.max_break_duration_threshold)} minutes. Please resume work.",
                                     "hr_reminder_id": hr_id,
                                     "scheduled_time": now,
                                     "status": "Pending"
                                 }).insert(ignore_permissions=True)

                # D. Lunch Reminder (Max Duration) -> Monitors 'Break' status
                if settings.get("enable_max_lunch_reminders") and settings.max_lunch_duration_threshold:
                    presence_status = frappe.db.get_value("Employee Presence", session.employee, "status")
                    if presence_status == "Break":
                        # Calculate Live Break duration (mapped to Lunch)
                        # Note: Breaks are tracked via Employee Break records, not intervals.
                        # Use get_live_break_seconds with the session name explicitly
                        class SessionStub:
                            def __init__(self, name):
                                self.name = name
                        
                        lunch_seconds = get_live_break_seconds(SessionStub(session.get('name')))
                        lunch_mins = lunch_seconds / 60.0
                        
                        if lunch_mins >= settings.max_lunch_duration_threshold:
                            hr_id = "MAX-LUNCH"
                            last_sent = get_last_enqueued_time(session.employee, hr_id)
                            
                            frequency = settings.lunch_reminder_frequency or 60
                            
                            # Add a 0.1 minute buffer to account for scheduler jitter
                            diff = (now - last_sent).total_seconds() / 60 if last_sent else frequency + 1
                            
                            # DEBUG LOGGING
                            frappe.log_error(
                                title="DEBUG: MAX-LUNCH Check",
                                message=f"Employee: {session.employee}\nLunch Mins: {lunch_mins}\nThreshold: {settings.max_lunch_duration_threshold}\nLast Sent: {last_sent}\nNow: {now}\nDiff: {diff}\nFrequency: {frequency}"
                            )
                            
                            if not last_sent or diff >= (frequency - 0.1):
                                 # Use a new queue doc directly to avoid any hidden 'is_already_enqueued' checks
                                 frappe.get_doc({
                                     "doctype": "Employee Remainder Queue",
                                     "employee": session.employee,
                                     "content": settings.max_lunch_reminder_message or f"Your lunch break has exceeded {int(settings.max_lunch_duration_threshold)} minutes. Please resume work.",
                                     "hr_reminder_id": hr_id,
                                     "scheduled_time": now,
                                     "status": "Pending"
                                 }).insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(title="check_and_enqueue_reminders monitoring error", message=frappe.get_traceback())
    frappe.db.commit()
    
    # Process the queue immediately after enqueuing
    process_remainder_queue()

def is_already_enqueued_today(remainder_name, employee, hr_id=None, scheduled_time=None):
    """Check if already in queue for today."""
    filters = {
        "employee": employee,
    }
    
    if scheduled_time:
        # Check for this exact scheduled time to allow re-scheduling
        filters["scheduled_time"] = scheduled_time
    else:
        filters["scheduled_time"] = [">=", getdate(nowdate())]

    if hr_id:
        filters["hr_reminder_id"] = hr_id
    else:
        filters["remainder"] = remainder_name
        
    return frappe.db.exists("Employee Remainder Queue", filters)

def get_last_enqueued_time(employee, hr_id):
    """Get the creation time of the last enqueued reminder for this type today."""
    last = frappe.get_all("Employee Remainder Queue",
        filters={
            "employee": employee, 
            "hr_reminder_id": hr_id,
            "creation": [">=", getdate(nowdate())]
        },
        fields=["creation"],
        order_by="creation desc",
        limit=1
    )
    if last:
        from frappe.utils import get_datetime
        return get_datetime(last[0].creation)
    
    return None

def enqueue_remainder(remainder_name, employee, content, hr_id=None, trigger_time=None, custom_scheduled_time=None):
    """Add a reminder to the queue with its scheduled time."""
    scheduled_dt = now_datetime() 
    
    if custom_scheduled_time:
        scheduled_dt = custom_scheduled_time
    elif remainder_name:
        rem_doc = frappe.get_doc("Employee Remainder", remainder_name)
        rem_time = rem_doc.time
        rem_date = rem_doc.date or nowdate()
        scheduled_dt = get_datetime(f"{rem_date} {rem_time}")
        
        # For recurring reminders, if it passed today, move to next
        if rem_doc.repeat in ("Daily", "Weekly") and scheduled_dt <= now_datetime():
            scheduled_dt = add_to_date(scheduled_dt, days=1 if rem_doc.repeat == "Daily" else 7)
    
    elif hr_id:
        if hr_id.startswith("AUTO-") or hr_id.startswith("MAX-"):
            # If no custom time, use now
            if not custom_scheduled_time:
                scheduled_dt = now_datetime()
        else:
            if not trigger_time:
                settings = frappe.get_single("Employee Remainder Settings")
                hr_rem_name = hr_id.replace("HR-", "")
                trigger_time = "09:00:00"
                for r in settings.hr_remainders:
                    if r.name == hr_rem_name:
                        trigger_time = r.trigger_time
                        break
            
            scheduled_dt = get_datetime(f"{nowdate()} {trigger_time}")
            
            # If the time has already passed today, schedule for tomorrow
            if scheduled_dt <= now_datetime():
                scheduled_dt = add_to_date(scheduled_dt, days=1)

    queue_doc = frappe.get_doc({
        "doctype": "Employee Remainder Queue",
        "remainder": remainder_name,
        "hr_reminder_id": hr_id,
        "employee": employee,
        "content": content,
        "scheduled_time": scheduled_dt,
        "status": "Pending" # Default to Pending for background processing
    })
    queue_doc.insert(ignore_permissions=True)
    frappe.logger().info(f"Created Queue Entry {queue_doc.name} for {employee} at {scheduled_dt}")
    return queue_doc
    return queue_doc.name

def process_remainder_queue():
    """Send notifications from the queue ONLY IF scheduled_time <= now."""
    now = now_datetime()
    
    pending = frappe.get_all(
        "Employee Remainder Queue",
        filters={
            "status": "Pending",
            "scheduled_time": ["<=", add_to_date(now, seconds=10)]
        },
        fields=["name", "employee", "content", "remainder", "hr_reminder_id", "scheduled_time"]
    )

    if pending:
        frappe.logger().info(f"Processing {len(pending)} pending reminders at {now}")
    
    for item in pending:
        try:
            # FINAL SESSION CHECK: Only send if the employee has an active session TODAY
            has_session = frappe.db.exists("Employee Session", {
                "employee": item.employee,
                "login_date": item.scheduled_time.strftime('%Y-%m-%d'),
                "status": "Active"
            })
            
            if not has_session:
                # Skip for now, maybe they will log in later
                continue

            success = send_remainder_notification(item.name)
            if success:
                log_trigger(item.remainder, item.employee, "Success", item.hr_reminder_id)
            else:
                log_trigger(item.remainder, item.employee, "Error", item.hr_reminder_id)
        except Exception as e:
            frappe.log_error(title="process_remainder_queue item error", message=frappe.get_traceback())

@frappe.whitelist()
def manual_trigger_remainder(queue_name):
    """Manually trigger a reminder from the queue."""
    return send_remainder_notification(queue_name)

def send_remainder_notification(queue_name):
    """Send a chat message for a specific queue entry."""
    from company.company.api import get_chatbot_user
    
    queue_item = frappe.get_doc("Employee Remainder Queue", queue_name)
    receiver_email = frappe.db.get_value("Employee", queue_item.employee, "user")
    sender_email = get_chatbot_user()
    
    if not receiver_email or not sender_email:
        frappe.logger().warning(f"Reminder failed: No receiver ({receiver_email}) or sender ({sender_email}) for queue {queue_name}")
        frappe.db.set_value("Employee Remainder Queue", queue_name, "status", "Failed")
        return False

    try:
        from clefincode_chat.api.api_1_2_1.api import send, create_channel
        
        # 1. Generate Rich Content (Premium Formatting)
        user_name = frappe.db.get_value("User", receiver_email, "first_name") or "there"
        
        title = "HR Reminder" if queue_item.hr_reminder_id else "Reminder"
        
        content = f"🔔 {title}:<br><br>Hi {user_name}! 👋<br><b>{queue_item.content}</b>"

        # 2. Check if direct room exists (Robust SQL)
        room_name = frappe.db.sql("""
            SELECT c.name
            FROM `tabClefinCode Chat Channel` c
            JOIN `tabClefinCode Chat Channel User` u1 ON u1.parent = c.name
            JOIN `tabClefinCode Chat Channel User` u2 ON u2.parent = c.name
            WHERE c.type = 'Direct'
            AND c.is_parent = 1
            AND u1.user = %s
            AND u2.user = %s
        """, (sender_email, receiver_email), pluck=True)

        if room_name:
            room_name = room_name[0]
        else:
            # Create channel
            users = [
                {"email": sender_email, "platform": "Chat"},
                {"email": receiver_email, "platform": "Chat"}
            ]
            sender_name = frappe.db.get_value("User", sender_email, "full_name") or sender_email
            res = create_channel(
                channel_name="",
                users=json.dumps(users),
                type="Direct",
                last_message=content,
                creator_email=sender_email,
                creator=sender_name
            )
            if res and res.get("results"):
                room_name = res["results"][0]["room"]

        if room_name:
            sender_name = frappe.db.get_value("User", sender_email, "full_name") or sender_email
            
            # 3. Ensure receiver is active in the channel (Pattern from Leave Application)
            frappe.db.sql("""
                UPDATE `tabClefinCode Chat Channel User`
                SET is_removed = 0, active = 1
                WHERE parent = %s AND user = %s
            """, (room_name, receiver_email))
            
            from clefincode_chat.api.api_1_2_1.api import share_doctype
            share_doctype("ClefinCode Chat Channel", room_name, receiver_email)

            # 4. Send Message via clefincode_chat
            send(
                content=content,
                user=sender_name,
                room=room_name,
                email=sender_email,
                skip_notification=0 # IMPORTANT: Enable push notification
            )
            
            # 5. Force Realtime Notifications (Pattern from Leave Application)
            # This ensures both the sidebar updates and push notifications are triggered
            refresh_data = {
                "room": room_name,
                "realtime_type": "update_room",
                "content": content,
                "user": sender_name,
                "sender_email": sender_email,
                "room_type": "Direct"
            }
            frappe.publish_realtime(event="update_room", message=refresh_data, user=receiver_email)
            frappe.publish_realtime(event="new_chat_notification", message=refresh_data, user=receiver_email)
            
            frappe.db.set_value("Employee Remainder Queue", queue_name, "status", "Sent")
            
            # If manual reminder, mark as Completed
            if queue_item.remainder:
                repeat = frappe.db.get_value("Employee Remainder", queue_item.remainder, "repeat")
                if repeat == "Single":
                    frappe.db.set_value("Employee Remainder", queue_item.remainder, "status", "Completed")
            
            return True
        else:
            frappe.db.set_value("Employee Remainder Queue", queue_name, "status", "Failed")
            return False

    except Exception as e:
        frappe.log_error(title="Reminder Chat Notification Error", message=frappe.get_traceback())
        frappe.db.set_value("Employee Remainder Queue", queue_name, "status", "Failed")
        return False

def log_trigger(remainder_name, employee, status, hr_id=None):
    """Log the trigger attempt."""
    frappe.get_doc({
        "doctype": "Employee Remainder Log",
        "remainder": remainder_name,
        "employee": employee,
        "hr_reminder_id": hr_id,
        "triggered_at": now_datetime(),
    }).insert(ignore_permissions=True)
    frappe.db.commit()

@frappe.whitelist()
def get_hr_reminders_paginated(params=None):
    """Fetch HR configured reminders from HR Remainder Configuration with pagination, search and sort."""
    if isinstance(params, str):
        params = frappe.parse_json(params)
    
    params = params or {}
    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 10))
    search = params.get("search", "").lower()
    sort_by = params.get("sort_by", "creation_desc")
    
    # Convert frontend 'creation_desc' to SQL 'creation desc'
    order_by = sort_by.replace("_", " ")
        
    filters = {}
    if search:
        filters["message"] = ["like", f"%{search}%"]
        
    data = frappe.get_all("HR Remainder Configuration",
        filters=filters,
        fields=["name", "message", "trigger_time", "is_global", "creation", "modified"],
        order_by=order_by,
        start=(page - 1) * page_size,
        page_length=page_size
    )
    
    # Calculate type and fetch selected employees for each row
    for row in data:
        row["type"] = "Global" if row.is_global else "Selected"
        if not row.is_global:
            # Fetch employee details from child table joined with Employee doctype
            selected = frappe.db.get_all("HR Remainder Selected Employee",
                filters={"parent": row.name},
                fields=["employee as id"]
            )
            
            # Enrich with employee names
            enriched = []
            for s in selected:
                emp_name = frappe.db.get_value("Employee", s.id, "employee_name")
                enriched.append({
                    "id": s.id,
                    "name": emp_name or s.id
                })
            row["selected_employees"] = enriched
        else:
            row["selected_employees"] = []
    
    total = frappe.db.count("HR Remainder Configuration", filters=filters)
    
    return {
        "data": data,
        "total": total
    }

@frappe.whitelist()
def get_hr_reminders():
    """Fetch all HR configured reminders from settings (Legacy)."""
    settings = frappe.get_single("Employee Remainder Settings")
    return settings.hr_remainders or []

@frappe.whitelist()
def save_hr_remainder(data):
    """Add or update an HR reminder in settings."""
    if isinstance(data, str):
        data = frappe.parse_json(data)

    frappe.log_error(title="DEBUG: save_hr_remainder input", message=frappe.as_json(data))
    
    frappe.clear_cache()
    settings = frappe.get_single("Employee Remainder Settings")
    
    if data.get("name"):
        # Update existing entry
        found = False
        for row in settings.hr_remainders:
            if row.name == data["name"]:
                # Manually update fields to avoid potential issues with update() on nested tables
                # Handle nested child table manually in DB to ensure persistence
                frappe.db.sql("DELETE FROM `tabHR Remainder Selected Employee` WHERE parent=%s", row.name)
                for emp_data in data.get("selected_employees", []):
                    frappe.db.sql("""
                        INSERT INTO `tabHR Remainder Selected Employee` (name, parent, parenttype, parentfield, employee, creation, modified, owner)
                        VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), 'Administrator')
                    """, (frappe.generate_hash(length=10), row.name, "HR Remainder Configuration", "selected_employees", emp_data.get("employee")))
                
                found = True
                break
        if not found:
            # For new rows, we need to save first to get a name
            new_row = settings.append("hr_remainders", data)
            settings.save(ignore_permissions=True)
            frappe.db.commit()
            
            # Now save the nested table manually
            for emp_data in data.get("selected_employees", []):
                frappe.db.sql("""
                    INSERT INTO `tabHR Remainder Selected Employee` (name, parent, parenttype, parentfield, employee, creation, modified, owner)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), 'Administrator')
                """, (frappe.generate_hash(length=10), new_row.name, "HR Remainder Configuration", "selected_employees", emp_data.get("employee")))
    else:
        # Create new entry
        new_row = settings.append("hr_remainders", data)
        settings.save(ignore_permissions=True)
        frappe.db.commit()
        
        # Now save the nested table manually
        for emp_data in data.get("selected_employees", []):
            frappe.db.sql("""
                INSERT INTO `tabHR Remainder Selected Employee` (name, parent, parenttype, parentfield, employee, creation, modified, owner)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), 'Administrator')
            """, (frappe.generate_hash(length=10), new_row.name, "HR Remainder Configuration", "selected_employees", emp_data.get("employee")))
    
    settings.save(ignore_permissions=True)
    frappe.db.commit()
    
    # Reload to get the final names
    settings = frappe.get_single("Employee Remainder Settings")
    
    # Trigger immediate enqueuing for today if enabled
    target_name = data.get("name")
    if not target_name:
        # It was new, get the last one added
        target_name = settings.hr_remainders[-1].name
    
    frappe.log_error(
        title="DEBUG: save_hr_remainder",
        message=f"Saved {target_name}. Data: {frappe.as_json(data)}"
    )

    check_and_enqueue_reminders(hr_reminder_name=target_name)
    
    # Trigger immediate processing to avoid 1-min delay
    process_remainder_queue()
    
    return settings

@frappe.whitelist()
def delete_hr_remainder(name):
    """Delete an HR reminder from settings."""
    settings = frappe.get_single("Employee Remainder Settings")
    new_remainders = [r for r in settings.hr_remainders if r.name != name]
    settings.hr_remainders = new_remainders
    settings.save(ignore_permissions=True)
    frappe.db.commit()
    return True

@frappe.whitelist()
def get_reminder_settings():
    """Fetch global reminder settings."""
    return frappe.get_single("Employee Remainder Settings")

@frappe.whitelist()
def save_reminder_settings(data):
    """Update global reminder settings."""
    if isinstance(data, str):
        data = frappe.parse_json(data)
    
    settings = frappe.get_single("Employee Remainder Settings")
    
    # Prevent timestamp mismatch errors by removing 'modified' from incoming data
    # and catching the exception if it occurs
    if "modified" in data:
        del data["modified"]
        
    try:
        settings.update(data)
        settings.save(ignore_permissions=True)
    except frappe.TimestampMismatchError:
        # If mismatch still occurs, reload the latest and force apply
        settings = frappe.get_doc("Employee Remainder Settings")
        settings.update(data)
        settings.save(ignore_permissions=True)

    frappe.db.commit()
    
    # Immediately sync the queue for today based on new settings
    # 1. Clear existing PENDING automated/HR entries for today
    frappe.db.sql("""
        DELETE FROM `tabEmployee Remainder Queue` 
        WHERE status = 'Pending' 
        AND (hr_reminder_id LIKE 'AUTO-%%' OR hr_reminder_id LIKE 'HR-%%')
        AND scheduled_time >= %s
    """, (nowdate()))
    
    # 2. Re-trigger the enqueuing logic
    check_and_enqueue_reminders()
    
    # Trigger immediate processing for anything that might be due NOW
    process_remainder_queue()
    
    return settings

@frappe.whitelist()
def delete_remainder(name):
    """Delete a manual reminder."""
    frappe.db.delete("Employee Remainder", {"name": name})
    # Also clean up the queue
    frappe.db.delete("Employee Remainder Queue", {"remainder": name, "status": "Pending"})
    frappe.db.commit()
    return True
