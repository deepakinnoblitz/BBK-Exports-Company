frappe.ui.form.on('Employee Remainder Queue', {
	refresh: function(frm) {
		if (frm.doc.status === 'Pending' || frm.doc.status === 'Failed') {
			frm.add_custom_button(__('Trigger Now'), function() {
				frappe.call({
					method: 'company.company.employee_remainder_api.manual_trigger_remainder',
					args: {
						queue_name: frm.doc.name
					},
					callback: function(r) {
						if (r.message) {
							frappe.show_alert({
								message: __('Reminder Triggered Successfully'),
								indicator: 'green'
							});
							frm.reload_doc();
						} else {
							frappe.msgprint(__('Failed to trigger reminder. Check Error Log.'));
						}
					}
				});
			}).addClass('btn-primary');
		}
	}
});
