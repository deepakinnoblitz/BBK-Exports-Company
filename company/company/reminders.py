import frappe
from frappe.utils import now_datetime, add_to_date, format_datetime, format_date, get_url_to_form, get_datetime


# Workflow
# ----------------------------------------------------------------
# Call Save
#  → Validate Reminder
#  → Calculate trigger_at
#  → If trigger_at <= now < call_start_time → trigger_at = now
#  → Create / Update Reminder Queue
#  → Cron picks Pending Queue
#  → Email sent
#  → Queue marked Sent

logger = frappe.logger("reminder")

def get_remind_before_minutes(doc=None):
    """
    Priority:
    1. Doc.remind_before_minutes (if explicitly set, including 0)
    2. Reminder Settings.default_remind_before_minutes
    3. Hard fallback (15)
    """

    # 1️⃣ Per-document override (safe for Doc & dict)
    if doc is not None:
        value = doc.get("remind_before_minutes")
        if value is not None:
            return int(value)

    # 2️⃣ Global setting
    settings = frappe.get_single("Reminder Settings")
    if settings.default_remind_before_minutes is not None:
        return int(settings.default_remind_before_minutes)

    # 3️⃣ Fallback
    return 15


def handle_call_reminder(call):

    if frappe.flags.get("ignore_call_reminder"):
        return

    """
    Entry point from Call save.
    Decides whether to create/update/delete reminder queue.
    """

    # ❌ Reminder disabled or no start time
    if not call.enable_reminder or not call.call_start_time:
        delete_pending_queue("Calls", call.name)
        return

    # ❌ Call no longer scheduled
    if call.outgoing_call_status != "Scheduled":
        delete_pending_queue("Calls", call.name)
        return

    # ✅ Valid → proceed
    create_or_update_call_queue(call)

def get_reminder_emails():
    """
    Fetch email recipients from Reminder Settings → Email To
    """
    settings = frappe.get_single("Reminder Settings")

    emails = []

    for row in settings.email_to:
        if row.user:
            email = frappe.db.get_value("User", row.user, "email")
            if email:
                emails.append(email)

    return list(set(emails))  # remove duplicates

def get_primary_recipient():
    user = frappe.session.user
    if user and user != "Guest":
        email = frappe.db.get_value("User", user, "email")
        if email:
            return email
    return None

def get_call_trigger_at(call):
    start = get_datetime(call.call_start_time)
    minutes = get_remind_before_minutes(call)

    return add_to_date(start, minutes=-minutes)


def delete_pending_queue(doctype, name):
    frappe.db.delete(
        "Reminder Queue",
        {
            "reference_doctype": doctype,
            "reference_name": name,
        }
    )

def delete_reminders_and_linked_events(doctype, name):
    """
    1. Delete all Reminder Queue entries.
    2. Delete any Event records.
    """
    # Delete reminders
    delete_pending_queue(doctype, name)

    # Delete Events
    events = frappe.get_all(
        "Event",
        filters={
            "reference_doctype": doctype,
            "reference_docname": name
        },
        pluck="name"
    )
    for event_name in events:
        frappe.delete_doc(
            "Event", 
            event_name, 
            force=True, 
            ignore_on_trash=True
        )


def create_or_update_call_queue(call):
    now = now_datetime()

    call_start = get_datetime(call.call_start_time)
    trigger_at = get_datetime(get_call_trigger_at(call))

    # ❌ Call already started
    if now >= call_start:
        delete_pending_queue("Calls", call.name)
        return

    # Remove old pending entries
    delete_pending_queue("Calls", call.name)

    # ✅ Normal future reminder
    if trigger_at > now:
        queue_trigger = trigger_at

    # ✅ Created inside reminder window → Sent now
    else:
        queue_trigger = now

    queue = frappe.get_doc({
        "doctype": "Reminder Queue",
        "reference_doctype": "Calls",
        "reference_name": call.name,
        "reminder_type": "Calls",
        "trigger_at": queue_trigger,
        "status": "Pending",
        "channel": "Email",
        "recipients": get_primary_recipient() or ",".join(get_reminder_emails()),
        "attempts": 0,
    })
    queue.insert(ignore_permissions=True)


