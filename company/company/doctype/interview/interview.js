frappe.ui.form.on('Interview', {
    refresh(frm) {

        if (frm.doc.phone_number) {
            // Clean phone number (remove +, spaces, -, brackets)
            let phone = frm.doc.phone_number.replace(/[^0-9]/g, "");

            // Add country code if missing (India = 91)
            if (!phone.startsWith("91")) {
                phone = "91" + phone;
            }

            frm.add_custom_button('WhatsApp', () => {
                let msg = `Hello ${frm.doc.lead_name}, regarding your inquiry about ${frm.doc.service}.`;
                let url = `https://wa.me/${phone}?text=${encodeURIComponent(msg)}`;
                window.open(url, '_blank');
            });
        }
    },
    country(frm) {
        if (!frm.doc.country) return;

        frappe.call({
            method: "company.company.api.get_states",
            args: { country: frm.doc.country },
            callback: function (r) {
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
            callback: function (r) {
                let cities = r.message || [];

                // Add "Others"
                cities.push("Others");

                frm.set_df_property("city", "options", ["", ...cities].join("\n"));
                frm.refresh_field("city");
            }
        });
    },
    job_applicant(frm) {
        if (!frm.doc.job_applicant) return;

        frappe.db.get_value("Job Applicant", frm.doc.job_applicant,
            ["phone_number", "resume_attachment"], function (r) {

                if (!r) return;

                if (r.phone_number) {
                    frm.set_value("phone_number", r.phone_number);
                }

                if (r.resume_attachment) {
                    frm.set_value("resume_attachment", r.resume_attachment);
                }
                
            }
        );
    }
});