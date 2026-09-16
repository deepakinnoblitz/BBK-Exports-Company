
frappe.ui.form.on("Manual Chat Message", {
    onload: function (frm) {
        if (!frm.doc.sender) {
            frm.set_value("sender", frappe.session.user);
        }
    },
    refresh: function (frm) {
        if (frm.doc.select_all_users) {
            frm.trigger("select_all_users");
        }

        frm.add_custom_button(__("View Message Queue"), () => {
            frappe.set_route("List", "Chat Message Queue", {
                manual_chat_message: frm.docname
            });
        });
    },
    send_message: function (frm) {
        if (frm.doc.receivers && frm.doc.receivers.length > 0) {
            frappe.confirm(__("Are you sure you want to send this message to {0} recipients?", [frm.doc.receivers.length]), () => {
                frm.call("send_bulk_messages").then(r => {
                    if (r.message && r.message.success > 0) {
                        frm.refresh();
                    }
                });
            });
        } else {
            frappe.msgprint(__("Please add at least one receiver."));
        }
    },
    select_all_users: function (frm) {
        if (frm.doc.select_all_users) {
            frappe.call({
                method: "company.company.doctype.manual_chat_message.manual_chat_message.get_all_users",
                callback: function (r) {
                    if (r.message) {
                        frm.clear_table("receivers");
                        r.message.forEach(user => {
                            let row = frm.add_child("receivers");
                            row.receiver = user;
                        });
                        frm.refresh_field("receivers");
                        frappe.show_alert(__("Added {0} users to receivers list", [r.message.length]));
                    }
                }
            });
        }
    },
    test_scheduled_send: function (frm) {
        frm.call("test_scheduled_send").then(r => {
            if (r.message) {
                frappe.msgprint(r.message);
            }
        });
    }
});