def run_email_reminders():
    now = now_datetime()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n[SCHEDULER TRIGGERED] run_email_reminders running at {now_str}\n")
    logger.info(f"[CRON START] run_email_reminders started at {now_str}")
    frappe.log_error(title="DEBUG: Reminder Cron Start", message=f"Started at {now_str}")

    # Check ALL pending first to see if any exist regardless of time
    all_pending = frappe.get_all("Reminder Queue", filters={"status": "Pending"}, fields=["name", "trigger_at"])
    frappe.log_error(title="DEBUG: All Pending Count", message=f"Count: {len(all_pending)}\n{all_pending}")

    queues = frappe.get_all(
        "Reminder Queue",
        filters={
            "status": "Pending",
            "trigger_at": ["<=", now_str],
        },
        fields=["name", "trigger_at", "reference_doctype", "reference_name"]
    )

    logger.info(f"[CRON] Pending reminders count: {len(queues)}")
    if queues:
        frappe.log_error(title="Pending Reminders Found", message=f"Count: {len(queues)}\nRecords: {queues}")

    for q in queues:
        logger.info(
            f"[CRON PROCESSING START] Processing {q.name} | trigger_at={q.trigger_at}"
        )
        if q.reference_doctype == "Calls":
            process_call_queue_item(q)
        elif q.reference_doctype == "Meeting":
            process_meet_queue_item(q)
            
    frappe.db.commit()

    # Ensure all created email queues are dispatched immediately
    try:
        from frappe.email.queue import flush
        flush()
    except Exception as e:
        logger.error(f"[CRON EMAIL FLUSH FAILURE]: {str(e)}")



def process_call_queue_item(queue_row):

    queue = frappe.get_doc("Reminder Queue", queue_row.name)

    # Avoid double-processing
    if queue.status != "Pending":
        return

    try:
        queue.db_set("status", "Processing")

        doc = frappe.get_doc(
            queue.reference_doctype,
            queue.reference_name
        )

        logger.info(f"[CRON EMAIL ATTEMPT] Sending email for Call {queue.reference_name}")
        if queue.reference_doctype == "Calls":
            recipients = [r for r in (queue.recipients or "").split(",") if r]
            send_call_email(doc, recipients)

        else:
            raise Exception(
                f"Unsupported reference_doctype: {queue.reference_doctype}"
            )

        queue.db_set("status", "Sent")
        queue.db_set("sent_at", now_datetime())
        logger.info(f"[CRON SUCCESS] Reminder {queue_row.name} marked as Sent")
        frappe.db.commit()

    except Exception as e:
        fallback_recipients = get_reminder_emails()
        original_recipients = [r for r in (queue.recipients or "").split(",") if r]
        
        # If we have fallback recipients and they are different from what we just tried
        if fallback_recipients and set(fallback_recipients) != set(original_recipients):
            try:
                logger.info(f"[CRON EMAIL FALLBACK] Trying fallback for Call {queue.reference_name}")
                send_call_email(doc, fallback_recipients)
                queue.db_set("recipients", ",".join(fallback_recipients))
                queue.db_set("status", "Sent")
                queue.db_set("sent_at", now_datetime())
                frappe.db.commit()
                return
            except Exception as fallback_e:
                e = fallback_e

        logger.error(f"[CRON FAILURE] Reminder {queue_row.name} failed: {str(e)}")
        frappe.log_error(title=f"Reminder Queue Failure: {queue_row.name}", message=frappe.get_traceback())
        queue.db_set("status", "Failed")
        queue.db_set("attempts", (queue.attempts or 0) + 1)
        queue.db_set("last_error", str(e))
        frappe.db.commit()



def send_call_email(call, recipients):
    if not recipients:
        raise Exception("No reminder recipients configured")

    subject = f"Reminder: Call at {call.call_start_time}"
    

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=get_call_reminder_html(call),
        reference_doctype="Calls",
        reference_name=call.name,
        delayed=False,
        now=True
    )


