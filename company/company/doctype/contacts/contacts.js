// Copyright (c) 2025, deepak and contributors
// For license information, please see license.txt

frappe.ui.form.on("Contacts", {
    refresh(frm) {
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
