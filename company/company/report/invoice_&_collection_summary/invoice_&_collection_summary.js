
// Copyright (c) 2025, deepak and contributors
// For license information, please see license.txt

frappe.query_reports["Invoice & Collection Summary"] = {
    "filters": [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
            reqd: 1
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1
        },
        {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Contacts"
        },
        {
            fieldname: "invoice",
            label: __("Invoice"),
            fieldtype: "Link",
            options: "Invoice"
        }
    ]
};
