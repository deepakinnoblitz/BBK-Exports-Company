// Copyright (c) 2026, deepak and contributors
// For license information, please see license.txt

frappe.ui.form.on("CRM WhatsApp Campaign", {
	refresh(frm) {
		_render_dashboard(frm);
		_add_campaign_buttons(frm);
	},

	onload(frm) {
		// Setup value suggestions for existing filter rows on load
		if (frm.doc.filters) {
			frm.doc.filters.forEach(row => {
				_setup_value_suggestions(frm, row.doctype, row.name);
			});
		}
	},

	whatsapp_template(frm) {
		// Auto-populate subject from template name if subject field exists
		if (frm.doc.whatsapp_template && frm.fields_dict.subject) {
			frm.set_value("subject", frm.doc.whatsapp_template);
		}
	}
});

// ── Filter child table events ─────────────────────────────────────────────
frappe.ui.form.on("CRM Campaign Filter", {
	field_name(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "value", "");
		_setup_value_suggestions(frm, cdt, cdn);
	},
	filters_add(frm, cdt, cdn) {
		_setup_value_suggestions(frm, cdt, cdn);
	},
	value(frm, cdt, cdn) {
		_setup_value_suggestions(frm, cdt, cdn);
	}
});

// ── Action buttons ────────────────────────────────────────────────────────
function _add_campaign_buttons(frm) {
	const status = frm.doc.status;

	// Calculate Recipients (Draft only)
	if (status === "Draft") {
		frm.add_custom_button(__("Calculate Recipients"), function () {
			if (frm.is_new() || frm.doc.__unsaved) {
				frappe.msgprint(__("Please save the Campaign before calculating recipients."));
				return;
			}
			if (!frm.doc.target_type) {
				frappe.msgprint(__("Please select a Target Type first."));
				return;
			}
			frappe.call({
				method: "company.company.doctype.crm_whatsapp_campaign.crm_whatsapp_campaign.calculate_recipients",
				args: { campaign_name: frm.doc.name },
				callback(r) {
					frm.reload_doc();
					frappe.show_alert({
						message: __("Recipients calculated: {0}", [r.message]),
						indicator: "green"
					});
				}
			});
		}).addClass("btn-info");
	}

	// Start Campaign (Draft / Paused)
	if (["Draft", "Paused"].includes(status)) {
		frm.add_custom_button(__("Start Campaign"), function () {
			if (frm.is_new() || frm.doc.__unsaved) {
				frappe.msgprint(__("Please save the Campaign before starting."));
				return;
			}
			frappe.call({
				method: "company.company.doctype.crm_whatsapp_campaign.crm_whatsapp_campaign.start_campaign",
				args: { campaign_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Starting campaign…"),
				callback() {
					frappe.show_alert({ message: __("Campaign started"), indicator: "green" });
					frm.reload_doc();
				}
			});
		}).addClass("btn-primary");
	}

	// Pause + Cancel (Running)
	if (status === "Running") {
		frm.add_custom_button(__("Pause Campaign"), function () {
			frappe.call({
				method: "company.company.doctype.crm_whatsapp_campaign.crm_whatsapp_campaign.pause_campaign",
				args: { campaign_name: frm.doc.name },
				callback() {
					frappe.show_alert({ message: __("Campaign paused"), indicator: "orange" });
					frm.reload_doc();
				}
			});
		});

		frm.add_custom_button(__("Cancel Campaign"), function () {
			frappe.confirm(
				__("Are you sure you want to cancel this campaign? This cannot be undone."),
				function () {
					frappe.call({
						method: "company.company.doctype.crm_whatsapp_campaign.crm_whatsapp_campaign.cancel_campaign",
						args: { campaign_name: frm.doc.name },
						callback() {
							frappe.show_alert({ message: __("Campaign cancelled"), indicator: "red" });
							frm.reload_doc();
						}
					});
				}
			);
		});
	}
}

// ── Filter value autocomplete ─────────────────────────────────────────────
function _setup_value_suggestions(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!row || !row.field_name || !frm.doc.target_type) return;

	frappe.call({
		method: "company.company.doctype.crm_whatsapp_campaign.crm_whatsapp_campaign.get_filter_value_options",
		args: {
			target_type: frm.doc.target_type,
			field_name: row.field_name
		},
		callback(r) {
			if (r.message) {
				let grid_row = frm.fields_dict["filters"].grid.get_row(cdn);
				if (grid_row) {
					let field = grid_row.fields_dict["value"];
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

// ── Analytics Dashboard ───────────────────────────────────────────────────
function _render_dashboard(frm) {
	if (!frm.fields_dict.analytics_dashboard_html) return;

	if (frm.is_new() || frm.doc.__unsaved) {
		frm.fields_dict.analytics_dashboard_html.html(_get_dashboard_html(frm, [], "filters"));
		return;
	}

	frappe.call({
		method: "company.company.doctype.crm_whatsapp_campaign.crm_whatsapp_campaign.get_campaign_recipients",
		args: { campaign_name: frm.doc.name },
		callback(r) {
			let recipients = r.message ? r.message.recipients : [];
			let source = r.message ? r.message.source : "filters";
			frm.fields_dict.analytics_dashboard_html.html(_get_dashboard_html(frm, recipients, source));
		}
	});
}

function _get_dashboard_html(frm, recipients, source) {
	let sent    = frm.doc.sent_count    || 0;
	let failed  = frm.doc.failed_count  || 0;
	let total   = frm.doc.total_recipients || 0;
	let delivery_rate = total ? (((sent) / total) * 100).toFixed(1) : 0;
	let failure_rate  = total ? ((failed / total) * 100).toFixed(1) : 0;

	let status_badge = (status) => {
		let colors = {
			"Pending":    "background:#f1f5f9;color:#475569;",
			"Processing": "background:#fef3c7;color:#d97706;",
			"Sent":       "background:#d1fae5;color:#059669;",
			"Failed":     "background:#fee2e2;color:#dc2626;"
		};
		return `<span style="display:inline-block;padding:2px 8px;font-size:11px;font-weight:500;border-radius:9999px;${colors[status]||colors.Pending}">${status}</span>`;
	};

	let table_rows = recipients.map(rec => `
		<tr style="border-bottom:1px solid #f1f5f9;">
			<td style="padding:10px 12px;font-weight:500;color:#1e293b;">${rec.recipient_name || ""}</td>
			<td style="padding:10px 12px;color:#64748b;">${rec.recipient_phone || ""}</td>
			<td style="padding:10px 12px;text-align:center;">${status_badge(rec.status)}
				${rec.error_message ? `<div style="font-size:10px;color:#dc2626;margin-top:2px;">${rec.error_message}</div>` : ""}
			</td>
		</tr>`).join("");

	let list_label = source === "queue" ? "WhatsApp Queue / Delivery Status" : "Estimated Target Recipients";
	let list_html = recipients.length ? `
	<div style="margin-top:24px;">
		<h5 style="color:#475569;font-weight:600;font-size:13px;margin-bottom:12px;text-transform:uppercase;letter-spacing:0.5px;">${list_label} (${recipients.length})</h5>
		<div style="max-height:250px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;">
			<table style="margin:0;font-size:12px;width:100%;border-collapse:collapse;">
				<thead>
					<tr style="background:#f1f5f9;border-bottom:1px solid #e2e8f0;text-align:left;">
						<th style="padding:10px 12px;font-weight:600;color:#475569;">Name</th>
						<th style="padding:10px 12px;font-weight:600;color:#475569;">Phone</th>
						<th style="padding:10px 12px;font-weight:600;color:#475569;text-align:center;">Status</th>
					</tr>
				</thead>
				<tbody>${table_rows}</tbody>
			</table>
		</div>
	</div>` : `<div style="margin-top:24px;padding:15px;border:1px dashed #cbd5e1;border-radius:8px;text-align:center;color:#64748b;font-size:13px;">
		No recipients calculated yet. Set your audience filters and click "Calculate Recipients".
	</div>`;

	return `
	<div style="padding:20px;background:#fff;border-radius:12px;border:1px solid #e2e8f0;margin-bottom:24px;box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
		<h4 style="margin-top:0;margin-bottom:20px;color:#1e293b;font-weight:600;font-size:16px;">Campaign Analytics Dashboard</h4>
		<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:16px;margin-bottom:24px;">
			<div style="background:linear-gradient(135deg,#64748b,#475569);color:#fff;padding:16px;border-radius:8px;text-align:center;">
				<div style="font-size:11px;opacity:0.9;text-transform:uppercase;letter-spacing:0.5px;font-weight:500;">Total</div>
				<div style="font-size:26px;font-weight:700;margin-top:6px;">${total}</div>
			</div>
			<div style="background:linear-gradient(135deg,#3b82f6,#1d4ed8);color:#fff;padding:16px;border-radius:8px;text-align:center;">
				<div style="font-size:11px;opacity:0.9;text-transform:uppercase;letter-spacing:0.5px;font-weight:500;">Sent</div>
				<div style="font-size:26px;font-weight:700;margin-top:6px;">${sent}</div>
			</div>
			<div style="background:linear-gradient(135deg,#ef4444,#b91c1c);color:#fff;padding:16px;border-radius:8px;text-align:center;">
				<div style="font-size:11px;opacity:0.9;text-transform:uppercase;letter-spacing:0.5px;font-weight:500;">Failed</div>
				<div style="font-size:26px;font-weight:700;margin-top:6px;">${failed}</div>
			</div>
			<div style="background:linear-gradient(135deg,#10b981,#047857);color:#fff;padding:16px;border-radius:8px;text-align:center;">
				<div style="font-size:11px;opacity:0.9;text-transform:uppercase;letter-spacing:0.5px;font-weight:500;">Delivery %</div>
				<div style="font-size:26px;font-weight:700;margin-top:6px;">${delivery_rate}%</div>
			</div>
		</div>
		<h5 style="color:#475569;font-weight:600;font-size:13px;margin-bottom:16px;text-transform:uppercase;letter-spacing:0.5px;">Performance</h5>
		<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px;margin-bottom:15px;">
			<div>
				<div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:13px;">
					<span style="color:#64748b;font-weight:500;">Delivery Rate</span>
					<span style="color:#0f172a;font-weight:bold;">${delivery_rate}%</span>
				</div>
				<div style="background:#f1f5f9;height:8px;border-radius:4px;overflow:hidden;">
					<div style="background:#3b82f6;width:${delivery_rate}%;height:100%;border-radius:4px;"></div>
				</div>
			</div>
			<div>
				<div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:13px;">
					<span style="color:#64748b;font-weight:500;">Failure Rate</span>
					<span style="color:#0f172a;font-weight:bold;">${failure_rate}%</span>
				</div>
				<div style="background:#f1f5f9;height:8px;border-radius:4px;overflow:hidden;">
					<div style="background:#ef4444;width:${failure_rate}%;height:100%;border-radius:4px;"></div>
				</div>
			</div>
		</div>
		${list_html}
	</div>`;
}
