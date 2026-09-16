frappe.query_reports["Purchase Settlement Report"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today()
        },
        {
            "fieldname": "vendor",
            "label": __("Vendor"),
            "fieldtype": "Link",
            "options": "Contacts"
        },
        {
            "fieldname": "purchase",
            "label": __("Purchase"),
            "fieldtype": "Link",
            "options": "Purchase"
        }
    ]
};