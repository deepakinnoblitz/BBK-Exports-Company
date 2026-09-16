// =================== PURCHASE FORM SCRIPT ===================
frappe.ui.form.on("Purchase", {
    onload_post_render: function(frm) {
        
        // Filter Vendor Name to only show Customers with customer_type = 'Purchase'
        frm.set_query("vendor_name", function() {
            return {
                filters: {
                    customer_type: "Purchase"
                }
            };
        });

        // Set today's bill date by default
        if (!frm.doc.bill_date) {
            frm.set_value("bill_date", frappe.datetime.get_today());
        }

        // Live discount typing
        const discount_field = frm.fields_dict.overall_discount?.input;
        if (discount_field) {
            $(discount_field).on('input', function() {
                calculate_totals_live(frm);
            });
        }

        const discount_type_field = frm.fields_dict.overall_discount_type?.input;
        if (discount_type_field) {
            $(discount_type_field).on('change', function() {
                calculate_totals_live(frm);
            });
        }

        // Live calculation for child table quantity/price/discount
        const table_wrapper = frm.fields_dict.table_qecz?.grid.wrapper;
        if (table_wrapper) {
            table_wrapper.on(
                'input',
                'input[data-fieldname="quantity"], input[data-fieldname="price"], input[data-fieldname="discount"]',
                function() {
                    const $row = $(this).closest("tr");
                    const row_name = $row.attr("data-name");
                    const row = locals["Purchase Items"][row_name];
                    if (!row) return;

                    row.quantity = parseFloat($row.find('input[data-fieldname="quantity"]').val() || 0);
                    row.price = parseFloat($row.find('input[data-fieldname="price"]').val() || 0);
                    row.discount = parseFloat($row.find('input[data-fieldname="discount"]').val() || 0);

                    // Fetch available quantity if not already fetched
                    if (row.service && row.available_qty === undefined) {
                        frappe.db.get_value("Item", row.service, ["available_qty"])
                            .then(r => {
                                if (r && r.message) {
                                    row.available_qty = flt(r.message.available_qty || 0);
                                    validate_and_calculate(row, frm);
                                }
                            });
                    } else {
                        validate_and_calculate(row, frm);
                    }
                }
            );
        }

        calculate_totals_live(frm);
    },

    overall_discount: function(frm) { calculate_totals_live(frm); },
    overall_discount_type: function(frm) { calculate_totals_live(frm); },

    table_qecz_add: function(frm) { calculate_totals_live(frm); },
    table_qecz_remove: function(frm) { calculate_totals_live(frm); }
});

// =================== CHILD TABLE SCRIPT ===================
frappe.ui.form.on("Purchase Items", {
    service: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row || !row.service) return;

        frappe.db.get_value("Item", row.service, ["rate", "available_qty", "item_name", "item_code"])
            .then(r => {
                if (r && r.message) {
                    row.price = flt(r.message.rate || 0);
                    row.hsn_code = r.message.item_code || "";
                    row.available_qty = flt(r.message.available_qty || 0);
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
    tax_type: function(frm, cdt, cdn) { child_update(frm, cdt, cdn); }
});

// =================== HELPER FUNCTIONS ===================
function child_update(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    if (!row) return;
    validate_and_calculate(row, frm);
}

function validate_and_calculate(row, frm) {
    if (row.service && row.available_qty !== undefined && row.quantity > row.available_qty) {
        frappe.msgprint({
            title: "Quantity Warning",
            indicator: "orange",
            message: `Only ${row.available_qty} units available for Item ${row.service}. You entered ${row.quantity}.`
        });
        row.quantity = row.available_qty;
    }

    row.sub_total = calculate_row_amount(row);
    frm.refresh_field("table_qecz");
    calculate_totals_live(frm);
}

function calculate_row_amount(row) {
    let base_amount = (row.quantity || 0) * (row.price || 0);

    let discount_amt = 0;
    if (row.discount_type === "Percentage") discount_amt = base_amount * (row.discount || 0) / 100;
    else if (row.discount_type === "Flat") discount_amt = row.discount || 0;

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

    if (discount_type_val === "Flat") {
        grand_total = total_amount - discount_val;
    } else if (discount_type_val === "Percentage") {
        grand_total = total_amount - (total_amount * discount_val / 100);
    }

    // Round to 2 decimals safely
    grand_total = Math.round(grand_total * 100) / 100;
    total_amount = Math.round(total_amount * 100) / 100;
    total_qty = Math.round(total_qty * 100) / 100;

    // Prevent negative total
    grand_total = grand_total < 0 ? 0.0 : grand_total;

    frm.set_value("total_qty", total_qty);
    frm.set_value("total_amount", total_amount);
    frm.set_value("grand_total", grand_total);

    frm.refresh_field("total_qty");
    frm.refresh_field("total_amount");
    frm.refresh_field("grand_total");
}
