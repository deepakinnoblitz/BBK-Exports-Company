frappe.listview_settings['Salary Slip'] = {
    onload: function (listview) {
        add_generate_button(listview);
    },
    refresh: function (listview) {
        add_generate_button(listview);
    }
};

function add_generate_button(listview) {
    const allowed_roles = ['HR', 'System Manager'];
    const has_role = allowed_roles.some(role => frappe.user_roles.includes(role));
    if (!has_role) return;

    if (!listview.page.has_generate_button) {
        listview.page.add_menu_item(__('Generate Salary Slips'), function () {
            const today = new Date();
            const current_year = today.getFullYear();
            const current_month = today.getMonth() + 1;

            // Step 1: Prompt Year and Month
            frappe.prompt([
                {
                    fieldname: 'year',
                    fieldtype: 'Int',
                    label: 'Year',
                    reqd: 1,
                    default: current_year
                },
                {
                    fieldname: 'month',
                    fieldtype: 'Select',
                    options: '1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12',
                    label: 'Month',
                    reqd: 1,
                    default: current_month.toString()
                }
            ],
                function (values) {
                    // Step 2: Open MultiSelectDialog for Employees
                    const d = new frappe.ui.form.MultiSelectDialog({
                        doctype: "Employee",
                        target: listview,
                        setters: { status: "Active" },
                        get_query() {
                            return {
                                filters: { status: "Active" }
                            };
                        },
                        size: "large",
                        add_filters_group: 1,

                        // 🧾 Custom formatter for employee rows
                        format_item(item) {
                            return `
                                <div style="display:flex; justify-content:space-between; align-items:center; width:100%;">
                                    <div>
                                        <b>${item.employee_name || item.name}</b>
                                        <div style="font-size:12px; color:#6c757d;">${item.name}</div>
                                    </div>
                                    <span style="font-weight:500; color:${item.status === 'Active' ? 'green' : 'gray'};">
                                        ${item.status}
                                    </span>
                                </div>`;
                        },

                        action(selections) {
                            if (!selections.length) {
                                frappe.msgprint(__('Please select at least one employee'));
                                return;
                            }

                            const args = {
                                ...values,
                                employees: selections
                            };

                            frappe.call({
                                method: "company.company.api.generate_salary_slips_from_employee",
                                args: args,
                                freeze: true,
                                freeze_message: __("Generating Salary Slips..."),
                                callback: function (r) {
                                    frappe.msgprint(r.message);
                                    listview.refresh();
                                },
                                error: function (err) {
                                    frappe.msgprint(__('Error generating salary slips. Check console.'));
                                    console.error(err);
                                }
                            });

                            cur_dialog.hide();
                        }
                    });

                    // 🩵 PATCH: Once dialog loads, update list items with employee_name
                    frappe.after_ajax(() => {
                        setTimeout(() => {
                            const list_items = d.$wrapper.find('.list-item-container');
                            list_items.each(function () {
                                const item_el = $(this);
                                const emp_id = item_el.data('item-name');
                                if (!emp_id) return;

                                frappe.db.get_value('Employee', emp_id, 'employee_name', (r) => {
                                    if (r && r.employee_name) {
                                        item_el.find('.list-id').text(r.employee_name + ' (' + emp_id + ')');
                                    }
                                });
                            });
                        }, 300);
                    });
                },
                __('Select Month and Year'),
                __('Next')
            );
        }, true);

        listview.page.has_generate_button = true;
    }
}
