frappe.ui.form.on("Employee", {
    profile_picture: function(frm) {
        if (frm.doc.user) {
            frappe.db.set_value("User", frm.doc.user, "user_image", frm.doc.profile_picture);
        }
    }
});
