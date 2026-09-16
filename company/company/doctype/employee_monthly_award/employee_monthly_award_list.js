frappe.listview_settings['Employee Monthly Award'] = {
	onload: function(listview) {
		listview.page.add_inner_button(__('Generate Monthly Awards'), function() {
			let d = new frappe.ui.Dialog({
				title: __('Generate Awards'),
				fields: [
					{
						label: __('Month'),
						fieldname: 'month',
						fieldtype: 'Date',
						default: frappe.datetime.get_today(),
						reqd: 1
					}
				],
				primary_action_label: __('Generate'),
				primary_action(values) {
					frappe.call({
						method: 'company.company.doctype.employee_monthly_award.employee_monthly_award.calculate_monthly_awards',
						args: {
							month: values.month
						},
						callback: function(r) {
							if (!r.exc) {
								frappe.msgprint(__('Generated {0} awards successfully', [r.message]));
								listview.refresh();
							}
							d.hide();
						}
					});
				}
			});
			d.show();
		});
	}
};
