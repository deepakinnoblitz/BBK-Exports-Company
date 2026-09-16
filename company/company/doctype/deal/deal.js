frappe.ui.form.on("Deal", {

    refresh(frm) {
        frm._previous_stage = frm.doc.stage;
        frm.__whatsapp_processing = false;
    },

    before_save(frm) {

        if (frm.is_new()) {
            return;
        }

        // Prevent recursion
        if (frm.__whatsapp_processing) {
            frm.__whatsapp_processing = false;
            return;
        }

        // Stage not changed
        if (frm.doc.stage === frm._previous_stage) {
            return;
        }

        frappe.validated = false;

        show_whatsapp_automation_dialog(frm);
    },

    after_save(frm) {
        frm._previous_stage = frm.doc.stage;
    }

});


function show_whatsapp_automation_dialog(frm) {

    frappe.call({

        method:
            "company.company.doctype.crm_whatsapp_automation.crm_whatsapp_automation.get_automation_preview",

        args: {
            doctype: frm.doc.doctype,
            docname: frm.doc.name,
            current_state: frm.doc.stage,
            previous_state: frm._previous_stage
        },

        callback(r) {

            if (!r.message) {

                frm.__whatsapp_processing = true;
                frappe.validated = true;
                frm.save();

                return;
            }

            const automation = r.message;

            // Auto Send
            if (!automation.show_confirmation) {

                frappe.call({

                    method:
                        "company.company.doctype.crm_whatsapp_automation.crm_whatsapp_automation.send_automation_message",

                    args: {
                        automation_name: automation.automation_name,
                        doctype: frm.doc.doctype,
                        docname: frm.doc.name
                    },

                    callback() {

                        frm.__whatsapp_processing = true;
                        frappe.validated = true;
                        frm.save();

                    }

                });

                return;
            }

            const dialog = new frappe.ui.Dialog({

                title: automation.title || __("Send WhatsApp Message"),

                size: "large",

                fields: [
                    {
                        fieldtype: "HTML",
                        fieldname: "preview"
                    }
                ],

                primary_action_label: __("Send Message"),

                primary_action() {

                    dialog.disable_primary_action();

                    frappe.call({

                        method:
                            "company.company.doctype.crm_whatsapp_automation.crm_whatsapp_automation.send_automation_message",

                        freeze: true,
                        freeze_message: __("Sending WhatsApp..."),

                        args: {
                            automation_name: automation.automation_name,
                            doctype: frm.doc.doctype,
                            docname: frm.doc.name
                        },

                        callback() {

                            dialog.hide();

                            frappe.show_alert({
                                message: __("WhatsApp Message Sent"),
                                indicator: "green"
                            });

                            frm.__whatsapp_processing = true;
                            frappe.validated = true;
                            frm.save();

                        },

                        error() {

                            dialog.hide();

                            frappe.msgprint({
                                title: __("Error"),
                                indicator: "red",
                                message: __("Unable to send WhatsApp message.")
                            });

                        }

                    });

                },

                secondary_action_label: __("Skip"),

                secondary_action() {

                    dialog.hide();

                    frm.__whatsapp_processing = true;
                    frappe.validated = true;
                    frm.save();

                }

            });

            dialog.show();

            dialog.fields_dict.preview.$wrapper.html(`

                <div style="
                    padding:16px;
                    background:#f8fafc;
                    border-radius:8px;
                    border:1px solid #e5e7eb;
                ">

                    <div style="
                        font-size:15px;
                        font-weight:600;
                        margin-bottom:12px;
                    ">
                        ${automation.message || "Do you want to send this WhatsApp message?"}
                    </div>

                    <div style="
                        background:#e7ffdb;
                        border:1px solid #d1d5db;
                        border-radius:10px;
                        padding:14px;
                        white-space:pre-wrap;
                        max-height:300px;
                        overflow:auto;
                        line-height:1.6;
                    ">
${frappe.utils.escape_html(automation.preview)}
                    </div>

                </div>

            `);

        }

    });

}