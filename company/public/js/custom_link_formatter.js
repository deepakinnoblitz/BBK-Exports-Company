frappe.form.link_formatters['Employee'] = function(value, doc) {
    if (!value) return "";
    const employee_name = doc?.employee_name || doc?.__label || value;
    return `${employee_name} (${value})`;
};
