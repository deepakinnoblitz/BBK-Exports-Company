frappe.query_reports["Expense Report"] = {
    "filters": [
        {
            "fieldname": "expense_category",
            "label": "Expense Category",
            "fieldtype": "Data"
        },
        {
            "fieldname": "payment_type",
            "label": "Payment Type",
            "fieldtype": "Link",
            "options": "Payment Type"
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
