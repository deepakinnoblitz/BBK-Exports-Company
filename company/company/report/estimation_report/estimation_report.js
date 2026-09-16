frappe.query_reports["Estimation Report"] = {
	filters: [
		{
			"fieldname": "client_name",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Contacts"
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
	],
};
