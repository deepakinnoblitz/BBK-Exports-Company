// Copyright (c) 2025, deepak and contributors
// For license information, please see license.txt

frappe.ui.form.on('Salary Slip', {
    employee: function(frm) {
        if (frm.doc.employee) {
            frappe.db.get_value('Employee', frm.doc.employee, ['total_earnings', 'total_deductions', 'net_salary'], (r) => {
                if (r) {
                    frm.set_value('gross_pay', r.total_earnings);
                    frm.set_value('total_deduction', r.total_deductions);
                    frm.set_value('net_pay', r.net_salary);
                }
            });

            // Fetch the child tables
            frappe.model.with_doc('Employee', frm.doc.employee, function() {
                let employee = frappe.get_doc('Employee', frm.doc.employee);
                
                frm.clear_table('earnings');
                frm.clear_table('deductions');

                (employee.earnings || []).forEach(row => {
                    let d = frm.add_child('earnings');
                    d.component_name = row.component_name;
                    d.type = row.type;
                    d.amount = row.amount;
                    d.percentage = row.percentage;
                    d.static_amount = row.static_amount;
                });

                (employee.deductions || []).forEach(row => {
                    let d = frm.add_child('deductions');
                    d.component_name = row.component_name;
                    d.type = row.type;
                    d.amount = row.amount;
                    d.percentage = row.percentage;
                    d.static_amount = row.static_amount;
                });

                frm.refresh_field('earnings');
                frm.refresh_field('deductions');
                calculate_totals(frm);
            });
        }
    }
});

frappe.ui.form.on('Salary Structure', {
    amount: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    earnings_remove: function(frm) {
        calculate_totals(frm);
    },
    deductions_remove: function(frm) {
        calculate_totals(frm);
    }
});

function calculate_totals(frm) {
    let total_earnings = 0;
    let total_deductions = 0;

    (frm.doc.earnings || []).forEach(row => {
        total_earnings += flt(row.amount);
    });

    (frm.doc.deductions || []).forEach(row => {
        total_deductions += flt(row.amount);
    });

    frm.set_value("gross_pay", total_earnings);
    frm.set_value("total_deduction", total_deductions);
    
    // grand_gross_pay and grand_net_pay could be affected by attendance/LOP
    // For now, let's just set the basics
    frm.set_value("net_pay", total_earnings - total_deductions);
}
