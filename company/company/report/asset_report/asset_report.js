// Path: your_app/your_app/report/asset_assignment_report/asset_assignment_report.js
frappe.query_reports["Asset Report"] = {
    "filters": [
        {
            "fieldname": "asset",
            "label": __("Asset"),
            "fieldtype": "Link",
            "options": "Asset"
        },
        {
            "fieldname": "assigned_to",
            "label": __("Assigned To"),
            "fieldtype": "Link",
            "options": "Employee"
        },
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date"
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date"
        },
        {
            "fieldname": "returned_status",
            "label": __("Returned Status"),
            "fieldtype": "Select",
            "options": "\nReturned\nNot Returned"
        }
    ]
};
