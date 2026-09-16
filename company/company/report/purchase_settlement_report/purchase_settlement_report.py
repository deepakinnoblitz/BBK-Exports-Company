import frappe
from frappe.utils import flt
import json


def execute(filters=None):

    # Convert JSON to dict (Frappe sends filters as string)
    if isinstance(filters, str):
        filters = json.loads(filters)

    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)
    summary = get_summary(data)

    # Return 5 values → (columns, rows, message, chart, summary)
    return columns, data, None, None, summary


# ---------------------------------------------------
#  COLUMNS
# ---------------------------------------------------
def get_columns():
    return [
        {"label": "ID", "fieldname": "id", "fieldtype": "Data", "width": 120},
        {"label": "Purchase No", "fieldname": "purchase", "fieldtype": "Link", "options": "Purchase", "width": 150},
        {"label": "Date", "fieldname": "collection_date", "fieldtype": "Date", "width": 110},
        {"label": "Vendor", "fieldname": "vendor", "fieldtype": "Link", "options": "Contacts", "width": 150},
        {"label": "Vendor Name", "fieldname": "vendor_name", "fieldtype": "Data", "width": 150},
        {"label": "Mode", "fieldname": "mode_of_payment", "fieldtype": "Link", "options": "Payment Type", "width": 120},
        {"label": "Amount to Pay", "fieldname": "amount_to_pay", "fieldtype": "Currency", "width": 120},
        {"label": "Paid", "fieldname": "amount_collected", "fieldtype": "Currency", "width": 120},
        {"label": "Pending", "fieldname": "amount_pending", "fieldtype": "Currency", "width": 120},
    ]


# ---------------------------------------------------
#  MAIN DATA
# ---------------------------------------------------
def get_data(filters):

    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("pc.collection_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("pc.collection_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("vendor"):
        conditions.append("(pc.vendor_name LIKE %(vendor)s OR pc.vendor LIKE %(vendor)s)")
        values["vendor"] = f"%{filters['vendor']}%"

    if filters.get("purchase"):
        conditions.append("pc.purchase = %(purchase)s")
        values["purchase"] = filters["purchase"]

    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("pc.owner = %(owner)s")
        values["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("pc.owner = %(owner)s")
        values["owner"] = owner_val

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    settlements = frappe.db.sql(f"""
        SELECT
            pc.name AS id,
            pc.purchase,
            pc.collection_date,
            pc.mode_of_payment,
            pc.amount_to_pay,
            pc.amount_collected,
            pc.amount_pending,
            pc.vendor,
            pc.vendor_name,
            pc.creation,
            pc.modified
        FROM `tabPurchase Collection` pc
        WHERE {where_clause}
        ORDER BY pc.collection_date DESC, pc.creation DESC
    """, values, as_dict=True)

    return settlements or []


# ---------------------------------------------------
#  SUMMARY CARDS
# ---------------------------------------------------
def get_summary(data):

    total_to_pay = sum(flt(d.get("amount_to_pay")) for d in data)
    total_paid = sum(flt(d.get("amount_collected")) for d in data)
    total_pending = sum(flt(d.get("amount_pending")) for d in data)

    return [
        {
            "label": "Total Purchase Amount",
            "value": total_to_pay,
            "indicator": "blue",
            "datatype": "Currency",
        },
        {
            "label": "Total Paid",
            "value": total_paid,
            "indicator": "green",
            "datatype": "Currency",
        },
        {
            "label": "Total Pending",
            "value": total_pending,
            "indicator": "red",
            "datatype": "Currency",
        }
    ]