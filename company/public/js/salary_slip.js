// frappe.ui.form.on('Salary Slip', {
//     employee_type: function(frm) {
//         if (!frm.doc.employee_type || !frm.doc.pay_period_start || !frm.doc.pay_period_end) return;

//         frappe.call({
//             method: "company.company.api.get_salary_structure_components",
//             args: { salary_structure: frm.doc.employee_type },
//             callback: function(r) {
//                 if (r.message) {
//                     frm.clear_table("components");
//                     r.message.forEach(function(c) {
//                         frm.add_child("components", {
//                             component: c.component,
//                             amount: c.amount
//                         });
//                     });
//                     frm.refresh_field("components");

//                     frm.trigger("recalculate_summary");
//                 }
//             }
//         });
//     },

//     pay_period_start: function(frm) {
//         if (!frm.doc.pay_period_start) return;

//         let start_date = frappe.datetime.str_to_obj(frm.doc.pay_period_start);
//         let year = start_date.getFullYear();
//         let month = start_date.getMonth() + 1;

//         let last_day = new Date(year, month, 0);
//         frm.set_value("pay_period_end", frappe.datetime.obj_to_str(last_day));

//         if (frm.doc.employee_type) {
//             frm.trigger("employee_type");
//         }
//     },

//     recalculate_summary: function(frm) {
//         if (!frm.doc.employee || !frm.doc.employee_type || !frm.doc.pay_period_start || !frm.doc.pay_period_end) return;

//         frappe.call({
//             method: "company.company.api.calculate_salary_summary",
//             args: {
//                 employee: frm.doc.employee,
//                 employee_type: frm.doc.employee_type,
//                 pay_period_start: frm.doc.pay_period_start,
//                 pay_period_end: frm.doc.pay_period_end,
//                 components: frm.doc.components   // pass edited child table
//             },
//             callback: function(r) {
//                 if (r.message) {
//                     frm.set_value("gross_pay", r.message.gross_pay);
//                     frm.set_value("grand_gross_pay", r.message.grand_gross_pay);
//                     frm.set_value("net_pay", r.message.net_pay);
//                     frm.set_value("grand_net_pay", r.message.grand_net_pay);
//                     frm.set_value("no_of_leave", r.message.no_of_leave);
//                     frm.set_value("no_of_paid_leave", r.message.no_of_paid_leave);

//                     if (r.message.leave_validation_errors?.length > 0) {
//                         frappe.msgprint({
//                             title: __("Leave Allocation Warning"),
//                             message: r.message.leave_validation_errors.join("<br>"),
//                             indicator: "orange"
//                         });
//                     }
//                 }
//             }
//         });
//     }
// });

// // Trigger recalculation on child table change
// frappe.ui.form.on("Salary Slip Component Table", {
//     amount: function(frm) {
//         frm.trigger("recalculate_summary");
//     },
//     component: function(frm) {
//         frm.trigger("recalculate_summary");
//     }
// });



