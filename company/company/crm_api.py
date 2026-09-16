import frappe
from frappe.utils import get_datetime, add_days
from frappe.utils import strip_html
from frappe.utils import get_datetime, now_datetime

@frappe.whitelist()
def convert_lead(lead_name):
    lead = frappe.get_doc("Lead", lead_name)
    messages = []

    # ----------------------------------------------------
    # 0️⃣ VALIDATIONS
    # ----------------------------------------------------

    if not lead.company_name:
        frappe.throw("Company Name is required to create a Company")

    if not (lead.email or lead.phone_number):
        frappe.throw("Email or Phone is required to create a Contact")

    # ----------------------------------------------------
    # 1️⃣ ACCOUNT (Accounts) — Create or reuse
    # ----------------------------------------------------
    account_name = frappe.db.get_value(
        "Accounts",
        {"account_name": lead.company_name},
        "name"
    )

    if account_name:
        messages.append({
            "type": "warning",
            "text": f"Company already exists: {account_name}"
        })
    else:
        account = frappe.new_doc("Accounts")
        account.account_name = lead.company_name
        account.phone_number = lead.phone_number
        account.gstin = lead.gstin
        account.country = lead.country
        account.state = lead.state
        account.city = lead.city
        account.insert()

        account_name = account.name
        messages.append({
            "type": "success",
            "text": f"New Company created: {account_name}"
        })

    # ----------------------------------------------------
    # 2️⃣ CONTACT (Contacts) — Create or reuse
    # ----------------------------------------------------
    existing_contacts = frappe.get_all(
        "Contacts",
        or_filters=[
            ["email", "=", lead.email] if lead.email else ["name", "=", ""],
            ["phone", "=", lead.phone_number] if lead.phone_number else ["name", "=", ""],
        ],
        fields=["name"],
        limit=1
    )

    if existing_contacts:
        contact_name = existing_contacts[0].name
        messages.append({
            "type": "warning",
            "text": f"Contact already exists: {contact_name}"
        })
    else:
        contact_doc = frappe.new_doc("Contacts")
        contact_doc.first_name = lead.lead_name
        contact_doc.email = lead.email
        contact_doc.phone = lead.phone_number
        contact_doc.country = lead.country
        contact_doc.state = lead.state
        contact_doc.city = lead.city
        contact_doc.address = lead.billing_address
        contact_doc.source_lead = lead.name
        # Link the account via the Contact Company child table
        contact_doc.append("company_name", {
            "doctype": "Contact Company",
            "company_name": account_name
        })
        contact_doc.insert()

        contact_name = contact_doc.name
        messages.append({
            "type": "success",
            "text": f"New Contact created: {contact_name}"
        })

    # ----------------------------------------------------
    # 3️⃣ ENSURE COMPANY LINK — If contact already existed, add company if not linked
    # ----------------------------------------------------
    already_linked = frappe.db.exists(
        "Contact Company",
        {"parent": contact_name, "parenttype": "Contacts", "company_name": account_name}
    )

    if existing_contacts and not already_linked:
        frappe.get_doc("Contacts", contact_name).append("company_name", {
            "doctype": "Contact Company",
            "company_name": account_name
        })
        # Use db.insert for child table to avoid full doc save overhead
        child = frappe.new_doc("Contact Company")
        child.parenttype = "Contacts"
        child.parentfield = "company_name"
        child.parent = contact_name
        child.company_name = account_name
        child.insert()
        messages.append({
            "type": "success",
            "text": f"Linked existing contact to company: {account_name}"
        })

    # ----------------------------------------------------
    # 4️⃣ UPDATE LEAD STATUS
    # ----------------------------------------------------
    lead.db_set("status", "Converted")
    lead.db_set("converted_account", account_name)
    lead.db_set("converted_contact", contact_name)

    return {
        "account": account_name,
        "contact": contact_name,
        "messages": messages
    }


@frappe.whitelist()
def get_call_events(doctype, start, end, field_map, filters=None, fields=None):
    import json
    field_map = frappe._dict(json.loads(field_map))
    fields = frappe.parse_json(fields)

    # Detect Color field dynamically
    doc_meta = frappe.get_meta(doctype)
    for d in doc_meta.fields:
        if d.fieldtype == "Color":
            field_map.update({"color": d.fieldname})

    # Wrap SQL keyword fields
    start_col = f"`{field_map.start}`"
    end_col   = f"`{field_map.end}`"

    # STEP 1 → Find valid calls
    call_names = frappe.db.sql(
        f"""
        SELECT name
        FROM `tab{doctype}`
        WHERE IFNULL({start_col}, '0001-01-01 00:00:00') <= %s
          AND IFNULL({end_col},   '2199-12-31 00:00:00') >= %s
        """,
        (end, start),
        as_list=True
    )

    call_names = [c[0] for c in call_names]

    if not call_names:
        return []

    # STEP 2 → Fetch required fields
    if not fields:
        fields = [
            field_map.start,
            field_map.end,
            field_map.title,
            "name",
            "outgoing_call_status",
        ]

    if field_map.color:
        fields.append(field_map.color)

    events = frappe.get_list(
        doctype,
        fields=list(set(fields)),
        filters={"name": ["in", call_names]}
    )

    # STEP 3 → Format for FullCalendar
    for e in events:
        
        start_dt = e.get(field_map.start)
        end_dt   = e.get(field_map.end)

        # Required for FullCalendar
        e["id"] = e["name"]

        # ISO formatting
        if start_dt:
            e["start"] = start_dt.isoformat() + "+05:30"
        if end_dt:
            e["end"] = end_dt.isoformat() + "+05:30"

        # Title formatting (SAFE)
        title = e.get(field_map.title) or e["name"]

        # Safe time strings
        start_str = start_dt.strftime('%I:%M %p') if start_dt else None
        end_str   = end_dt.strftime('%I:%M %p') if end_dt else None

        # Build the title
        if start_str and end_str:
            # Both start and end exist
            e["title"] = f"{title} ({start_str} - {end_str})"
        elif start_str:
            # Only start time exists → no dash, no NULL
            e["title"] = f"{title} ({start_str})"
        else:
            # No times
            e["title"] = title

        # Colors
        status = e.get("outgoing_call_status")
        color_map = {
            "Scheduled": "#FBC02D",
            "Completed": "#0F8A4D",
        }
        e["color"] = color_map.get(status, "#FFFFFF")


        # All-day
        if start_dt and end_dt:
            e["allDay"] = start_dt.date() == end_dt.date()
        else:
            e["allDay"] = True

    return events



