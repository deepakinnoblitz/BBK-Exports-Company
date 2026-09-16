frappe.ui.form.on("Purchase Collection", {
    refresh(frm) {
        // Any refresh logic if needed
    },
    purchase(frm) {
        if (frm.doc.purchase) {
            frappe.db.get_doc("Purchase", frm.doc.purchase).then((purchase) => {
                const amount_to_pay = purchase.balance_amount || purchase.grand_total || 0;
                frm.set_value("amount_to_pay", amount_to_pay);

                // Initial pending = amount_to_pay - amount_collected
                const collected = frm.doc.amount_collected || 0;
                frm.set_value("amount_pending", Math.max(0, amount_to_pay - collected));
            });
        }
    },
    amount_collected(frm) {
        const to_pay = frm.doc.amount_to_pay || 0;
        const collected = frm.doc.amount_collected || 0;
        frm.set_value("amount_pending", Math.max(0, to_pay - collected));
    }
});
