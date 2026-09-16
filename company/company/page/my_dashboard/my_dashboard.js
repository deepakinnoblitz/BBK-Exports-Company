// my_dashboard.js

frappe.pages['my-dashboard'].on_page_load = function(wrapper) {
    console.log("Enhanced Dashboard script loaded");

    // Create the page
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Business Dashboard',
        single_column: true
    });

    // Inject dashboard container
    const container = document.createElement('div');
    container.id = 'dashboard-container';
    container.className = 'container-fluid';
    page.main[0].appendChild(container);

    // Add CSS
    const style = document.createElement('style');
    style.innerHTML = `
        .container-fluid { padding: 25px; background: #f8f9fa; min-height: 100vh; max-width: 100%; }
        .dashboard-header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 15px; margin-bottom: 30px; box-shadow: 0 15px 35px rgba(102,126,234,0.15); position: relative; overflow: hidden; }
        .dashboard-header::before { content: ''; position: absolute; top: -50%; right: -20%; width: 200px; height: 200px; background: rgba(255, 255, 255, 1); border-radius: 50%; }
        .dashboard-header h2 { margin: 0; font-size: 32px; font-weight: 700; text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2); color: white; }
        .dashboard-header p { margin: 10px 0 0 0; opacity: 0.95; font-size: 18px; }
        .dashboard-header .last-updated { position: absolute; top: 20px; right: 30px; opacity: 0.8; font-size: 14px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 25px; margin-bottom: 35px; }
        .stat-card { background: white; padding: 30px; border-radius: 15px; box-shadow: 0 8px 25px rgba(0,0,0,0.08); border-left: 5px solid; transition: all 0.3s ease; position: relative; overflow: hidden; }
        .stat-card.leads { border-left-color: #4CAF50; }
        .stat-card.invoices { border-left-color: #2196F3; }
        .stat-card.estimations { border-left-color: #FF9800; }
        .stat-card.customers { border-left-color: #9C27B0; }
        .stat-number { font-size: 38px; font-weight: 800; margin-bottom: 10px; line-height: 1; position: relative; z-index: 1; }
        .stat-label { color: #6c757d; font-size: 15px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; position: relative; z-index: 1; }
        .kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .kpi-card { background: white; padding: 20px; border-radius: 12px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }
        .kpi-value { font-size: 24px; font-weight: 700; margin-bottom: 5px; }
        .kpi-label { color: #6c757d; font-size: 13px; text-transform: uppercase; }
        .charts-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(450px, 1fr)); gap: 30px; margin-bottom: 35px; }
        .chart-container { background: white; padding: 30px; border-radius: 15px; box-shadow: 0 8px 25px rgba(0,0,0,0.08); transition: all 0.3s ease; }
        .chart-container.full-width-chart { grid-column: 1 / -1; }
        .recent-activity { background: white; border-radius: 15px; padding: 30px; box-shadow: 0 8px 25px rgba(0,0,0,0.08); }
        .activity-item { display: flex; align-items: center; padding: 18px 0; border-bottom: 1px solid #eee; }
        .activity-item:last-child { border-bottom: none; }
        .activity-icon { width: 45px; height: 45px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-right: 18px; font-size: 18px; font-weight: 600; }
        .activity-leads { background: #e8f5e8; color: #4CAF50; }
        .activity-invoices { background: #e3f2fd; color: #2196F3; }
        .activity-estimations { background: #fff3e0; color: #FF9800; }
        .activity-customers { background: #f3e5f5; color: #9C27B0; }
        .refresh-btn { position: fixed; bottom: 30px; right: 30px; background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; border-radius: 50%; width: 65px; height: 65px; font-size: 22px; cursor: pointer; box-shadow: 0 8px 25px rgba(102,126,234,0.3); transition: all 0.3s ease; z-index: 1000; }
        .refresh-btn:hover { transform: scale(1.15) rotate(180deg); box-shadow: 0 12px 35px rgba(102,126,234,0.4); }
        @media (max-width: 768px) {
            .stats-grid { grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }
            .charts-grid { grid-template-columns: 1fr; gap: 20px; }
        }
    `;
    document.head.appendChild(style);

    // Initialize dashboard
    new EnhancedDashboard(container);
};

