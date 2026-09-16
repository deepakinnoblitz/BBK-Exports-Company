// =================== QUOTATION PARENT ===================
frappe.ui.form.on("Quatation", {
    onload_post_render: function(frm) {
        // Default formatter for quantity in grid
        const field = frm.fields_dict.items.grid.get_field('quantity');
        if (field) {
            field.formatter = function(value) {
                return value !== undefined && value !== null ? value : 0;
            };
        }
        frm.fields_dict.items.grid.refresh();

        // Live discount typing
        const discount_field = frm.fields_dict.discount.input;
        if (discount_field) {
            $(discount_field).on('input', function() {
                calculate_totals_live(frm);
            });
        }

        // Live discount type change
        const discount_type_field = frm.fields_dict.discount_type.input;
        if (discount_type_field) {
            $(discount_type_field).on('change', function() {
                calculate_totals_live(frm);
            });
        }

        // Live calculation for child table quantity/rate
        frm.fields_dict.items.grid.wrapper.on('input', 'input[data-fieldname="quantity"], input[data-fieldname="rate"]', function() {
            const $row = $(this).closest("tr");
            const row_name = $row.attr("data-name");
            const row = locals["Quotation Item"][row_name];
            if (!row) return;

            const quantity_val = parseFloat($row.find('input[data-fieldname="quantity"]').val() || 0);
            const rate_val = parseFloat($row.find('input[data-fieldname="rate"]').val() || 0);

            row.quantity = quantity_val;
            row.rate = rate_val;
            row.amount = quantity_val * rate_val;

            frm.refresh_field("items");
            calculate_totals_live(frm);
        });

        calculate_totals_live(frm);
    },

    items_add: function(frm) { calculate_totals_live(frm); },
    items_remove: function(frm) { calculate_totals_live(frm); },
    validate: function(frm) { calculate_totals_live(frm); },
    before_save: function(frm) { calculate_totals_live(frm); }
});

// =================== LIVE CALCULATION FUNCTION ===================
function calculate_totals_live(frm) {
    let total_qty = 0;
    let total_amount = 0;

    if (!frm.doc.items) return;

    // Sum all amounts and quantities
    frm.doc.items.forEach(row => {
        total_qty += Number(row.quantity || 0);
        total_amount += Number(row.amount || 0);
    });

    // Get live discount from DOM
    const discount_val = parseFloat($(frm.fields_dict.discount.input).val() || 0);
    const discount_type_val = $(frm.fields_dict.discount_type.input).val() || "Flat";

    let grand_total = total_amount;
    if (discount_type_val === "Flat") {
        grand_total = total_amount - discount_val;
    } else if (discount_type_val === "Percentage") {
        grand_total = total_amount - (total_amount * discount_val / 100);
    }
    if (grand_total < 0) grand_total = 0;

    frm.set_value("total_qty", total_qty);
    frm.set_value("total_amount", total_amount);
    frm.set_value("grand_total", Number(grand_total.toFixed(2)));

    frm.refresh_field("total_qty");
    frm.refresh_field("total_amount");
    frm.refresh_field("grand_total");
}

// =================== QUOTATION ITEM CHILD TABLE ===================
frappe.ui.form.on("Quotation Item", {
    item_code: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row) return;

        if (row.item_code) {
            frappe.db.get_value("Item", row.item_code, ["available_qty", "rate"])
                .then(r => {
                    if (r && r.message) {
                        row.rate = Number(r.message.rate || 0);
                        row.amount = Number((row.quantity || 0) * row.rate);
                        frm.refresh_field("items");
                        setTimeout(() => calculate_totals_live(frm), 100);
                    }
                });
        }
    },

    quantity: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row) return;

        row.amount = Number((row.quantity || 0) * (row.rate || 0));
        frm.refresh_field("items");

        if (row.item_code && row.quantity > 0) {
            frappe.db.get_value("Item", row.item_code, "available_qty")
                .then(r => {
                    const available = Number(r.message.available_qty || 0);
                    if (row.quantity > available) {
                        frappe.msgprint({
                            title: "Quantity Warning",
                            indicator: "orange",
                            message: `Only ${available} units available for Item ${row.item_code}. You entered ${row.quantity}.`
                        });
                        row.quantity = available;
                        row.amount = Number(row.quantity * row.rate);
                        frm.refresh_field("items");
                    }
                    setTimeout(() => calculate_totals_live(frm), 100);
                });
        } else {
            setTimeout(() => calculate_totals_live(frm), 100);
        }
    },

    rate: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row) return;

        row.amount = Number((row.quantity || 0) * (row.rate || 0));
        frm.refresh_field("items");
        setTimeout(() => calculate_totals_live(frm), 100);
    }
});


