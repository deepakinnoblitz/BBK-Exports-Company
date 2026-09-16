frappe.query_reports["Proposal Report"] = {
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
			fieldname: "status",
			label: "Status",
			fieldtype: "Select",
			options: "\nDraft\nSent\nApproved\nRejected\nExpired"
		},
		{
			fieldname: "company_name",
			label: "Company Name",
			fieldtype: "Data"
		},
		{
			fieldname: "lead",
			label: "Lead",
			fieldtype: "Link",
			options: "Lead"
		}
	]
};
