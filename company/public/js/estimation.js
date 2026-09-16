// ======================================================
// ESTIMATION FORM SCRIPT (CLEAN VERSION)
// ======================================================
frappe.ui.form.on("Estimation", {
    onload_post_render(frm) {

        // Default date
        if (!frm.doc.estimate_date) {
            frm.set_value("estimate_date", frappe.datetime.get_today());
        }

        // Auto Ref No
        if (frm.is_new() && !frm.doc.ref_no) {
            frappe.call({
                method: "company.company.api.get_next_estimation_preview",
                callback(r) {
                    if (r.message) frm.set_value("ref_no", r.message);
                }
            });
        }

        // Live discount listeners
        $(frm.fields_dict.overall_discount.input).on("input", () => calculate_totals_live(frm));
        $(frm.fields_dict.overall_discount_type.input).on("change", () => calculate_totals_live(frm));

        // Child table listeners
        frm.fields_dict.table_qecz.grid.wrapper.on(
            "input",
            'input[data-fieldname="quantity"], input[data-fieldname="price"], input[data-fieldname="discount"]',
            function () {
                let row = locals["Estimation Items"][$(this).closest("tr").attr("data-name")];
                validate_and_calculate(row, frm);
            }
        );

        calculate_totals_live(frm);
    },

    overall_discount(frm) { calculate_totals_live(frm); },
    overall_discount_type(frm) { calculate_totals_live(frm); },
    table_qecz_add(frm) { calculate_totals_live(frm); },
    table_qecz_remove(frm) { calculate_totals_live(frm); }
});


// ======================================================
// CHILD TABLE SCRIPT (CLEAN VERSION)
// ======================================================
frappe.ui.form.on("Estimation Items", {

    service(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        frappe.db.get_value("Item", row.service, ["rate", "item_name", "item_code"])
            .then(r => {
                if (!r.message) return;

                row.price = Number(r.message.rate || 0);
                row.hsn_code = r.message.item_code || "";
                row.description = r.message.item_name || "";

                validate_and_calculate(row, frm);
            });
    },

    quantity: trigger_child_update,
    price: trigger_child_update,
    discount: trigger_child_update,
    discount_type: trigger_child_update,

    tax_type(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        frappe.db.get_value("Tax Types", row.tax_type, ["tax_percentage", "tax_type"])
            .then(r => {
                if (!r.message) return;

                row.tax_percentage = Number(r.message.tax_percentage || 0);
                row.tax_type_master = r.message.tax_type; // GST or IGST

                validate_and_calculate(row, frm);
            });
    }
});


// ======================================================
// HELPERS
// ======================================================
function trigger_child_update(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    validate_and_calculate(row, frm);
}

function validate_and_calculate(row, frm) {
    calculate_row_amount_dynamic(row);
    frm.refresh_field("table_qecz");
    calculate_totals_live(frm);
}


// ======================================================
// ROW CALCULATION (CLEAN VERSION)
// ======================================================
function calculate_row_amount_dynamic(row) {

    // Base amount
    let base = (row.quantity || 0) * (row.price || 0);

    // Discount
    let disc = 0;
    if (row.discount_type === "Percentage") {
        disc = base * (row.discount || 0) / 100;
    } else if (row.discount_type === "Flat") {
        disc = row.discount || 0;
    }

    let taxable = base - disc;

    // Tax
    let tax_amount = taxable * (Number(row.tax_percentage || 0) / 100);
    row.tax_amount = tax_amount;

    // TAX SPLIT USING MASTER FIELD `tax_type`
    let tax_type = (row.tax_type_master || "").toUpperCase().trim();

    if (tax_type === "GST") {
        row.cgst = tax_amount / 2;
        row.sgst = tax_amount / 2;
        row.igst = 0;
    }
    else if (tax_type === "IGST") {
        row.cgst = 0;
        row.sgst = 0;
        row.igst = tax_amount;
    }
    else {
        row.cgst = 0;
        row.sgst = 0;
        row.igst = 0;
    }

    row.sub_total = taxable + tax_amount;
    return row.sub_total;
}


// ======================================================
// GRAND TOTAL CALCULATION (CLEAN VERSION)
// ======================================================
function calculate_totals_live(frm) {

    let qty = 0;
    let total = 0;

    (frm.doc.table_qecz || []).forEach(row => {
        qty += Number(row.quantity || 0);
        total += Number(row.sub_total || 0);
    });

    // Overall Discount
    let overall_disc = parseFloat(frm.doc.overall_discount || 0);
    let disc_type = frm.doc.overall_discount_type || "Flat";

    if (disc_type === "Flat") {
        total -= overall_disc;
    } else if (disc_type === "Percentage") {
        total -= (total * overall_disc / 100);
    }

    if (total < 0) total = 0;

    frm.set_value("total_qty", qty);
    frm.set_value("total_amount", total);
    frm.set_value("grand_total", Number(total.toFixed(2)));
}
