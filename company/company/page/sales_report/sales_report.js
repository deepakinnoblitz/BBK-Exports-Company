frappe.pages['sales-report'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Sales Report',
        single_column: true
    });

    // Add Font Awesome and custom CSS for modern styling
    if (!$('head').find('link[href*="font-awesome"]').length) {
        $('head').append('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">','<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">');
    }
    
    const custom_css = `
        <style>
            * {
                font-family: var(--font-stack);
            }

            :root {
                --font-stack: "InterVariable", "Inter", -apple-system, BlinkMacSystemFont,
                            "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, 
                            "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif;
            }

            
            .sales-report-container {
                padding: 20px;
                background: #f8f9fa;
                min-height: calc(100vh - 120px);
                font-family: var(--font-stack);
            }
            
            .filter-card {
                background: white;
                border-radius: 12px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.08);
                padding: 24px;
                margin-bottom: 24px;
                border: 1px solid #e3e6f0;
            }
            
            .filter-title {
                font-size: 18px;
                font-weight: 600;
                color: #2c3e50;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .form-group {
                margin-bottom: 1rem;
            }
            
            .form-label {
                font-weight: 600;
                color: #495057;
                margin-bottom: 8px;
                font-size: 14px;
                display: block;
            }
            
            .form-control {
                border: 1px solid #ced4da;
                border-radius: 6px;
                padding: 10px 12px;
                font-size: 14px;
                transition: all 0.2s ease;
                background: white;
                font-family: var(--font-stack);
            }
            
            .form-control:focus {
                border-color: #667eea;
                box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.15);
                outline: none;
            }
            
            .btn-filter {
                background: #667eea;
                border: 1px solid #667eea;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: 500;
                color: white;
                transition: all 0.2s ease;
                min-height: 42px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                font-size: 14px;
                font-family: var(--font-stack);
            }
            
            .btn-filter:hover {
                background: #5a67d8;
                border-color: #5a67d8;
                color: white;
            }
            
            .btn-clear {
                background: #6c757d;
                border: 1px solid #6c757d;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 500;
                color: white;
                transition: all 0.2s ease;
                font-size: 13px;
                font-family: var(--font-stack);
            }
            
            .btn-clear:hover {
                background: #5a6268;
                border-color: #545b62;
                color: white;
            }
            
            .summary-cards {
                margin-bottom: 30px;
            }
            
            .summary-card {
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                border: 1px solid #e3e6f0;
                transition: all 0.2s ease;
                overflow: hidden;
                position: relative;
                margin-bottom: 20px;
                height: 100px;
            }
            
            .summary-card:hover {
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }
            
            .summary-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
                background: var(--card-accent);
            }
            
            .card-primary { --card-accent: #667eea; }
            .card-success { --card-accent: #28a745; }
            .card-danger { --card-accent: #dc3545; }
            .card-warning { --card-accent: #ffc107; }
            .card-info { --card-accent: #17a2b8; }
            
            .card-body-custom {
                padding: 20px;
                display: flex;
                align-items: center;
                height: 100%;
            }
            
            .card-icon {
                width: 60px;
                height: 60px;
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
                color: white;
                margin-right: 16px;
                background: var(--card-accent);
                flex-shrink: 0;
            }
            
            .card-content {
                flex: 1;
            }
            
            .card-title {
                font-size: 14px;
                color: #6c757d;
                margin-bottom: 4px;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .card-value {
                font-size: 24px;
                font-weight: 700;
                color: #2c3e50;
                margin: 0;
            }
            
            .report-table-container {
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                border: 1px solid #e3e6f0;
                overflow: hidden;
            }
            
            .table-header {
                background: #f8f9fa;
                padding: 20px 24px;
                border-bottom: 1px solid #e9ecef;
                display: flex;
                justify-content: between;
                align-items: center;
            }
            
            .table-title {
                font-size: 16px;
                font-weight: 600;
                color: #2c3e50;
                margin: 0;
                display: flex;
                align-items: center;
                gap: 8px;
                font-family: var(--font-stack);
            }
            
            .custom-table {
                margin: 0;
                font-size: 13px;
                font-family: var(--font-stack);
            }
            
            .custom-table thead th {
                background: #495057;
                color: white;
                font-weight: 500;
                border: none;
                padding: 12px 16px;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.3px;
                font-family: var(--font-stack);
            }
            
            .custom-table tbody tr {
                transition: all 0.2s ease;
            }
            
            .custom-table tbody tr:hover {
                background: #f8f9fa;
            }
            
            .custom-table tbody td {
                padding: 12px 16px;
                border-bottom: 1px solid #e9ecef;
                vertical-align: middle;
                font-family: var(--font-stack);
            }
            
            .custom-table tbody tr:last-child td {
                border-bottom: none;
            }
            
            .no-data {
                text-align: center;
                padding: 60px 20px;
                color: #6c757d;
                background: white;
                border-radius: 12px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            }
            
            .no-data-icon {
                font-size: 48px;
                color: #dee2e6;
                margin-bottom: 16px;
            }
            
            .loading-container {
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 40px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            }
            
            .loading-spinner {
                width: 40px;
                height: 40px;
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .export-buttons {
                display: flex;
                gap: 12px;
                margin-left: auto;
            }
            
            .btn-export {
                background: #28a745;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                color: white;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                transition: all 0.3s ease;
            }
            
            .btn-export:hover {
                background: #218838;
                transform: translateY(-1px);
                color: white;
            }
            
            .status-badge {
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .status-paid { background: #d4edda; color: #155724; }
            .status-pending { background: #fff3cd; color: #856404; }
            .status-overdue { background: #f8d7da; color: #721c24; }
            
            .currency-amount {
                font-weight: 500;
                color: #2c3e50;
                font-family: var(--font-stack);
            }
            
            @media (max-width: 768px) {
                .filter-card {
                    padding: 16px;
                }
                
                .summary-card {
                    margin-bottom: 16px;
                }
                
                .card-body-custom {
                    padding: 16px;
                }
                
                .card-icon {
                    width: 50px;
                    height: 50px;
                    font-size: 20px;
                }
                
                .card-value {
                    font-size: 20px;
                }
                
                .custom-table {
                    font-size: 12px;
                }
                
                .custom-table thead th,
                .custom-table tbody td {
                    padding: 12px 16px;
                }
            }
        </style>
    `;
    
    // Inject custom CSS
    $('head').append(custom_css);

    // Main container
    let main_container = $('<div class="sales-report-container"></div>').appendTo(page.main);

    // --- Enhanced Filters Section ---
    let filter_card = $(`
        <div class="filter-card">
            <h3 class="filter-title">
                <i class="fa fa-filter"></i>
                Report Filters
            </h3>
            <div class="row g-3 align-items-end">
                <div class="col-md-3">
                    <div class="form-group">
                        <label class="form-label">From Date</label>
                        <div id="from-date"></div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="form-group">
                        <label class="form-label">To Date</label>
                        <div id="to-date"></div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="form-group">
                        <label class="form-label">Client Name</label>
                        <div id="client-link"></div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="form-group">
                        <div class="d-grid gap-2">
                            <button class="btn btn-filter" id="filter-btn">
                                <i class="fa fa-search"></i>
                                Filter
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            <div class="row mt-2">
                <div class="col-12">
                    <button class="btn btn-clear" id="clear-btn">
                        <i class="fa fa-times"></i>
                        Clear Filters
                    </button>
                </div>
            </div>
        </div>
    `).appendTo(main_container);

    // --- Report container ---
    let report_container = $('<div></div>').appendTo(main_container);

    // Get filter elements
    let filter_btn = filter_card.find('#filter-btn');
    let clear_btn = filter_card.find('#clear-btn');

    // Replace plain text input with ERPNext Link field
    let client_link = new frappe.ui.form.ControlLink({
        df: {
            fieldtype: 'Link',
            options: 'Customer',  // or "Client" if your doctype is named Client
            fieldname: 'client_name',
            placeholder: 'Select Client',
            label: 'Client Name'
        },
        parent: filter_card.find('#client-link'),
        only_input: true
    });
    client_link.refresh();

    // Frappe Date Picker
    let from_date = new frappe.ui.form.ControlDate({
        df: {
            fieldtype: 'Date',
            fieldname: 'from_date',
            label: 'From Date',
            reqd: 1
        },
        parent: filter_card.find('#from-date'),
        only_input: true
    });
    from_date.refresh();

    let to_date = new frappe.ui.form.ControlDate({
        df: {
            fieldtype: 'Date',
            fieldname: 'to_date',
            label: 'To Date',
            reqd: 1
        },
        parent: filter_card.find('#to-date'),
        only_input: true
    });
    to_date.refresh();



    // Set default date range (last 30 days)
    function setDefaultDates() {
        let today = frappe.datetime.get_today();
        let thirtyDaysAgo = frappe.datetime.add_days(today, -30);

        from_date.set_value(thirtyDaysAgo);
        to_date.set_value(today);
    }

    function showLoading() {
        report_container.html(`
            <div class="loading-container">
                <div class="loading-spinner"></div>
                <div class="ms-3">
                    <h6 class="mb-1">Loading Report...</h6>
                    <small class="text-muted">Please wait while we fetch your data</small>
                </div>
            </div>
        `);
    }

    function formatCurrency(amount) {
        if (!amount || amount === 0) return '₹0.00';
        return '₹' + parseFloat(amount).toLocaleString('en-IN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    function getStatusBadge(status) {
        const statusMap = {
            'Paid': 'status-paid',
            'Pending': 'status-pending',
            'Overdue': 'status-overdue',
            'Draft': 'status-pending'
        };
        
        let className = statusMap[status] || 'status-pending';
        return `<span class="status-badge ${className}">${status}</span>`;
    }

    function load_report() {
        showLoading();
        
        let filters = {
            from_date: from_date.get_value(),
            to_date: to_date.get_value(),
            client_name: client_link.get_value()
        };

        frappe.call({
            method: "company.company.report.sales_report.sales_report.execute",
            args: { filters: filters },
            callback: function(r) {
                report_container.empty();

                if(!r.message || r.message.length === 0) {
                    report_container.html(`
                        <div class="no-data">
                            <div class="no-data-icon">
                                <i class="fa fa-chart-line"></i>
                            </div>
                            <h5 class="text-muted mb-2">No Records Found</h5>
                            <p class="text-muted">Try adjusting your filters or date range to see more data.</p>
                        </div>
                    `);
                    return;
                }

                let data = r.message[1]; // actual data
                let columns = r.message[0]; // column definitions

                // --- Enhanced Summary Cards ---
                let summary_section = $('<div class="summary-cards"></div>').appendTo(report_container);
                let cards_row = $('<div class="row"></div>').appendTo(summary_section);

                const card_info = [
                    {
                        field: 'total_sales', 
                        label: 'Total Sales', 
                        color: 'primary', 
                        icon: 'fa-chart-line',
                        description: 'Overall sales amount'
                    },
                    {
                        field: 'received_sales', 
                        label: 'Received Amount', 
                        color: 'success', 
                        icon: 'fa-check-circle',
                        description: 'Successfully collected'
                    },
                    {
                        field: 'pending_sales', 
                        label: 'Pending Amount', 
                        color: 'danger', 
                        icon: 'fa-clock',
                        description: 'Awaiting payment'
                    },
                    {
                        field: 'invoice_count', 
                        label: 'Total Invoices', 
                        color: 'info', 
                        icon: 'fa-file-text',
                        description: 'Number of invoices'
                    }
                ];

                // Calculate summary data if available
                let summary_data = r.message[2] || {};
                if (!summary_data.total_sales) {
                    // Calculate from data if summary not provided
                    summary_data.total_sales = data.reduce((sum, row) => sum + (parseFloat(row.grand_total) || 0), 0);
                    summary_data.received_sales = data.filter(row => row.status === 'Paid').reduce((sum, row) => sum + (parseFloat(row.grand_total) || 0), 0);
                    summary_data.pending_sales = summary_data.total_sales - summary_data.received_sales;
                    summary_data.invoice_count = data.length;
                }

                card_info.forEach(ci => {
                    let value = summary_data[ci.field] || 0;
                    if (ci.field !== 'invoice_count') {
                        value = formatCurrency(value);
                    }

                    let card = $(`
                        <div class="col-lg-3 col-md-6 col-sm-12">
                            <div class="summary-card card-${ci.color}">
                                <div class="card-body-custom">
                                    <div class="card-icon">
                                        <i class="fa ${ci.icon}"></i>
                                    </div>
                                    <div class="card-content">
                                        <div class="card-title">${ci.label}</div>
                                        <div class="card-value">${value}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `);
                    cards_row.append(card);
                });

                // --- Enhanced Data Table ---
                let table_container = $(`
                    <div class="report-table-container">
                        <div class="table-header">
                            <h4 class="table-title">
                                <i class="fa fa-table"></i>
                                Sales Report Details
                            </h4>
                            <div class="export-buttons">
                    
                            </div>
                        </div>
                        <div class="table-responsive">
                            <table class="table custom-table">
                                <thead><tr></tr></thead>
                                <tbody></tbody>
                            </table>
                        </div>
                    </div>
                `).appendTo(report_container);

                let table = table_container.find('.custom-table');
                let thead_row = table.find('thead tr');
                
                // Build table headers
                columns.forEach(col => {
                    thead_row.append(`<th>${col.label}</th>`);
                });

                let tbody = table.find('tbody');
                
                // Build table rows with enhanced formatting
                data.forEach((row, index) => {
                    let tr = $('<tr></tr>').appendTo(tbody);
                    
                    columns.forEach(col => {
                        let value = row[col.fieldname] || '';
                        
                        // Format specific columns
                        if (col.fieldtype === 'Currency' || col.fieldname.includes('amount') || col.fieldname.includes('total')) {
                            value = `<span class="currency-amount">${formatCurrency(value)}</span>`;
                        } else if (col.fieldname === 'status' && value) {
                            value = getStatusBadge(value);
                        } else if (col.fieldtype === 'Date' && value) {
                            value = frappe.datetime.str_to_user(value);
                        }
                        
                        tr.append(`<td>${value}</td>`);
                    });
                });

                // Export functionality
                table_container.find('#export-excel').on('click', function() {
                    // Implement Excel export
                    frappe.msgprint('Excel export functionality to be implemented');
                });

                table_container.find('#export-pdf').on('click', function() {
                    // Implement PDF export
                    frappe.msgprint('PDF export functionality to be implemented');
                });
            },
            error: function(err) {
                report_container.html(`
                    <div class="no-data">
                        <div class="no-data-icon" style="color: #dc3545;">
                            <i class="fas fa-exclamation-triangle"></i>
                        </div>
                        <h5 style="color: #dc3545;" class="mb-2">Error Loading Report</h5>
                        <p class="text-muted">There was an error loading the report. Please try again.</p>
                        <button class="btn btn-filter mt-2" onclick="load_report()">
                            <i class="fas fa-redo"></i>
                            Retry
                        </button>
                    </div>
                `);
            }
        });
    }

    function clear_filters() {
    // Reset Client Link field
    client_link.set_value("");

    // Reset Date fields to default last 30 days
    setDefaultDates();

    // Reload report
    load_report();
}


    // Event handlers
    filter_btn.on('click', load_report);
    clear_btn.on('click', clear_filters);

    // Enter key support for client input
    client_input.on('keypress', function(e) {
        if (e.which === 13) {
            load_report();
        }
    });

    // Initialize with default dates and load report
    setDefaultDates();
    load_report();
};