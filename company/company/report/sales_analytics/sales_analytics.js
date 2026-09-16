
// Copyright (c) 2025, deepak and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Analytics"] = {
    "filters": [

        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1)
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.get_today()
        },
        {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Contacts",
            reqd: 0
        },
        {
            fieldname: "group_by_invoice",
            label: __("Group by Invoice"),
            fieldtype: "Check",
            default: 1
        }
    ]
};
