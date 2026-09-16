import frappe
import json
from frappe import _


def execute(filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)
    summary = get_summary(data)

    return columns, data, None, None, summary


def get_columns():
    return [
        {"label": _("Deal ID"), "fieldname": "name", "fieldtype": "Link", "options": "Deal", "width": 140},
        {"label": _("Title"), "fieldname": "deal_title", "fieldtype": "Data", "width": 200},
        {"label": _("Client Name"), "fieldname": "contact_name", "fieldtype": "Data", "width": 160},
        {"label": _("Client ID"), "fieldname": "contact", "fieldtype": "Link", "options": "Contacts", "width": 140},
        {"label": _("Company Name"), "fieldname": "company_name", "fieldtype": "Data", "width": 160},
        {"label": _("Company ID"), "fieldname": "account", "fieldtype": "Link", "options": "Accounts", "width": 140},
        {"label": _("Stage"), "fieldname": "stage", "fieldtype": "Data", "width": 130},
    ]


def get_data(filters):
    conditions = []
    query_filters = {}

    if filters.get("contact"):
        conditions.append("d.contact = %(contact)s")
        query_filters["contact"] = filters["contact"]

    if filters.get("account"):
        conditions.append("d.account = %(account)s")
        query_filters["account"] = filters["account"]

    if filters.get("stage") and filters.get("stage") != "all":
        conditions.append("d.stage = %(stage)s")
        query_filters["stage"] = filters["stage"]

    if filters.get("from_date"):
        conditions.append("DATE(d.creation) >= %(from_date)s")
        query_filters["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("DATE(d.creation) <= %(to_date)s")
        query_filters["to_date"] = filters["to_date"]

    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("d.owner = %(owner)s")
        query_filters["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("d.owner = %(owner)s")
        query_filters["owner"] = owner_val

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    query = f"""
        SELECT
            d.name,
            d.deal_title,
            d.contact,
            c.first_name AS contact_name,
            d.account,
            a.account_name AS company_name,
            d.stage,
            d.creation,
            d.modified,
            d.owner
        FROM `tabDeal` d
        LEFT JOIN `tabContacts` c ON c.name = d.contact
        LEFT JOIN `tabAccounts` a ON a.name = d.account
        {where}
        ORDER BY d.creation DESC
    """
    return frappe.db.sql(query, query_filters, as_dict=True)


def get_summary(data):
    total = len(data)
    closed = sum(1 for d in data if d.get("stage") == "Closed")
    active = total - closed

    return [
        {"label": _("Total Prospects"), "value": total, "indicator": "blue"},
        {"label": _("Active Prospects"), "value": active, "indicator": "green"},
        {"label": _("Closed Prospects"), "value": closed, "indicator": "orange"},
    ]