def get_call_reminder_html(call):
    call_date = format_date(call.call_start_time)
    call_time = format_datetime(call.call_start_time, "hh:mm a")
    call_url = get_url_to_form("Calls", call.name)

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="margin:0; padding:0; background:#f1f5f9; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f1f5f9; padding:40px 20px;">
    <tr>
        <td align="center">
            
            <!-- Main Card -->
            <table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border-radius:16px; box-shadow:0 4px 16px rgba(0,0,0,0.06); overflow:hidden;">
                
                <!-- Header Section -->
                <tr>
                    <td style="background:#ffffff; padding:40px 32px 32px; text-align:center;">
                        
                        <!-- Icon Circle -->
                        <table cellpadding="0" cellspacing="0" border="0" align="center" style="margin-bottom:20px;">
                            <tr>
                                <td width="64" height="64" align="center" valign="middle" style="border-radius:50%; box-shadow:0 4px 12px rgba(59,130,246,0.3);">
                                    <img src="https://cdn-icons-png.flaticon.com/512/724/724664.png" width="42" height="42" alt="Phone" style="display:block;"/>
                                </td>
                            </tr>
                        </table>

                        <h1 style="margin:0 0 10px; font-size:28px; font-weight:700; color:#0f172a; letter-spacing:-0.03em;">
                            Upcoming Call Reminder
                        </h1>
                        
                        <p style="margin:0; color:#64748b; font-size:15px; line-height:1.6;">
                            You have a scheduled call coming up
                        </p>
                    </td>
                </tr>

                <!-- Divider -->
                <tr>
                    <td style="padding:0 32px;">
                        <table width="100%" cellpadding="0" cellspacing="0" border="0">
                            <tr>
                                <td style="border-top:2px solid #f1f5f9;"></td>
                            </tr>
                        </table>
                    </td>
                </tr>

                <!-- Content Section -->
                <tr>
                    <td style="padding:32px;">
                        
                        <!-- Call Title Box -->
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; margin-bottom:24px;">
                            <tr>
                                <td style="padding:24px;">
                                    <div style="font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin-bottom:10px;">
                                        SUBJECT
                                    </div>
                                    <div style="font-size:20px; font-weight:700; color:#0f172a; line-height:1.4;">
                                        {call.title or "Scheduled Call"}
                                    </div>
                                </td>
                            </tr>
                        </table>

                        <!-- Details Container -->
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0; border-radius:12px; overflow:hidden;">
                            
                            <!-- Date Row -->
                            <tr>
                                <td style="padding:18px 20px; border-bottom:1px solid #f1f5f9; background:#ffffff;">
                                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                        <tr>
                                            <td width="24" valign="middle">
                                                <img src="https://cdn-icons-png.flaticon.com/512/747/747310.png" width="20" height="20" alt="Calendar" style="display:block; opacity:0.7;"/>
                                            </td>
                                            <td valign="middle" style="padding-left:12px; color:#475569; font-size:15px; font-weight:500;">
                                                Date
                                            </td>
                                            <td align="right" valign="middle" style="color:#0f172a; font-size:15px; font-weight:600;">
                                                {call_date}
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                            <!-- Time Row -->
                            <tr>
                                <td style="padding:18px 20px; border-bottom:1px solid #f1f5f9; background:#ffffff;">
                                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                        <tr>
                                            <td width="24" valign="middle">
                                                <img src="https://cdn-icons-png.flaticon.com/512/2838/2838590.png" width="20" height="20" alt="Clock" style="display:block; opacity:0.7;"/>
                                            </td>
                                            <td valign="middle" style="padding-left:12px; color:#475569; font-size:15px; font-weight:500;">
                                                Time
                                            </td>
                                            <td align="right" valign="middle" style="color:#0f172a; font-size:15px; font-weight:600;">
                                                {call_time}
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                            <!-- Status Row -->
                            <tr>
                                <td style="padding:18px 20px; background:#ffffff;">
                                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                        <tr>
                                            <td width="24" valign="middle">
                                                <img src="https://cdn-icons-png.flaticon.com/512/190/190411.png" width="20" height="20" alt="Status" style="display:block; opacity:0.7;"/>
                                            </td>
                                            <td valign="middle" style="padding-left:12px; color:#475569; font-size:15px; font-weight:500;">
                                                Status
                                            </td>
                                            <td align="right" valign="middle">
                                                <span style="display:inline-block; padding:6px 16px; background:#dbeafe; color:#1e40af; font-size:13px; font-weight:700; border-radius:20px; letter-spacing:0.3px;">
                                                    {call.outgoing_call_status or "Scheduled"}
                                                </span>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                        </table>

                        <!-- CTA Button -->
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:32px;">
                            <tr>
                                <td align="center">
                                    <a href="{call_url}" style="display:inline-block; padding:16px 40px; border-radius:10px; background:#3b82f6; color:#ffffff; text-decoration:none; font-weight:700; font-size:16px; box-shadow:0 4px 12px rgba(59,130,246,0.3); letter-spacing:0.3px;">
                                        View Call Details →
                                    </a>
                                </td>
                            </tr>
                        </table>

                    </td>
                </tr>

                <!-- Footer Inside Card -->
                <tr>
                    <td style="padding:24px 32px; background:#f8fafc; border-top:1px solid #e2e8f0;">
                        <p style="margin:0; text-align:center; font-size:12px; color:#94a3b8; line-height:1.6;">
                            This is an automated notification from your CRM system<br/>
                            <span style="font-size:11px; color:#cbd5e1;">Manage your notification preferences in account settings</span>
                        </p>
                    </td>
                </tr>

            </table>

        </td>
    </tr>