// Enhanced Dashboard
class EnhancedDashboard {
    constructor(container) {
        this.container = container;
        this.data = { leads: 0, invoices: 0, estimations: 0, customers: 0 };
        this.init();
    }

    async init() {
        this.create_layout();
        await this.load_data();
        this.setup_refresh();
    }

    create_layout() {
        this.container.innerHTML = `
            <div class="dashboard-header">
                <h2>Company Dashboard</h2>
                <div class="last-updated">Last updated: --</div>
            </div>

            <div class="stats-grid">
                <div class="stat-card leads">
                    <div class="stat-number" id="leads-count">-</div>
                    <div class="stat-label">Active Leads</div>
                </div>
                <div class="stat-card invoices">
                    <div class="stat-number" id="invoices-count">-</div>
                    <div class="stat-label">Total Invoices</div>
                </div>
                <div class="stat-card estimations">
                    <div class="stat-number" id="estimations-count">-</div>
                    <div class="stat-label">Estimations</div>
                </div>
                <div class="stat-card customers">
                    <div class="stat-number" id="customers-count">-</div>
                    <div class="stat-label">Customers</div>
                </div>
            </div>

            <div class="kpi-row">
                <div class="kpi-card">
                    <div class="kpi-value" id="conversion-rate">-</div>
                    <div class="kpi-label">Conversion Rate</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-value" id="avg-deal-size">-</div>
                    <div class="kpi-label">Avg Deal Size</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-value" id="monthly-revenue">-</div>
                    <div class="kpi-label">Monthly Revenue</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-value" id="pipeline-value">-</div>
                    <div class="kpi-label">Pipeline Value</div>
                </div>
            </div>

            <div class="charts-grid">
                <div class="chart-container">
                    <div class="chart-title">📈 Performance Trends</div>
                    <div id="performance-chart">Loading...</div>
                </div>
                <div class="chart-container">
                    <div class="chart-title">🎯 Revenue Distribution</div>
                    <div id="revenue-chart">Loading...</div>
                </div>
            </div>

            <div class="charts-grid">
                <div class="chart-container full-width-chart">
                    <div class="chart-title">📊 Sales Funnel Analysis</div>
                    <div id="funnel-chart">Loading...</div>
                </div>
            </div>

            <div class="recent-activity">
                <div class="chart-title">🔔 Recent Activity Feed</div>
                <div id="activity-list">Loading...</div>
            </div>

            <button class="refresh-btn"><i class="fa fa-refresh"></i></button>
        `;
    }

    async load_data() {
        await this.load_counts();
        await this.load_kpis();
        await this.render_performance_chart();
        await this.render_revenue_chart();
        await this.render_funnel_chart();
        await this.load_recent_activity();
        this.update_last_updated();
    }

    async load_counts() {
        const leads = await frappe.call({ method: 'frappe.client.get_count', args: { doctype: 'Leads' } });
        const invoices = await frappe.call({ method: 'frappe.client.get_count', args: { doctype: 'Invoice' } });
        const estimations = await frappe.call({ method: 'frappe.client.get_count', args: { doctype: 'Estimation' } });
        const customers = await frappe.call({ method: 'frappe.client.get_count', args: { doctype: 'Customer' } });

        this.data = {
            leads: leads.message,
            invoices: invoices.message,
            estimations: estimations.message,
            customers: customers.message
        };

        document.getElementById('leads-count').textContent = this.data.leads;
        document.getElementById('invoices-count').textContent = this.data.invoices;
        document.getElementById('estimations-count').textContent = this.data.estimations;
        document.getElementById('customers-count').textContent = this.data.customers;
    }

