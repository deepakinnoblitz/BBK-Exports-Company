frappe.ui.form.on("Invoice Collection", {
    invoice: function(frm) {
        if (frm.doc.invoice) {
            frappe.db.get_doc("Invoice", frm.doc.invoice).then(invoice_doc => {
                frm.set_value("customer", invoice_doc.client_name);

                // Get total already collected for this invoice
                frappe.db.get_list("Invoice Collection", {
                    filters: { invoice: frm.doc.invoice },
                    fields: ["amount_collected"]
                }).then(existing => {
                    let total_collected = 0;
                    if (existing && existing.length) {
                        total_collected = existing.reduce((sum, r) => sum + (r.amount_collected || 0), 0);
                    }

                    const remaining = invoice_doc.grand_total - total_collected;
                    frm.set_value("amount_to_pay", remaining);

                    // Initial pending = remaining - this collection (usually 0 on load)
                    const collected_now = frm.doc.amount_collected || 0;
                    frm.set_value("amount_pending", remaining - collected_now);
                });
            });
        }
    },
    refresh: function(frm) {
        if (frm.fields_dict.amount_collected) {
            $(frm.fields_dict.amount_collected.input).on("input", function() {
                const pay = frm.doc.amount_to_pay || 0;
                const collected_now = flt($(this).val());
                frm.set_value("amount_pending", pay - collected_now);
            });
        }
    }
});
