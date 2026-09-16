# Copyright (c) 2025, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime, format_datetime
from company.company.reminders import handle_call_reminder

class Calls(Document):

    def validate(self):

        is_calendar_drag = frappe.flags.get("from_calendar_drag")

        if self.outgoing_call_status == "Scheduled":

            if not self.call_start_time:
                frappe.throw("Please select a Call Start Time for Scheduled calls.")

            start_dt = get_datetime(self.call_start_time)

            # 🔥 Skip ONLY past-time validation on drag
            if not is_calendar_drag:
                if start_dt < now_datetime():
                    frappe.throw("Scheduled Call Time cannot be in the past.")

    def after_insert(self):
        """Create Event when Call is created."""
        create_event_for_call(self)
        handle_call_reminder(self)

    def on_update(self):

        handle_call_reminder(self)

        """Update or create Event when Call is modified."""

        if frappe.flags.get("ignore_call_sync"):
            return  

        # Create if not exists
        if not frappe.db.exists("Event", {
            "reference_doctype": "Calls",
            "reference_docname": self.name
        }):
            create_event_for_call(self)
        else:
            update_event_for_call(self)

        # Sync status
        if self.outgoing_call_status == "Completed":
            event_name = frappe.db.get_value(
                "Event",
                {"reference_doctype": "Calls", "reference_docname": self.name},
                "name"
            )
            if event_name:
                event = frappe.get_doc("Event", event_name)
                event.status = "Completed"
                event.save(ignore_permissions=True)

    def on_trash(self):
        """
        Handle Call deletion.
        """
        from company.company.reminders import delete_reminders_and_linked_events
        delete_reminders_and_linked_events("Calls", self.name)


def create_event_for_call(doc):
    """Creates Calendar Event automatically from Call."""

    # Prevent duplicate creation
    if frappe.db.exists("Event", {
        "reference_doctype": "Calls",
        "reference_docname": doc.name
    }):
        return

    event = frappe.new_doc("Event")

    # -------- TITLE FORMAT --------
    call_start_time = doc.get("call_start_time")
    if call_start_time:
        formatted_start = format_datetime(call_start_time, "hh:mm a")
        event.subject = f"{doc.title} - {formatted_start}"
    else:
        event.subject = doc.title

    # Category
    event.event_category = "Call"
    event.event_type = "Private"

    # -------- TIME --------
    event.starts_on = doc.get("call_start_time")
    event.ends_on = doc.get("call_end_time")

    # Status
    event.status = doc.outgoing_call_status

    # Always timed

    start = get_datetime(doc.get("call_start_time"))
    end = get_datetime(doc.get("call_end_time"))

    if start.date() == end.date():
        event.all_day = 0
    else:
        event.all_day = 0 

    # -------- COLOR --------
    status = doc.outgoing_call_status
    color_map = {
        "Scheduled": "#FBC02D",
        "Completed": "#0DB260",
    }
    event.color = color_map.get(status, "#FBC02D")

    # -------- DESCRIPTION --------
    event.description = f"""
        <b>Call For:</b> {doc.call_for or ''}<br>
        <b>Purpose:</b> {doc.call_purpose or ''}<br>
        <b>Agenda:</b><br>{doc.call_agenda or ''}
    """

    # -------- LINK EVENT BACK TO MEETING --------
    event.reference_doctype = "Calls"
    event.reference_docname = doc.name

    event.insert(ignore_permissions=True)
    frappe.db.commit()


# -------------------------------------------------------
# EVENT UPDATE
# -------------------------------------------------------

def update_event_for_call(doc):
    """Updates Calendar Event linked to this Call."""

    event_name = frappe.db.get_value(
        "Event",
        {"reference_doctype": "Calls", "reference_docname": doc.name},
        "name"
    )

    if not event_name:
        return  # No event found

    event = frappe.get_doc("Event", event_name)

    # -------- TITLE FORMAT --------
    call_start_time = doc.get("call_start_time")
    if call_start_time:
        formatted_start = format_datetime(call_start_time, "hh:mm a")
        event.subject = f"{doc.title} - {formatted_start}"
    else:
        event.subject = doc.title

    # -------- TIME --------
    event.starts_on = doc.get("call_start_time")
    event.ends_on = doc.get("call_end_time")

    # Status
    event.status = doc.outgoing_call_status

    # Always timed
    start = get_datetime(doc.get("call_start_time"))
    end = get_datetime(doc.get("call_end_time"))

    if not start or not end:
        return

    if start.date() == end.date():
        event.all_day = 0
    else:
        event.all_day = 0 

    # -------- COLOR --------
    status = doc.outgoing_call_status
    color_map = {
        "Scheduled": "#FBC02D",
        "Completed": "#0DB260",
    }
    event.color = color_map.get(status, "#FBC02D")

    # -------- DESCRIPTION --------
    event.description = f"""
        <b>Call For:</b> {doc.call_for or ''}<br>
        <b>Purpose:</b> {doc.call_purpose or ''}<br>
        <b>Agenda:</b><br>{doc.call_agenda or ''}
    """

    # Save changes
    event.save(ignore_permissions=True)
    frappe.db.commit()
