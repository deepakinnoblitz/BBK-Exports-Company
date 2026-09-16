// Redirection script for Employees from Desk to React Frontend
frappe.after_ajax(function () {
    // frappe.after_ajax ensures bootinfo (roles) is fully loaded before we run
    if (typeof frappe === 'undefined' || !frappe.user_roles) return;

    const isEmployee = frappe.user_roles.includes('Employee') || frappe.user_roles.includes('HR');
    const isAdmin = frappe.user_roles.includes('Administrator');

    if (isEmployee && !isAdmin) {
        // Redirect to the React SPA home page
        window.location.href = '/';
    }
});
