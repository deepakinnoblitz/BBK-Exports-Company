import frappe


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters or {})
    summary = get_summary(data)

    # Return order is important
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
            "label": "Call For",
            "fieldname": "call_for",
            "fieldtype": "Data",
            "width": 100
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
            "fieldname": "account_name",
            "fieldtype": "Link",
            "options": "Accounts",
            "width": 160
        },
        {
            "label": "Call Status",
            "fieldname": "outgoing_call_status",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": "Completed Status",
            "fieldname": "completed_call_status",
            "fieldtype": "Data",
            "width": 220
        },
        {
            "label": "Call Start",
            "fieldname": "call_start_time",
            "fieldtype": "Datetime",
            "width": 160
        },
        {
            "label": "Call End",
            "fieldname": "call_end_time",
            "fieldtype": "Datetime",
            "width": 160
        },
        {
            "label": "Call Owner",
            "fieldname": "owner_name",
            "fieldtype": "Link",
            "options": "User",
            "width": 150
        },
        {
            "label": "Reminder Enabled",
            "fieldname": "enable_reminder",
            "fieldtype": "Check",
            "width": 120
        }
    ]


# ------------------------------------------------------
# DATA
# ------------------------------------------------------
def get_data(filters):
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("DATE(c.call_start_time) >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("DATE(c.call_start_time) <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("call_for"):
        conditions.append("c.call_for = %(call_for)s")
        values["call_for"] = filters["call_for"]

    if filters.get("status"):
        conditions.append("c.outgoing_call_status = %(status)s")
        values["status"] = filters["status"]

    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner_name")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("c.owner_name = %(owner_name)s")
        values["owner_name"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("c.owner_name = %(owner_name)s")
        values["owner_name"] = owner_val

    if filters.get("enable_reminder") is not None:
        conditions.append("c.enable_reminder = %(enable_reminder)s")
        values["enable_reminder"] = filters["enable_reminder"]

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    return frappe.db.sql(
        f"""
        SELECT
            c.name,
            c.title,
            c.call_for,
            c.lead_name,
            l.lead_name AS lead_title,
            c.contact_name,
            cnt.first_name AS contact_title,
            c.account_name,
            acc.account_name AS account_title,
            c.outgoing_call_status,
            c.completed_call_status,
            c.call_start_time,
            c.call_end_time,
            c.owner_name,
            u.full_name AS owner_full_name,
            c.enable_reminder,
            c.creation,
            c.modified
        FROM `tabCalls` c
        LEFT JOIN `tabLead` l ON l.name = c.lead_name
        LEFT JOIN `tabContacts` cnt ON cnt.name = c.contact_name
        LEFT JOIN `tabAccounts` acc ON acc.name = c.account_name
        LEFT JOIN `tabUser` u ON u.name = c.owner_name
        {where_clause}
        ORDER BY c.call_start_time DESC
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
    reminders = sum(1 for d in data if d.get("enable_reminder"))

    return [
        {
            "label": "Total Calls",
            "value": total,
            "indicator": "Blue"
        },
        {
            "label": "Scheduled Calls",
            "value": scheduled,
            "indicator": "Orange"
        },
        {
            "label": "Completed Calls",
            "value": completed,
            "indicator": "Green"
        },
        {
            "label": "Reminder Enabled",
            "value": reminders,
            "indicator": "Purple"
        }
    ]