@frappe.whitelist()
def get_meeting_events(doctype, start, end, field_map, filters=None, fields=None):
    import json
    field_map = frappe._dict(json.loads(field_map))
    fields = frappe.parse_json(fields)

    # Detect Color field dynamically
    doc_meta = frappe.get_meta(doctype)
    for d in doc_meta.fields:
        if d.fieldtype == "Color":
            field_map.update({"color": d.fieldname})

    # Wrap SQL keyword fields
    start_col = f"`{field_map.start}`"
    end_col   = f"`{field_map.end}`"

    # ---------------------------------------
    # STEP 1 → RAW SQL (same as call events)
    # ---------------------------------------
    meeting_names = frappe.db.sql(
        f"""
        SELECT name
        FROM `tab{doctype}`
        WHERE IFNULL({start_col}, '0001-01-01 00:00:00') <= %s
          AND IFNULL({end_col},   '2199-12-31 00:00:00') >= %s
        """,
        (end, start),
        as_list=True
    )

    meeting_names = [m[0] for m in meeting_names]

    if not meeting_names:
        return []

    # ---------------------------------------
    # STEP 2 → Fetch required fields
    # ---------------------------------------
    if not fields:
        fields = [
            field_map.start,
            field_map.end,
            field_map.title,
            "name",
            "outgoing_call_status",
        ]

    if field_map.color:
        fields.append(field_map.color)

    events = frappe.get_list(
        doctype,
        fields=list(set(fields)),
        filters={"name": ["in", meeting_names]}
    )

    # ---------------------------------------
    # STEP 3 → Format output (IDENTICAL TO CALLS)
    # ---------------------------------------
    for e in events:

        start_dt = e.get(field_map.start)
        end_dt   = e.get(field_map.end)

        # FullCalendar ID
        e["id"] = e["name"]

        # ISO formatting for calendar
        if start_dt:
            e["start"] = start_dt.isoformat() + "+05:30"

        if end_dt:
            e["end"] = end_dt.isoformat() + "+05:30"

        # Title (SAFE)
        title = e.get(field_map.title) or e["name"]

        # Safe time strings
        start_str = start_dt.strftime("%I:%M %p") if start_dt else None
        end_str   = end_dt.strftime("%I:%M %p") if end_dt else None

        # Title building (identical logic from calls)
        if start_str and end_str:
            e["title"] = f"{title} ({start_str} - {end_str})"
        elif start_str:
            e["title"] = f"{title} ({start_str})"
        else:
            e["title"] = title

        # Colors (meeting version)
        status = e.get("outgoing_call_status")
        color_map = {
            "Scheduled": "#FBC02D",
            "Completed": "#0DB260",
        }
        e["color"] = color_map.get(status, "#FFFFFF")

        # All-day event logic
        if start_dt and end_dt:
            e["allDay"] = start_dt.date() == end_dt.date()
        else:
            e["allDay"] = True

    return events



@frappe.whitelist()
def get_events_with_category(start, end, filters=None):
    events = frappe.db.sql("""
        SELECT 
            name, subject, event_category, event_type,
            starts_on,
            COALESCE(ends_on, starts_on) AS ends_on,
            color
        FROM `tabEvent`
        WHERE starts_on <= %s
        AND COALESCE(ends_on, starts_on) >= %s
    """, (end, start), as_dict=True)

    # Fix ending date for FullCalendar → must be exclusive
    for e in events:
        if e.get("ends_on"):
            start_dt = get_datetime(e["starts_on"])
            end_dt   = get_datetime(e["ends_on"])

            # Only add +1 day when event spans multiple days
            if end_dt.date() > start_dt.date():
                e["ends_on"] = add_days(end_dt, 1)

    return events


def sync_event_to_call(doc, method):
    """Sync Event changes back to Calls (bi-directional sync)."""

    # Avoid infinite loop
    if frappe.flags.get("ignore_event_sync"):
        return

    # Only sync when event is linked to Calls
    if doc.reference_doctype != "Calls" or not doc.reference_docname:
        return

    call = frappe.get_doc("Calls", doc.reference_docname)

    # Title (subject before '- hh:mm')
    if doc.subject:
        call.title = doc.subject.split("-")[0].strip()

    # Time
    call.call_start_time = doc.starts_on
    call.call_end_time = doc.ends_on

    # Status
    call.outgoing_call_status = "Completed" if doc.status == "Completed" else "Scheduled"

    # Prevent loop
    frappe.flags.ignore_call_sync = True

    call.save(ignore_permissions=True)



