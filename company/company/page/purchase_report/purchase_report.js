frappe.pages['purchase-report'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Purchase Report',
        single_column: true
    });

    // Inject simple CSS for styling
    const custom_css = `
        <style>
            * { font-family: "Inter", sans-serif; }
            .purchase-report-container { padding: 20px; }
            .summary-cards { margin-bottom: 20px; }
            .summary-card {
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                padding: 20px;
                margin-bottom: 20px;
                text-align: center;
            }
            .card-title { font-size: 14px; color: #666; text-transform: uppercase; }
            .card-value { font-size: 22px; font-weight: bold; color: #2c3e50; }
            .report-table-container {
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.08);
                padding: 15px;
            }
            .custom-table thead th {
                background: #495057;
                color: white;
                padding: 10px;
                font-size: 13px;
            }
            .custom-table tbody td {
                padding: 10px;
                border-bottom: 1px solid #eee;
                font-size: 13px;
            }
            .currency-amount { font-weight: 500; color: #2c3e50; }
        </style>
    `;
    $('head').append(custom_css);

    // Main container
    let main_container = $('<div class="purchase-report-container"></div>').appendTo(page.main);

    // Containers
    let summary_section = $('<div class="summary-cards row"></div>').appendTo(main_container);
    let report_container = $('<div></div>').appendTo(main_container);

    function formatCurrency(amount) {
        if (!amount || amount === 0) return '₹0.00';
        return '₹' + parseFloat(amount).toLocaleString('en-IN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    function load_report() {
        // Call your Purchase report execute function
        frappe.call({
            method: "company.company.report.purchase_report.purchase_report.execute",
            args: {},
            callback: function(r) {
                report_container.empty();
                summary_section.empty();

                if (!r.message || r.message.length === 0) {
                    report_container.html(`
                        <div style="padding:40px;text-align:center;color:#999;">
                            <i class="fa fa-file-alt" style="font-size:40px;color:#ddd;"></i>
                            <p>No purchase records found.</p>
                        </div>
                    `);
                    return;
                }

                let columns = r.message[0];
                let data = r.message[1];

                // --- Summary Cards ---
                let total_amount = data.reduce((sum, row) => sum + (parseFloat(row.grand_total) || 0), 0);
                let total_invoices = data.length;

                let cards = [
                    { label: "Total Purchases", value: total_invoices },
                    { label: "Total Amount", value: formatCurrency(total_amount) }
                ];

                cards.forEach(c => {
                    let card = $(`
                        <div class="col-md-3 col-sm-6">
                            <div class="summary-card">
                                <div class="card-title">${c.label}</div>
                                <div class="card-value">${c.value}</div>
                            </div>
                        </div>
                    `);
                    summary_section.append(card);
                });

                // --- Data Table ---
                let table_container = $(`
                    <div class="report-table-container">
                        <table class="table custom-table">
                            <thead><tr></tr></thead>
                            <tbody></tbody>
                        </table>
                    </div>
                `).appendTo(report_container);

                let table = table_container.find('.custom-table');
                let thead_row = table.find('thead tr');
                
                columns.forEach(col => {
                    thead_row.append(`<th>${col.label}</th>`);
                });

                let tbody = table.find('tbody');
                data.forEach(row => {
                    let tr = $('<tr></tr>').appendTo(tbody);
                    columns.forEach(col => {
                        let value = row[col.fieldname] || '';
                        if (col.fieldtype === "Currency" || col.fieldname.includes("total")) {
                            value = `<span class="currency-amount">${formatCurrency(value)}</span>`;
                        } else if (col.fieldtype === "Date" && value) {
                            value = frappe.datetime.str_to_user(value);
                        }
                        tr.append(`<td>${value}</td>`);
                    });
                });
            }
        });
    }

    load_report();
};
