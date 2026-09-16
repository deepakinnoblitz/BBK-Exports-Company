
frappe.ui.form.on("Calls", {
    refresh(frm) {
        toggle_reminder(frm);
        toggle_reminder_section(frm);

        if (!frm.doc.__islocal && frm.doc.outgoing_call_status !== "Scheduled") {

            frm.add_custom_button("Schedule Call", () => {

                frappe.new_doc("Calls", {

                    call_for: "Lead",
                    lead_name: frm.doc.lead_name,

                    title: `Followup Call with ${frm.doc.lead_name}  `
                });

            }, "Schedule");


            frm.add_custom_button("Schedule Meeting", () => {

                frappe.new_doc("Meeting", {

                    meet_for: "Lead",
                    lead_name: frm.doc.lead_name,

                    title: `Meet with ${frm.doc.lead_name} `
                });
            }, "Schedule");
        }
    },
    enable_reminder(frm) {
        toggle_reminder(frm);
    },
    outgoing_call_status(frm) {
        toggle_reminder_section(frm);
    },

    // Custom delete handler
    before_delete(frm) {
        // Check if there's a linked Event
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Event",
                fields: ["name"],
                filters: {
                    reference_doctype: "Calls",
                    reference_docname: frm.doc.name
                },
                limit: 1
            },
            async: false,
            callback: function (res) {
                if (res.message && res.message.length > 0) {
                    // Event is linked - show options
                    frappe.validated = false; // Prevent default delete
                    show_delete_options_dialog(frm, res.message[0].name);
                }
                // If no event linked, allow normal delete to proceed
            }
        });
    }
});

function toggle_reminder(frm) {
    frm.toggle_display(
        "remind_before_minutes",
        frm.doc.enable_reminder === 1
    );

    frm.toggle_reqd(
        "remind_before_minutes",
        frm.doc.enable_reminder === 1
    );
}


function toggle_reminder_section(frm) {
    const show = frm.doc.outgoing_call_status !== "Completed";
    frm.toggle_display("reminder_setting_section", show);
}

// Show delete options dialog
function show_delete_options_dialog(frm, event_id) {
    let d = new frappe.ui.Dialog({
        title: __("Delete Options"),
        indicator: "red",
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "delete_html",
                options: `
                    <p>The Call <b>${frm.doc.name}</b> is linked with Calendar Event <b>${event_id}</b>.</p>
                    <p>What would you like to do?</p>
                    <div style="margin-top: 15px;">
                        <button class="btn btn-danger btn-sm" id="delete_call_only_btn" style="margin-right: 10px;">
                            Delete Call Only
                        </button>
                        <button class="btn btn-danger" id="delete_both_btn">
                            Delete Call + Event
                        </button>
                    </div>
                `
            }
        ]
    });

    d.show();

    // Handle "Delete Call Only" button
    setTimeout(() => {
        d.$wrapper.find('#delete_call_only_btn').on('click', () => {
            d.hide();
            delete_call_only(frm);
        });

        // Handle "Delete Call + Event" button
        d.$wrapper.find('#delete_both_btn').on('click', () => {
            d.hide();
            delete_call_and_event(frm, event_id);
        });
    }, 100);
}

// Delete only the Call (unlink the Event first)
function delete_call_only(frm) {
    frappe.confirm(
        __('Are you sure you want to delete only the Call? The linked Event will remain in the calendar.'),
        () => {
            // First, unlink the event
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Event",
                    fields: ["name"],
                    filters: {
                        reference_doctype: "Calls",
                        reference_docname: frm.doc.name
                    },
                    limit: 1
                },
                callback: function (res) {
                    if (res.message && res.message.length > 0) {
                        let event_name = res.message[0].name;

                        // Unlink the event
                        frappe.call({
                            method: "frappe.client.set_value",
                            args: {
                                doctype: "Event",
                                name: event_name,
                                fieldname: {
                                    reference_doctype: null,
                                    reference_docname: null
                                }
                            },
                            callback: function () {
                                // Now delete the call
                                frappe.call({
                                    method: "frappe.client.delete",
                                    args: {
                                        doctype: "Calls",
                                        name: frm.doc.name
                                    },
                                    callback: function () {
                                        frappe.show_alert({
                                            message: __("Call deleted successfully. Event remains in calendar."),
                                            indicator: "green"
                                        });
                                        frappe.set_route("List", "Calls");
                                    }
                                });
                            }
                        });
                    }
                }
            });
        }
    );
}

// Delete both Call and Event
function delete_call_and_event(frm, event_id) {
    frappe.confirm(
        __('Are you sure you want to delete both the Call and the linked Event?'),
        () => {
            // First delete the event
            frappe.call({
                method: "frappe.client.delete",
                args: {
                    doctype: "Event",
                    name: event_id
                },
                callback: function () {
                    // Then delete the call
                    frappe.call({
                        method: "frappe.client.delete",
                        args: {
                            doctype: "Calls",
                            name: frm.doc.name
                        },
                        callback: function () {
                            frappe.show_alert({
                                message: __("Call and Event deleted successfully"),
                                indicator: "green"
                            });
                            frappe.set_route("List", "Calls");
                        }
                    });
                }
            });
        }
    );
}
