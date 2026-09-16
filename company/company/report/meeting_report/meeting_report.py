import frappe


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters or {})
    summary = get_summary(data)

    return columns, data, None, None, summary


# ------------------------------------------------------
# COLUMNS
# ------------------------------------------------------
def get_columns():
    return [
        {
            "label": "Title",
            "fieldname": "title",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": "Meet For",
            "fieldname": "meet_for",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": "Lead Name",
            "fieldname": "lead_name",
            "fieldtype": "Link",
            "options": "Lead",
            "width": 160
        },
        {
            "label": "Contact Name",
            "fieldname": "contact_name",
            "fieldtype": "Link",
            "options": "Contacts",
            "width": 160
        },
        {
            "label": "Account Name",
            "fieldname": "accounts_name",
            "fieldtype": "Link",
            "options": "Accounts",
            "width": 160
        },
        {
            "label": "Meeting Venue",
            "fieldname": "meeting_venue",
            "fieldtype": "Data",
            "width": 140
        },
        {
            "label": "Location",
            "fieldname": "location",
            "fieldtype": "Data",
            "width": 160
        },
        {
            "label": "Meet Status",
            "fieldname": "outgoing_call_status",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": "Completed Status",
            "fieldname": "completed_meet_status",
            "fieldtype": "Data",
            "width": 220
        },
        {
            "label": "From",
            "fieldname": "from_time",
            "fieldtype": "Datetime",
            "width": 160
        },
        {
            "label": "To",
            "fieldname": "to_time",
            "fieldtype": "Datetime",
            "width": 160
        },
        {
            "label": "Owner",
            "fieldname": "owner_name",
            "fieldtype": "Link",
            "options": "User",
            "width": 150
        },
        {
            "label": "Reminder Enabled",
            "fieldname": "enable_reminder",
            "fieldtype": "Data",
            "width": 140
        }
    ]


# ------------------------------------------------------
# DATA
# ------------------------------------------------------
def get_data(filters):
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("DATE(m.`from`) >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("DATE(m.`from`) <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("meet_for"):
        conditions.append("m.meet_for = %(meet_for)s")
        values["meet_for"] = filters["meet_for"]

    if filters.get("status"):
        conditions.append("m.outgoing_call_status = %(status)s")
        values["status"] = filters["status"]

    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("m.owner_name = %(owner)s")
        values["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("m.owner_name = %(owner)s")
        values["owner"] = owner_val

    if filters.get("enable_reminder") is not None:
        conditions.append("m.enable_reminder = %(enable_reminder)s")
        values["enable_reminder"] = filters["enable_reminder"]

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    return frappe.db.sql(
        f"""
        SELECT
            m.name,
            m.title,
            m.meet_for,
            m.lead_name,
            l.lead_name AS lead_title,
            m.contact_name,
            cnt.first_name AS contact_title,
            m.accounts_name,
            acc.account_name AS account_title,
            m.meeting_venue,
            m.location,
            m.outgoing_call_status,
            m.completed_meet_status,
            m.`from` AS from_time,
            m.`to` AS to_time,
            m.owner_name,
            u.full_name AS owner_full_name,
            m.creation,
            m.modified,
            CASE
                WHEN m.enable_reminder = 1 THEN 'Yes'
                ELSE 'No'
            END AS enable_reminder
        FROM `tabMeeting` m
        LEFT JOIN `tabLead` l ON l.name = m.lead_name
        LEFT JOIN `tabContacts` cnt ON cnt.name = m.contact_name
        LEFT JOIN `tabAccounts` acc ON acc.name = m.accounts_name
        LEFT JOIN `tabUser` u ON u.name = m.owner_name
        {where_clause}
        ORDER BY m.`from` DESC
        """,
        values,
        as_dict=True
    )


# ------------------------------------------------------
# SUMMARY (KPI CARDS)
# ------------------------------------------------------
def get_summary(data):
    total = len(data)
    scheduled = sum(1 for d in data if d.get("outgoing_call_status") == "Scheduled")
    completed = sum(1 for d in data if d.get("outgoing_call_status") == "Completed")
    reminders = sum(1 for d in data if d.get("enable_reminder") == "Yes")

    return [
        {
            "label": "Total Meetings",
            "value": total,
            "indicator": "Blue"
        },
        {
            "label": "Scheduled Meetings",
            "value": scheduled,
            "indicator": "Orange"
        },
        {
            "label": "Completed Meetings",
            "value": completed,
            "indicator": "Green"
        },
        {
            "label": "Reminder Enabled",
            "value": reminders,
            "indicator": "Purple"
        }
    ]
