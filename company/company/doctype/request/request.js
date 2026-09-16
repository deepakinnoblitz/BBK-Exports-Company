// Copyright (c) 2025, deepak and contributors
// For license information, please see license.txt

frappe.ui.form.on("Request", {
    subject(frm) {
        // Character limit is now handled by backend validate or can be added here with a higher limit
    },

    after_save: function (frm) {
        if (frm.doc.docstatus === 0) {
            frappe.call({
                method: "frappe.client.submit",
                args: {
                    doc: frm.doc  // ✅ pass the full document, not just name
                },
                callback: function (r) {
                    if (!r.exc) {
                        frappe.msgprint("✅ Request submitted.");
                        frappe.set_route("Form", frm.doc.doctype, frm.doc.name);
                    }
                }
            });
        }
    },

    refresh(frm) {
        // Remove specific workflow actions from Actions menu
        setTimeout(() => {
            if (frm.page.actions) {
                frm.page.actions.find('li').each(function () {
                    const label = $(this).find('.menu-item-label').text().trim();
                    if (["Ask Clarification", "Reply", "Help"].includes(label)) {
                        $(this).remove();
                    }
                });

                if (frm.page.actions.find('.menu-item-label').length === 0) {
                    frm.page.actions_btn_group.hide();
                } else {
                    frm.page.actions_btn_group.show();
                }
            }
        }, 300);

        // HR → Reply to Employee
        if (
            frm.doc.workflow_state === "Pending" &&
            frappe.user.has_role("HR")
        ) {
            frm.add_custom_button(
                "Reply to Employee",
                () => {
                    const rounds = ["hr_query", "hr_query_2", "hr_query_3", "hr_query_4", "hr_query_5"];
                    let next_field = rounds.find(field => !frm.doc[field]);

                    if (!next_field) {
                        frappe.msgprint(__("Maximum communication rounds (5) reached."));
                        return;
                    }

                    frappe.prompt(
                        [
                            {
                                fieldname: "query",
                                label: "HR Question",
                                fieldtype: "Small Text",
                                reqd: 1
                            }
                        ],
                        (values) => {
                            frm.set_value(next_field, values.query);

                            frappe.confirm(
                                "Do you want to send this clarification request to the employee?",
                                () => {
                                    const save_action = frm.doc.docstatus === 1 ? 'Update' : 'Save';
                                    frm.save(save_action).then(() => {
                                        frappe.xcall("frappe.model.workflow.apply_workflow", {
                                            doc: frm.doc,
                                            action: "Ask Clarification"
                                        }).then(doc => {
                                            frappe.model.sync(doc);
                                            frm.refresh();
                                        });
                                    });
                                },
                                () => {
                                    frm.reload_doc();
                                }
                            );
                        },
                        "Reply to Employee"
                    );
                },
                null
            );
            frm.change_custom_button_type("Reply to Employee", null, "primary");
        }

        // Employee → Reply
        if (
            frm.doc.workflow_state === "Clarification Requested" &&
            frappe.user.has_role("Employee")
        ) {
            frm.add_custom_button(
                "Reply to HR",
                () => {
                    const hr_rounds = ["hr_query", "hr_query_2", "hr_query_3", "hr_query_4", "hr_query_5"];
                    const emp_rounds = ["employee_reply", "employee_reply_2", "employee_reply_3", "employee_reply_4", "employee_reply_5"];

                    let round_index = -1;
                    for (let i = 0; i < 5; i++) {
                        if (frm.doc[hr_rounds[i]] && !frm.doc[emp_rounds[i]]) {
                            round_index = i;
                            break;
                        }
                    }

                    if (round_index === -1) {
                        frappe.msgprint(__("No pending HR queries to reply to."));
                        return;
                    }

                    let next_field = emp_rounds[round_index];

                    frappe.prompt(
                        [
                            {
                                fieldname: "reply",
                                label: "Your Reply",
                                fieldtype: "Small Text",
                                reqd: 1
                            }
                        ],
                        (values) => {
                            frm.set_value(next_field, values.reply);

                            frappe.confirm(
                                "Are you sure you want to submit your reply to HR?",
                                () => {
                                    const save_action = frm.doc.docstatus === 1 ? 'Update' : 'Save';
                                    frm.save(save_action).then(() => {
                                        frappe.xcall("frappe.model.workflow.apply_workflow", {
                                            doc: frm.doc,
                                            action: "Reply"
                                        }).then(doc => {
                                            frappe.model.sync(doc);
                                            frm.refresh();
                                        });
                                    });
                                },
                                () => {
                                    frm.reload_doc();
                                }
                            );
                        },
                        "Reply to HR"
                    );
                },
                null
            );
            frm.change_custom_button_type("Reply to HR", null, "primary");
        }

        // Field Editability during clarification
        if (frm.doc.docstatus === 1) {
            const editable_fields = ["subject", "message"];
            const can_edit = frm.doc.workflow_state === "Clarification Requested" && frappe.user.has_role("Employee");

            let sync_count = 0;
            const sync_timer = setInterval(() => {
                const read_only = can_edit ? 0 : 1;
                editable_fields.forEach(f => {
                    frm.set_df_property(f, "read_only", read_only);
                });
                sync_count++;
                if (sync_count >= 5) clearInterval(sync_timer);
            }, 400);

            // Always display conversation fields after submit
            const conversation_fields = [
                "hr_query", "hr_query_2", "hr_query_3", "hr_query_4", "hr_query_5",
                "employee_reply", "employee_reply_2", "employee_reply_3", "employee_reply_4", "employee_reply_5"
            ];

            conversation_fields.forEach(f => {
                if (frm.fields_dict[f]) {
                    frm.toggle_display(f, true);
                    frm.set_df_property(f, "read_only", 1);
                    frm.refresh_field(f);
                }
            });
        }
    }
});
