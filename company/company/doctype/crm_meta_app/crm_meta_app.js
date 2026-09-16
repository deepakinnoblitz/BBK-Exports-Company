// Copyright (c) 2026, deepak and contributors
// For license information, please see license.txt

frappe.ui.form.on("CRM Meta App", {
    refresh(frm) {
        let webhook_path = "/api/method/company.company.crm_meta_api.webhook";
        frm.set_value("webhook_url", frappe.urllib.get_base_url() + webhook_path);

        frm.add_custom_button(__("Copy Webhook URL"), function() {
            if (frm.doc.webhook_url) {
                let url = frm.doc.webhook_url;
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(url).then(() => {
                        frappe.show_alert({
                            message: __("Webhook URL copied to clipboard!"),
                            indicator: "green"
                        });
                    });
                } else {
                    let textarea = document.createElement("textarea");
                    textarea.value = url;
                    textarea.style.position = "fixed";
                    document.body.appendChild(textarea);
                    textarea.select();
                    try {
                        document.execCommand("copy");
                        frappe.show_alert({
                            message: __("Webhook URL copied to clipboard!"),
                            indicator: "green"
                        });
                    } catch (err) {
                        frappe.show_alert({
                            message: __("Failed to copy URL. Please copy manually."),
                            indicator: "red"
                        });
                    }
                    document.body.removeChild(textarea);
                }
            }
        });
    }
});
