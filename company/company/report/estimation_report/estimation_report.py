import frappe
import json
from frappe import _

def execute(filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)
    summary = get_summary(filters)

    return columns, data, None, None, summary

def get_columns():
    return [
        {"label": _("Ref No"), "fieldname": "name", "fieldtype": "Link", "options": "Estimation", "width": 120},
        {"label": _("Client"), "fieldname": "customer_name", "fieldtype": "Data", "width": 150},
        {"label": _("Company"), "fieldname": "company_name", "fieldtype": "Data", "width": 150},
        {"label": _("Estimate Date"), "fieldname": "estimate_date", "fieldtype": "Date", "width": 110},
        {"label": _("Qty"), "fieldname": "quantity", "fieldtype": "Float", "width": 80},
        {"label": _("Price"), "fieldname": "price", "fieldtype": "Currency", "width": 100},
        {"label": _("Total Tax"), "fieldname": "tax_amount", "fieldtype": "Currency", "width": 110},
        {"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 130},
    ]

def get_data(filters):
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
            e.name,
            e.customer_name,
            e.client_name,
            e.billing_name,
            e.estimate_date,
            e.grand_total,
            e.total_amount as price,
            e.total_qty as quantity,
            a.account_name as company_name,
            SUM(i.tax_amount) as tax_amount,
            e.creation,
            e.modified
        FROM `tabEstimation` e
        LEFT JOIN `tabAccounts` a ON a.name = e.billing_name
        LEFT JOIN `tabEstimation Items` i ON i.parent = e.name
        {where}
        GROUP BY 
            e.name,
            e.customer_name,
            e.client_name,
            e.billing_name,
            e.estimate_date,
            e.grand_total,
            e.total_amount,
            e.total_qty,
            a.account_name,
            e.creation,
            e.modified
        ORDER BY e.estimate_date DESC
    """
    return frappe.db.sql(query, query_filters, as_dict=True)

def get_summary(filters):
    conditions = []
    query_filters = {}

    if filters.get("client_name"):
        conditions.append("client_name = %(client_name)s")
        query_filters["client_name"] = filters["client_name"]
    if filters.get("billing_name"):
        conditions.append("billing_name = %(billing_name)s")
        query_filters["billing_name"] = filters["billing_name"]
    if filters.get("from_date"):
        conditions.append("estimate_date >= %(from_date)s")
        query_filters["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("estimate_date <= %(to_date)s")
        query_filters["to_date"] = filters["to_date"]
    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("owner = %(owner)s")
        query_filters["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("owner = %(owner)s")
        query_filters["owner"] = owner_val

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    totals = frappe.db.sql(f"""
        SELECT
            SUM(grand_total) AS total_amount,
            SUM(total_qty) AS total_qty
        FROM `tabEstimation`
        {where}
    """, query_filters, as_dict=True)[0]

    count_filters = []
    if filters.get("client_name"):
        count_filters.append(["client_name", "=", filters["client_name"]])
    if filters.get("billing_name"):
        count_filters.append(["billing_name", "=", filters["billing_name"]])
    if filters.get("from_date"):
        count_filters.append(["estimate_date", ">=", filters["from_date"]])
    if filters.get("to_date"):
        count_filters.append(["estimate_date", "<=", filters["to_date"]])
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        count_filters.append(["owner", "=", owner_filter])
    elif owner_val and owner_val != "all":
        count_filters.append(["owner", "=", owner_val])

    estimation_count = frappe.db.count("Estimation", filters=count_filters)

    return [
        {
            "label": "Total Amount",
            "value": totals.total_amount or 0,
            "indicator": "blue",
            "datatype": "Currency"
        },
        {
            "label": "Total Quantity",
            "value": totals.total_qty or 0,
            "indicator": "green",
            "datatype": "Float"
        },
        {
            "label": "Estimation Records",
            "value": estimation_count,
            "indicator": "orange"
        }
    ]
