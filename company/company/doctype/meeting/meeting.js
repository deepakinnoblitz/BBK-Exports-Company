
frappe.ui.form.on("Meeting", {
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
