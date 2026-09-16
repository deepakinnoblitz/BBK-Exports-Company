// Copyright (c) 2025, deepak
// For license information, please see license.txt

frappe.ui.form.on("Upload Attendance", {
    refresh: function(frm) {
        if (frm.doc.attendance_file) {
            frm.add_custom_button(__('Import Attendance'), function() {
                frappe.call({
                    method: "company.company.doctype.upload_attendance.upload_attendance.import_attendance",
                    args: { docname: frm.doc.name },
                    callback: function(r) {
                        if (r.message) {
                            frappe.msgprint(r.message);
                            frm.reload_doc();
                        }
                    }
                });
            });
        }
    }
});
