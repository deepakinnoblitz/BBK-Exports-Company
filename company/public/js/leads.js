frappe.ui.form.on("Leads", {
    after_save: function(frm) {

        // Only convert when user chooses "Move to Customer"
        if (frm.doc.move_to_party !== "Move to Customer") return;

        // STEP 1 — Check if customer already exists for this lead
        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Customer",
                filters: { lead: frm.doc.name },
                fields: ["name"]
            },
            callback: function(r) {

                // Customer already exists = stop here
                if (r.message && r.message.length > 0) return;

                // STEP 2 — Fetch STATES by country
                frappe.call({
                    method: "company.company.api.get_states",
                    args: { country: frm.doc.country },
                    callback: function(stateRes) {

                        let state_list = stateRes.message || [];
                        let selected_state = state_list.includes(frm.doc.state)
                            ? frm.doc.state
                            : "";

                        // STEP 3 — Fetch CITIES by selected state
                        frappe.call({
                            method: "company.company.api.get_cities",
                            args: {
                                country: frm.doc.country,
                                state: selected_state
                            },
                            callback: function(cityRes) {

                                let city_list = cityRes.message || [];
                                let selected_city = city_list.includes(frm.doc.city)
                                    ? frm.doc.city
                                    : "";

                                // ⭐ FIX: Add Select Options BEFORE inserting Customer
                                // This ensures state/city dropdown shows saved values
                                frappe.meta.get_docfield("Customer", "state").options =
                                    ["", ...state_list].join("\n");
                                
                                frappe.meta.get_docfield("Customer", "city").options =
                                    ["", ...city_list].join("\n");

                                // STEP 4 — Now insert Customer with all mapped fields
                                frappe.call({
                                    method: "frappe.client.insert",
                                    args: {
                                        doc: {
                                            doctype: "Customer",
                                            customer_name: frm.doc.lead_name,
                                            company_name: frm.doc.company_name,
                                            gstin: frm.doc.gstin,
                                            phone_number: frm.doc.phone_number,
                                            email: frm.doc.email,
                                            country: frm.doc.country,
                                            state: selected_state,
                                            city: selected_city,
                                            billing_address: frm.doc.billing_address,
                                            remarks: frm.doc.remarks,
                                            assigned_to: frm.doc.assigned_to,
                                            lead: frm.doc.name
                                        }
                                    },
                                    callback: function(res) {
                                        if (!res.exc) {

                                            // STEP 5 — Update lead flag
                                            frappe.call({
                                                method: "frappe.client.set_value",
                                                args: {
                                                    doctype: "Leads",
                                                    name: frm.doc.name,
                                                    fieldname: { customer_created: 1 }
                                                },
                                                callback: function() {

                                                    frm.reload_doc();

                                                    frappe.msgprint({
                                                        title: "Success",
                                                        indicator: "green",
                                                        message: "✅ Customer created and Lead updated successfully!"
                                                    });
                                                }
                                            });
                                        }
                                    }
                                });

                            }
                        });
                    }
                });
            }
        });

    }
});
