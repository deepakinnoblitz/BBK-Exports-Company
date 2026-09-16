// Copyright (c) 2026, Administrator and contributors
// For license information, please see license.txt

frappe.ui.form.on("HR Document Template", {
	refresh(frm) {
		frm.trigger("load_available_variables");
	},
	document_for(frm) {
		frm.trigger("load_available_variables");
	},
	load_available_variables(frm) {
		frappe.call({
			method: "company.company.doctype.hr_document_template.hr_document_template.get_document_template_variables",
			args: {
				document_for: frm.doc.document_for || "Employee"
			},
			callback(r) {
				if (r.message) {
					let formatted_vars = r.message.map(
						v => `${v.label}: ${v.variable} (${v.fieldtype})`
					).join("\n");
					frm.set_value("available_variables", formatted_vars);
				}
			}
		});
	}
});