def sync_event_to_meeting(doc, method):
    """Sync Event changes back to Meeting (bi-directional sync)."""

    # Avoid infinite loop
    if frappe.flags.get("ignore_meeting_sync"):
        return

    # Only sync when event is linked to Meeting
    if doc.reference_doctype != "Meeting" or not doc.reference_docname:
        return

    meeting = frappe.get_doc("Meeting", doc.reference_docname)

    # Title (subject before '- hh:mm')
    if doc.subject:
        meeting.title = doc.subject.split("-")[0].strip()

    # Time — MUST use update() because 'from' is a Python keyword
    meeting.update({
        "from": doc.starts_on,
        "to": doc.ends_on
    })

    # Status
    meeting.outgoing_call_status = (
        "Completed" if doc.status == "Completed" else "Scheduled"
    )

    # Prevent loop
    frappe.flags.ignore_meeting_sync = True
    meeting.save(ignore_permissions=True)
    frappe.flags.ignore_meeting_sync = False


def sync_event_to_todo(doc, method):    
    """Sync Event changes back to ToDo (bi-directional sync)."""

    # Avoid infinite loop
    if frappe.flags.get("ignore_todo_sync"):
        return

    # Only sync when event is linked to ToDo
    if doc.reference_doctype != "ToDo" or not doc.reference_docname:
        return

    todo = frappe.get_doc("ToDo", doc.reference_docname)

    # Title (subject before '- hh:mm')
    if doc.subject:
        todo.description = doc.subject.split("-")[0].strip()

    todo.update({
        "date": doc.starts_on,
    })

    todo.priority = doc.priority
    # Status
    todo.status = (
        "Cancelled" if doc.status in ["Cancelled", "Canceled"] else ("Closed" if doc.status == "Closed" else "Open")
    )   

    # Prevent loop
    frappe.flags.ignore_todo_sync = True
    todo.save(ignore_permissions=True)
    frappe.flags.ignore_todo_sync = False



def validate_event(doc, method=None):
    """
    Calendar validation for Calls, Meetings, and ToDo
    """

    # No reference → ignore
    if not doc.reference_doctype or not doc.reference_docname:
        return

    # -------------------------
    # CALLS
    # -------------------------
    if doc.reference_doctype == "Calls":
        _validate_call_event(doc)

    # -------------------------
    # MEETINGS
    # -------------------------
    elif doc.reference_doctype == "Meeting":
        _validate_meeting_event(doc)

    # -------------------------
    # TODO
    # -------------------------
    elif doc.reference_doctype == "ToDo":
        _validate_todo_event(doc)


def _validate_call_event(doc):
    """
    Calendar-level validation for Calls
    """

    start_dt = get_datetime(doc.starts_on) if doc.starts_on else None
    end_dt   = get_datetime(doc.ends_on) if doc.ends_on else None
    now_dt   = now_datetime()

    # -------------------------
    # BASIC SANITY
    # -------------------------
    if start_dt and end_dt and start_dt > end_dt:
        frappe.throw("Call start time cannot be after end time.")

    # -------------------------
    # 🔑 USE EVENT STATUS ONLY
    # -------------------------

    # 🔵 Scheduled (Open)
    if doc.status == "Open":
        if not start_dt:
            frappe.throw("Call start time is required.")

        if start_dt < now_dt:
            frappe.throw("Scheduled Call Time cannot be in the past.")

    # 🟢 Completed
    elif doc.status == "Completed":
        if not end_dt:
            frappe.throw("Completed Call must have an end time.")

        if end_dt > now_dt:
            frappe.throw("Completed Call End Time cannot be in the future.")



# ------------------------------------------------
# MEETING VALIDATION (FIXED)
# ------------------------------------------------
def _validate_meeting_event(doc):
    meeting = frappe.get_doc("Meeting", doc.reference_docname)

    if not doc.starts_on:
        frappe.throw("Meeting start time is required.")

    start_dt = get_datetime(doc.starts_on)
    now_dt = now_datetime()

    # Scheduled → future only
    if meeting.outgoing_call_status == "Scheduled":
        if start_dt < now_dt:
            frappe.throw("Scheduled Meeting cannot be in the past.")

    # Completed → past only
    elif meeting.outgoing_call_status == "Completed":
        if start_dt > now_dt:
            frappe.throw("Completed Meeting cannot be in the future.")


# ------------------------------------------------
# TODO VALIDATION (TODAY ALLOWED)
# ------------------------------------------------
def _validate_todo_event(doc):

    todo = frappe.get_doc("ToDo", doc.reference_docname)

    if not doc.starts_on:
        frappe.throw("ToDo due date is required.")

    start_dt = get_datetime(doc.starts_on)
    today = now_datetime().date()
    start_date = start_dt.date()

    # -------------------------
    # OPEN TODO
    # -------------------------
    if todo.status == "Open":
        # ❌ Yesterday or earlier
        if start_date < today:
            frappe.throw("Open ToDo cannot have a past due date.")

    # -------------------------
    # CLOSED TODO
    # -------------------------
    elif todo.status == "Closed":
        # ❌ Future dates
        if start_date > today:
            frappe.throw("Completed ToDo cannot be in the future.")




