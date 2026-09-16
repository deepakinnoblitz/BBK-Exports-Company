// Copyright (c) 2025, deepak and contributors
// For license information, please see license.txt

frappe.ui.form.on('Employee', {
    onload(frm) {
        const restricted_fields = [
            "total_earnings",
            "total_deductions",
            "net_salary",
            "employee_id",
            "date_of_joining",
            "pf_number",
            "esi_no",
            "status",
            "user",
            "bank_account",
            "bank_name",
            "office_phone_number",
            "department",
            "designation"
        ];

        // Check if current user has the HR role
        const is_hr = frappe.user.has_role('HR');

        // Loop through all restricted fields
        restricted_fields.forEach(field => {
            frm.set_df_property(field, 'read_only', is_hr ? 0 : 1);
        });
    },
    refresh(frm) {
        // Attach a live input listener to CTC field
        const ctc_input = frm.fields_dict.ctc?.$input;
        if (ctc_input && !ctc_input.attr("data-live-ctc")) {
            ctc_input.attr("data-live-ctc", "1"); // prevent double-binding

            ctc_input.on("input", frappe.utils.debounce(async function () {
                await calculate_ctc_breakdown(frm);
            }, 500)); // waits 0.5s after typing stops
        }

        // 1️⃣ Auto-load states if country is present
        if (frm.doc.country) {
            frappe.call({
                method: "company.company.api.get_states",
                args: { country: frm.doc.country },
                callback(r) {
                    frm.set_df_property("state", "options", ["", ...(r.message || []), "Others"].join("\n"));
                    frm.refresh_field("state");
                }
            });
        }

        // 2️⃣ Auto-load city if state is present
        if (frm.doc.country && frm.doc.state && frm.doc.state !== "Others") {
            frappe.call({
                method: "company.company.api.get_cities",
                args: {
                    country: frm.doc.country,
                    state: frm.doc.state
                },
                callback(r) {
                    frm.set_df_property("city", "options", ["", ...(r.message || []), "Others"].join("\n"));
                    frm.refresh_field("city");
                }
            });
        }
    },
    ctc: async function (frm) {
        await calculate_ctc_breakdown(frm);
    },
    country(frm) {
        if (!frm.doc.country) return;

        frappe.call({
            method: "company.company.api.get_states",
            args: { country: frm.doc.country },
            callback(r) {
                frm.set_df_property("state", "options", ["", ...(r.message || []), "Others"].join("\n"));
                frm.refresh_field("state");
            }
        });
    },

    state(frm) {
        if (!frm.doc.country || !frm.doc.state) return;

        if (frm.doc.state === "Others") {
            frm.set_df_property("city", "options", "Others");
            frm.refresh_field("city");
            return;
        }

        frappe.call({
            method: "company.company.api.get_cities",
            args: {
                country: frm.doc.country,
                state: frm.doc.state
            },
            callback(r) {
                frm.set_df_property("city", "options", ["", ...(r.message || []), "Others"].join("\n"));
                frm.refresh_field("city");
            }
        });
    }
});

// Trigger calculations on table row addition or removal
frappe.ui.form.on('Salary Structure', {
    amount: function (frm, cdt, cdn) {
        calculate_totals(frm);
    },
    earnings_remove: function (frm) {
        calculate_totals(frm);
    },
    deductions_remove: function (frm) {
        calculate_totals(frm);
    }
});


// ================= Helper Functions =================
async function calculate_ctc_breakdown(frm) {
    if (!frm.doc.ctc) return;

    const ctc = flt(frm.doc.ctc);

    // Fetch all Salary Structure Components (Master list)
    const components = await frappe.db.get_list("Salary Structure Component", {
        fields: ["component_name", "type", "percentage", "static_amount"],
        limit: 100
    });

    if (!components || !components.length) {
        return;
    }

    // Clear existing tables
    frm.clear_table("earnings");
    frm.clear_table("deductions");

    let total_earnings = 0;
    let total_deductions = 0;

    for (let comp of components) {
        let value = 0;
        if (flt(comp.static_amount) > 0) {
            value = flt(comp.static_amount);
        } else if (flt(comp.percentage) > 0) {
            value = ctc * flt(comp.percentage) / 100;
        }

        const target_table = comp.type === "Earning" ? "earnings" : "deductions";
        const row = frm.add_child(target_table);
        row.component_name = comp.component_name;
        row.type = comp.type;
        row.percentage = comp.percentage;
        row.static_amount = comp.static_amount;
        row.amount = value;

        if (comp.type === "Earning") total_earnings += value;
        else if (comp.type === "Deduction") total_deductions += value;
    }

    frm.set_value("total_earnings", total_earnings);
    frm.set_value("total_deductions", total_deductions);
    frm.set_value("net_salary", total_earnings - total_deductions);

    frm.refresh_field("earnings");
    frm.refresh_field("deductions");
}

function calculate_totals(frm) {
    let total_earnings = 0;
    let total_deductions = 0;

    (frm.doc.earnings || []).forEach(row => {
        total_earnings += flt(row.amount);
    });

    (frm.doc.deductions || []).forEach(row => {
        total_deductions += flt(row.amount);
    });

    frm.set_value("total_earnings", total_earnings);
    frm.set_value("total_deductions", total_deductions);
    frm.set_value("net_salary", total_earnings - total_deductions);
}
