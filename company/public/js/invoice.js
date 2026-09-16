// =================== INVOICE FORM SCRIPT ===================
frappe.ui.form.on("Invoice", {
    onload_post_render: function(frm) {
        // Set today's date by default
        if (!frm.doc.invoice_date) {
            frm.set_value("invoice_date", frappe.datetime.get_today());
        }

        // Generate ref_no without save
        if (!frm.doc.ref_no && frm.is_new()) {
            frappe.call({
                method: "company.company.api.get_next_invoice_preview",
                callback: function(r) {
                    if (r.message) {
                        frm.set_value("ref_no", r.message);
                    }
                }
            });
        }

        // Live discount typing
        const discount_field = frm.fields_dict.overall_discount.input;
        if (discount_field) {
            $(discount_field).on('input', function() {
                calculate_totals_live(frm);
            });
        }

        const discount_type_field = frm.fields_dict.overall_discount_type.input;
        if (discount_type_field) {
            $(discount_type_field).on('change', function() {
                calculate_totals_live(frm);
            });
        }

        // Live calculation for child table quantity/price/discount
        frm.fields_dict.table_qecz.grid.wrapper.on(
            'input',
            'input[data-fieldname="quantity"], input[data-fieldname="price"], input[data-fieldname="discount"]',
            function() {
                const $row = $(this).closest("tr");
                const row_name = $row.attr("data-name");
                const row = locals["Invoice Items"][row_name];
                if (!row) return;

                row.quantity = parseFloat($row.find('input[data-fieldname="quantity"]').val() || 0);
                row.price = parseFloat($row.find('input[data-fieldname="price"]').val() || 0);
                row.discount = parseFloat($row.find('input[data-fieldname="discount"]').val() || 0);

                validate_and_calculate(row, frm);
            }
        );

        calculate_totals_live(frm);
    },

    overall_discount: function(frm) { calculate_totals_live(frm); },
    overall_discount_type: function(frm) { calculate_totals_live(frm); },

    table_qecz_add: function(frm) { calculate_totals_live(frm); },
    table_qecz_remove: function(frm) { calculate_totals_live(frm); },

    grand_total: function(frm) { calculate_balance_amount(frm); },

    received_amount: function(frm) {calculate_balance_amount(frm);}
});

frappe.ui.form.on("Invoice", {
    validate: function(frm) {
        if (!frm.is_new() && frm.doc.has_collections) {
            frappe.throw("This invoice already has collections. Editing is not allowed.");
        }
    },

    onload: function(frm) {
        if (!frm.is_new()) {
            // Get collections count (sync)
            frappe.call({
                method: "company.company.api.has_invoice_collections",
                args: { invoice_name: frm.doc.name },
                async: false,   // IMPORTANT!
                callback: function(r) {
                    if (r.message === true) {
                        frm.doc.has_collections = true; // Mark flag
                        frm.set_read_only();
                        frappe.msgprint("This invoice already has collections. Editing is not allowed.");
                    }
                }
            });
        }
    }
});


frappe.ui.form.on("Invoice", {
    validate: function(frm) {
        // Recalculate totals and balance
        calculate_totals_live(frm);
        calculate_balance_amount(frm);

        // Persist values to database
        frm.set_value("grand_total", flt(frm.doc.grand_total));
        frm.set_value("balance_amount", flt(frm.doc.balance_amount));
    }
});

// =================== CHILD TABLE SCRIPT ===================
frappe.ui.form.on("Invoice Items", {
    service: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row || !row.service) return;

        // Fetch item rate and details (no available_qty)
        frappe.db.get_value("Item", row.service, ["rate", "item_name", "item_code"])
            .then(r => {
                if (r && r.message) {
                    row.price = flt(r.message.rate || 0);
                    row.hsn_code = r.message.item_code || "";
                    row.description = r.message.item_name || "";
                    row.sub_total = calculate_row_amount(row);
                    frm.refresh_field("table_qecz");
                    calculate_totals_live(frm);
                }
            });
    },

    quantity: function(frm, cdt, cdn) { child_update(frm, cdt, cdn); },
    price: function(frm, cdt, cdn) { child_update(frm, cdt, cdn); },
    discount: function(frm, cdt, cdn) { child_update(frm, cdt, cdn); },
    discount_type: function(frm, cdt, cdn) { child_update(frm, cdt, cdn); },
    tax_type: function(frm, cdt, cdn) { child_update(frm, cdt, cdn); },
    grand_total: function(frm) { calculate_balance_amount(frm); }
});

// =================== HELPER FUNCTIONS ===================
function child_update(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    if (!row) return;
    validate_and_calculate(row, frm);
}

function validate_and_calculate(row, frm) {
    // Stock check removed completely
    row.sub_total = calculate_row_amount(row);
    frm.refresh_field("table_qecz");
    calculate_totals_live(frm);
}

function calculate_row_amount(row) {
    let base_amount = (row.quantity || 0) * (row.price || 0);

    let discount_amt = 0;
    if (row.discount_type === "Percentage")
        discount_amt = base_amount * (row.discount || 0) / 100;
    else if (row.discount_type === "Flat")
        discount_amt = row.discount || 0;

    let taxable = base_amount - discount_amt;

    let tax_rate = 0;
    if (row.tax_type) {
        if (row.tax_type.includes("18%")) tax_rate = 18;
        else if (row.tax_type.includes("28%")) tax_rate = 28;
        else if (row.tax_type.includes("12%")) tax_rate = 12;
        else if (row.tax_type.includes("5%")) tax_rate = 5;
        else if (row.tax_type.includes("3%")) tax_rate = 3;
        else if (row.tax_type.includes("27%")) tax_rate = 27;
    }

    row.tax_amount = (taxable * tax_rate) / 100;
    return taxable + row.tax_amount;
}

function calculate_totals_live(frm) {
    let total_qty = 0.0;
    let total_amount = 0.0;

    (frm.doc.table_qecz || []).forEach(row => {
        total_qty += flt(row.quantity, 2);
        total_amount += flt(row.sub_total, 2);
    });

    const discount_val = flt(frm.doc.overall_discount, 2);
    const discount_type_val = frm.doc.overall_discount_type || "Flat";

    let grand_total = total_amount;

    if (discount_type_val === "Flat")
        grand_total = total_amount - discount_val;
    else if (discount_type_val === "Percentage")
        grand_total = total_amount - (total_amount * discount_val / 100);

    // Ensure no negatives
    grand_total = Math.max(0, Math.round(grand_total * 100) / 100);

    frm.set_value("total_qty", total_qty);
    frm.set_value("total_amount", total_amount);
    frm.set_value("grand_total", grand_total);

    frm.refresh_field("total_qty");
    frm.refresh_field("total_amount");
    frm.refresh_field("grand_total");
}


// =================== BALANCE CALCULATION (LIVE) ===================
function calculate_balance_amount(frm) {
    let received = flt(frm.doc.received_amount || 0);
    let grand_total = flt(frm.doc.grand_total || 0);

    let balance = grand_total - received;
    if (balance < 0) balance = 0;

    frm.set_value("balance_amount", balance);
}



function update_received_amount(frm) {
    if (frm.is_new()) return;

    frappe.call({
        method: "company.company.api.get_total_collected",
        args: { invoice_name: frm.doc.name },
        callback: function(r) {
            let total_collected = flt(r.message || 0);

            // Set received amount
            frm.set_value("received_amount", total_collected);

            // Update balance
            calculate_balance_amount(frm);

            frm.refresh_field("received_amount");
            frm.refresh_field("balance_amount");
        }
    });
}