def delete_linked_record_on_event_trash(doc, method):
    """
    When an Event is deleted, also delete the linked Call, Meeting, or Todo record.
    This ensures data consistency across the system.
    """
    
    # Check if event has a linked record
    if not doc.reference_doctype or not doc.reference_docname:
        return
    
    # Only handle Calls, Meeting, and ToDo
    if doc.reference_doctype not in ["Calls", "Meeting", "ToDo"]:
        return
    
    try:
        # Check if the linked record still exists
        if frappe.db.exists(doc.reference_doctype, doc.reference_docname):
            # Clean up EVERYTHING first (Reminders, Events, etc)
            from company.company.reminders import delete_reminders_and_linked_events
            delete_reminders_and_linked_events(doc.reference_doctype, doc.reference_docname)

            # Delete the linked record
            frappe.delete_doc(
                doc.reference_doctype, 
                doc.reference_docname, 
                ignore_permissions=True,
                force=True,
                ignore_on_trash=True
            )
    except Exception as e:
        # Log error but don't block Event deletion
        frappe.log_error(
            message=f"Failed to delete linked {doc.reference_doctype} {doc.reference_docname}: {str(e)}",
            title="Event Cascading Delete Error"
        )

        
@frappe.whitelist()
def force_delete_doc(doctype, name):
    """
    Force delete a doctype (Meeting, Calls, ToDo) and its reminders/events.
    """
    if not frappe.db.exists(doctype, name):
        return {"status": "error", "message": f"{doctype} {name} not found"}

    try:
        # 1. Clean up reminders and linked events
        from company.company.reminders import delete_reminders_and_linked_events
        delete_reminders_and_linked_events(doctype, name)

        # 2. Delete the record
        frappe.delete_doc(
            doctype, 
            name, 
            ignore_permissions=True,
            force=True,
            ignore_on_trash=True
        )
        
        # 3. Commit the transaction
        frappe.db.commit()
        return {"status": "success", "message": f"{doctype} deleted successfully"}
        
    except Exception as e:
        frappe.db.rollback()
        frappe.throw(f"Failed to delete {doctype}: {str(e)}")


def create_event_for_todo(doc, method=None):
    """Create Event when ToDo is created."""
    if frappe.flags.get("ignore_todo_sync"):
        return

    # Check if event already exists
    if frappe.db.exists("Event", {"reference_doctype": "ToDo", "reference_docname": doc.name}):
        return

    event = frappe.new_doc("Event")
    event.subject = doc.description or "Todo Tasks"
    event.event_category = "Todo"
    event.event_type = "Private"
    
    date_str = doc.date or doc.creation
    if date_str:
        event.starts_on = f"{date_str} 00:00:00" if len(str(date_str)) <= 10 else str(date_str)
        event.ends_on = event.starts_on
    else:
        event.starts_on = frappe.utils.now_datetime()
        event.ends_on = event.starts_on

    event.status = "Cancelled" if doc.status in ["Cancelled", "Canceled"] else ("Closed" if doc.status == "Closed" else "Open")
    event.all_day = 1
    event.reference_doctype = "ToDo"
    event.reference_docname = doc.name

    frappe.flags.ignore_todo_sync = True
    event.insert(ignore_permissions=True)
    frappe.flags.ignore_todo_sync = False
    frappe.db.commit()


def update_event_for_todo(doc, method=None):
    """Update Event when ToDo is updated."""
    if frappe.flags.get("ignore_todo_sync"):
        return

    event_name = frappe.db.get_value("Event", {"reference_doctype": "ToDo", "reference_docname": doc.name}, "name")
    
    if not event_name:
        create_event_for_todo(doc)
        return

    event = frappe.get_doc("Event", event_name)
    event.subject = doc.description or "Todo Tasks"
    
    date_str = doc.date or doc.creation
    if date_str:
        event.starts_on = f"{date_str} 00:00:00" if len(str(date_str)) <= 10 else str(date_str)
        event.ends_on = event.starts_on

    event.status = "Cancelled" if doc.status in ["Cancelled", "Canceled"] else ("Closed" if doc.status == "Closed" else "Open")
    
    frappe.flags.ignore_todo_sync = True
    event.save(ignore_permissions=True)
    frappe.flags.ignore_todo_sync = False
    frappe.db.commit()


def delete_event_for_todo(doc, method=None):
    """Delete Event when ToDo is deleted."""
    if frappe.flags.get("ignore_todo_sync"):
        return

    event_name = frappe.db.get_value("Event", {"reference_doctype": "ToDo", "reference_docname": doc.name}, "name")
    if event_name:
        frappe.flags.ignore_todo_sync = True
        frappe.delete_doc("Event", event_name, ignore_permissions=True, force=True)
        frappe.flags.ignore_todo_sync = False
        frappe.db.commit()


@frappe.whitelist()
def get_lead_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Lead DocType for export."""
    lead_meta = frappe.get_meta("Lead")
    valid_fields = []

    # Always include Lead ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "Lead ID"
    })

    for field in lead_meta.fields:
        is_allowed = field.fieldname in ("status", "owner_name")
        if is_allowed or (not field.read_only and not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            if field.fieldname != "sales_pipeline":
                label = field.label
                if field.fieldname == "status":
                    label = "Status"
                elif field.fieldname == "owner_name":
                    label = "Owner Name"
                elif field.fieldname == "workflow_state":
                    label = "Stage"
                
                valid_fields.append({
                    "fieldname": field.fieldname,
                    "label": label
                })

    return valid_fields


@frappe.whitelist()
def get_client_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Contacts DocType for export."""
    contacts_meta = frappe.get_meta("Contacts")
    valid_fields = []

    # Always include Contacts ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "Client ID"
    })

    for field in contacts_meta.fields:
        is_allowed = field.fieldname in ("company_name", "owner_name", "source_lead")
        if is_allowed or (not field.read_only and not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            label = field.label
            if field.fieldname == "first_name":
                label = "Name"
            elif field.fieldname == "company_name":
                label = "Company"
            elif field.fieldname == "phone":
                label = "Phone"
            elif field.fieldname == "owner_name":
                label = "Owner"
            elif field.fieldname == "source_lead":
                label = "Source Lead"
            elif field.fieldname == "customer_type":
                label = "Client Type"
            
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": label
            })

    return valid_fields


