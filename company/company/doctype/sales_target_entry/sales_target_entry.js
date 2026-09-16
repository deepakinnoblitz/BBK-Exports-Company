frappe.ui.form.on("Sales Target Entry", {
    refresh(frm) {
        // Preview Sales Entry ID
        if (frm.is_new() && !frm.doc.sales_entry_id) {
            frappe.call({
                method: "company.company.doctype.sales_target_entry.sales_target_entry.get_next_sales_target_preview",
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("sales_entry_id", r.message);
                    }
                }
            });
        }

        // Set logged in user
        if (frm.is_new() && !frm.doc.sales_person) {
            frm.set_value("sales_person", frappe.session.user);
        }
    },

    in_date(frm) {
        if (!frm.doc.in_date) return;

        const month = frappe.datetime
            .str_to_obj(frm.doc.in_date)
            .toLocaleString("default", { month: "long" });

        frm.set_value("month", month);
    },

    contact_name(frm) {
        if (!frm.doc.contact_name) {
            frm.set_value("contact_number", "");
            return;
        }

        frappe.db.get_value(
            "Contacts",
            frm.doc.contact_name,
            "phone"
        ).then((r) => {
            if (r.message) {
                frm.set_value("contact_number", r.message.phone || "");
            }
        });
    },

    value(frm) {
        calculate_balance(frm);
    },

    advance(frm) {
        calculate_balance(frm);
    }
});

function calculate_balance(frm) {
    const value = flt(frm.doc.value);
    const advance = flt(frm.doc.advance);

    frm.set_value("balance", value - advance);
}