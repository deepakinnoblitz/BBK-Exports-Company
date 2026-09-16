// =================== Expense FORM SCRIPT ===================
frappe.ui.form.on("Expense", {

    onload_post_render(frm) {
        // Set today's date by default
        if (!frm.doc.date) {
            frm.set_value("date", frappe.datetime.get_today());
        }

        // Attach live calculation listener for child table inputs
        const wrapper = frm.fields_dict.table_qecz?.grid.wrapper;
        if (wrapper) {
            wrapper.on("input",
                'input[data-fieldname="quantity"], input[data-fieldname="price"]',
                () => calculate_totals(frm)
            );
        }

        // Initial calculation
        calculate_totals(frm);
        
    },

    table_qecz_add(frm) {
        calculate_totals(frm);
    },

    table_qecz_remove(frm) {
        calculate_totals(frm);
    }
});

// =================== CHILD TABLE SCRIPT ===================
frappe.ui.form.on("Expense Items", {

    quantity(frm, cdt, cdn) {
        update_row(frm, cdt, cdn);
    },

    price(frm, cdt, cdn) {
        update_row(frm, cdt, cdn);
    },
    amount(frm, cdt, cdn) {
        calculate_totals(frm);
    }
});

// =================== HELPER FUNCTIONS ===================
function update_row(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    // Calculate row amount
    row.amount = flt((row.quantity || 0) * (row.price || 0));

    frm.refresh_field("table_qecz");

    // Update total
    calculate_totals(frm);
}

function calculate_totals(frm) {
    let total = 0;

    (frm.doc.table_qecz || []).forEach(row => {
        total += flt(row.amount || 0);
    });

    frm.set_value("total", total);
    frm.refresh_field("total");
}
