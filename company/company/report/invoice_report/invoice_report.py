import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
    if isinstance(filters, str):
        import json
        filters = json.loads(filters)
    
    filters = filters or {}
    
    columns = get_columns()
    data = get_data(filters)
    summary = get_summary(filters)
    
    return columns, data, None, None, summary

def get_columns():
    return [
        {"label": _("Ref No"), "fieldname": "name", "fieldtype": "Link", "options": "Invoice", "width": 120},
        {"label": _("Client"), "fieldname": "customer_name", "fieldtype": "Data", "width": 150},
        {"label": _("Company"), "fieldname": "company_name", "fieldtype": "Data", "width": 150},
        {"label": _("Invoice Date"), "fieldname": "invoice_date", "fieldtype": "Date", "width": 110},
        {"label": _("Qty"), "fieldname": "quantity", "fieldtype": "Float", "width": 80},
        {"label": _("Price"), "fieldname": "price", "fieldtype": "Currency", "width": 100},
        {"label": _("Total Tax"), "fieldname": "tax_amount", "fieldtype": "Currency", "width": 110},
        {"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 120},
    ]

def get_data(filters):
    conditions = []
    params = {}

    if filters.get("client_name"):
        conditions.append("i.client_name = %(client_name)s")
        params["client_name"] = filters["client_name"]
    if filters.get("billing_name"):
        conditions.append("i.billing_name = %(billing_name)s")
        params["billing_name"] = filters["billing_name"]
    if filters.get("from_date"):
        conditions.append("i.invoice_date >= %(from_date)s")
        params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("i.invoice_date <= %(to_date)s")
        params["to_date"] = filters["to_date"]
    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("i.owner = %(owner)s")
        params["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("i.owner = %(owner)s")
        params["owner"] = owner_val

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    query = f"""
        SELECT
            i.name,
            i.customer_name,
            i.client_name,
            i.billing_name,
            i.invoice_date,
            i.grand_total,
            i.total_amount as price,
            i.total_qty as quantity,
            a.account_name as company_name,
            SUM(it.tax_amount) as tax_amount,
            i.creation,
            i.modified
        FROM `tabInvoice` i
        LEFT JOIN `tabAccounts` a ON a.name = i.billing_name
        LEFT JOIN `tabInvoice Items` it ON it.parent = i.name
        {where}
        GROUP BY 
            i.name,
            i.customer_name,
            i.client_name,
            i.billing_name,
            i.invoice_date,
            i.grand_total,
            i.total_amount,
            i.total_qty,
            a.account_name,
            i.creation,
            i.modified
        ORDER BY i.invoice_date DESC
    """
    return frappe.db.sql(query, params, as_dict=True)

def get_summary(filters):
    conditions = []
    params = {}
    count_filters = []

    if filters.get("client_name"):
        conditions.append("client_name = %(client_name)s")
        params["client_name"] = filters["client_name"]
        count_filters.append(["client_name", "=", filters["client_name"]])
        
    if filters.get("billing_name"):
        conditions.append("billing_name = %(billing_name)s")
        params["billing_name"] = filters["billing_name"]
        count_filters.append(["billing_name", "=", filters["billing_name"]])

    if filters.get("from_date"):
        conditions.append("invoice_date >= %(from_date)s")
        params["from_date"] = filters["from_date"]
        count_filters.append(["invoice_date", ">=", filters["from_date"]])
        
    if filters.get("to_date"):
        conditions.append("invoice_date <= %(to_date)s")
        params["to_date"] = filters["to_date"]
        count_filters.append(["invoice_date", "<=", filters["to_date"]])

    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("owner = %(owner)s")
        params["owner"] = owner_filter
        count_filters.append(["owner", "=", owner_filter])
    elif owner_val and owner_val != "all":
        conditions.append("owner = %(owner)s")
        params["owner"] = owner_val
        count_filters.append(["owner", "=", owner_val])

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    totals_res = frappe.db.sql(f"""
        SELECT
            SUM(grand_total) AS total_amount,
            SUM(total_qty) AS total_qty
        FROM `tabInvoice`
        {where}
    """, params, as_dict=True)
    
    totals = totals_res[0] if totals_res else frappe._dict(total_amount=0, total_qty=0)

    invoice_count = frappe.db.count("Invoice", filters=count_filters)

    return [
        {"label": _("Total Amount"), "value": flt(totals.total_amount), "indicator": "blue", "datatype": "Currency"},
        {"label": _("Total Quantity"), "value": flt(totals.total_qty), "indicator": "green", "datatype": "Float"},
        {"label": _("Invoice Records"), "value": invoice_count, "indicator": "orange"},
    ]
