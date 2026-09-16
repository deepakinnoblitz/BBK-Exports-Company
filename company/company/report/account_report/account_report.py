import frappe


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters or {})
    summary = get_summary(data)

    # Order is important
    return columns, data, None, None, summary


# ------------------------------------------------------
# COLUMNS
# ------------------------------------------------------
def get_columns():
    return [
        {
            "label": "Account Name",
            "fieldname": "account_name",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": "Phone Number",
            "fieldname": "phone_number",
            "fieldtype": "Phone",
            "width": 140
        },
        {
            "label": "Website",
            "fieldname": "website",
            "fieldtype": "Data",
            "width": 180
        },
        {
            "label": "GSTIN",
            "fieldname": "gstin",
            "fieldtype": "Data",
            "width": 150
        },
        {
            "label": "Country",
            "fieldname": "country",
            "fieldtype": "Link",
            "options": "Country",
            "width": 120
        },
        {
            "label": "State",
            "fieldname": "state",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": "City",
            "fieldname": "city",
            "fieldtype": "Data",
            "width": 120
        },
        {
            "label": "Owner",
            "fieldname": "owner_name",
            "fieldtype": "Link",
            "options": "User",
            "width": 150
        }
    ]


# ------------------------------------------------------
# DATA
# ------------------------------------------------------
def get_data(filters):
    conditions = []
    values = {}

    if filters.get("account_name"):
        conditions.append("a.account_name LIKE %(account_name)s")
        values["account_name"] = f"%{filters['account_name']}%"

    if filters.get("country"):
        conditions.append("a.country = %(country)s")
        values["country"] = filters["country"]

    if filters.get("state"):
        conditions.append("a.state = %(state)s")
        values["state"] = filters["state"]

    if filters.get("city"):
        conditions.append("a.city = %(city)s")
        values["city"] = filters["city"]

    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("a.owner_name = %(owner)s")
        values["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("a.owner_name = %(owner)s")
        values["owner"] = owner_val

    if filters.get("from_date"):
        conditions.append("DATE(a.creation) >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("DATE(a.creation) <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    return frappe.db.sql(
        f"""
        SELECT
            a.name,
            a.account_name,
            a.phone_number,
            a.website,
            a.gstin,
            a.country,
            a.state,
            a.city,
            a.owner_name,
            u.full_name AS owner_full_name,
            a.creation,
            a.modified
        FROM `tabAccounts` a
        LEFT JOIN `tabUser` u ON u.name = a.owner_name
        {where_clause}
        ORDER BY a.creation DESC
        """,
        values,
        as_dict=True
    )


# ------------------------------------------------------
# SUMMARY (KPI CARDS)
# ------------------------------------------------------
def get_summary(data):
    total = len(data)
    with_gstin = sum(1 for d in data if d.get("gstin"))
    with_website = sum(1 for d in data if d.get("website"))
    with_phone = sum(1 for d in data if d.get("phone_number"))

    return [
        {
            "label": "Total Accounts",
            "value": total,
            "indicator": "Blue"
        },
        {
            "label": "With GSTIN",
            "value": with_gstin,
            "indicator": "Green"
        },
        {
            "label": "With Website",
            "value": with_website,
            "indicator": "Purple"
        },
        {
            "label": "With Phone",
            "value": with_phone,
            "indicator": "Orange"
        }
    ]
