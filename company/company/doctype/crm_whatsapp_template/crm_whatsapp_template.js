frappe.ui.form.on("CRM WhatsApp Template", {
    refresh(frm) {
        if (frm.doc.used_for) {
            load_variables(frm);
        }
    },

    used_for(frm) {
        load_variables(frm);
    }
});

function load_variables(frm) {

    if (!frm.doc.used_for) {
        frm.set_value("available_variables", "");
        return;
    }

    frappe.call({
        method: "company.company.doctype.crm_whatsapp_template.crm_whatsapp_template.get_whatsapp_template_variables",
        args: {
            used_for: frm.doc.used_for
        },
        callback(r) {

            let variables = r.message || [];

            let text = "";

            variables.forEach(v => {
                text += `${v.label.padEnd(25)} : {{${v.fieldname}}}\n`;
            });

            frm.set_value("available_variables", text);
        }
    });

}