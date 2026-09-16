import frappe
import json

def execute(filters=None):

    # Convert JSON to dict
    if isinstance(filters, str):
        filters = json.loads(filters)

    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)
    summary = get_summary(filters)

    # MUST RETURN 5 VALUES!
    return columns, data, None, None, summary



# ----------------------------------
#  TABLE COLUMNS
# ----------------------------------
def get_columns():
    return [
        {"label": "Purchase ID", "fieldname": "name", "fieldtype": "Link", "options": "Purchase", "width": 120},
        {"label": "Vendor Name", "fieldname": "vendor_name", "fieldtype": "Link", "options": "Contacts", "width": 140},
        {"label": "Bill No", "fieldname": "bill_no", "fieldtype": "Data", "width": 120},
        {"label": "Bill Date", "fieldname": "bill_date", "fieldtype": "Date", "width": 110},
        {"label": "Payment Type", "fieldname": "payment_type", "fieldtype": "Link", "options": "Payment Type", "width": 120},

        {"label": "Item", "fieldname": "service", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": "HSN Code", "fieldname": "hsn_code", "fieldtype": "Data", "width": 100},
        {"label": "Description", "fieldname": "description", "fieldtype": "Data", "width": 150},
        {"label": "Qty", "fieldname": "quantity", "fieldtype": "Float", "width": 80},
        {"label": "Price", "fieldname": "price", "fieldtype": "Currency", "width": 100},
        {"label": "Discount", "fieldname": "discount", "fieldtype": "Currency", "width": 100},
        {"label": "Tax Type", "fieldname": "tax_type", "fieldtype": "Data", "width": 120},
        {"label": "Tax Amount", "fieldname": "tax_amount", "fieldtype": "Currency", "width": 110},
        {"label": "Subtotal", "fieldname": "sub_total", "fieldtype": "Currency", "width": 120},

        {"label": "Grand Total", "fieldname": "grand_total", "fieldtype": "Currency", "width": 130},
    ]


# ----------------------------------
#  MAIN TABLE DATA
# ----------------------------------
def get_data(filters):
    conditions = []
    query_filters = {}

    if filters.get("vendor"):
        conditions.append("p.vendor_name = %(vendor)s")
        query_filters["vendor"] = filters["vendor"]

    if filters.get("from_date"):
        conditions.append("p.bill_date >= %(from_date)s")
        query_filters["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("p.bill_date <= %(to_date)s")
        query_filters["to_date"] = filters["to_date"]

    has_permission = frappe.db.exists("User Permission", {"user": frappe.session.user})
    owner_val = filters.get("owner")
    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        conditions.append("p.owner = %(owner)s")
        query_filters["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        conditions.append("p.owner = %(owner)s")
        query_filters["owner"] = owner_val

    where = " AND ".join(conditions)
    if where:
        where = "WHERE " + where

    query = f"""
        SELECT
            p.name,
            p.vendor_name,
            v.first_name as vendor_real_name,
            p.bill_no,
            p.bill_date,
            p.payment_type,
            p.grand_total,
            c.service,
            c.hsn_code,
            c.description,
            c.quantity,
            c.price,
            c.discount,
            c.tax_type,
            c.tax_amount,
            c.sub_total,
            p.creation,
            p.modified
        FROM `tabPurchase` p
        LEFT JOIN `tabContacts` v ON v.name = p.vendor_name
        LEFT JOIN `tabPurchase Items` c ON c.parent = p.name
        {where}
        ORDER BY p.bill_date DESC
    """

    return frappe.db.sql(query, query_filters, as_dict=True)


# ----------------------------------
#  SUMMARY CARDS (ONLY THIS YOU WANT)
# ----------------------------------
def get_summary(filters):
    conditions = []
    query_filters = {}

    if filters.get("vendor"):
        conditions.append("vendor_name = %(vendor)s")
        query_filters["vendor"] = filters["vendor"]

    if filters.get("from_date"):
        conditions.append("bill_date >= %(from_date)s")
        query_filters["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("bill_date <= %(to_date)s")
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
            SUM(grand_total) AS total_purchase,
            SUM(total_qty) AS total_qty
        FROM `tabPurchase`
        {where}
    """, query_filters, as_dict=True)[0]

    total_purchase = totals.total_purchase or 0
    total_qty = totals.total_qty or 0

    # Safe count
    count_filters_for_db_count = {}

    if filters.get("vendor"):
        count_filters_for_db_count["vendor_name"] = filters["vendor"]

    if filters.get("from_date"):
        count_filters_for_db_count["bill_date"] = (">=", filters["from_date"])

    if filters.get("to_date"):
        count_filters_for_db_count["bill_date"] = ("<=", filters["to_date"])

    if has_permission:
        owner_filter = owner_val if (owner_val and owner_val != "all") else frappe.session.user
        count_filters_for_db_count["owner"] = owner_filter
    elif owner_val and owner_val != "all":
        count_filters_for_db_count["owner"] = owner_val

    purchase_count = frappe.db.count("Purchase", filters=count_filters_for_db_count)

    return [
        {
            "label": "Total Purchase Amount",
            "value": total_purchase,
            "indicator": "blue",
            "datatype": "Currency"
        },
        {
            "label": "Total Quantity Purchased",
            "value": total_qty,
            "indicator": "green",
            "datatype": "Float"
        },
        {
            "label": "Purchase Records",
            "value": purchase_count,
            "indicator": "orange"
        }
    ]
