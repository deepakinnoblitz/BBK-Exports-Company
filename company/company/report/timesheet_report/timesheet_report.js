frappe.query_reports["Timesheet Report"] = {
    "filters": [
        {
            fieldname: "employee",
            label: __("Employee"),
            fieldtype: "Link",
            options: "Employee",
            reqd: 0,
            default: "",   // ❗ remove email default
            hidden: 0
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "Link",
            options: "Project",
        },
        {
            fieldname: "activity_type",
            label: __("Activity Type"),
            fieldtype: "Link",
            options: "Activity Type",
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_start()
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today()
        }
    ],

    // 🚀 Set correct employee linked to current user
    onload: function(report) {
        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Employee",
                filters: { user: frappe.session.user },
                fieldname: "name"
            },
            callback: function(r) {
                if (r.message) {

                    // Fill Employee filter correctly
                    report.set_filter_value("employee", r.message.name);

                    // OPTIONAL → Make it read-only (if needed)
                    // report.filters[0].df.read_only = 1;
                    // report.refresh_filter("employee");
                }
            }
        });
    }
};
