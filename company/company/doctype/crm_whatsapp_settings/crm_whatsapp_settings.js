frappe.ui.form.on('CRM WhatsApp Settings', {
    refresh(frm) {

        toggle_whatsapp_fields(frm);

        frm.add_custom_button('Test Connection', () => {
            frappe.call({
                method: 'company.company.crm_whatsapp_api.test_connection',
                freeze: true,
                freeze_message: 'Testing Connection...',
                callback(r) {
                    if (r.message?.success) {
                        frappe.show_alert({
                            message: 'WhatsApp Connected Successfully ✅',
                            indicator: 'green'
                        });
                    } else {
                        frappe.msgprint({
                            title: 'Error',
                            indicator: 'red',
                            message: r.message?.error || 'Connection Failed'
                        });
                    }
                }
            });
        });

        frm.add_custom_button('Send WhatsApp Message', () => {
            frappe.prompt(
                [
                    {
                        label: 'Phone Number',
                        fieldname: 'phone',
                        fieldtype: 'Data',
                        reqd: 1
                    },
                    {
                        label: 'Message',
                        fieldname: 'message',
                        fieldtype: 'Long Text'
                    },
                    {
                        label: 'Attachment',
                        fieldname: 'attachment',
                        fieldtype: 'Attach'
                    }
                ],
                (values) => {
                    frappe.call({
                        method: 'company.company.crm_whatsapp_api.send_whatsapp',
                        args: {
                            phone: values.phone,
                            message: values.message,
                            attachment: values.attachment
                        },
                        freeze: true,
                        freeze_message: 'Sending WhatsApp Message...',
                        callback(r) {
                            if (r.message?.success) {
                                frappe.show_alert({
                                    message: 'WhatsApp Message Sent Successfully ✅',
                                    indicator: 'green'
                                });
                            } else {
                                frappe.msgprint({
                                    title: 'WhatsApp Error',
                                    indicator: 'red',
                                    message:
                                        r.message?.error?.error?.message ||
                                        r.message?.error ||
                                        'Failed to send message'
                                });
                            }
                        }
                    });
                },
                'Send WhatsApp Message',
                'Send'
            );
        });

        frm.add_custom_button('Copy Webhook URL', () => {
            const webhook_url =
                window.location.origin +
                '/api/method/company.company.crm_whatsapp_webhook.webhook';
            if (
                navigator.clipboard &&
                navigator.clipboard.writeText
            ) {
                navigator.clipboard.writeText(webhook_url)
                    .then(() => {
                        frappe.show_alert({
                            message: 'Webhook URL Copied ✅',
                            indicator: 'green'
                        });
                    });
            } else {
                const textarea =
                    document.createElement('textarea');
                textarea.value = webhook_url;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);

                frappe.show_alert({
                    message: 'Webhook URL Copied ✅',
                    indicator: 'green'
                });
            }
        });
    },

    enable_whatsapp(frm) {
        toggle_whatsapp_fields(frm);
    }
});

function toggle_whatsapp_fields(frm) {

    const fields = [
        'token_type',

        'access_token',
        'phone_number_id',
        'business_account_id',
        'verify_token',
        'webhook_secret',
        'connection_status',
        'last_connected_on'
    ];

    fields.forEach(field => {
        frm.toggle_display(
            field,
            frm.doc.enable_whatsapp
        );
    });
}