frappe.query_reports["Contact Report"] = {
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
			fieldname: "country",
			label: "Country",
			fieldtype: "Link",
			options: "Country"
		},
		{
			fieldname: "state",
			label: "State",
			fieldtype: "Data"
		},
		{
			fieldname: "city",
			label: "City",
			fieldtype: "Data"
		},
		{
			fieldname: "source_lead",
			label: "Source Lead",
			fieldtype: "Link",
			options: "Lead"
		},
		{
			fieldname: "owner",
			label: "Owner",
			fieldtype: "Link",
			options: "User"
		}
	]
};
