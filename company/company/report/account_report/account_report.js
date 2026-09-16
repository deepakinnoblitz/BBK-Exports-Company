frappe.query_reports["Account Report"] = {
  filters: [
    {
      fieldname: "account_name",
      label: "Account Name",
      fieldtype: "Data"
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
      fieldname: "owner",
      label: "Owner",
      fieldtype: "Link",
      options: "User"
    }
  ]
};
