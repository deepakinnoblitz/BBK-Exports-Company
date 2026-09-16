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
        {"label": "Name", "fieldname": "first_name", "fieldtype": "Data", "width": 180},
        {"label": "Company", "fieldname": "company_name", "fieldtype": "Data", "width": 180},
        {"label": "Email", "fieldname": "email", "fieldtype": "Data", "width": 200},
        {"label": "Phone", "fieldname": "phone", "fieldtype": "Phone", "width": 140},
        {"label": "Country", "fieldname": "country", "fieldtype": "Link", "options": "Country", "width": 120},
        {"label": "State", "fieldname": "state", "fieldtype": "Data", "width": 120},
        {"label": "City", "fieldname": "city", "fieldtype": "Data", "width": 120},
        {"label": "Source Lead", "fieldname": "source_lead", "fieldtype": "Link", "options": "Lead", "width": 150},
        {"label": "Owner", "fieldname": "owner_name", "fieldtype": "Link", "options": "User", "width": 150},
    ]


# ------------------------------------------------------
# DATA
# ------------------------------------------------------
def get_data(filters):
    conditions = []
    values = {}

    if filters.get("country"):
        conditions.append("c.country = %(country)s")
        values["country"] = filters["country"]

    if filters.get("state"):
        conditions.append("c.state = %(state)s")
        values["state"] = filters["state"]

    if filters.get("city"):
        conditions.append("c.city = %(city)s")
        values["city"] = filters["city"]

    if filters.get("source_lead"):
        conditions.append("c.source_lead = %(source_lead)s")
        values["source_lead"] = filters["source_lead"]

    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("c.owner_name = %(owner)s")
        values["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("c.owner_name = %(owner)s")
        values["owner"] = owner_val
    
    if filters.get("from_date"):
        conditions.append("DATE(c.creation) >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    
    if filters.get("to_date"):
        conditions.append("DATE(c.creation) <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

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
            c.country,
            c.state,
            c.city,
            c.source_lead,
            l.lead_name AS source_lead_name,
            c.owner_name,
            u.full_name AS owner_full_name,
            c.creation,
            c.modified
        FROM `tabContacts` c
        LEFT JOIN `tabLead` l ON l.name = c.source_lead
        LEFT JOIN `tabUser` u ON u.name = c.owner_name
        {where_clause}
        ORDER BY c.creation DESC
        """,
        values,
        as_dict=True
    )


# ------------------------------------------------------
# SUMMARY (KPI CARDS)
# ------------------------------------------------------
def get_summary(data):
    total = len(data)
    with_email = sum(1 for d in data if d.get("email"))
    with_phone = sum(1 for d in data if d.get("phone"))
    converted_from_lead = sum(1 for d in data if d.get("source_lead"))

    return [
        {
            "label": "Total Contacts",
            "value": total,
            "indicator": "Blue"
        },
        {
            "label": "With Email",
            "value": with_email,
            "indicator": "Green"
        },
        {
            "label": "With Phone",
            "value": with_phone,
            "indicator": "Orange"
        },
        {
            "label": "Converted from Lead",
            "value": converted_from_lead,
            "indicator": "Purple"
        }
    ]
