// Copyright (c) 2026, deepak and contributors
// For license information, please see license.txt

frappe.ui.form.on("CRM WhatsApp Automation", {
	refresh(frm) {
        frm.trigger("set_state_options");
	},

    document_type(frm) {
        frm.trigger("set_state_options");
    },

    set_state_options(frm) {
        frappe.call({
            method: "company.company.frontend_api.get_automation_options",
            callback: function(r) {
                if (r.message) {
                    let lead_states = ["", ...(r.message.lead_workflow_states || [])];
                    let deal_stages = ["", ...(r.message.deal_stages || [])];

                    // Set Lead Workflow States
                    frm.set_df_property("workflow_state", "options", lead_states);
                    frm.set_df_property("previous_workflow_state", "options", lead_states);
                    
                    // Set Deal Stages
                    frm.set_df_property("deal_stage", "options", deal_stages);
                    frm.set_df_property("previous_deal_stage", "options", deal_stages);

                    frm.refresh_field("workflow_state");
                    frm.refresh_field("previous_workflow_state");
                    frm.refresh_field("deal_stage");
                    frm.refresh_field("previous_deal_stage");
                }
            }
        });
    }
});
