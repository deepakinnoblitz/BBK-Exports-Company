// -----------------------------------------
// FORM SCRIPT (Lead Form)
// -----------------------------------------
frappe.ui.form.on("Lead", {

    refresh(frm) {

        // 1️⃣ Hide all buttons in Create mode
        if (frm.doc.__islocal) {
            frm.clear_custom_buttons();
            return;
        }

        hide_actions_menu_button(frm);

        sort_pipeline_timeline_desc(frm);

        // Add Pipeline workflow menu
        add_pipeline_workflow_menu(frm);

        render_dynamic_sales_pipeline(frm);

        // 1️⃣ Convert Lead Button
        if (!frm.doc.__islocal && frm.doc.workflow_state !== "New Lead") {
            frm.add_custom_button("Convert Lead", () => {
                show_convert_dialog(frm);
            });
        }


        if (!frm.doc.__islocal) {
            frm.add_custom_button("Schedule Call", () => {

                frappe.new_doc("Calls", {
                    reference_doctype: "Lead",
                    reference_name: frm.doc.name,

                    call_for: "Lead",
                    lead_name: frm.doc.name,

                    title: `Followup Call with ${frm.doc.lead_name} (${frm.doc.name})`
                });

            }, "Schedule");


            frm.add_custom_button("Schedule Meeting", () => {

                frappe.new_doc("Meeting", {
                    reference_doctype: "Lead",
                    reference_name: frm.doc.name,

                    meet_for: "Lead",
                    lead_name: frm.doc.name,

                    title: `Meet with ${frm.doc.lead_name} (${frm.doc.name})`
                });
            }, "Schedule");
        }

        // 2️⃣ WhatsApp Button
        if (frm.doc.phone_number) {
            let phone = frm.doc.phone_number.replace(/[^0-9]/g, "");
            if (!phone.startsWith("91")) phone = "91" + phone;

            frm.add_custom_button("WhatsApp", () => {
                let msg = `Hello ${frm.doc.lead_name}, regarding your inquiry about ${frm.doc.service}.`;
                let url = `https://wa.me/${phone}?text=${encodeURIComponent(msg)}`;
                window.open(url, "_blank");
            });
        }

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

        // 3️⃣ Auto-load city
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

    converted_pipeline_timeline_add(frm) {
        sort_pipeline_timeline_desc(frm);
    },

    workflow_state(frm) {
        // Live update pipeline when status changes
        const pipeline = frm.get_field("sales_pipeline");
        if (!pipeline) return;

        const $wrapper = pipeline.$wrapper;
        const stages = get_pipeline_stages_from_workflow(frm);

        update_pipeline_ui($wrapper, stages, frm.doc.workflow_state);

        // 🔥 Update details block
        $wrapper
            .find("#pipeline-stage-details")
            .html(get_stage_details_html(frm));
    },

    country(frm) {
        if (!frm.doc.country) return;

        frappe.call({
            method: "company.company.api.get_states",
            args: { country: frm.doc.country },
            callback(r) {
                const states = r.message || [];

                frm.set_df_property("state", "options", ["", ...states, "Others"].join("\n"));

                // Find "Tamil Nadu" loosely
                const tamilNadu = states.find(s => s.trim().toLowerCase() === "tamil nadu");

                // Also explicitly check if state is "Andhra Pradesh" (which might be auto-selected) to override it
                if ((!frm.doc.state || frm.doc.state === "Andhra Pradesh") && tamilNadu) {
                    frm.set_value("state", tamilNadu);
                }

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

function convert_lead(frm, options) {
    frappe.call({
        method: "company.company.crm_api.convert_lead",
        args: {
            lead_name: frm.doc.name,
        },
        freeze: true,
        freeze_message: "Converting Lead...",
        callback(r) {
            if (!r.message) return;

            let html = `<b>Conversion Status</b><br><br>`;

            r.message.messages.forEach(m => {
                const color = m.type === "success" ? "#16a34a" : "#d97706";
                const icon = m.type === "success" ? "✔" : "⚠";

                html += `
                    <div style="color:${color}; font-weight:500; margin-bottom:6px;">
                        ${icon} ${m.text}
                    </div>
                `;
            });

            html += `<br>`;

            if (r.message.account) {
                html += `<a class="btn btn-primary" href="/app/accounts/${r.message.account}">Open Account</a>&nbsp;`;
            }
            if (r.message.contact) {
                html += `<a class="btn btn-secondary" href="/app/contacts/${r.message.contact}">Open Contact</a>&nbsp;`;
            }

            frappe.msgprint({
                title: "Lead Converted",
                indicator: "green",
                message: html
            });

            frm.reload_doc();
        }
    });
}


// -----------------------------------------
// PIPELINE RENDER
// -----------------------------------------
function render_dynamic_sales_pipeline(frm) {
    const pipeline_field = "sales_pipeline";
    const status_field = "workflow_state";

    const pipeline = frm.get_field(pipeline_field);
    const status_meta = frappe.meta.get_docfield("Lead", status_field);

    if (!pipeline || !status_meta) return;

    const $wrapper = pipeline.$wrapper;

    // Clear previous pipeline (important for SPA navigation)
    $wrapper.find(".sales-pipeline-container").remove();

    // Hide textarea field
    $wrapper.find("textarea").hide();

    const stages = get_pipeline_stages_from_workflow(frm);

    const html = `
        <div class="sales-pipeline-container">
            <div class="pipeline-track">
                ${stages.map((s, i) => `
                    <div class="pipeline-stage"
                         data-stage="${s.key}"
                         data-index="${i}"
                         style="--stage-color:${s.color}">
                        <span>${s.key}</span>
                    </div>
                `).join("")}
            </div>
            <!-- 🔥 CURRENT STAGE DETAILS -->
            <div class="pipeline-stage-details" id="pipeline-stage-details">
                ${get_stage_details_html(frm)}
            </div>
        </div>
    `;

    $wrapper.append(html);

    // Initial highlight
    update_pipeline_ui($wrapper, stages, frm.doc.workflow_state);
}


// -----------------------------------------
// PIPELINE UI STATE
// -----------------------------------------
function update_pipeline_ui($wrapper, stages, activeStage) {
    const activeIndex = stages.findIndex(s => s.key === activeStage);

    $wrapper.find(".pipeline-stage").each(function () {
        const index = parseInt($(this).data("index"), 10);

        $(this).removeClass("active completed");

        if (index < activeIndex) {
            $(this).addClass("completed");
        } else if (index === activeIndex) {
            $(this).addClass("active");
        }
    });
}


// -----------------------------------------
// STAGES (FROM STATUS OPTIONS)
// -----------------------------------------

function get_pipeline_stages_from_workflow(frm) {
    const workflows = frappe.workflow && frappe.workflow.workflows;
    if (!workflows || !workflows["Lead"]) return [];

    const workflow = workflows["Lead"];

    return workflow.states.map(state => ({
        key: state.state,
        color: get_pipeline_color_by_status(state.state)
    }));
}



// -----------------------------------------
// COLORS
// -----------------------------------------
function get_pipeline_color_by_status(workflow_state) {
    const colors = {
        "New Lead": "#38bdf8",          // sky blue
        "Contacted": "#0ea5e9",         // blue
        "Qualified": "#22c55e",         // green
        "Proposal Sent": "#6366f1",     // indigo
        "In Negotiation": "#f97316",    // orange
        "Follow-up Scheduled": "#eab308", // amber
        "On Hold": "#9ca3af",           // gray
        "Not Interested": "#ef4444",    // red
        "In Active": "#64748b",         // slate
        "Closed": "#15803d"             // dark green
    };

    return colors[workflow_state] || "#94a3b8";
}

function get_stage_details_html(frm) {
    const d = frm.doc;
    const stage = d.workflow_state || "Unknown";

    const actions = {
        "New Lead": [
            "Verify lead details",
            "Assign owner",
            "Make first contact"
        ],
        "Contacted": [
            "Understand requirements",
            "Update remarks",
            "Schedule follow-up"
        ],
        "Qualified": [
            "Confirm budget & timeline",
            "Prepare proposal",
            "Convert lead if ready"
        ],
        "Proposal Sent": [
            "Follow up on proposal",
            "Handle objections",
            "Prepare negotiation points"
        ],
        "In Negotiation": [
            "Negotiate pricing",
            "Finalize terms",
            "Get approval"
        ],
        "Follow-up Scheduled": [
            "Complete scheduled activity",
            "Update follow-up notes"
        ],
        "On Hold": [
            "Wait for customer response",
            "Set reminder"
        ],
        "Not Interested": [
            "Capture reason",
            "Close lead"
        ],
        "In Active": [
            "Re-engagement campaign",
            "Cold follow-up"
        ],
        "Closed": [
            "Verify conversion",
            "Review performance"
        ]
    };

    const stage_actions = actions[stage] || [];

    return `
        <div class="stage-panel">
            <div class="stage-panel-header">
                <div class="stage-subtitle">Current Lead Stage</div>
                <div class="stage-badge">${stage}</div>
            </div>
            <div class="stage-heading">Need to do Next</div>
            <div class="stage-panel-body">
                <div class="stage-actions-grid">
                    ${stage_actions.map(a => `
                        <div class="stage-action-card">
                            <span class="check">✔</span>
                            <span class="text">${a}</span>
                        </div>
                    `).join("")}
                </div>
            </div>

            <div class="stage-panel-footer">
                <div><b>Lead:</b> ${d.lead_name || d.name}</div>
                <div><b>Service:</b> ${d.service || "-"}</div>
            </div>
        </div>
    `;
}


function add_pipeline_workflow_menu(frm) {
    if (!frm.page) return;

    // Remove old Pipeline button (SPA safety)
    frm.page.remove_inner_button("Lead Pipeline");

    const actions = get_available_workflow_actions(frm);

    if (!actions.length) return;

    actions.forEach(action => {
        frm.add_custom_button(action, () => {
            apply_workflow_action(frm, action);
        }, "Lead Pipeline");
    });
}


function get_available_workflow_actions(frm) {
    const workflows = frappe.workflow?.workflows;
    if (!workflows || !workflows["Lead"]) return [];

    const workflow = workflows["Lead"];
    const current_state = frm.doc.workflow_state;

    return workflow.transitions
        .filter(t => t.state === current_state)
        .map(t => t.action);
}


function apply_workflow_action(frm, action) {
    const previous_state = frm.doc.workflow_state;

    frappe.confirm(
        `Are you sure you want to <b>${action}</b>?`,
        () => {
            // 🔑 IMPORTANT: release focus
            if (document.activeElement) {
                document.activeElement.blur();
            }
            frappe.call({
                method: "frappe.model.workflow.apply_workflow",
                args: {
                    doc: frm.doc,
                    action: action
                },
                freeze: true,
                callback() {
                    frm.reload_doc().then(() => {

                        show_whatsapp_automation_dialog(frm, previous_state, () => {

                            if (
                                frm.doc.workflow_state !== "New Lead" &&
                                !frm.doc.converted_account
                            ) {
                                show_convert_dialog(frm);
                            }

                        });

                    });
                }
            });
        }
    );
}

function show_convert_dialog(frm, msg) {

    const dialog = new frappe.ui.Dialog({

        title: __("Convert Lead"),

        fields: [
            {
                fieldtype: "HTML",
                fieldname: "confirm",
                options: `
                    <div style="
                        padding:12px;
                        background:#e0f2fe;
                        border:1px solid #bae6fd;
                        border-radius:8px;
                        color:#075985;
                        margin-bottom:12px;
                    ">
                        <b>${msg || "Are you sure you want to convert this Lead?"}</b><br>
                        This action will move the Lead to <b>Accounts & Contacts</b>.
                    </div>
                `
            },
            {
                fieldtype: "HTML",
                fieldname: "info",
                options: `
                    <div style="line-height:1.6">
                        <b>This will:</b>
                        <ul>
                            <li>Create or link an <b>Account</b></li>
                            <li>Create or link a <b>Contact</b></li>
                        </ul>
                    </div>
                `
            }
        ],

        primary_action_label: __("Yes, Convert Lead"),

        primary_action() {
            dialog.hide();
            convert_lead(frm);
        }

    });

    dialog.show();
}

function hide_actions_menu_button(frm) {
    if (!frm.page) return;

    // This targets the actual Actions dropdown button
    frm.page.wrapper
        .find('.actions-btn-group')
        .hide();
}

function sort_pipeline_timeline_desc(frm) {
    if (!frm.doc.converted_pipeline_timeline) return;

    // Sort rows by date_and_time DESC
    frm.doc.converted_pipeline_timeline.sort((a, b) => {
        return new Date(b.date_and_time) - new Date(a.date_and_time);
    });

    frm.refresh_field("converted_pipeline_timeline");
}


frappe.realtime.on("lead_followup_updated", function (data) {
    if (!cur_frm) return;

    if (cur_frm.doctype === "Lead" && cur_frm.doc.name === data.lead) {
        cur_frm.reload_doc();
    }
});

function show_whatsapp_automation_dialog(frm, previous_state, next = () => {}) {

    frappe.call({
        method: "company.company.doctype.crm_whatsapp_automation.crm_whatsapp_automation.get_automation_preview",
        args: {
            doctype: frm.doc.doctype,
            docname: frm.doc.name,
            previous_state: previous_state
        },

        callback(r) {

            if (!r.message) {
                next();
                return;
            }

            const automation = r.message;

            if (!automation.show_confirmation) {
                next();
                return;
            }

            let dialog_fields = [];
            
            if (frm.doc.workflow_state === "Proposal Sent") {
                dialog_fields.push({
                    fieldname: "proposal",
                    label: __("Proposal"),
                    fieldtype: "Link",
                    options: "Proposal",
                    reqd: 1
                });
            }

            dialog_fields.push({
                fieldtype: "HTML",
                fieldname: "preview"
            });

            const dialog = new frappe.ui.Dialog({

                title: automation.title || __("Send WhatsApp Message"),

                size: "large",

                fields: dialog_fields,

                primary_action_label: __("Send Message"),

                primary_action() {

                    let proposal = null;
                    if (frm.doc.workflow_state === "Proposal Sent") {
                        proposal = dialog.get_value("proposal");

                        if (!proposal) {
                            frappe.msgprint(__("Please select a Proposal."));
                            return;
                        }
                    }

                    dialog.disable_primary_action();

                    frappe.call({

                        method: "company.company.doctype.crm_whatsapp_automation.crm_whatsapp_automation.send_automation_message",

                        freeze: true,
                        freeze_message: __("Sending WhatsApp..."),

                        args: {

                            automation_name: automation.automation_name,
                            doctype: frm.doc.doctype,
                            docname: frm.doc.name,
                            proposal_name: proposal

                        },

                        callback(res) {

                            dialog.hide();

                            if (res.exc) {

                                frappe.msgprint({
                                    title: __("Error"),
                                    indicator: "red",
                                    message: __("Unable to send WhatsApp message.")
                                });

                            } else {

                                frappe.show_alert({
                                    message: __("WhatsApp Message Sent Successfully"),
                                    indicator: "green"
                                });

                            }

                            next();

                        },

                        error() {

                            dialog.hide();

                            frappe.msgprint({
                                title: __("Error"),
                                indicator: "red",
                                message: __("Unable to send WhatsApp message.")
                            });

                            next();

                        }

                    });

                },

                secondary_action_label: __("Skip"),

                secondary_action() {

                    dialog.hide();
                    next();

                }

            });

            dialog.show();

            if (frm.doc.workflow_state === "Proposal Sent") {
                // Filter Proposal by Lead
                dialog.set_query("proposal", () => {

                    return {
                        filters: {
                            lead: frm.doc.name
                        }
                    };

                });
            }

            dialog.fields_dict.preview.$wrapper.html(`

                <div style="
                    padding:16px;
                    background:#f8fafc;
                    border-radius:8px;
                    border:1px solid #e5e7eb;
                ">

                    <div style="
                        font-size:15px;
                        font-weight:600;
                        margin-bottom:10px;
                    ">
                        ${automation.message || "Do you want to send this WhatsApp message?"}
                    </div>

                    <div style="
                        background:white;
                        border:1px solid #d1d5db;
                        border-radius:6px;
                        padding:14px;
                        white-space:pre-wrap;
                        font-size:13px;
                        line-height:1.6;
                        max-height:300px;
                        overflow:auto;
                    ">
${frappe.utils.escape_html(automation.preview)}
                    </div>

                </div>

            `);

        }

    });

}