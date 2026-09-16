import frappe
from frappe import _

def execute(filters=None):
    if isinstance(filters, str):
        import json
        filters = json.loads(filters)
    
    filters = filters or {}
    
    columns = get_columns()
    data = get_data(filters)
    summary = get_summary(data)
    
    return columns, data, None, None, summary

def get_columns():
    return [
        {"label": _("Proposal No"), "fieldname": "name", "fieldtype": "Link", "options": "Proposal", "width": 140},
        {"label": _("Proposal Title"), "fieldname": "proposal_title", "fieldtype": "Data", "width": 200},
        {"label": _("Lead ID"), "fieldname": "lead", "fieldtype": "Link", "options": "Lead", "width": 140},
        {"label": _("Lead Name"), "fieldname": "lead_name", "fieldtype": "Data", "width": 150},
        {"label": _("Company Name"), "fieldname": "company_name", "fieldtype": "Data", "width": 180},
        {"label": _("Proposal Date"), "fieldname": "proposal_date", "fieldtype": "Date", "width": 110},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": _("Attachments"), "fieldname": "total_attachments", "fieldtype": "Int", "width": 100},
    ]

def get_data(filters):
    conditions = []
    params = {}

    if filters.get("lead") and filters.get("lead") != "all":
        conditions.append("lead = %(lead)s")
        params["lead"] = filters["lead"]
    if filters.get("status") and filters.get("status") != "all":
        conditions.append("status = %(status)s")
        params["status"] = filters["status"]
    if filters.get("company_name") and filters.get("company_name") != "all":
        conditions.append("company_name LIKE %(company_name)s")
        params["company_name"] = f"%{filters['company_name']}%"
    if filters.get("from_date"):
        conditions.append("proposal_date >= %(from_date)s")
        params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("proposal_date <= %(to_date)s")
        params["to_date"] = filters["to_date"]

    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("owner_name = %(owner)s")
        params["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("owner_name = %(owner)s")
        params["owner"] = owner_val

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    # Sort order is handled client-side or we can default to creation DESC
    query = f"""
        SELECT
            name,
            proposal_title,
            reference_no,
            lead,
            lead_name,
            company_name,
            proposal_date,
            status,
            total_attachments,
            owner_name,
            creation,
            modified
        FROM `tabProposal`
        {where}
        ORDER BY creation DESC
    """
    return frappe.db.sql(query, params, as_dict=True)

def get_summary(data):
    total = len(data)
    approved = sum(1 for d in data if d.get("status") == "Approved")
    pending = sum(1 for d in data if d.get("status") in ["Draft", "Sent"])

    return [
        {"label": _("Total Proposals"), "value": total, "indicator": "blue"},
        {"label": _("Approved Proposals"), "value": approved, "indicator": "green"},
        {"label": _("Pending Proposals"), "value": pending, "indicator": "orange"},
    ]
