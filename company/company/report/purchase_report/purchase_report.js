// Copyright (c) 2025, deepak and contributors
// For license information, please see license.txt

frappe.query_reports["Purchase Report"] = {
    "filters": [
        {
            "fieldname": "vendor",
            "label": "Vendor",
            "fieldtype": "Link",
            "options": "Contacts",
            "get_query": function () {
                return {
                    "filters": {
                        "customer_type": "Purchase"
                    }
                };
            }
        },
        {
            "fieldname": "from_date",
            "label": "From Date",
            "fieldtype": "Date"
        },
        {
            "fieldname": "to_date",
            "label": "To Date",
            "fieldtype": "Date"
        }
    ]
};
