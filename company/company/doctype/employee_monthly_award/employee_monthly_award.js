frappe.ui.form.on('Employee Monthly Award', {
    setup: function (frm) {
        frm.set_query('employee', function () {
            return {
                filters: {
                    'status': 'Active'
                }
            };
        });
    },
    manually_selected: function (frm) {
        if (frm.doc.manually_selected) {
            frm.set_value('is_auto_generated', 0);
        }
    },
    is_auto_generated: function (frm) {
        if (frm.doc.is_auto_generated) {
            frm.set_value('manually_selected', 0);
        }
    }
});
