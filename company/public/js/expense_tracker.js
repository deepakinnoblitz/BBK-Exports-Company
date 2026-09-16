// ------------------------------
// EXPENSE LIST VIEW CARDS
// ------------------------------
frappe.listview_settings["Expense Tracker"] = {
    onload(listview) {
        expense_listview_instance = listview;
        // --- Default Month Filter ---
        listview.filter_area.clear();

        // ------------------------------

        expense_insert_custom_block();
        setTimeout(() => expense_insert_custom_block(), 100);

        const original_refresh = listview.refresh;
        listview.refresh = function () {
            original_refresh.apply(this, arguments);
            expense_reload_summary();
        };

        listview.page.wrapper.on('show', () => {
            setTimeout(() => expense_insert_custom_block(), 100);
        });
    }
};


// --------------------------------------------------
// RELOAD SUMMARY FUNCTION
// --------------------------------------------------
function expense_reload_summary() {
    let filter = $("#expense-summary-filter").val();
    let type = $("#expense-type-filter").val() || "All";

    let from = "";
    let to = "";

    if (filter === "custom" && expense_datepicker_control) {
        let dr = expense_datepicker_control.get_value();
        if (dr && dr.length === 2) {
            from = dr[0];
            to = dr[1];
        }
    }

    expense_load_summary_cards(filter, from, to, type);
}



// --------------------------------------------------
// Insert Custom Filter + Cards Block
// --------------------------------------------------
function expense_insert_custom_block() {
    if ($(".custom-expense-block").length) {
        return;
    }

    let container = $(".layout-main-section-wrapper:visible, .page-content:visible").first();

    if (!container.length) {
        return;
    }

    container.prepend(`
        <div class="custom-expense-block"
            style="padding: 20px; 
                   border-radius: 10px; 
                   display: block !important;
                   visibility: visible !important;">

            <div style="display:flex; gap:15px; align-items:center; margin-bottom:15px;">
                <select id="expense-type-filter" class="form-control" style="width:150px;">
                    <option value="All">All Types</option>
                    <option value="Income">Income</option>
                    <option value="Expense">Expense</option>
                </select>

                <select id="expense-summary-filter" class="form-control" style="width:180px;">
                    <option value="">Select Filter</option>
                    <option value="today">Today</option>
                    <option value="this_week">This Week</option>
                    <option value="this_month">This Month</option>
                    <option value="this_year">This Year</option>
                    <option value="custom">Custom Range</option>
                </select>

                <div id="expense-date-range-picker" style="width:250px; display:none;"></div>

                <button class="btn btn-primary" id="expense-apply-filter">Apply</button>
            </div>

            <div id="expense-summary-cards" 
                 style="display:flex !important; 
                        gap:15px; 
                        min-height: 80px;
                        visibility: visible !important;"></div>
        </div>
    `);

    expense_initialize_datepicker();
    expense_bind_filter_actions();

    $("#expense-summary-filter").val("");

    // Load summary without any filter
    setTimeout(() => {
        expense_load_summary_cards("", "", "", "All");
    }, 100);

}

let expense_listview_instance = null;



// --------------------------------------------------
// DATE RANGE PICKER
// --------------------------------------------------
let expense_datepicker_control = null;

function expense_initialize_datepicker() {
    expense_datepicker_control = frappe.ui.form.make_control({
        parent: $("#expense-date-range-picker"),
        df: {
            fieldtype: "DateRange",
            fieldname: "custom_date_range"
        },
        render_input: true,
    });
}



// --------------------------------------------------
// FILTER ACTION HANDLERS
// --------------------------------------------------
function expense_bind_filter_actions() {

    $("#expense-summary-filter").change(function () {
        if ($(this).val() === "custom") {
            $("#expense-date-range-picker").show();
        } else {
            $("#expense-date-range-picker").hide();
        }
    });

    $("#expense-apply-filter").click(function () {
        let filter_type = $("#expense-summary-filter").val();
        let expense_type = $("#expense-type-filter").val();

        let from_date = "";
        let to_date = "";

        if (filter_type === "custom") {
            let val = expense_datepicker_control.get_value();
            if (val && val.length === 2) {
                from_date = val[0];
                to_date = val[1];
            }
        } else if (filter_type === "today") {
            from_date = to_date = frappe.datetime.get_today();
        } else if (filter_type === "this_week") {
            from_date = frappe.datetime.add_days(frappe.datetime.get_today(), -7);
            to_date = frappe.datetime.get_today();
        } else if (filter_type === "this_month") {
            from_date = frappe.datetime.month_start();
            to_date = frappe.datetime.month_end();
        } else if (filter_type === "this_year") {
            from_date = frappe.datetime.year_start();
            to_date = frappe.datetime.year_end();
        }

        // Apply filters to List View dynamically
        if (expense_listview_instance) {
            let filters = [];
            if (from_date && to_date) {
                filters.push(["Expense Tracker", "date_time", "between", [from_date, to_date]]);
            }
            if (expense_type && expense_type !== "All") {
                filters.push(["Expense Tracker", "type", "=", expense_type]);
            }

            expense_listview_instance.filter_area.clear().then(() => {
                if (filters.length > 0) {
                    expense_listview_instance.filter_area.add(filters);
                } else {
                    expense_listview_instance.refresh();
                }
            });
        }

        expense_load_summary_cards(filter_type, from_date, to_date, expense_type);
    });
}



// --------------------------------------------------
// LOAD SUMMARY CARDS
// --------------------------------------------------
function expense_load_summary_cards(filter_type = "", from_date = "", to_date = "", expense_type = "") {

    frappe.call({
        method: "company.company.api.get_expense_tracker_summary",
        args: {
            filter_type,
            from_date,
            to_date,
            expense_type
        },
        callback: function (r) {

            let data = r.message;
            if (!data) {
                $("#expense-summary-cards").html(`
                    <div style="padding:20px; text-align:center; width:100%; background: #fff0f0; border: 1px solid #ffcccc;">
                        <p style="color:red; margin:0;">API returned no data</p>
                    </div>
                `);
                return;
            }

            let html = `
                <div class="card" style="padding:15px; background:white; border-radius:8px;
                     border-left:4px solid #4caf50; flex:1; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h4 style="margin:0; color:#4caf50;">Total Income</h4>
                    <h2 style="margin:5px 0;">₹ ${format_amount(data.total_income)}</h2>
                </div>

                <div class="card" style="padding:15px; background:white; border-radius:8px;
                     border-left:4px solid #f44336; flex:1; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h4 style="margin:0; color:#f44336;">Total Expense</h4>
                    <h2 style="margin:5px 0;">₹ ${format_amount(data.total_expense)}</h2>
                </div>

                <div class="card" style="padding:15px; background:white; border-radius:8px;
                     border-left:4px solid #2196f3; flex:1; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h4 style="margin:0; color:#2196f3;">Balance</h4>
                    <h2 style="margin:5px 0;">₹ ${format_amount(data.balance)}</h2>
                </div>
            `;

            $("#expense-summary-cards").html(html);
        },
        error: function (r) {
            console.error("Expense Tracker API Error:", r);
            $("#expense-summary-cards").html(`
                <div style="padding:20px; text-align:center; width:100%; background: #fff0f0; border: 1px solid #ffcccc;">
                    <p style="color:red; margin:0;">Error loading summary. Check console.</p>
                </div>
            `);
        }

    });
}

function format_amount(amount) {
    amount = Number(amount) || 0;
    return amount.toLocaleString("en-IN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}
