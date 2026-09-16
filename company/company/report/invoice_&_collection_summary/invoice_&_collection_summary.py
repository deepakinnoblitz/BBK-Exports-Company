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
        {"label": "Invoice No", "fieldname": "invoice", "fieldtype": "Link", "options": "Invoice", "width": 150},
        {"label": "Date", "fieldname": "collection_date", "fieldtype": "Date", "width": 110},
        {"label": "Mode", "fieldname": "mode_of_payment", "fieldtype": "Link", "options": "Payment Type", "width": 120},
        {"label": "Amount to Pay", "fieldname": "amount_to_pay", "fieldtype": "Currency", "width": 120},
        {"label": "Amount", "fieldname": "amount_collected", "fieldtype": "Currency", "width": 120},
        {"label": "Pending", "fieldname": "amount_pending", "fieldtype": "Currency", "width": 120},
    ]


# ---------------------------------------------------
#  MAIN DATA
# ---------------------------------------------------
def get_data(filters):

    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("ic.collection_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("ic.collection_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("customer"):
        conditions.append("(ic.customer_name LIKE %(customer)s OR ic.customer LIKE %(customer)s)")
        values["customer"] = f"%{filters['customer']}%"

    if filters.get("invoice"):
        conditions.append("ic.invoice = %(invoice)s")
        values["invoice"] = filters["invoice"]

    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("ic.owner = %(owner)s")
        values["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("ic.owner = %(owner)s")
        values["owner"] = owner_val

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    collections = frappe.db.sql(f"""
        SELECT
            ic.name AS id,
            ic.invoice,
            ic.collection_date,
            ic.mode_of_payment,
            ic.amount_to_pay,
            ic.amount_collected,
            ic.amount_pending,
            ic.customer,
            ic.customer_name,
            ic.creation,
            ic.modified
        FROM `tabInvoice Collection` ic
        WHERE {where_clause}
        ORDER BY ic.collection_date DESC, ic.creation DESC
    """, values, as_dict=True)

    return collections or []


# ---------------------------------------------------
#  SUMMARY CARDS
# ---------------------------------------------------
def get_summary(data):

    total_to_pay = sum(flt(d.get("amount_to_pay")) for d in data)
    total_collected = sum(flt(d.get("amount_collected")) for d in data)
    total_pending = sum(flt(d.get("amount_pending")) for d in data)

    return [
        {
            "label": "Total Amount to Pay",
            "value": total_to_pay,
            "indicator": "blue",
            "datatype": "Currency",
        },
        {
            "label": "Total Collected",
            "value": total_collected,
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



