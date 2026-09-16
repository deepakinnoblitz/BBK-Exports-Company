// Copyright (c) 2026, Innoblitz and contributors
// For license information, please see license.txt

frappe.ui.form.on("Permission Management", {
	backend_master_role: function(frm) {
		if (frm.doc.backend_master_role) {
			frm.trigger("populate_default_permissions");
		}
	},

	populate_default_permissions: function(frm) {
		frm.call({
			doc: frm.doc,
			method: "populate_default_permissions",
			callback: function(r) {
				frm.refresh_field("permissions");
			}
		});
	}
});

// Auto-check View if Add, Edit, Delete or Export is selected
frappe.ui.form.on("Permission Access", {
	add_permission: function(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		if (row.add_permission && !row.view_permission) {
			frappe.model.set_value(cdt, cdn, "view_permission", 1);
		}
	},
	edit_permission: function(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		if (row.edit_permission && !row.view_permission) {
			frappe.model.set_value(cdt, cdn, "view_permission", 1);
		}
	},
	delete_permission: function(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		if (row.delete_permission && !row.view_permission) {
			frappe.model.set_value(cdt, cdn, "view_permission", 1);
		}
	},
	export_permission: function(frm, cdt, cdn) {
		let row = frappe.get_doc(cdt, cdn);
		if (row.export_permission && !row.view_permission) {
			frappe.model.set_value(cdt, cdn, "view_permission", 1);
		}
	}
});
