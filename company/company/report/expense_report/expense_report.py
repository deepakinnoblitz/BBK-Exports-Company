import frappe
from frappe.utils import flt
import json


def execute(filters=None):

    # Convert JSON to dict if needed
    if isinstance(filters, str):
        filters = json.loads(filters)

    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)
    summary = get_summary(data, filters)

    # MUST return 5 items for Frappe Query Report
    return columns, data, None, None, summary


# ---------------------------------------------------
#  COLUMNS
# ---------------------------------------------------
def get_columns():
    return [
        {"label": "Expense No", "fieldname": "expense_no", "fieldtype": "Link", "options": "Expenses", "width": 130},
        {"label": "Expense Category", "fieldname": "expense_category", "fieldtype": "Data", "width": 140},
        {"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 110},
        {"label": "Payment Type", "fieldname": "payment_type", "fieldtype": "Link", "options": "Payment Type", "width": 120},

        {"label": "Item", "fieldname": "items", "fieldtype": "Data", "width": 150},
        {"label": "Quantity", "fieldname": "quantity", "fieldtype": "Float", "width": 80},
        {"label": "Price", "fieldname": "price", "fieldtype": "Currency", "width": 100},
        {"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 120},

        {"label": "Total", "fieldname": "total", "fieldtype": "Currency", "width": 130},
    ]


# ---------------------------------------------------
#  DATA
# ---------------------------------------------------
def get_data(filters):
    conditions = []
    query_filters = {}

    if filters.get("expense_category"):
        conditions.append("e.expense_category LIKE %(expense_category)s")
        query_filters["expense_category"] = f"%{filters['expense_category']}%"

    if filters.get("payment_type"):
        conditions.append("e.payment_type = %(payment_type)s")
        query_filters["payment_type"] = filters["payment_type"]

    if filters.get("from_date"):
        conditions.append("e.date >= %(from_date)s")
        query_filters["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("e.date <= %(to_date)s")
        query_filters["to_date"] = filters["to_date"]

    condition_sql = " AND ".join(conditions)
    if condition_sql:
        condition_sql = "WHERE " + condition_sql

    query = f"""
        SELECT
            e.name,
            e.expense_no,
            e.expense_category,
            e.date,
            e.payment_type,
            e.total,
            c.items,
            c.quantity,
            c.price,
            c.amount
        FROM `tabExpenses` e
        LEFT JOIN `tabExpenses Items` c ON c.parent = e.name
        {condition_sql}
        ORDER BY e.date DESC
    """

    return frappe.db.sql(query, query_filters, as_dict=True)

def get_summary(data, filters):
    conditions = []
    query_filters = {}

    if filters.get("expense_category"):
        conditions.append("expense_category LIKE %(expense_category)s")
        query_filters["expense_category"] = f"%{filters['expense_category']}%"

    if filters.get("payment_type"):
        conditions.append("payment_type = %(payment_type)s")
        query_filters["payment_type"] = filters["payment_type"]

    if filters.get("from_date"):
        conditions.append("date >= %(from_date)s")
        query_filters["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("date <= %(to_date)s")
        query_filters["to_date"] = filters["to_date"]

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    res = frappe.db.sql(f"""
        SELECT 
            SUM(total) as total_expense,
            COUNT(*) as record_count
        FROM `tabExpenses`
        {where}
    """, query_filters, as_dict=True)[0]

    total_qty = sum(flt(d.get("quantity")) for d in data)

    return [
        {"label": "Total Expense Amount", "value": flt(res.total_expense), "indicator": "blue", "datatype": "Currency"},
        {"label": "Total Quantity", "value": total_qty, "indicator": "green", "datatype": "Float"},
        {"label": "Expense Records", "value": res.record_count, "indicator": "orange"},
    ]


