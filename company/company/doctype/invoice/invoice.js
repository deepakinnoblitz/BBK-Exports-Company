// Copyright (c) 2025, deepak and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Invoice", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on("Invoice", {
    refresh(frm) {
        toggle_conversion_section(frm);

        // Sync latest contact details
        if (frm.doc.client_name) {
            frappe.db.get_value("Contacts", frm.doc.client_name, ["company_name", "first_name", "phone", "address"], (r) => {
                if (r) {
                    frm.set_value("billing_name", r.company_name);
                    frm.set_value("customer_name", r.first_name);
                    frm.set_value("phone_number", r.phone);
                    frm.set_value("billing_address", r.address);
                }
            });
        }

        if (!frm.doc.__islocal) {

            frm.add_custom_button("Preview PDF", function () {

                let doctype = "Invoice";
                let name = encodeURIComponent(frm.doc.name);
                let format = encodeURIComponent("Invoice Print Format");

                // Preview PDF (open in browser)
                let url = `/api/method/frappe.utils.print_format.download_pdf?
                doctype=${doctype}
                &name=${name}
                &format=${format}
                &no_letterhead=1
                &letterhead=No Letterhead
                &settings={}
                &trigger_print=0
            `.replace(/\s+/g, "");

                window.open(url, "_blank");

            }, "Print Invoice"); // Under Print dropdown



            frm.add_custom_button("Download PDF", function () {

                let doctype = "Invoice";
                let name = encodeURIComponent(frm.doc.name);
                let format = encodeURIComponent("Invoice Print Format");

                // ⬇️ Force Download URL
                let url = `/api/method/frappe.utils.print_format.download_pdf?
                doctype=${doctype}
                &name=${name}
                &format=${format}
                &no_letterhead=1
                &letterhead=No Letterhead
                &settings={}
                &download=1
            `.replace(/\s+/g, "");

                // === FORCE DOWNLOAD ===
                let a = document.createElement("a");
                a.href = url;
                a.download = `${frm.doc.name}.pdf`;
                document.body.appendChild(a);
                a.click();
                a.remove();

            }, "Print Invoice");

        }

        // Add Edit Customer Button to Section Header
        add_edit_customer_button(frm, "invoice_details_section");
    },
    client_name(frm) {
        if (!frm.doc.client_name) return;

        frappe.db.get_value("Contacts", frm.doc.client_name, ["company_name", "first_name", "phone", "address"], (r) => {
            if (r) {
                frm.set_value("billing_name", r.company_name);
                frm.set_value("customer_name", r.first_name);
                frm.set_value("phone_number", r.phone);
                frm.set_value("billing_address", r.address);
            }
        });

        // Update button visibility/link
        add_edit_customer_button(frm, "invoice_details_section");
    },
    validate(frm) {
        // ... (existing validation logic) ...
        // Remove empty rows from items table
        // We check if 'service' is present. 'quantity' has default 1, so we ignore it.
        if (frm.doc.table_qecz && frm.doc.table_qecz.length > 0) {
            frm.doc.table_qecz = frm.doc.table_qecz.filter(row => row.service);
            frm.refresh_field("table_qecz");
        }

        // Ensure at least one row remains
        if (!frm.doc.table_qecz || frm.doc.table_qecz.length === 0) {
            frappe.msgprint({
                title: __('Validation Warning'),
                message: __('Please add at least one item to the Invoice'),
                indicator: 'red'
            });
            frappe.validated = false;
        }

        // Ensure Price is not Zero
        let invalid_price = false;
        if (frm.doc.table_qecz) {
            frm.doc.table_qecz.forEach(row => {
                if (flt(row.price) <= 0) {
                    invalid_price = true;
                }
            });
        }

        if (invalid_price) {
            frappe.msgprint({
                title: __('Validation Warning'),
                message: __('Price cannot be zero for items'),
                indicator: 'red'
            });
            frappe.validated = false;
        }
    }
});

function toggle_conversion_section(frm) {
    if (frm.doc.converted_from_estimation == 1) {
        // Show the section
        frm.set_df_property("converted_from_estimation", "hidden", 0);
        frm.set_df_property("converted_estimation_id", "hidden", 0);
    } else {
        // Hide the section
        frm.set_df_property("converted_from_estimation", "hidden", 1);
        frm.set_df_property("converted_estimation_id", "hidden", 1);
    }
}

function add_edit_customer_button(frm, section_fieldname) {
    // 1. Find the section using data-fieldname attribute for robustness
    const $section = frm.$wrapper.find(`[data-fieldname="${section_fieldname}"]`);
    if ($section.length === 0) return;

    const $header = $section.find(".section-head");
    if ($header.length === 0) return;

    // 2. Remove existing button if any
    $header.find(".custom-edit-btn").remove();

    // 3. If no client selected, do nothing else
    if (!frm.doc.client_name) return;

    // 4. Create and append the button
    const $btn = $(`<button class="btn btn-xs btn-primary custom-edit-btn" style="float: right;">Edit Customer Details</button>`);

    $btn.on("click", function (e) {
        e.preventDefault();
        e.stopPropagation(); // Prevent collapsing section
        frappe.set_route("Form", "Contacts", frm.doc.client_name);
    });

    $header.append($btn);
}
