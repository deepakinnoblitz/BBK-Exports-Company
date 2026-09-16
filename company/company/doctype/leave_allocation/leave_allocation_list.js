frappe.listview_settings['Leave Allocation'] = {
    onload: function (listview) {
        listview.page.add_inner_button(__('Auto Allocate Monthly Leaves'), function () {
            let current_step = 'input';
            let d = new frappe.ui.Dialog({
                title: __('Auto Allocate Monthly Leaves'),
                size: 'large',
                fields: [
                    {
                        label: __('Year'),
                        fieldname: 'year',
                        fieldtype: 'Int',
                        default: frappe.datetime.now_date().split("-")[0],
                        reqd: 1
                    },
                    {
                        fieldtype: 'Column Break',
                        fieldname: 'cb1'
                    },
                    {
                        label: __('Month'),
                        fieldname: 'month',
                        fieldtype: 'Int',
                        default: parseInt(frappe.datetime.now_date().split("-")[1]),
                        reqd: 1
                    },
                    {
                        fieldtype: 'Section Break',
                        fieldname: 'sb1'
                    },
                    {
                        fieldtype: 'HTML',
                        fieldname: 'preview_html'
                    }
                ],
                primary_action_label: __('Next'),
                primary_action(values) {
                    if (current_step === 'input') {
                        show_preview(values);
                    } else {
                        confirm_allocation(values);
                    }
                }
            });

            function show_preview(values) {
                frappe.call({
                    method: "company.company.api.get_leave_allocation_preview",
                    args: {
                        year: values.year,
                        month: values.month
                    },
                    callback: function (r) {
                        current_step = 'preview';
                        let data = r.message || [];
                        let html = `
                            <style>
                                .allocation-preview-table {
                                    width: 100%;
                                    border-collapse: separate;
                                    border-spacing: 0;
                                    font-family: var(--font-stack);
                                }
                                .allocation-preview-table thead th {
                                    background-color: #f3f5f7;
                                    color: #4b5563;
                                    font-weight: 600;
                                    text-transform: uppercase;
                                    font-size: 11px;
                                    letter-spacing: 0.05em;
                                    padding: 12px 16px;
                                    border-bottom: 2px solid #e5e7eb;
                                    border-right: 1px solid #e5e7eb;
                                    position: sticky;
                                    top: 0;
                                    z-index: 10;
                                }
                                .allocation-preview-table thead th:last-child {
                                    border-right: none;
                                }
                                .allocation-preview-table tbody td {
                                    padding: 14px 16px;
                                    border-bottom: 1px solid #f3f4f6;
                                    border-right: 1px solid #f3f4f6;
                                    vertical-align: middle;
                                }
                                .allocation-preview-table tbody td:last-child {
                                    border-right: none;
                                }
                                .allocation-preview-table tbody tr:hover {
                                    background-color: #f9fafb;
                                }
                                .emp-name {
                                    font-weight: 600;
                                    color: #111827;
                                    font-size: 13px;
                                }
                                .emp-id {
                                    color: #6b7280;
                                    font-size: 11px;
                                }
                                .probation-badge {
                                    padding: 4px 10px;
                                    border-radius: 9999px;
                                    font-size: 10px;
                                    font-weight: 600;
                                    display: inline-block;
                                }
                                .probation-badge.danger { background-color: #fee2e2; color: #991b1b; }
                                .probation-badge.info { background-color: #e0f2fe; color: #075985; }
                                .alloc-item {
                                    margin-bottom: 6px;
                                    background: #fff;
                                    padding: 4px 8px;
                                    border: 1px solid #f3f4f6;
                                    border-radius: 6px;
                                }
                                .alloc-tag {
                                    font-size: 10px;
                                    padding: 2px 6px;
                                    border-radius: 4px;
                                    margin-left: 4px;
                                }
                                .tag-already { background-color: #fef3c7; color: #92400e; }
                                .tag-proposed { background-color: #dcfce7; color: #166534; }
                            </style>
                            <div style="max-height: 600px; overflow-y: auto; margin-top: 10px; border: 1px solid #e5e7eb; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                                <table class="allocation-preview-table">
                                    <thead>
                                        <tr>
                                            <th style="width: 60px; text-align: center;">${__('S.No')}</th>
                                            <th style="width: 150px;">${__('Employee')}</th>
                                            <th style="text-align: center;">${__('Joining Date')}</th>
                                            <th style="text-align: center;">${__('Status')}</th>
                                            <th>${__('Proposed Allocations')}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                        `;

                        data.forEach((row, idx) => {
                            let allocs = row.allocations.map(a => {
                                let tagClass = a.exists ? 'tag-already' : 'tag-proposed';
                                let tagText = a.exists ? __('Already Allocated') : __('Proposed');
                                return `
                                    <div class="alloc-item">
                                        <span style="color: #374151; font-weight: 500;">${a.leave_type}</span>: 
                                        <span style="color: #111827; font-weight: 600;">${a.count}</span>
                                        <span class="alloc-tag ${tagClass}">${tagText}</span>
                                    </div>`;
                            }).join('');

                            let statusHtml = row.in_probation
                                ? `<span class="probation-badge danger">${__('Probation')}</span>`
                                : `<span class="probation-badge info">${__('Permanent')}</span>`;

                            html += `
                                <tr>
                                    <td style="text-align: center; color: #9ca3af; font-weight: 500;">${idx + 1}</td>
                                    <td>
                                        <div class="emp-name">${row.employee_name}</div>
                                        <div class="emp-id">${row.employee_id}</div>
                                    </td>
                                    <td style="text-align: center; color: #4b5563;">${frappe.datetime.str_to_user(row.date_of_joining)}</td>
                                    <td style="text-align: center;">${statusHtml}</td>
                                    <td>${allocs || '<span style="color: #9ca3af; font-style: italic;">' + __('No pending allocations') + '</span>'}</td>
                                </tr>
                            `;
                        });

                        html += `
                                    </tbody>
                                </table>
                            </div>
                            <div class="text-muted small" style="margin-top: 8px;">
                                ${__('* Paid Leave is skipped for employees in probation (< 3 months).')}
                            </div>
                        `;

                        d.fields_dict.preview_html.$wrapper.html(html);
                        d.get_field('year').df.hidden = 1;
                        d.get_field('month').df.hidden = 1;
                        d.refresh();

                        d.set_primary_action_label(__('Allocate'));

                        // Add Back Button if not already present
                        if (!d.get_secondary_label() || d.get_secondary_label() !== __('Back')) {
                            d.set_secondary_action_label(__('Back'));
                            d.set_secondary_action(() => {
                                current_step = 'input';
                                d.get_field('year').df.hidden = 0;
                                d.get_field('month').df.hidden = 0;
                                d.fields_dict.preview_html.$wrapper.empty();
                                d.refresh();
                                d.set_primary_action_label(__('Next'));
                                d.set_secondary_action_label(""); // clear back button
                            });
                        }
                    }
                });
            }

            function confirm_allocation(values) {
                frappe.confirm(
                    __('Are you sure you want to allocate leaves for {0}-{1}?', [values.year, values.month]),
                    () => {
                        frappe.call({
                            method: "company.company.api.auto_allocate_monthly_leaves",
                            args: {
                                year: values.year,
                                month: values.month
                            },
                            callback: function (r) {
                                if (r.message) {
                                    frappe.msgprint(r.message);
                                    listview.refresh();
                                    d.hide();
                                }
                            }
                        });
                    }
                );
            }

            d.show();
        });
    }
};
