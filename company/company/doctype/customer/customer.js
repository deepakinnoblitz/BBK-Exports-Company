// Copyright (c) 2025, deepak and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Customer", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Customer", {
    country(frm) {
        if (!frm.doc.country) return;

        frappe.call({
            method: "company.company.api.get_states",
            args: { country: frm.doc.country },
            callback: function(r) {
                let states = r.message || [];

                // Add "Others" at the end
                states.push("Others");

                frm.set_df_property("state", "options", ["", ...states].join("\n"));
                frm.refresh_field("state");
            }
        });
    },

    state(frm) {
        if (!frm.doc.country || !frm.doc.state) return;

        // If user selects "Others", clear city field and force manual entry
        if (frm.doc.state === "Others") {
            frm.set_df_property("city", "options", ["Others"].join("\n"));
            frm.refresh_field("city");
            return;
        }

        frappe.call({
            method: "company.company.api.get_cities",
            args: {
                country: frm.doc.country,
                state: frm.doc.state
            },
            callback: function(r) {
                let cities = r.message || [];

                // Add "Others"
                cities.push("Others");

                frm.set_df_property("city", "options", ["", ...cities].join("\n"));
                frm.refresh_field("city");
            }
        });
    }
});
