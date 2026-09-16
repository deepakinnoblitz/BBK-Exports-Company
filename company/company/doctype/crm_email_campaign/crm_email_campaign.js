frappe.ui.form.on('CRM Email Campaign', {
    onload: function(frm) {
        // Setup initial suggestion lists for existing filter rows
        if (frm.doc.filters) {
            frm.doc.filters.forEach(row => {
                setup_value_suggestions(frm, row.doctype, row.name);
            });
        }
    },
    refresh(frm) {
        // Render dashboard
        render_dashboard(frm);

        if (frm.doc.status === 'Draft') {
            frm.add_custom_button(__('Calculate Recipients'), () => {
                if (frm.is_new() || frm.doc.__unsaved) {
                    frappe.msgprint(__('Please save the Campaign before calculating recipients.'));
                    return;
                }
                frappe.call({
                    method: 'company.company.doctype.crm_email_campaign.crm_email_campaign.calculate_recipients',
                    args: {
                        campaign_name: frm.doc.name
                    },
                    callback(r) {
                        frm.reload_doc();
                        frappe.show_alert({
                            message: __('Recipients calculated: {0}', [r.message]),
                            indicator: 'green'
                        });
                    }
                });
            }).addClass('btn-info');
        }

        if (frm.doc.status === 'Draft' || frm.doc.status === 'Paused') {
            frm.add_custom_button(__('Start Campaign'), () => {
                if (frm.is_new() || frm.doc.__unsaved) {
                    frappe.msgprint(__('Please save the Campaign before starting.'));
                    return;
                }
                frappe.call({
                    method: 'company.company.doctype.crm_email_campaign.crm_email_campaign.start_campaign',
                    args: {
                        campaign_name: frm.doc.name
                    },
                    callback() {
                        frm.reload_doc();
                    }
                });
            }).addClass('btn-primary');
        }

        if (frm.doc.status === 'Running') {
            frm.add_custom_button(__('Pause Campaign'), () => {
                frappe.call({
                    method: 'company.company.doctype.crm_email_campaign.crm_email_campaign.pause_campaign',
                    args: {
                        campaign_name: frm.doc.name
                    },
                    callback() {
                        frm.reload_doc();
                    }
                });
            });

            frm.add_custom_button(__('Cancel Campaign'), () => {
                frappe.call({
                    method: 'company.company.doctype.crm_email_campaign.crm_email_campaign.cancel_campaign',
                    args: {
                        campaign_name: frm.doc.name
                    },
                    callback() {
                        frm.reload_doc();
                    }
                });
            });
        }
    },
    email_template: function(frm) {
        if (frm.doc.email_template) {
            frappe.db.get_value('CRM Email Template', frm.doc.email_template, 'subject', (r) => {
                if (r && r.subject) {
                    frm.set_value('subject', r.subject);
                }
            });
        }
    }
});

frappe.ui.form.on('CRM Campaign Filter', {
    field_name: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, 'value', '');
        setup_value_suggestions(frm, cdt, cdn);
    },
    filters_add: function(frm, cdt, cdn) {
        setup_value_suggestions(frm, cdt, cdn);
    },
    value: function(frm, cdt, cdn) {
        setup_value_suggestions(frm, cdt, cdn);
    }
});

function setup_value_suggestions(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    if (!row || !row.field_name || !frm.doc.target_type) {
        return;
    }
    
    frappe.call({
        method: 'company.company.doctype.crm_email_campaign.crm_email_campaign.get_filter_value_options',
        args: {
            target_type: frm.doc.target_type,
            field_name: row.field_name
        },
        callback: function(r) {
            if (r.message) {
                let grid_row = frm.fields_dict['filters'].grid.get_row(cdn);
                if (grid_row) {
                    let field = grid_row.fields_dict['value'];
                    if (field) {
                        field.df.options = r.message;
                        if (field.awesomplete) {
                            field.awesomplete.list = r.message;
                        }
                    }
                }
            }
        }
    });
}

