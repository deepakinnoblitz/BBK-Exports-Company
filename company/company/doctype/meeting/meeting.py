# Copyright (c) 2025, deepak
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, format_datetime, now_datetime
from company.company.reminders import handle_meet_reminder

class Meeting(Document):

    def validate(self):
        self.validate_meeting_time()

    def validate_meeting_time(self):

        start = self.get("from")
        end = self.get("to")

        # 1️⃣ Start time mandatory
        if not start:
            frappe.throw("Please select Meeting Start Time.")

        start_dt = get_datetime(start)

        # 2️⃣ End time must be after start
        if end:
            end_dt = get_datetime(end)

            if end_dt <= start_dt:
                frappe.throw("Meeting End Time must be after Start Time.")

        # 3️⃣ Start time cannot be in the past (ONLY if Scheduled)
        # Use your actual field name for status
        if self.outgoing_call_status == "Scheduled":

            # Skip past-time validation when dragged from calendar
            if not frappe.flags.get("from_calendar_drag"):
                if start_dt < now_datetime():
                    frappe.throw("Scheduled Meeting Start Time cannot be in the past.")

    def after_insert(self):
        """Create Event when Meeting is created."""
        create_event_for_meeting(self)
        handle_meet_reminder(self)

    def on_update(self):

        handle_meet_reminder(self)

        """Update or create Event when Meeting is modified."""

        if frappe.flags.get("ignore_meeting_sync"):
            return 

        # Create if not exists
        if not frappe.db.exists("Event", {
            "reference_doctype": "Meeting",
            "reference_docname": self.name
        }):
            create_event_for_meeting(self)
        else:
            update_event_for_meeting(self)

        # Sync status
        if self.outgoing_call_status == "Completed":
            event_name = frappe.db.get_value(
                "Event",
                {"reference_doctype": "Meeting", "reference_docname": self.name},
                "name"
            )
            if event_name:
                event = frappe.get_doc("Event", event_name)
                event.status = "Completed"
                event.save(ignore_permissions=True)

    def on_trash(self):
        """
        Handle Meeting deletion.
        """
        from company.company.reminders import delete_reminders_and_linked_events
        delete_reminders_and_linked_events("Meeting", self.name)


# -------------------------------------------------------
# EVENT CREATION
# -------------------------------------------------------

def create_event_for_meeting(doc):
    """Creates Calendar Event automatically from Meeting."""

    # Prevent duplicate creation
    if frappe.db.exists("Event", {
        "reference_doctype": "Meeting",
        "reference_docname": doc.name
    }):
        return

    event = frappe.new_doc("Event")

    # -------- TITLE FORMAT --------
    meeting_start = doc.get("from")
    if meeting_start:
        formatted_start = format_datetime(meeting_start, "hh:mm a")
        event.subject = f"{doc.title} - {formatted_start}"
    else:
        event.subject = doc.title

    # Category
    event.event_category = "Meeting"
    event.event_type = "Private"

    # -------- TIME --------
    event.starts_on = doc.get("from")
    event.ends_on = doc.get("to")

    # Always timed

    start = get_datetime(doc.get("from"))
    end = get_datetime(doc.get("to"))

    # Status
    event.status = doc.outgoing_call_status

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
        <b>Meeting Venue:</b> {doc.meeting_venue or ''}<br>
        <b>Location:</b> {doc.location or ''}<br>
        <b>Host:</b> {doc.host or ''}<br>
    """

    # -------- LINK EVENT BACK TO MEETING --------
    event.reference_doctype = "Meeting"
    event.reference_docname = doc.name


    event.insert(ignore_permissions=True)
    frappe.db.commit()


# -------------------------------------------------------
# EVENT UPDATE
# -------------------------------------------------------

def update_event_for_meeting(doc):
    """Updates Calendar Event linked to this Meeting."""

    event_name = frappe.db.get_value(
        "Event",
        {"reference_doctype": "Meeting", "reference_docname": doc.name},
        "name"
    )

    if not event_name:
        return  # No event found

    event = frappe.get_doc("Event", event_name)

    # -------- TITLE FORMAT --------
    meeting_start = doc.get("from")
    if meeting_start:
        formatted_start = format_datetime(meeting_start, "hh:mm a")
        event.subject = f"{doc.title} - {formatted_start}"
    else:
        event.subject = doc.title

    # -------- TIME --------
    event.starts_on = doc.get("from")
    event.ends_on = doc.get("to")

    # Always timed
    start = get_datetime(doc.get("from"))
    end = get_datetime(doc.get("to"))

    # Status
    event.status = doc.outgoing_call_status

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
        <b>Meeting Venue:</b> {doc.meeting_venue or ''}<br>
        <b>Location:</b> {doc.location or ''}<br>
        <b>Host:</b> {doc.host or ''}<br>
    """

    # Save changes
    event.save(ignore_permissions=True)
    frappe.db.commit()
