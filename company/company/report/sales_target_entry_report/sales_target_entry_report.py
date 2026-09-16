# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters or {})
    report_summary = get_report_summary(data)

    return columns, data, None, None, report_summary


def get_columns():
    return [
        {
            "label": _("Sales Entry ID"),
            "fieldname": "sales_entry_id",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("Sales Person"),
            "fieldname": "sales_person",
            "fieldtype": "Link",
            "options": "User",
            "width": 160,
        },
        {
            "label": _("Month"),
            "fieldname": "month",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("In Date"),
            "fieldname": "in_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": _("Contact"),
            "fieldname": "contact_name",
            "fieldtype": "Link",
            "options": "Contacts",
            "width": 180,
        },
        {
            "label": _("Contact Number"),
            "fieldname": "contact_number",
            "fieldtype": "Phone",
            "width": 140,
        },
        {
            "label": _("Industry"),
            "fieldname": "industry",
            "fieldtype": "Data",
            "width": 140,
        },
        {
            "label": _("Lead Source"),
            "fieldname": "lead_source",
            "fieldtype": "Link",
            "options": "Lead From",
            "width": 140,
        },
        {
            "label": _("Service"),
            "fieldname": "service",
            "fieldtype": "Link",
            "options": "Service",
            "width": 160,
        },
        {
            "label": _("Value"),
            "fieldname": "value",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "label": _("Advance"),
            "fieldname": "advance",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "label": _("Balance"),
            "fieldname": "balance",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "label": _("GST Type"),
            "fieldname": "gst_type",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Status"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Out Date"),
            "fieldname": "out_date",
            "fieldtype": "Date",
            "width": 110,
        },
    ]


def get_data(filters):
    conditions = ""
    values = {}

    if filters.get("sales_person"):
        conditions += " AND sales_person = %(sales_person)s"
        values["sales_person"] = filters["sales_person"]

    if filters.get("month"):
        conditions += " AND month = %(month)s"
        values["month"] = filters["month"]

    if filters.get("status"):
        conditions += " AND status = %(status)s"
        values["status"] = filters["status"]

    if filters.get("from_date"):
        conditions += " AND in_date >= %(from_date)s"
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions += " AND in_date <= %(to_date)s"
        values["to_date"] = filters["to_date"]

    return frappe.db.sql(
        f"""
        SELECT
            sales_entry_id,
            sales_person,
            month,
            in_date,
            contact_name,
            contact_number,
            industry,
            lead_source,
            service,
            value,
            advance,
            balance,
            gst_type,
            status,
            out_date
        FROM `tabSales Target Entry`
        WHERE docstatus < 2
        {conditions}
        ORDER BY in_date DESC
        """,
        values,
        as_dict=True,
    )


def get_report_summary(data):
    total_sales = sum(flt(row.get("value")) for row in data)
    total_advance = sum(flt(row.get("advance")) for row in data)
    total_balance = sum(flt(row.get("balance")) for row in data)

    return [
        {
            "label": _("Total Sales"),
            "value": total_sales,
            "indicator": "Green",
            "datatype": "Currency",
        },
        {
            "label": _("Total Advance"),
            "value": total_advance,
            "indicator": "Blue",
            "datatype": "Currency",
        },
        {
            "label": _("Total Balance"),
            "value": total_balance,
            "indicator": "Orange",
            "datatype": "Currency",
        },
        {
            "label": _("Total Entries"),
            "value": len(data),
            "indicator": "Purple",
            "datatype": "Int",
        },
    ]