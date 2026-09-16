frappe.ui.form.on('Job Applicant', {
    refresh(frm) {

        // -----------------------------
        // 1️⃣ Load States on Refresh
        // -----------------------------
        if (frm.doc.country) {
            frappe.call({
                method: "company.company.api.get_states",
                args: { country: frm.doc.country },
                callback: function (r) {
                    let states = r.message || [];
                    states.push("Others");

                    frm.set_df_property("state", "options", ["", ...states].join("\n"));
                    frm.refresh_field("state");
                }
            });
        }

        // -----------------------------
        // 2️⃣ Load Cities on Refresh
        // -----------------------------
        if (frm.doc.country && frm.doc.state) {

            if (frm.doc.state === "Others") {
                frm.set_df_property("city", "options", ["Others"].join("\n"));
                frm.refresh_field("city");
            } else {
                frappe.call({
                    method: "company.company.api.get_cities",
                    args: {
                        country: frm.doc.country,
                        state: frm.doc.state
                    },
                    callback: function (r) {
                        let cities = r.message || [];
                        cities.push("Others");

                        frm.set_df_property("city", "options", ["", ...cities].join("\n"));
                        frm.refresh_field("city");
                    }
                });
            }
        }

        // -----------------------------
        // 3️⃣ WhatsApp Button (existing)
        // -----------------------------
        if (frm.doc.phone_number) {
            let phone = frm.doc.phone_number.replace(/[^0-9]/g, "");

            if (!phone.startsWith("91")) {
                phone = "91" + phone;
            }

            frm.add_custom_button('WhatsApp', () => {
                let msg = `Hello ${frm.doc.applicant_name}, regarding your Job Application about ${frm.doc.job_title}.`;
                let url = `https://wa.me/${phone}?text=${encodeURIComponent(msg)}`;
                window.open(url, '_blank');
            });
        }
    },

    // Existing country event
    country(frm) {
        if (!frm.doc.country) return;

        frappe.call({
            method: "company.company.api.get_states",
            args: { country: frm.doc.country },
            callback: function (r) {
                let states = r.message || [];
                states.push("Others");

                frm.set_df_property("state", "options", ["", ...states].join("\n"));
                frm.refresh_field("state");
            }
        });
    },

    // Existing state event
    state(frm) {
        if (!frm.doc.country || !frm.doc.state) return;

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
            callback: function (r) {
                let cities = r.message || [];
                cities.push("Others");

                frm.set_df_property("city", "options", ["", ...cities].join("\n"));
                frm.refresh_field("city");
            }
        });
    }
});