@frappe.whitelist()
def get_client_export_data(names=None):
    """Returns contacts data with company_name populated from the child table for export."""
    import json
    if isinstance(names, str):
        names = json.loads(names)
        
    conditions = []
    values = {}
    if names:
        conditions.append("c.name IN %(names)s")
        values["names"] = tuple(names)
        
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    
    return frappe.db.sql(
        f"""
        SELECT
            c.name,
            c.first_name,
            (
                SELECT GROUP_CONCAT(COALESCE(a.account_name, cc.company_name) SEPARATOR ', ')
                FROM `tabContact Company` cc
                LEFT JOIN `tabAccounts` a ON cc.company_name = a.name
                WHERE cc.parent = c.name AND cc.parenttype = 'Contacts' AND cc.parentfield = 'company_name'
            ) AS company_name,
            c.email,
            c.phone,
            c.notes,
            c.address,
            c.customer_type,
            c.country,
            c.state,
            c.city,
            c.source_lead,
            c.owner_name,
            c.creation,
            c.modified
        FROM `tabContacts` c
        {where_clause}
        ORDER BY c.creation DESC
        """,
        values,
        as_dict=True
    )


@frappe.whitelist()
def get_company_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Accounts DocType for export."""
    accounts_meta = frappe.get_meta("Accounts")
    valid_fields = []

    # Always include Accounts ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "Company ID"
    })

    for field in accounts_meta.fields:
        is_allowed = field.fieldname in ("owner_name",)
        if is_allowed or (not field.read_only and not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            label = field.label
            if field.fieldname == "account_name":
                label = "Account Name"
            elif field.fieldname == "phone_number":
                label = "Phone"
            elif field.fieldname == "owner_name":
                label = "Owner"
            
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": label
            })

    return valid_fields


@frappe.whitelist()
def get_call_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Calls DocType for export."""
    calls_meta = frappe.get_meta("Calls")
    valid_fields = []

    # Always include Calls ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "Call ID"
    })

    for field in calls_meta.fields:
        is_allowed = field.fieldname in ("owner_name",)
        if is_allowed or (not field.read_only and not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            label = field.label
            if field.fieldname == "title":
                label = "Title"
            elif field.fieldname == "call_for":
                label = "Call For"
            elif field.fieldname == "outgoing_call_status":
                label = "Status"
            elif field.fieldname == "owner_name":
                label = "Owner"
            
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": label
            })

    return valid_fields


@frappe.whitelist()
def get_meeting_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Meeting DocType for export."""
    meeting_meta = frappe.get_meta("Meeting")
    valid_fields = []

    # Always include Meeting ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "Meeting ID"
    })

    for field in meeting_meta.fields:
        is_allowed = field.fieldname in ("owner_name",)
        if is_allowed or (not field.read_only and not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            label = field.label
            if field.fieldname == "title":
                label = "Title"
            elif field.fieldname == "meet_for":
                label = "Meet For"
            elif field.fieldname == "outgoing_call_status":
                label = "Status"
            elif field.fieldname == "owner_name":
                label = "Owner"
            
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": label
            })

    return valid_fields


@frappe.whitelist()
def get_proposal_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Proposal DocType for export."""
    proposal_meta = frappe.get_meta("Proposal")
    valid_fields = []

    # Always include Proposal ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "Proposal ID"
    })

    for field in proposal_meta.fields:
        is_allowed = field.fieldname in ("owner_name",)
        if is_allowed or (not field.read_only and not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            label = field.label
            if field.fieldname == "proposal_title":
                label = "Proposal Title"
            elif field.fieldname == "reference_no":
                label = "Proposal No"
            elif field.fieldname == "status":
                label = "Status"
            elif field.fieldname == "owner_name":
                label = "Owner"
            
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": label
            })

    return valid_fields


@frappe.whitelist()
def get_prospect_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Deal DocType for export."""
    deal_meta = frappe.get_meta("Deal")
    valid_fields = []

    # Always include Deal ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "Deal ID"
    })

    for field in deal_meta.fields:
        is_allowed = field.fieldname in ("owner",)
        if is_allowed or (not field.read_only and not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            label = field.label
            if field.fieldname == "deal_title":
                label = "Title"
            elif field.fieldname == "stage":
                label = "Stage"
            elif field.fieldname == "account":
                label = "Company ID"
            elif field.fieldname == "contact":
                label = "Client ID"
            
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": label
            })

            # Inject virtual fields next to account/contact
            if field.fieldname == "account":
                valid_fields.append({
                    "fieldname": "company_name",
                    "label": "Company"
                })
            elif field.fieldname == "contact":
                valid_fields.append({
                    "fieldname": "contact_name",
                    "label": "Client Name"
                })

    return valid_fields


@frappe.whitelist()
def get_purchase_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Purchase DocType for export."""
    purchase_meta = frappe.get_meta("Purchase")
    valid_fields = []

    # Always include Purchase ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "Purchase ID"
    })

    for field in purchase_meta.fields:
        is_allowed = field.fieldname in ("owner",)
        if is_allowed or (not field.read_only and not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            label = field.label
            if field.fieldname == "vendor_name":
                label = "Vendor"
            elif field.fieldname == "quantity":
                label = "Qty"
            
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": label
            })

    return valid_fields