    async load_kpis() {
        const conversionRate = this.data.leads > 0 ? ((this.data.customers / this.data.leads) * 100).toFixed(1) + '%' : '0%';
        
        // Monthly Revenue
        const invoices = await frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "Invoice",
                fields: ["grand_total", "invoice_date"],
                filters: { invoice_date: ['>=', frappe.datetime.add_months(frappe.datetime.get_today(), -1)] }
            }
        });
        const monthlyRevenue = invoices.message.reduce((acc, inv) => acc + inv.grand_total, 0);
        const avgDealSize = invoices.message.length > 0 ? monthlyRevenue / invoices.message.length : 0;

        document.getElementById('conversion-rate').textContent = conversionRate;
        document.getElementById('monthly-revenue').textContent = '₹' + monthlyRevenue.toLocaleString('en-IN', { maximumFractionDigits: 0 });
        document.getElementById('avg-deal-size').textContent = '₹' + avgDealSize.toLocaleString('en-IN', { maximumFractionDigits: 0 });
        document.getElementById('pipeline-value').textContent = '₹0'; // Optional: sum of Opportunities
    }

    async render_performance_chart() {
        // Simple weekly performance chart (Leads, Invoices, Customers)
        const chartData = [];
        const today = frappe.datetime.get_today();
        const lastWeek = frappe.datetime.add_days(today, -6);

        // Fetch daily counts for Leads, Invoices, Customers
        const leads = await frappe.call({ method: "frappe.client.get_list", args: { doctype: "Leads", fields: ["creation"], filters: { creation: ['between', [lastWeek, today]] } } });
        const invoices = await frappe.call({ method: "frappe.client.get_list", args: { doctype: "Invoice", fields: ["creation"], filters: { creation: ['between', [lastWeek, today]] } } });
        const customers = await frappe.call({ method: "frappe.client.get_list", args: { doctype: "Customer", fields: ["creation"], filters: { creation: ['between', [lastWeek, today]] } } });

        for (let i = 0; i < 7; i++) {
            const day = frappe.datetime.add_days(lastWeek, i);
            chartData.push({
                day,
                leads: leads.message.filter(l => l.creation.startsWith(day)).length,
                invoices: invoices.message.filter(l => l.creation.startsWith(day)).length,
                customers: customers.message.filter(l => l.creation.startsWith(day)).length
            });
        }

        // Render simple text chart
        const chartEl = document.getElementById('performance-chart');
        chartEl.innerHTML = chartData.map(d => `
            <div>${d.day}: Leads ${d.leads}, Invoices ${d.invoices}, Customers ${d.customers}</div>
        `).join('');
    }

    async render_revenue_chart() {
        const invoices = await frappe.call({ method: "frappe.client.get_list", args: { doctype: "Invoice", fields: ["grand_total", "client_name"] } });
        const groupTotals = {};
        invoices.message.forEach(inv => {
            const group = inv.client_name || 'Others';
            if (!groupTotals[group]) groupTotals[group] = 0;
            groupTotals[group] += inv.grand_total;
        });

        const chartEl = document.getElementById('revenue-chart');
        chartEl.innerHTML = Object.keys(groupTotals).map(g => `<div>${g}: ₹${groupTotals[g]}</div>`).join('');
    }

    async render_funnel_chart() {
        // Funnel: Leads → Quotations → Customers
        const leads = this.data.leads;
        const quotations = this.data.estimations;
        const customers = this.data.customers;

        const chartEl = document.getElementById('funnel-chart');
        chartEl.innerHTML = `
            <div>Leads: ${leads}</div>
            <div>Quotations: ${quotations}</div>
            <div>Customers: ${customers}</div>
        `;
    }

    async load_recent_activity() {
        const leads = await frappe.call({ method: "frappe.client.get_list", args: { doctype: "Leads", fields: ["name", "lead_name", "creation"], limit_page_length: 5, order_by: "creation desc" } });
        const invoices = await frappe.call({ method: "frappe.client.get_list", args: { doctype: "Invoice", fields: ["name", "grand_total", "creation"], limit_page_length: 5, order_by: "creation desc" } });

        const activities = [];
        leads.message.forEach(l => activities.push({ type: 'leads', icon: '👤', msg: l.lead_name, time: l.creation }));
        invoices.message.forEach(i => activities.push({ type: 'invoices', icon: '📄', msg: i.name + ' ₹' + i.grand_total, time: i.creation }));

        activities.sort((a,b) => new Date(b.time) - new Date(a.time));

        const html = activities.map(a => `
            <div class="activity-item">
                <div class="activity-icon activity-${a.type}">${a.icon}</div>
                <div>${a.msg} (${a.time})</div>
            </div>
        `).join('');

        document.getElementById('activity-list').innerHTML = html;
    }

    update_last_updated() {
        const now = new Date();
        document.querySelector('.last-updated').textContent = `Last updated: ${now.toLocaleString()}`;
    }

    setup_refresh() {
        document.querySelector('.refresh-btn').addEventListener('click', async () => {
            await this.load_data();
        });
    }
}
