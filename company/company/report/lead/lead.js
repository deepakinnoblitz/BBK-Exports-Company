frappe.query_reports["Lead"] = {
	filters: [
		{
			fieldname: "from_date",
			label: "From Date",
			fieldtype: "Date"
		},
		{
			fieldname: "to_date",
			label: "To Date",
			fieldtype: "Date"
		},
		{
			fieldname: "leads_type",
			label: "Leads Type",
			fieldtype: "Select",
			options: "\nIncoming\nOutgoing"
		},
		{
			fieldname: "leads_from",
			label: "Leads From",
			fieldtype: "Link",
			options: "Lead From"
		},
		{
			fieldname: "owner",
			label: "Owner",
			fieldtype: "Link",
			options: "User"
		}
	]
};