@frappe.whitelist()
def get_invoice_collection_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Invoice Collection DocType for export."""
    ic_meta = frappe.get_meta("Invoice Collection")
    valid_fields = []

    # Always include Invoice Collection ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "ID"
    })

    for field in ic_meta.fields:
        is_allowed = field.fieldname in ("owner",)
        if is_allowed or (not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            label = field.label
            if field.fieldname == "invoice":
                label = "Invoice No"
            elif field.fieldname == "collection_date":
                label = "Date"
            elif field.fieldname == "mode_of_payment":
                label = "Mode"
            elif field.fieldname == "amount_to_pay":
                label = "Amount to Pay"
            elif field.fieldname == "amount_collected":
                label = "Amount Collected"
            elif field.fieldname == "amount_pending":
                label = "Amount Pending"
            
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": label
            })

    return valid_fields


@frappe.whitelist()
def get_purchase_settlement_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Purchase Collection DocType for export."""
    pc_meta = frappe.get_meta("Purchase Collection")
    valid_fields = []

    # Always include Purchase Collection ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "ID"
    })

    for field in pc_meta.fields:
        is_allowed = field.fieldname in ("owner",)
        if is_allowed or (not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            label = field.label
            if field.fieldname == "purchase":
                label = "Purchase No"
            elif field.fieldname == "collection_date":
                label = "Date"
            elif field.fieldname == "vendor_name":
                label = "Vendor Name"
            elif field.fieldname == "vendor":
                label = "Vendor"
            elif field.fieldname == "mode_of_payment":
                label = "Mode"
            elif field.fieldname == "amount_to_pay":
                label = "Amount to Pay"
            elif field.fieldname == "amount_collected":
                label = "Amount Collected"
            elif field.fieldname == "amount_pending":
                label = "Amount Pending"
            
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": label
            })

    return valid_fields


import hashlib

def _make_file_token(file_id):
    secret = frappe.local.conf.get("encryption_key") or frappe.local.site
    return hashlib.sha256(f"{file_id}-{secret}".encode()).hexdigest()[:32]


@frappe.whitelist()
def get_proposal_attachments(proposal_ids):
    """Fetches attachments for the given proposal IDs and generates signed download tokens."""
    import json
    if isinstance(proposal_ids, str):
        proposal_ids = json.loads(proposal_ids)
    
    if not proposal_ids:
        return []

    attachments = frappe.get_all(
        "Proposal Attachment",
        fields=["name", "file_name", "attachment", "parent"],
        filters={"parent": ["in", proposal_ids]}
    )

    for att in attachments:
        att["token"] = _make_file_token(att["name"])

    return attachments


@frappe.whitelist(allow_guest=True)
def download_proposal_attachment(file_id, token):
    """Downloads a proposal attachment file using a valid signed token, bypassing permission checks."""
    if not file_id or not token:
        frappe.respond_as_web_page("Invalid request", "Missing file ID or token.", http_status_code=400)
        return

    expected_token = _make_file_token(file_id)
    if token != expected_token:
        frappe.throw("Invalid or expired link", frappe.PermissionError)

    # Fetch file details without calling get_doc
    file_details = frappe.db.get_value("Proposal Attachment", {"name": file_id}, ["file_name", "attachment"], as_dict=True)
    if not file_details or not file_details.attachment:
        frappe.respond_as_web_page("Not Found", "The requested file could not be found.", http_status_code=404)
        return

    file_url = file_details.attachment

    import os
    site_path = frappe.get_site_path()
    
    if file_url.startswith("/private/"):
        relative_path = file_url.lstrip("/")
    elif file_url.startswith("/files/"):
        relative_path = os.path.join("public", file_url.lstrip("/"))
    else:
        relative_path = file_url.lstrip("/")

    file_path = os.path.abspath(os.path.join(site_path, relative_path))

    # Security check: Ensure file path is within site path to prevent path traversal
    if not file_path.startswith(os.path.abspath(site_path)):
        frappe.throw("Access denied", frappe.PermissionError)

    if not os.path.exists(file_path):
        frappe.respond_as_web_page("File Not Found", "The file could not be found on disk.", http_status_code=404)
        return

    # Read and return the file
    with open(file_path, "rb") as f:
        file_content = f.read()

    frappe.local.response.filename = file_details.file_name or os.path.basename(file_path)
    frappe.local.response.filecontent = file_content
    frappe.local.response.type = "download"


