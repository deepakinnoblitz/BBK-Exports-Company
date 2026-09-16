// Copyright (c) 2026, deepak and contributors
// For license information, please see license.txt

frappe.ui.form.on("Task Manager", {
	// Validate hours_spent format live when user types/changes the field
	hours_spent(frm) {
		validate_hours_format(frm);
	},

	// Also validate on form save (before_save client trigger)
	before_save(frm) {
		if (frm.doc.status === "Completed") {
			if (!validate_hours_format(frm)) {
				frappe.validated = false;
			}
		}
	},

	department(frm) {
		// If department changes, reset the fetch checkbox and clear assignees
		frm.set_value("fetch_from_department", 0);
		frm.clear_table("assignees");
		// Add one empty row so the table isn't totally empty
		frm.add_child("assignees");
		frm.refresh_field("assignees");
	},

	fetch_from_department(frm) {
		if (frm.doc.fetch_from_department && frm.doc.department) {
			frappe.call({
				method: "company.company.doctype.task_manager.task_manager.get_employees_from_department",
				args: {
					department: frm.doc.department
				},
				callback: function(r) {
					if (r.message && r.message.length > 0) {
						// ALWAYS CLEAR existing assignees when fetching from department as requested
						frm.clear_table("assignees");
						
						r.message.forEach(emp => {
							let row = frm.add_child("assignees");
							row.employee = emp.name;
							row.employee_name = emp.employee_name;
							row.user = emp.user; 
							row.department = emp.department;
						});

						frm.refresh_field("assignees");
						frappe.show_alert({message: __("Replaced assignees with employees from {0}", [frm.doc.department]), indicator: "green"});
					} else {
						frappe.msgprint(__("No employees found in this department."));
						frm.set_value("fetch_from_department", 0);
					}
				}
			});
		} else if (frm.doc.fetch_from_department && !frm.doc.department) {
			frappe.msgprint(__("Please select a Department first."));
			frm.set_value("fetch_from_department", 0);
		}
	},

	// Show/hide Close Task section based on status
	status(frm) {
		toggle_close_section(frm);
	},

	refresh(frm) {
		toggle_close_section(frm);

		// Add a prominent "Close Task" button when status is Open or In Progress
		if (["Open", "In Progress", "Review", "Reopened"].includes(frm.doc.status) && !frm.is_new()) {
			frm.add_custom_button(__("Close Task"), function () {
				show_close_task_dialog(frm);
			}, ).addClass("btn-primary");
		}

		// Add a "Reopen Task" button for HR/System Manager when task is Completed
		if (frm.doc.status === "Completed" && !frm.is_new()) {
			const user_roles = frappe.user_roles;
			if (user_roles.includes("HR") || user_roles.includes("System Manager")) {
				frm.add_custom_button(__("Reopen Task"), function () {
					frappe.confirm(
						__("Are you sure you want to Reopen this task?"),
						function () {
							frappe.call({
								method: "company.company.doctype.task_manager.task_manager.reopen_task",
								args: { task_name: frm.doc.name },
								callback(r) {
									if (r.message) {
										frappe.show_alert({ message: __("Task Reopened"), indicator: "orange" });
										frm.reload_doc();
									}
								},
							});
						}
					);
				}, ).addClass("btn-warning");
			}
		}
	},
});

/**
 * Validates the HH:MM format of hours_spent.
 * Returns true if valid, false if invalid.
 */
function validate_hours_format(frm) {
	const val = frm.doc.hours_spent;

	// Only validate if a value has been entered
	if (!val) return true;

	const hhmm_regex = /^([0-9]{1,5}):([0-5][0-9])$/;

	if (!hhmm_regex.test(val)) {
		frappe.msgprint({
			title: __("Invalid Format"),
			message: __("Hours Spent must be in <b>HH:MM</b> format. For example: <b>02:30</b> means 2 hours 30 minutes."),
			indicator: "red",
		});
		frm.set_value("hours_spent", "");
		frm.get_field("hours_spent").set_invalid();
		return false;
	}

	// Check that minutes part is valid (0-59)
	const parts = val.split(":");
	const minutes = parseInt(parts[1]);
	if (minutes > 59) {
		frappe.msgprint({
			title: __("Invalid Minutes"),
			message: __("Minutes must be between 00 and 59."),
			indicator: "red",
		});
		frm.set_value("hours_spent", "");
		return false;
	}

	frm.get_field("hours_spent").set_valid();
	return true;
}

/**
 * Show/hide the close task details section based on status.
 */
function toggle_close_section(frm) {
	const is_completed = frm.doc.status === "Completed";
	frm.set_df_property("close_task_section", "hidden", !is_completed);
	frm.set_df_property("hours_spent", "hidden", !is_completed);
	frm.set_df_property("remarks", "hidden", !is_completed);
	frm.set_df_property("closing_attachment", "hidden", !is_completed);
}

/**
 * Opens a dialog to collect Close Task details,
 * then calls the Python API endpoint.
 */
function show_close_task_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Close Task"),
		fields: [
			{
				label: __("Hours Spent"),
				fieldname: "hours_spent",
				fieldtype: "Data",
				reqd: 1,
				description: __("Format HH:MM — e.g. 02:30"),
			},
			{
				label: __("Remarks"),
				fieldname: "remarks",
				fieldtype: "Text Editor",
				reqd: 1,
			},
			{
				label: __("Attachment"),
				fieldname: "attachment",
				fieldtype: "Attach",
				reqd: frm.doc.attachment_required ? 1 : 0,
				description: frm.doc.attachment_required
					? __("This task requires an attachment to close.")
					: "",
			},
		],
		primary_action_label: __("Close Task"),
		primary_action(values) {
			// Validate HH:MM format inside the dialog
			const hhmm_regex = /^([0-9]{1,5}):([0-5][0-9])$/;
			if (!hhmm_regex.test(values.hours_spent)) {
				frappe.msgprint({
					title: __("Invalid Format"),
					message: __("Hours Spent must be in <b>HH:MM</b> format. Example: <b>02:30</b>"),
					indicator: "red",
				});
				return;
			}

			frappe.call({
				method: "company.company.doctype.task_manager.task_manager.close_task",
				args: {
					task_name: frm.doc.name,
					hours_spent: values.hours_spent,
					remarks: values.remarks,
					attachment: values.attachment || null,
				},
				callback(r) {
					if (r.message) {
						frappe.show_alert({ message: __("Task Closed Successfully"), indicator: "green" });
						dialog.hide();
						frm.reload_doc();
					}
				},
			});
		},
	});

	dialog.show();
}
