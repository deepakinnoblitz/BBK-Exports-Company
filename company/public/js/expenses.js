// =================== EXPENSES FORM SCRIPT ===================
frappe.ui.form.on("Expenses", {
    onload_post_render: function (frm) {

        // Auto set today's date if empty
        if (!frm.doc.date) {
            frm.set_value("date", frappe.datetime.get_today());
        }

        // TRUE REALTIME LIVE CALCULATION FOR CHILD TABLE ROWS
        frm.fields_dict.table_qecz.grid.wrapper.on("keyup", "input", function (e) {
            const row = frm.fields_dict.table_qecz.grid.get_selected_row();
            if (!row) return;

            let doc = row.doc;

            // Get live-typed quantity + price
            let qty = flt(row.get_field('quantity').$input.val());
            let price = flt(row.get_field('price').$input.val());

            doc.quantity = qty;
            doc.price = price;
            doc.amount = qty * price;

            // Refresh only amount cell, not whole grid
            row.refresh_field("amount");

            // Update totals live
            calculate_expenses_totals_live(frm);
        });

        // Initial totals on load
        calculate_expenses_totals_live(frm);
    },

    validate: function (frm) {

        // Remove empty rows
        if (frm.doc.table_qecz && frm.doc.table_qecz.length > 0) {
            frm.doc.table_qecz = frm.doc.table_qecz.filter(r => r.items);
            frm.refresh_field("table_qecz");
        }

        // Must have 1 row
        if (!frm.doc.table_qecz || frm.doc.table_qecz.length === 0) {
            frappe.msgprint("Please add at least one item to Expenses");
            frappe.validated = false;
        }

        // Price cannot be zero
        let invalid = frm.doc.table_qecz.some(r => flt(r.price) <= 0);
        if (invalid) {
            frappe.msgprint("Price cannot be zero for items");
            frappe.validated = false;
        }

        calculate_expenses_totals_live(frm);
    },

    table_qecz_remove: function (frm) {
        calculate_expenses_totals_live(frm);
    }
});


// =================== GET NEXT NUMBER ===================
frappe.ui.form.on("Expenses", {
    onload: function (frm) {
        if (!frm.doc.expense_no) {
            frappe.call({
                method: "company.company.api.get_next_expense_preview",
                callback: function (r) {
                    if (r.message) {
                        frm.set_value('expense_no', r.message);
                    }
                }
            });
        }
    }
});

// =================== CHILD TABLE SCRIPT ===================
frappe.ui.form.on("Expenses Items", {
    quantity: function (frm, cdt, cdn) {
        update_child_and_total(frm, cdt, cdn);
    },
    price: function (frm, cdt, cdn) {
        update_child_and_total(frm, cdt, cdn);
    }
});

// =================== HELPER FUNCTIONS ===================
function update_child_and_total(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    row.amount = (row.quantity || 0) * (row.price || 0);

    // Refresh just the amount column
    frm.fields_dict.table_qecz.grid.get_row(cdn).refresh_field("amount");

    calculate_expenses_totals_live(frm);
}

function calculate_expenses_totals_live(frm) {
    let total = 0;

    (frm.doc.table_qecz || []).forEach(r => {
        total += flt(r.amount);
    });

    frm.set_value("total", total);
    frm.refresh_field("total");
}
