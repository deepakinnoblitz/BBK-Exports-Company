frappe.query_reports["Calls Report"] = {
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
      fieldname: "call_for",
      label: "Call For",
      fieldtype: "Select",
      options: "\nLead\nContact\nAccounts"
    },
    {
      fieldname: "status",
      label: "Call Status",
      fieldtype: "Select",
      options: "\nScheduled\nCompleted"
    },
    {
      fieldname: "owner_name",
      label: "Call Owner",
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
