import frappe


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters or {})
    summary = get_summary(data)

    # IMPORTANT ORDER
    return columns, data, None, None, summary


# ------------------------------------------------------
# COLUMNS
# ------------------------------------------------------
def get_columns():
    return [
        {"label": "Lead Name", "fieldname": "lead_name", "fieldtype": "Data", "width": 180},
        {"label": "Company", "fieldname": "company_name", "fieldtype": "Data", "width": 180},
        {"label": "Phone", "fieldname": "phone_number", "fieldtype": "Phone", "width": 140},
        {"label": "Email", "fieldname": "email", "fieldtype": "Data", "width": 180},
        {"label": "Service", "fieldname": "service", "fieldtype": "Link", "options": "Service", "width": 140},
        {"label": "Leads Type", "fieldname": "leads_type", "fieldtype": "Data", "width": 100},
        {"label": "Leads From", "fieldname": "leads_from", "fieldtype": "Link", "options": "Lead From", "width": 100},
        {"label": "Owner", "fieldname": "owner_name", "fieldtype": "Link", "options": "User", "width": 150},
    ]


# ------------------------------------------------------
# DATA
# ------------------------------------------------------
def get_data(filters):
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("DATE(l.creation) >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("DATE(l.creation) <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("leads_type"):
        conditions.append("l.leads_type = %(leads_type)s")
        values["leads_type"] = filters["leads_type"]

    if filters.get("leads_from"):
        conditions.append("l.leads_from = %(leads_from)s")
        values["leads_from"] = filters["leads_from"]

    if filters.get("service"):
        conditions.append("l.service = %(service)s")
        values["service"] = filters["service"]

    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("l.owner_name = %(owner)s")
        values["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("l.owner_name = %(owner)s")
        values["owner"] = owner_val

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    return frappe.db.sql(
        f"""
        SELECT
            l.name,
            l.lead_name,
            l.company_name,
            l.phone_number,
            l.email,
            l.service,
            l.leads_type,
            l.leads_from,
            l.owner_name,
            u.full_name AS owner_full_name,
            l.creation,
            l.modified
        FROM `tabLead` l
        LEFT JOIN `tabUser` u ON u.name = l.owner_name
        {where_clause}
        ORDER BY l.creation DESC
        """,
        values,
        as_dict=True
    )


# ------------------------------------------------------
# SUMMARY (KPI CARDS)
# ------------------------------------------------------
def get_summary(data):
    total = len(data)
    incoming = sum(1 for d in data if d.get("leads_type") == "Incoming")
    outgoing = sum(1 for d in data if d.get("leads_type") == "Outgoing")

    return [
        {
            "label": "Total Leads",
            "value": total,
            "indicator": "Blue"
        },
        {
            "label": "Incoming Leads",
            "value": incoming,
            "indicator": "Green"
        },
        {
            "label": "Outgoing Leads",
            "value": outgoing,
            "indicator": "Orange"
        }
    ]