function render_dashboard(frm) {
    if (!frm.fields_dict.analytics_dashboard_html) return;
    
    if (frm.is_new() || frm.doc.__unsaved) {
        let html = get_dashboard_html(frm, [], 'filters');
        frm.fields_dict.analytics_dashboard_html.html(html);
        return;
    }
    
    frappe.call({
        method: 'company.company.doctype.crm_email_campaign.crm_email_campaign.get_campaign_recipients',
        args: {
            campaign_name: frm.doc.name
        },
        callback: function(r) {
            let recipients = r.message ? r.message.recipients : [];
            let source = r.message ? r.message.source : 'filters';
            let html = get_dashboard_html(frm, recipients, source);
            frm.fields_dict.analytics_dashboard_html.html(html);
        }
    });
}

function get_dashboard_html(frm, recipients, source) {
    let sent = frm.doc.sent_count || 0;
    let opened = frm.doc.open_count || 0;
    let clicked = frm.doc.click_count || 0;
    let failed = frm.doc.failed_count || 0;
    let total = frm.doc.total_recipients || 0;
    
    let open_rate = sent ? ((opened / sent) * 100).toFixed(1) : 0;
    let click_rate = sent ? ((clicked / sent) * 100).toFixed(1) : 0;
    let delivery_rate = total ? (((sent - failed) / total) * 100).toFixed(1) : 0;
    let failure_rate = total ? ((failed / total) * 100).toFixed(1) : 0;
    
    // Status Badge colors
    let get_status_badge = (status) => {
        let colors = {
            'Pending': 'background-color: #f1f5f9; color: #475569;',
            'Processing': 'background-color: #fef3c7; color: #d97706;',
            'Sent': 'background-color: #d1fae5; color: #059669;',
            'Failed': 'background-color: #fee2e2; color: #dc2626;'
        };
        return `<span style="display: inline-block; padding: 2px 8px; font-size: 11px; font-weight: 500; border-radius: 9999px; ${colors[status] || colors.Pending}">${status}</span>`;
    };

    // Tracking flags
    let get_tracking_flags = (rec) => {
        let flags = [];
        if (rec.opened) flags.push('<span style="color: #059669; font-weight: 600;">Opened</span>');
        if (rec.clicked) flags.push('<span style="color: #0891b2; font-weight: 600;">Clicked</span>');
        return flags.join(' | ') || '<span style="color: #94a3b8;">None</span>';
    };

    let table_rows = recipients.map(rec => {
        let tracking = get_tracking_flags(rec);
        let status_badge = get_status_badge(rec.status);
        let err_tooltip = rec.error_message ? `<div style="font-size: 10px; color: #dc2626; margin-top: 2px;">${rec.error_message}</div>` : '';
        return `
        <tr style="border-bottom: 1px solid #f1f5f9;">
            <td style="padding: 10px 12px; font-weight: 500; color: #1e293b;">${rec.recipient_name || ''}</td>
            <td style="padding: 10px 12px; color: #64748b;">${rec.recipient_email || ''}</td>
            <td style="padding: 10px 12px; text-align: center;">${status_badge} ${err_tooltip}</td>
            <td style="padding: 10px 12px; text-align: center;">${tracking}</td>
        </tr>
        `;
    }).join('');

    let list_label = source === 'queue' ? 'Email Queue / Delivery Status' : 'Estimated Target Recipients';
    let list_html = recipients.length ? `
    <div style="margin-top: 24px;">
        <h5 style="color: #475569; font-weight: 600; font-size: 13px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">${list_label} (${recipients.length})</h5>
        <div style="max-height: 250px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 8px; background-color: #f8fafc; box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.03);">
            <table style="margin: 0; font-size: 12px; width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background-color: #f1f5f9; border-bottom: 1px solid #e2e8f0; text-align: left; position: sticky; top: 0; z-index: 10;">
                        <th style="padding: 10px 12px; font-weight: 600; color: #475569;">Name</th>
                        <th style="padding: 10px 12px; font-weight: 600; color: #475569;">Email</th>
                        <th style="padding: 10px 12px; font-weight: 600; color: #475569; text-align: center;">Status</th>
                        <th style="padding: 10px 12px; font-weight: 600; color: #475569; text-align: center;">Activity</th>
                    </tr>
                </thead>
                <tbody>
                    ${table_rows}
                </tbody>
            </table>
        </div>
    </div>
    ` : `
    <div style="margin-top: 24px; padding: 15px; border: 1px dashed #cbd5e1; border-radius: 8px; text-align: center; color: #64748b; font-size: 13px;">
        No recipients calculated yet. Please set your audience filters and click "Calculate Recipients".
    </div>
    `;

    return `
    <div style="padding: 20px; background-color: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
        <h4 style="margin-top: 0; margin-bottom: 20px; color: #1e293b; font-weight: 600; font-size: 16px;">Campaign Analytics Dashboard</h4>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 16px; margin-bottom: 24px;">
            <div style="background: linear-gradient(135deg, #64748b, #475569); color: white; padding: 16px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                <div style="font-size: 11px; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500;">Total Target</div>
                <div style="font-size: 26px; font-weight: 700; margin-top: 6px;">${total}</div>
            </div>
            <div style="background: linear-gradient(135deg, #3b82f6, #1d4ed8); color: white; padding: 16px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                <div style="font-size: 11px; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500;">Sent</div>
                <div style="font-size: 26px; font-weight: 700; margin-top: 6px;">${sent}</div>
            </div>
            <div style="background: linear-gradient(135deg, #10b981, #047857); color: white; padding: 16px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                <div style="font-size: 11px; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500;">Opened</div>
                <div style="font-size: 26px; font-weight: 700; margin-top: 6px;">${opened}</div>
            </div>
            <div style="background: linear-gradient(135deg, #06b6d4, #0891b2); color: white; padding: 16px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                <div style="font-size: 11px; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500;">Clicked</div>
                <div style="font-size: 26px; font-weight: 700; margin-top: 6px;">${clicked}</div>
            </div>
            <div style="background: linear-gradient(135deg, #ef4444, #b91c1c); color: white; padding: 16px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                <div style="font-size: 11px; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500;">Failed</div>
                <div style="font-size: 26px; font-weight: 700; margin-top: 6px;">${failed}</div>
            </div>
        </div>
        
        <h5 style="color: #475569; font-weight: 600; font-size: 13px; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 0.5px;">Performance Summary</h5>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; margin-bottom: 15px;">
            <div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                    <span style="color: #64748b; font-weight: 500;">Delivery Rate</span>
                    <span style="color: #0f172a; font-weight: bold;">${delivery_rate}%</span>
                </div>
                <div style="background-color: #f1f5f9; height: 8px; border-radius: 4px; overflow: hidden; border: 1px solid #e2e8f0;">
                    <div style="background-color: #3b82f6; width: ${delivery_rate}%; height: 100%; border-radius: 4px;"></div>
                </div>
            </div>
            <div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                    <span style="color: #64748b; font-weight: 500;">Open Rate</span>
                    <span style="color: #0f172a; font-weight: bold;">${open_rate}%</span>
                </div>
                <div style="background-color: #f1f5f9; height: 8px; border-radius: 4px; overflow: hidden; border: 1px solid #e2e8f0;">
                    <div style="background-color: #10b981; width: ${open_rate}%; height: 100%; border-radius: 4px;"></div>
                </div>
            </div>
            <div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                    <span style="color: #64748b; font-weight: 500;">Click Rate</span>
                    <span style="color: #0f172a; font-weight: bold;">${click_rate}%</span>
                </div>
                <div style="background-color: #f1f5f9; height: 8px; border-radius: 4px; overflow: hidden; border: 1px solid #e2e8f0;">
                    <div style="background-color: #06b6d4; width: ${click_rate}%; height: 100%; border-radius: 4px;"></div>
                </div>
            </div>
            <div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                    <span style="color: #64748b; font-weight: 500;">Failure Rate</span>
                    <span style="color: #0f172a; font-weight: bold;">${failure_rate}%</span>
                </div>
                <div style="background-color: #f1f5f9; height: 8px; border-radius: 4px; overflow: hidden; border: 1px solid #e2e8f0;">
                    <div style="background-color: #ef4444; width: ${failure_rate}%; height: 100%; border-radius: 4px;"></div>
                </div>
            </div>
        </div>
        
        ${list_html}
    </div>
    `;
}