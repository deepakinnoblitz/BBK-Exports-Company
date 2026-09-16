
import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data

def get_columns():
    return [
        {"label": "Asset", "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 150},
        {"label": "Asset Name", "fieldname": "asset_name", "fieldtype": "Data", "width": 200},
        {"label": "Assigned To", "fieldname": "assigned_to", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Assigned On", "fieldname": "assigned_on", "fieldtype": "Date", "width": 150},
        {"label": "Returned On", "fieldname": "returned_on", "fieldtype": "Date", "width": 150},
    ]

def get_data(filters):
    conditions = []
    values = {}

    if filters.get("asset"):
        conditions.append("aa.asset = %(asset)s")
        values["asset"] = filters["asset"]

    if filters.get("assigned_to"):
        conditions.append("aa.assigned_to = %(assigned_to)s")
        values["assigned_to"] = filters["assigned_to"]

    if filters.get("from_date"):
        conditions.append("aa.assigned_on >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("aa.assigned_on <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("returned_status") == "Returned":
        conditions.append("aa.returned_on IS NOT NULL")
    elif filters.get("returned_status") == "Not Returned":
        conditions.append("aa.returned_on IS NULL")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT
            aa.asset,
            a.asset_name,
            aa.assigned_to,
            e.employee_name,
            aa.assigned_on,
            aa.returned_on
        FROM `tabAsset Assignment` aa
        LEFT JOIN `tabAsset` a ON a.name = aa.asset
        LEFT JOIN `tabEmployee` e ON e.name = aa.assigned_to
        WHERE {where_clause}
        ORDER BY aa.assigned_on DESC
    """

    return frappe.db.sql(query, values, as_dict=True)
