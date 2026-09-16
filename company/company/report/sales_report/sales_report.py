import frappe
import json

@frappe.whitelist()
def execute(filters=None):

    # Ensure filters is a dict
    if isinstance(filters, str):
        filters = json.loads(filters)

    if not filters:
        filters = {}

    # Columns
    columns = [
        {"fieldname": "client_name", "label": "Client Name", "fieldtype": "Data", "width": 200},
        {"fieldname": "invoice_no", "label": "Invoice No", "fieldtype": "Link", "options": "Invoice", "width": 160},
        {"fieldname": "invoice_date", "label": "Invoice Date", "fieldtype": "Date", "width": 120},
        {"fieldname": "item", "label": "Item", "fieldtype": "Data", "width": 160},
        {"fieldname": "qty", "label": "Qty", "fieldtype": "Float", "width": 80},
        {"fieldname": "price", "label": "Price", "fieldtype": "Currency", "width": 120},
        {"fieldname": "grand_total", "label": "Invoice Total", "fieldtype": "Currency", "width": 150},
        {"fieldname": "received_amount", "label": "Received", "fieldtype": "Currency", "width": 150},
        {"fieldname": "balance_amount", "label": "Pending", "fieldtype": "Currency", "width": 150},
    ]

    # SQL Conditions
    conditions = []

    if filters.get("from_date"):
        conditions.append(f"inv.invoice_date >= '{filters['from_date']}'")

    if filters.get("to_date"):
        conditions.append(f"inv.invoice_date <= '{filters['to_date']}'")

    if filters.get("customer"):
        conditions.append(f"inv.client_name = '{filters['customer']}'")

    if filters.get("item"):
        conditions.append(f"child.service = '{filters['item']}'")

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    # GROUP BY logic
    group_by = ""
    if filters.get("group_by_invoice"):
        group_by = "GROUP BY inv.name"

    # Main Query
    query = f"""
        SELECT
            inv.client_name,
            inv.name AS invoice_no,
            inv.invoice_date,
            child.service AS item,
            child.quantity AS qty,
            child.price AS price,
            inv.grand_total,
            inv.received_amount,
            inv.balance_amount

        FROM `tabInvoice` inv
        LEFT JOIN `tabInvoice Items` child ON child.parent = inv.name

        {where}
        {group_by}

        ORDER BY inv.invoice_date DESC
    """

    data = frappe.db.sql(query, as_dict=True)

    # Totals (for summary cards)
    totals = frappe.db.sql(f"""
        SELECT
            SUM(grand_total) AS total_sales,
            SUM(received_amount) AS total_received,
            SUM(balance_amount) AS total_pending
        FROM `tabInvoice` inv
        {where.replace("inv.", "")}
    """, as_dict=True)[0]

    total_sales = totals.total_sales or 0
    total_received = totals.total_received or 0
    total_pending = totals.total_pending or 0

    # Ratio calculations
    received_percent = (total_received / total_sales * 100) if total_sales else 0
    pending_percent = (total_pending / total_sales * 100) if total_sales else 0

    # Report Summary Cards
    report_summary = [
        {"label": "Total Sales Amount", "value": total_sales, "indicator": "blue", "datatype": "Currency"},
        {"label": f"Received Amount ({received_percent:.1f}%)",
         "value": total_received,
         "indicator": "green" if received_percent >= 50 else "orange",
         "datatype": "Currency"},
        {"label": f"Pending Amount ({pending_percent:.1f}%)",
         "value": total_pending,
         "indicator": "red" if total_pending > 0 else "green",
         "datatype": "Currency"},
    ]

    # Pie Chart
    chart = {
        "data": {
            "labels": ["Received", "Pending"],
            "datasets": [{"values": [total_received, total_pending]}]
        },
        "type": "pie",
        "colors": ["#22c55e", "#ef4444"]
    }

    summary_data = {
        "total_sales": total_sales,
        "received_sales": total_received,
        "pending_sales": total_pending,
        "invoice_count": len(data)
    }

    return columns, data, summary_data, chart, report_summary
