// Copyright (c) 2026, Administrator and contributors
// For license information, please see license.txt

frappe.ui.form.on("HR Document Generation", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Preview / Re-Render"), function() {
				frm.save();
			});
		}
	},
	employee(frm) {
		if (frm.doc.employee) {
			frappe.db.get_value("Employee", frm.doc.employee, "employee_name", (r) => {
				if (r && r.employee_name) {
					frm.set_value("employee_name", r.employee_name);
				}
			});
		}
	},
	document_template(frm) {
		if (frm.doc.document_template) {
			frappe.db.get_value("HR Document Template", frm.doc.document_template, ["category", "subject", "template_content"], (r) => {
				if (r) {
					if (r.category) frm.set_value("document_type", r.category);
					if (!frm.doc.subject && r.subject) frm.set_value("subject", r.subject);
					if (!frm.doc.template_content && r.template_content) frm.set_value("template_content", r.template_content);
				}
			});
		}
	}
});