</table>

</body>
</html>
"""

# End of Call Reminder    


def handle_meet_reminder(meet):

    if frappe.flags.get("ignore_meet_reminder"):
        return

    """
    Entry point from meet save.
    Decides whether to create/update/delete reminder queue.
    """

    # ❌ Reminder disabled or no start time
    start = get_datetime(meet.get("from"))
    if not meet.enable_reminder or not start:
        delete_pending_queue("Meeting", meet.name)
        return

    # ❌ Meeting no longer scheduled
    if meet.outgoing_call_status != "Scheduled":
        delete_pending_queue("Meeting", meet.name)
        return

    # ✅ Valid → proceed
    create_or_update_meet_queue(meet)


def get_meet_trigger_at(meet):
    start = get_datetime(meet.get("from"))
    minutes = get_remind_before_minutes(meet)

    return add_to_date(start, minutes=-minutes)

def create_or_update_meet_queue(meet):
    now = now_datetime()

    meet_start = get_datetime(meet.get("from"))
    trigger_at = get_datetime(get_meet_trigger_at(meet))

    # ❌ meet already started
    if now >= meet_start:
        delete_pending_queue("Meeting", meet.name)
        return

    # Remove old pending entries
    delete_pending_queue("Meeting", meet.name)

    # ✅ Normal future reminder
    if trigger_at > now:
        queue_trigger = trigger_at

    # ✅ Created inside reminder window → send now
    else:
        queue_trigger = now

    queue = frappe.get_doc({
        "doctype": "Reminder Queue",
        "reference_doctype": "Meeting",
        "reference_name": meet.name,
        "reminder_type": "Meeting",
        "trigger_at": queue_trigger,
        "status": "Pending",
        "channel": "Email",
        "recipients": get_primary_recipient() or ",".join(get_reminder_emails()),
        "attempts": 0,
    })
    queue.insert(ignore_permissions=True)


def process_meet_queue_item(queue_row):

    queue = frappe.get_doc("Reminder Queue", queue_row.name)

    # Avoid double-processing
    if queue.status != "Pending":
        return

    try:
        queue.db_set("status", "Processing")

        doc = frappe.get_doc(
            queue.reference_doctype,
            queue.reference_name
        )

        if queue.reference_doctype == "Meeting":
            recipients = [r for r in (queue.recipients or "").split(",") if r]
            send_meet_email(doc, recipients)

        else:
            raise Exception(
                f"Unsupported reference_doctype: {queue.reference_doctype}"
            )

        queue.db_set("status", "Sent")
        queue.db_set("sent_at", now_datetime())
        logger.info(f"[CRON SUCCESS] Reminder {queue_row.name} marked as Sent")
        frappe.db.commit()

    except Exception as e:
        fallback_recipients = get_reminder_emails()
        original_recipients = [r for r in (queue.recipients or "").split(",") if r]
        
        # If we have fallback recipients and they are different from what we just tried
        if fallback_recipients and set(fallback_recipients) != set(original_recipients):
            try:
                logger.info(f"[CRON EMAIL FALLBACK] Trying fallback for Meeting {queue.reference_name}")
                send_meet_email(doc, fallback_recipients)
                queue.db_set("recipients", ",".join(fallback_recipients))
                queue.db_set("status", "Sent")
                queue.db_set("sent_at", now_datetime())
                frappe.db.commit()
                return
            except Exception as fallback_e:
                e = fallback_e

        logger.error(f"[CRON FAILURE] Reminder {queue_row.name} failed: {str(e)}")
        frappe.log_error(title=f"Reminder Queue Failure: {queue_row.name}", message=frappe.get_traceback())
        queue.db_set("status", "Failed")
        queue.db_set("attempts", (queue.attempts or 0) + 1)
        queue.db_set("last_error", str(e))
        frappe.db.commit()

def send_meet_email(meet, recipients):
    if not recipients:
        raise Exception("No reminder recipients configured")

    start_on = meet.get("from")
    subject = f"Reminder: Meeting at {start_on}"
    
    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=get_meet_reminder_html(meet),
        reference_doctype="Meeting",
        reference_name=meet.name,
        delayed=False,
        now=True
    )


def get_meet_reminder_html(meet):
    start_on = meet.get("from")
    meet_date = format_date(start_on)
    meet_time = format_datetime(start_on, "hh:mm a")
    meet_url = get_url_to_form("Meeting", meet.name)
    start_on = meet.get("from")

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="margin:0; padding:0; background:#f1f5f9; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f1f5f9; padding:40px 20px; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);">
    <tr>
        <td align="center">
            
            <!-- Main Card -->
            <table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border-radius:16px; box-shadow:0 4px 16px rgba(0,0,0,0.06); overflow:hidden;">
                
                <!-- Header Section -->
                <tr>
                    <td style="background:#ffffff; padding:40px 32px 32px; text-align:center;">
                        
                        <!-- Icon Circle -->
                        <table cellpadding="0" cellspacing="0" border="0" align="center" style="margin-bottom:20px;">
                            <tr>
                                <td width="64" height="64" align="center" valign="middle" style="border-radius:50%; box-shadow:0 4px 12px rgba(59,130,246,0.3);">
                                    <img src="https://cdn-icons-png.flaticon.com/512/747/747310.png" width="42" height="42" alt="Phone" style="display:block;"/>
                                </td>
                            </tr>
                        </table>

                        <h1 style="margin:0 0 10px; font-size:28px; font-weight:700; color:#0f172a; letter-spacing:-0.03em;">
                            Upcoming meet Reminder
                        </h1>
                        
                        <p style="margin:0; color:#64748b; font-size:15px; line-height:1.6;">
                            You have a scheduled Meeting coming up
                        </p>
                    </td>
                </tr>

                <!-- Divider -->
                <tr>
                    <td style="padding:0 32px;">
                        <table width="100%" cellpadding="0" cellspacing="0" border="0">
                            <tr>
                                <td style="border-top:2px solid #f1f5f9;"></td>
                            </tr>
                        </table>
                    </td>
                </tr>

                <!-- Content Section -->
                <tr>
                    <td style="padding:32px;">
                        
                        <!-- meet Title Box -->
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; margin-bottom:24px;">
                            <tr>
                                <td style="padding:24px;">
                                    <div style="font-size:11px; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin-bottom:10px;">
                                        SUBJECT
                                    </div>
                                    <div style="font-size:20px; font-weight:700; color:#0f172a; line-height:1.4;">
                                        {meet.title or "Scheduled meet"}
                                    </div>
                                </td>
                            </tr>
                        </table>

                        <!-- Details Container -->
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #e2e8f0; border-radius:12px; overflow:hidden;">
                            
                            <!-- Date Row -->
                            <tr>
                                <td style="padding:18px 20px; border-bottom:1px solid #f1f5f9; background:#ffffff;">
                                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                        <tr>
                                            <td width="24" valign="middle">
                                                <img src="https://cdn-icons-png.flaticon.com/512/747/747310.png" width="20" height="20" alt="Calendar" style="display:block; opacity:0.7;"/>
                                            </td>
                                            <td valign="middle" style="padding-left:12px; color:#475569; font-size:15px; font-weight:500;">
                                                Date
                                            </td>
                                            <td align="right" valign="middle" style="color:#0f172a; font-size:15px; font-weight:600;">
                                                {meet_date}
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                            <!-- Time Row -->
                            <tr>
                                <td style="padding:18px 20px; border-bottom:1px solid #f1f5f9; background:#ffffff;">
                                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                        <tr>
                                            <td width="24" valign="middle">
                                                <img src="https://cdn-icons-png.flaticon.com/512/2838/2838590.png" width="20" height="20" alt="Clock" style="display:block; opacity:0.7;"/>
                                            </td>
                                            <td valign="middle" style="padding-left:12px; color:#475569; font-size:15px; font-weight:500;">
                                                Time
                                            </td>
                                            <td align="right" valign="middle" style="color:#0f172a; font-size:15px; font-weight:600;">
                                                {meet_time}
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                            <!-- Status Row -->
                            <tr>
                                <td style="padding:18px 20px; background:#ffffff;">
                                    <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                        <tr>
                                            <td width="24" valign="middle">
                                                <img src="https://cdn-icons-png.flaticon.com/512/190/190411.png" width="20" height="20" alt="Status" style="display:block; opacity:0.7;"/>
                                            </td>
                                            <td valign="middle" style="padding-left:12px; color:#475569; font-size:15px; font-weight:500;">
                                                Status
                                            </td>
                                            <td align="right" valign="middle">
                                                <span style="display:inline-block; padding:6px 16px; background:#dbeafe; color:#1e40af; font-size:13px; font-weight:700; border-radius:20px; letter-spacing:0.3px;">
                                                    {meet.outgoing_call_status or "Scheduled"}
                                                </span>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                        </table>

                        <!-- CTA Button -->
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:32px;">
                            <tr>
                                <td align="center">
                                    <a href="{meet_url}" style="display:inline-block; padding:16px 40px; border-radius:10px; background:#3b82f6; color:#ffffff; text-decoration:none; font-weight:700; font-size:16px; box-shadow:0 4px 12px rgba(59,130,246,0.3); letter-spacing:0.3px;">
                                        View meet Details →
                                    </a>
                                </td>
                            </tr>
                        </table>

                    </td>
                </tr>

                <!-- Footer Inside Card -->
                <tr>
                    <td style="padding:24px 32px; background:#f8fafc; border-top:1px solid #e2e8f0;">
                        <p style="margin:0; text-align:center; font-size:12px; color:#94a3b8; line-height:1.6;">
                            This is an automated notification from your CRM system<br/>
                            <span style="font-size:11px; color:#cbd5e1;">Manage your notification preferences in account settings</span>
                        </p>
                    </td>
                </tr>

            </table>

        </td>
    </tr>
</table>

</body>
</html>
"""


@frappe.whitelist()
def force_send_call_queue(queue_name):
    queue = frappe.get_doc("Reminder Queue", queue_name)

    if queue.status == "Sent":
        frappe.throw("Reminder already sent")

    # Override trigger time
    queue.db_set("trigger_at", now_datetime())

    # Process immediately
    process_call_queue_item(queue)


@frappe.whitelist()
def force_send_meet_queue(queue_name):
    queue = frappe.get_doc("Reminder Queue", queue_name)

    if queue.status == "Sent":
        frappe.throw("Reminder already sent")

    # Override trigger time
    queue.db_set("trigger_at", now_datetime())

    # Process immediately
    process_meet_queue_item(queue)


@frappe.whitelist()
def delete_call_reminder_queue(call_name):
    """
    Delete all reminder queues for a specific Call.
    This is used when user wants to delete a Call with active reminders.
    """
    delete_pending_queue("Calls", call_name)
    return {"status": "success", "message": "Reminder queue deleted"}
