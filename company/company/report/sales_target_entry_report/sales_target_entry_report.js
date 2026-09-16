// Copyright (c) 2026, deepak and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Target Entry Report"] = {
    filters: [
        {
            fieldname: "sales_person",
            label: __("Sales Person"),
            fieldtype: "Link",
            options: "User",
        },
        {
            fieldname: "month",
            label: __("Month"),
            fieldtype: "Select",
            options:
                "\nJanuary\nFebruary\nMarch\nApril\nMay\nJune\nJuly\nAugust\nSeptember\nOctober\nNovember\nDecember",
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options:
                "\nNew\nConfirmed\nIn Progress\nCompleted\nHold\nCancelled",
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
        },
    ],
};