@frappe.whitelist()
def get_estimation_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Estimation DocType for export."""
    est_meta = frappe.get_meta("Estimation")
    valid_fields = []

    # Always include Estimation ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "Estimation ID"
    })

    for field in est_meta.fields:
        is_allowed = field.fieldname in ("owner",)
        if is_allowed or (not field.read_only and not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            label = field.label
            if field.fieldname == "customer_name":
                label = "Customer ID"
            elif field.fieldname == "billing_name":
                label = "Bank Account"
            elif field.fieldname == "estimate_date":
                label = "Estimate Date"
            elif field.fieldname == "total_qty":
                label = "Qty"
            elif field.fieldname == "grand_total":
                label = "Grand Total"
            
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": label
            })

    return valid_fields


@frappe.whitelist()
def get_estimation_export_data(filters=None):
    import json
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    conditions = []
    query_filters = {}

    if filters.get("client_name"):
        conditions.append("e.client_name = %(client_name)s")
        query_filters["client_name"] = filters["client_name"]
    if filters.get("billing_name"):
        conditions.append("e.billing_name = %(billing_name)s")
        query_filters["billing_name"] = filters["billing_name"]
    if filters.get("from_date"):
        conditions.append("e.estimate_date >= %(from_date)s")
        query_filters["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("e.estimate_date <= %(to_date)s")
        query_filters["to_date"] = filters["to_date"]
    
    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("e.owner = %(owner)s")
        query_filters["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("e.owner = %(owner)s")
        query_filters["owner"] = owner_val

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    query = f"""
        SELECT
            e.name as estimation_id,
            e.deal,
            e.client_name as customer_id,
            e.estimate_date,
            e.grand_total,
            e.total_amount,
            e.total_qty,
            e.overall_discount_type,
            e.overall_discount,
            e.bank_account,
            e.owner,
            e.attachments,
            a.account_name as company_name,
            i.service,
            i.hsn_code,
            i.description,
            i.quantity as qty,
            i.price,
            i.discount,
            i.tax_type,
            i.tax_amount,
            i.sub_total as total
        FROM `tabEstimation` e
        LEFT JOIN `tabAccounts` a ON a.name = e.billing_name
        LEFT JOIN `tabEstimation Items` i ON i.parent = e.name
        {where}
        ORDER BY e.estimate_date DESC, e.name DESC, i.idx ASC
    """
    
    res = frappe.db.sql(query, query_filters, as_dict=True)
    for row in res:
        if row.get("attachments") and row["attachments"] != "-":
            row["attachment_token"] = _make_file_token(row["attachments"])
    return res


@frappe.whitelist(allow_guest=True)
def download_estimation_attachment(file_path, token):
    """Downloads an estimation attachment file using a valid signed token, bypassing permission checks."""
    if not file_path or not token:
        frappe.respond_as_web_page("Invalid request", "Missing file path or token.", http_status_code=400)
        return

    expected_token = _make_file_token(file_path)
    if token != expected_token:
        frappe.throw("Invalid or expired link", frappe.PermissionError)

    import os
    site_path = frappe.get_site_path()
    
    if file_path.startswith("/private/"):
        relative_path = file_path.lstrip("/")
    elif file_path.startswith("/files/"):
        relative_path = os.path.join("public", file_path.lstrip("/"))
    else:
        relative_path = file_path.lstrip("/")

    file_path_on_disk = os.path.abspath(os.path.join(site_path, relative_path))

    # Security check: Ensure file path is within site path to prevent path traversal
    if not file_path_on_disk.startswith(os.path.abspath(site_path)):
        frappe.throw("Access denied", frappe.PermissionError)

    if not os.path.exists(file_path_on_disk):
        frappe.respond_as_web_page("File Not Found", "The file could not be found on disk.", http_status_code=404)
        return

    # Read and return the file
    with open(file_path_on_disk, "rb") as f:
        file_content = f.read()

    frappe.local.response.filename = os.path.basename(file_path_on_disk)
    frappe.local.response.filecontent = file_content
    frappe.local.response.type = "download"


@frappe.whitelist()
def get_invoice_export_data(filters=None):
    import json
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    conditions = []
    query_filters = {}

    if filters.get("client_name"):
        conditions.append("i.client_name = %(client_name)s")
        query_filters["client_name"] = filters["client_name"]
    if filters.get("billing_name"):
        conditions.append("i.billing_name = %(billing_name)s")
        query_filters["billing_name"] = filters["billing_name"]
    if filters.get("from_date"):
        conditions.append("i.invoice_date >= %(from_date)s")
        query_filters["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("i.invoice_date <= %(to_date)s")
        query_filters["to_date"] = filters["to_date"]
    
    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("i.owner = %(owner)s")
        query_filters["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("i.owner = %(owner)s")
        query_filters["owner"] = owner_val

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    query = f"""
        SELECT
            i.name as invoice_id,
            i.deal,
            i.client_name as customer_id,
            i.invoice_date,
            i.grand_total,
            i.total_amount,
            i.total_qty,
            i.overall_discount_type,
            i.overall_discount,
            i.bank_account,
            i.owner,
            i.attachments,
            a.account_name as company_name,
            it.service,
            it.hsn_code,
            it.description,
            it.quantity as qty,
            it.price,
            it.discount,
            it.tax_type,
            it.tax_amount,
            it.sub_total as total
        FROM `tabInvoice` i
        LEFT JOIN `tabAccounts` a ON a.name = i.billing_name
        LEFT JOIN `tabInvoice Items` it ON it.parent = i.name
        {where}
        ORDER BY i.invoice_date DESC, i.name DESC, it.idx ASC
    """
    
    res = frappe.db.sql(query, query_filters, as_dict=True)
    for row in res:
        if row.get("attachments") and row["attachments"] != "-":
            row["attachment_token"] = _make_file_token(row["attachments"])
    return res


@frappe.whitelist(allow_guest=True)
def download_invoice_attachment(file_path, token):
    """Downloads an invoice attachment file using a valid signed token, bypassing permission checks."""
    if not file_path or not token:
        frappe.respond_as_web_page("Invalid request", "Missing file path or token.", http_status_code=400)
        return

    expected_token = _make_file_token(file_path)
    if token != expected_token:
        frappe.throw("Invalid or expired link", frappe.PermissionError)

    import os
    site_path = frappe.get_site_path()
    
    if file_path.startswith("/private/"):
        relative_path = file_path.lstrip("/")
    elif file_path.startswith("/files/"):
        relative_path = os.path.join("public", file_path.lstrip("/"))
    else:
        relative_path = file_path.lstrip("/")

    file_path_on_disk = os.path.abspath(os.path.join(site_path, relative_path))

    # Security check: Ensure file path is within site path to prevent path traversal
    if not file_path_on_disk.startswith(os.path.abspath(site_path)):
        frappe.throw("Access denied", frappe.PermissionError)

    if not os.path.exists(file_path_on_disk):
        frappe.respond_as_web_page("File Not Found", "The file could not be found on disk.", http_status_code=404)
        return

    # Read and return the file
    with open(file_path_on_disk, "rb") as f:
        file_content = f.read()

    frappe.local.response.filename = os.path.basename(file_path_on_disk)
    frappe.local.response.filecontent = file_content
    frappe.local.response.type = "download"






@frappe.whitelist()
def get_invoice_export_fields():
    """Returns a list of writable, non-hidden, non-child-table fields from the Invoice DocType for export."""
    inv_meta = frappe.get_meta("Invoice")
    valid_fields = []

    # Always include Invoice ID (name) first
    valid_fields.append({
        "fieldname": "name",
        "label": "Invoice ID"
    })

    for field in inv_meta.fields:
        is_allowed = field.fieldname in ("owner",)
        if is_allowed or (not field.read_only and not field.hidden and field.fieldtype not in ("Table", "HTML", "Section Break", "Column Break", "Button", "Tab Break")):
            label = field.label
            if field.fieldname == "customer_name":
                label = "Customer ID"
            elif field.fieldname == "invoice_date":
                label = "Invoice Date"
            elif field.fieldname == "payment_terms":
                label = "Payment Terms"
            elif field.fieldname == "due_date":
                label = "Due Date"
            elif field.fieldname == "po_no":
                label = "PO No"
            elif field.fieldname == "po_date":
                label = "PO Date"
            elif field.fieldname == "bank_account":
                label = "Bank Account"
            elif field.fieldname == "terms_and_conditions":
                label = "Terms and Conditions"
            
            valid_fields.append({
                "fieldname": field.fieldname,
                "label": label
            })

    return valid_fields


@frappe.whitelist()
def get_purchase_export_data(filters=None):
    import json
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    conditions = []
    query_filters = {}

    if filters.get("vendor_name"):
        conditions.append("p.vendor_name = %(vendor_name)s")
        query_filters["vendor_name"] = filters["vendor_name"]
    if filters.get("payment_type"):
        conditions.append("p.payment_type = %(payment_type)s")
        query_filters["payment_type"] = filters["payment_type"]
    if filters.get("from_date"):
        conditions.append("p.bill_date >= %(from_date)s")
        query_filters["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("p.bill_date <= %(to_date)s")
        query_filters["to_date"] = filters["to_date"]
    
    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("p.owner = %(owner)s")
        query_filters["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("p.owner = %(owner)s")
        query_filters["owner"] = owner_val

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    query = f"""
        SELECT
            p.name as purchase_id,
            p.vendor_name,
            c.first_name as vendor_real_name,
            p.bill_no,
            p.bill_date,
            p.grand_total,
            p.total_amount,
            p.total_qty,
            p.overall_discount_type,
            p.overall_discount,
            p.payment_type,
            p.owner,
            p.attach as attachments,
            pi.service,
            pi.hsn_code,
            pi.description,
            pi.quantity as qty,
            pi.price,
            pi.discount,
            pi.tax_type,
            pi.tax_amount,
            pi.sub_total as total
        FROM `tabPurchase` p
        LEFT JOIN `tabContacts` c ON c.name = p.vendor_name
        LEFT JOIN `tabPurchase Items` pi ON pi.parent = p.name
        {where}
        ORDER BY p.bill_date DESC, p.name DESC, pi.idx ASC
    """
    
    res = frappe.db.sql(query, query_filters, as_dict=True)
    for row in res:
        if row.get("attachments") and row["attachments"] != "-":
            row["attachment_token"] = _make_file_token(row["attachments"])
    return res


@frappe.whitelist(allow_guest=True)
def download_purchase_attachment(file_path, token):
    """Downloads a purchase attachment file using a valid signed token, bypassing permission checks."""
    if not file_path or not token:
        frappe.respond_as_web_page("Invalid request", "Missing file path or token.", http_status_code=400)
        return

    expected_token = _make_file_token(file_path)
    if token != expected_token:
        frappe.throw("Invalid or expired link", frappe.PermissionError)

    import os
    site_path = frappe.get_site_path()
    
    if file_path.startswith("/private/"):
        relative_path = file_path.lstrip("/")
    elif file_path.startswith("/files/"):
        relative_path = os.path.join("public", file_path.lstrip("/"))
    else:
        relative_path = file_path.lstrip("/")

    file_path_on_disk = os.path.abspath(os.path.join(site_path, relative_path))

    # Security check: Ensure file path is within site path to prevent path traversal
    if not file_path_on_disk.startswith(os.path.abspath(site_path)):
        frappe.throw("Access denied", frappe.PermissionError)

    if not os.path.exists(file_path_on_disk):
        frappe.respond_as_web_page("File Not Found", "The file could not be found on disk.", http_status_code=404)
        return

    # Read and return the file
    with open(file_path_on_disk, "rb") as f:
        file_content = f.read()

    frappe.local.response.filename = os.path.basename(file_path_on_disk)
    frappe.local.response.filecontent = file_content
    frappe.local.response.type = "download"

