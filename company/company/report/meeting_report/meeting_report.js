frappe.query_reports["Meeting Report"] = {
  filters: [
    {
      fieldname: "from_date",
      label: "From Date",
      fieldtype: "Datetime"
    },
    {
      fieldname: "to_date",
      label: "To Date",
      fieldtype: "Datetime"
    },
    {
      fieldname: "meet_for",
      label: "Meet For",
      fieldtype: "Select",
      options: "\nLead\nContact\nAccount\nOthers"
    },
    {
      fieldname: "status",
      label: "Meet Status",
      fieldtype: "Select",
      options: "\nScheduled\nCompleted"
    },
    {
      fieldname: "owner",
      label: "Owner",
      fieldtype: "Link",
      options: "User"
    },
    {
      fieldname: "enable_reminder",
      label: "Reminder Enabled",
      fieldtype: "Check"
    }
  ]
};
