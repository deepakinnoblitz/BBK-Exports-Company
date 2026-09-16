// ------------------------------
// INCOME LIST VIEW CARDS
// ------------------------------
frappe.listview_settings["Income"] = {
    onload(listview) {
        income_insert_custom_block();
        setTimeout(() => income_insert_custom_block(), 100);
        setTimeout(() => income_insert_custom_block(), 500);
        setTimeout(() => income_insert_custom_block(), 1000);

        const original_refresh = listview.refresh;
        listview.refresh = function () {
            original_refresh.apply(this, arguments);
            income_reload_summary();
        };

        listview.page.wrapper.on('show', () => {
            setTimeout(() => income_insert_custom_block(), 100);
        });
    }
};


// --------------------------------------------------
// RELOAD SUMMARY FUNCTION
// --------------------------------------------------
function income_reload_summary() {
    let filter = $("#income-summary-filter").val();

    let from = "";
    let to = "";

    if (filter === "custom" && income_datepicker_control) {
        let dr = income_datepicker_control.get_value();
        if (dr && dr.length === 2) {
            from = dr[0];
            to = dr[1];
        }
    }

    income_load_summary_cards(filter, from, to);
}



// --------------------------------------------------
// Insert Custom Filter + Cards Block
// --------------------------------------------------
function income_insert_custom_block() {
    if ($(".custom-income-block").length) {
        return;
    }

    let container = $(".layout-main-section-wrapper:visible, .page-content:visible").first();

    if (!container.length) {
        return;
    }

    container.prepend(`
        <div class="custom-income-block"
            style="padding: 20px; 
                   border-radius: 10px; 
                   margin-bottom: 15px;
                   display: block !important;
                   visibility: visible !important;">

            <div style="display:flex; gap:15px; align-items:center; margin-bottom:15px;">
                <select id="income-summary-filter" class="form-control" style="width:180px;">
                    <option value="">Select Filter</option>
                    <option value="today">Today</option>
                    <option value="this_week">This Week</option>
                    <option value="this_month">This Month</option>
                    <option value="this_year">This Year</option>
                    <option value="custom">Custom Range</option>
                </select>

                <div id="income-date-range-picker" style="width:250px; display:none;"></div>

                <button class="btn btn-primary" id="income-apply-filter">Apply</button>
            </div>

            <div id="income-summary-cards" 
                 style="display:flex !important; 
                        gap:15px; 
                        min-height: 80px;
                        visibility: visible !important;"></div>
        </div>
    `);

    income_initialize_datepicker();
    income_bind_filter_actions();

    $("#income-summary-filter").val("this_month");

    setTimeout(() => {
        income_load_summary_cards("this_month");
    }, 100);
}



// --------------------------------------------------
// DATE RANGE PICKER
// --------------------------------------------------
let income_datepicker_control = null;

function income_initialize_datepicker() {
    income_datepicker_control = frappe.ui.form.make_control({
        parent: $("#income-date-range-picker"),
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
function income_bind_filter_actions() {

    $("#income-summary-filter").change(function () {
        if ($(this).val() === "custom") {
            $("#income-date-range-picker").show();
        } else {
            $("#income-date-range-picker").hide();
        }
    });

    $("#income-apply-filter").click(function () {
        let filter_type = $("#income-summary-filter").val();

        let from_date = "";
        let to_date = "";

        if (filter_type === "custom") {
            let val = income_datepicker_control.get_value();
            if (val && val.length === 2) {
                from_date = val[0];
                to_date = val[1];
            }
        }

        income_load_summary_cards(filter_type, from_date, to_date);
    });
}



// --------------------------------------------------
// LOAD SUMMARY CARDS
// --------------------------------------------------
function income_load_summary_cards(filter_type = "", from_date = "", to_date = "") {

    frappe.call({
        method: "company.company.api.get_expense_income_summary",
        args: {
            filter_type,
            from_date,
            to_date
        },
        callback: function (r) {

            if (!r.message) {
                $("#income-summary-cards").html(`
                    <div style="padding:20px; text-align:center; width:100%;">
                        <p style="color:#888;">No data available</p>
                    </div>
                `);
                return;
            }

            let data = r.message;

            let html = `
                <div class="card" style="padding:15px; background:white; border-radius:8px;
                     border-left:4px solid #4caf50; flex:1;">
                    <h4 style="margin:0; color:#4caf50;">Total Income</h4>
                    <h2 style="margin:5px 0;">₹ ${format_amount(data.total_income)}</h2>
                </div>

                <div class="card" style="padding:15px; background:white; border-radius:8px;
                     border-left:4px solid #f44336; flex:1;">
                    <h4 style="margin:0; color:#f44336;">Total Expense</h4>
                    <h2 style="margin:5px 0;">₹ ${format_amount(data.total_expense)}</h2>
                </div>

                <div class="card" style="padding:15px; background:white; border-radius:8px;
                     border-left:4px solid #2196f3; flex:1;">
                    <h4 style="margin:0; color:#2196f3;">Balance</h4>
                    <h2 style="margin:5px 0;">₹ ${format_amount(data.balance)}</h2>
                </div>
            `;

            $("#income-summary-cards").html(html);
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
