frappe.ui.form.on("Attendance", {
    onload: function (frm) {
        // Set default date on load
        if (!frm.doc.attendance_date) {
            frm.set_value("attendance_date", frappe.datetime.get_today());
        }
        calculate_working_hours(frm);
    },

    in_time: function (frm) {
        calculate_working_hours(frm);
    },

    out_time: function (frm) {
        calculate_working_hours(frm);
    },

    status: function (frm) {
        // Handle Absent
        if (frm.doc.status === "Absent") {
            frm.set_value("in_time", "00:00:00");
            frm.set_value("out_time", "00:00:00");
            reset_hours(frm);
        }

        // Handle On Leave
        frm.set_df_property("leave_type", "reqd", frm.doc.status === "On Leave");

        // Recalculate if present
        if (frm.doc.status === "Present" || frm.doc.status === "Half Day") {
            calculate_working_hours(frm);
        }
    },

    before_save: function (frm) {
        // Always recalc before saving
        calculate_working_hours(frm);

        // Auto-fill approver if workflow approved
        if (frm.doc.workflow_state === "Approved" && !frm.doc.approver_name) {
            frm.set_value("approver_name", frappe.session.user);
        }
    },

    validate: function (frm) {
        calculate_working_hours(frm);

        // Prevent future date
        if (frm.doc.attendance_date && frm.doc.attendance_date > frappe.datetime.get_today()) {
            frappe.msgprint(__('Attendance date cannot be a future date'));
            frappe.validated = false;
            return;
        }

        // Prevent duplicate attendance (same employee + date)
        if (frm.doc.employee && frm.doc.attendance_date) {
            frappe.db.exists('Attendance', {
                employee: frm.doc.employee,
                attendance_date: frm.doc.attendance_date,
                docstatus: 0
            }).then(exists => {
                if (exists && frm.doc.__islocal) {
                    frappe.msgprint(__('Attendance for this employee on this date already exists.'));
                    frappe.validated = false;
                }
            });
        }

        // Leave type required for On Leave
        if (frm.doc.status === "On Leave" && !frm.doc.leave_type) {
            frappe.msgprint(__('Please select a Leave Type when status is On Leave'));
            frappe.validated = false;
            return;
        }

        // Status corrections based on working hours
        if (frm.doc.status === "Half Day" && frm.doc.working_hours_decimal >= 4) {
            frappe.msgprint(__('Working hours are {0} hours. Status cannot be Half Day.', [frm.doc.working_hours_decimal]));
            frm.set_value("status", "Present");
            frm.validated = false;
            return;
        }

        if (frm.doc.status === "Present" && frm.doc.working_hours_decimal > 0 && frm.doc.working_hours_decimal < 4) {
            frappe.msgprint(__('Working hours are less than 4. Status must be Half Day.'));
            frm.set_value("status", "Half Day");
            frm.validated = false;
            return;
        }
    }
});

// ============================================================
// 🔹 Working Hours + Overtime Calculation (Decimal Display)
// ============================================================

function calculate_working_hours(frm) {
    let inTimeRaw = frm.doc.in_time;
    let outTimeRaw = frm.doc.out_time;

    // Consider empty, "00:00", or "00:00:00" as no time
    const inTime = (!inTimeRaw || inTimeRaw === "00:00" || inTimeRaw === "00:00:00") ? null : inTimeRaw;
    const outTime = (!outTimeRaw || outTimeRaw === "00:00" || outTimeRaw === "00:00:00") ? null : outTimeRaw;

    // Reset all fields first
    reset_hours(frm);

    // Both times empty → Absent
    if (!inTime && !outTime) {
        frm.set_value("status", "Absent");
        return;
    }

    // Only one time filled → Missing
    if ((inTime && !outTime) || (!inTime && outTime)) {
        frm.set_value("status", "Missing");
        return;
    }

    // Both times exist → calculate working hours
    let start = moment(inTime, "HH:mm:ss");
    let end = moment(outTime, "HH:mm:ss");

    if (!start.isValid() || !end.isValid()) return;
    if (end.isBefore(start)) end.add(1, "day"); // handle overnight shifts

    let total_minutes = end.diff(start, "minutes");
    if (total_minutes <= 0) {
        frm.set_value("status", "Missing");
        return;
    }

    // Regular working minutes (up to 9 hours)
    let reg_hours = Math.floor(total_minutes / 60);
    let reg_minutes = total_minutes % 60;
    let hours_decimal = (total_minutes / 60).toFixed(2);


    // Set working hours display as HH:MM
    frm.set_value("working_hours_display", `${reg_hours}:${reg_minutes.toString().padStart(2,'0')}`);
    frm.set_value("working_hours_decimal", hours_decimal);

    // Status based on total hours
    if (total_minutes < 4 * 60) {
        frm.set_value("status", "Half Day");
    } else {
        frm.set_value("status", "Present");
    }

    // Overtime (beyond 9 hours)
    let overtime_minutes = total_minutes - 9 * 60;
    if (overtime_minutes > 0) {
        let ot_hours = Math.floor(overtime_minutes / 60);
        let ot_mins = overtime_minutes % 60;
        let ot_decimal = (overtime_minutes / 60).toFixed(2);

        frm.set_value("overtime_display", `${ot_hours}:${ot_mins.toString().padStart(2,'0')}`);
        frm.set_value("overtime_decimal", ot_decimal);
    } else {
        frm.set_value("overtime_display", "0:00");
        frm.set_value("overtime_decimal", 0);
    }
}



// ============================================================
// 🔧 Helpers
// ============================================================

function normalize_time(value) {
    if (!value) return null;
    if (typeof value === "object" && value._d) {
        return moment(value).format("HH:mm:ss");
    }
    if (typeof value === "string") {
        if (value.length === 5) value += ":00"; // handle HH:mm
        return value;
    }
    return null;
}

function reset_hours(frm) {
    frm.set_value("working_hours_display", "0.00");
    frm.set_value("working_hours_decimal", 0);
    frm.set_value("overtime_display", "0.00");
    frm.set_value("overtime_decimal", 0);
}
