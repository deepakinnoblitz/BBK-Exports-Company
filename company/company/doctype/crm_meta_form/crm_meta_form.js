// Copyright (c) 2026, deepak and contributors
// For license information, please see license.txt

frappe.ui.form.on("CRM Meta Form", {
    onload(frm) {
        // Fetch and override child metadata options before rendering
        frappe.call({
            method: "company.company.doctype.crm_meta_form.crm_meta_form.get_lead_fields",
            callback: function (r) {
                if (r.message && r.message.length > 0) {
                    let options = r.message.map(f => f.fieldname).sort();
                    let options_str = ["", ...options].join("\n");
                    
                    // Override child table DocType metadata options globally
                    let docfield = frappe.meta.get_docfield("CRM Meta Field Mapping", "crm_field");
                    if (docfield) {
                        docfield.options = options_str;
                    }
                }
            }
        });
    },

    refresh(frm) {
        frm.trigger("show_mandatory_fields_alert");
        frm.trigger("setup_lead_field_options");

        // Auto-populate mandatory rows if this is a new document and the table is empty
        if (frm.is_new() && (!frm.doc.field_mappings || frm.doc.field_mappings.length === 0)) {
            frm.trigger("auto_populate_mandatory_fields");
        }
    },

    setup_lead_field_options(frm) {
        frappe.call({
            method: "company.company.doctype.crm_meta_form.crm_meta_form.get_lead_fields",
            callback: function (r) {
                if (r.message && r.message.length > 0) {
                    let options = r.message.map(f => f.fieldname).sort();
                    let options_str = ["", ...options].join("\n");

                    // Update options on child table DocType metadata globally
                    let docfield = frappe.meta.get_docfield("CRM Meta Field Mapping", "crm_field");
                    if (docfield) {
                        docfield.options = options_str;
                    }

                    // Update grid column metadata
                    let grid = frm.fields_dict["field_mappings"].grid;
                    let grid_field = grid.get_docfield("crm_field");
                    if (grid_field) {
                        grid_field.options = options_str;
                    }

                    // Also update parent field property and force refresh
                    frm.set_df_property("field_mappings", "options", options_str, frm.doc.name, "crm_field");
                    grid.refresh();
                }
            }
        });
    },

    auto_populate_mandatory_fields(frm) {
        frappe.call({
            method: "company.company.doctype.crm_meta_form.crm_meta_form.get_mandatory_lead_fields",
            callback: function (r) {
                if (r.message && r.message.length > 0) {
                    const default_meta_keys = {
                        "lead_name": "full_name",
                        "email": "email",
                        "phone_number": "phone_number"
                    };

                    r.message.forEach(f => {
                        let row = frm.add_child("field_mappings");
                        row.crm_field = f.fieldname;
                        row.meta_label = f.label;
                        row.meta_field = default_meta_keys[f.fieldname] || "";
                        if (f.fieldname === "lead_name" || f.fieldname === "phone_number") {
                            row.required = 1;
                        }
                    });

                    frm.refresh_field("field_mappings");
                }
            }
        });
    },

    show_mandatory_fields_alert(frm) {
        frappe.call({
            method: "company.company.doctype.crm_meta_form.crm_meta_form.get_mandatory_lead_fields",
            callback: function (r) {
                if (r.message && r.message.length > 0) {
                    // Get list of currently mapped fields (either with a Meta Field key or a Default Value)
                    let mapped_fields = (frm.doc.field_mappings || [])
                        .filter(row => row.crm_field && (row.meta_field || row.default_value))
                        .map(row => row.crm_field);

                    // Filter down to only missing mandatory fields
                    let missing_fields = r.message.filter(f => !mapped_fields.includes(f.fieldname));

                    if (missing_fields.length > 0) {
                        let fields_list = missing_fields.map(f => `<li><b>${f.label}</b> (<code>${f.fieldname}</code>)</li>`).join("");
                        let alert_html = `
                            <div style="padding: 12px; background-color: var(--light-red, #fff3f3); border-left: 4px solid var(--red, #ff5858); border-radius: 4px; margin-bottom: 5px; color: var(--text-color, #333);">
                                <span style="font-weight: bold; color: var(--red, #d2322d);">Missing Mandatory Lead Fields:</span>
                                <p style="margin: 5px 0 0 0; font-size: 0.9em;">
                                    Please ensure the following mandatory fields from the Lead DocType are configured in your field mapping table below (as mapped fields or static defaults) to prevent webhook processing failures:
                                </p>
                                <ul style="margin: 8px 0 0 15px; padding: 0; font-size: 0.9em; line-height: 1.4em;">
                                    ${fields_list}
                                </ul>
                            </div>
                        `;
                        frm.fields_dict.mandatory_fields_alert.html(alert_html);
                    } else {
                        // Clear alert if all mandatory fields are mapped
                        frm.fields_dict.mandatory_fields_alert.html("");
                    }
                }
            }
        });
    }
});

// Re-evaluate alert when child table mapping changes
frappe.ui.form.on("CRM Meta Field Mapping", {
    form_render(frm, cdt, cdn) {
        // Set the options on the field inside the active popup form
        let field = frappe.meta.get_docfield(cdt, "crm_field", frm.doc.name);
        if (field && frm.crm_field_options_str) {
            field.options = frm.crm_field_options_str;
        }
    },
    field_mappings_add(frm) {
        frm.trigger("show_mandatory_fields_alert");
    },
    field_mappings_remove(frm) {
        frm.trigger("show_mandatory_fields_alert");
    },
    crm_field(frm) {
        frm.trigger("show_mandatory_fields_alert");
    },
    meta_field(frm) {
        frm.trigger("show_mandatory_fields_alert");
    },
    default_value(frm) {
        frm.trigger("show_mandatory_fields_alert");
    }
});
