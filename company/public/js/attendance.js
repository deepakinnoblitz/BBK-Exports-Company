frappe.ui.form.on("Attendance", {
    onload: function (frm) {
        if (!frm.doc.attendance_date) {
            frm.set_value("attendance_date", frappe.datetime.get_today());
        }
        frm.add_fetch("employee", "shift", "shift");
        if (frm.doc.employee && !frm.doc.shift) {
            frappe.db.get_value("Employee", frm.doc.employee, "shift", function (r) {
                if (r && r.shift) {
                    frm.set_value("shift", r.shift);
                }
            });
        }
        calculate_working_hours(frm);
    },

    employee: function (frm) {
        if (frm.doc.employee) {
            frappe.db.get_value("Employee", frm.doc.employee, "shift", function (r) {
                if (r && r.shift) {
                    frm.set_value("shift", r.shift);
                }
            });
        }
    },

    shift: function (frm) {
        calculate_working_hours(frm);
    },

    in_time: function (frm) {
        calculate_working_hours(frm);
    },

    out_time: function (frm) {
        calculate_working_hours(frm);
    },

    status: function (frm) {
        if (frm.doc.status === "Absent") {
            frm.set_value("in_time", "00:00:00");
            frm.set_value("out_time", "00:00:00");
            reset_hours(frm);
        }

        frm.set_df_property("leave_type", "reqd", frm.doc.status === "On Leave");

        if (frm.doc.status === "Present" || frm.doc.status === "Half Day") {
            calculate_working_hours(frm);
        }
    },

    before_save: function (frm) {
        update_times_from_punches(frm);
        calculate_working_hours(frm);

        if (frm.doc.workflow_state === "Approved" && !frm.doc.approver_name) {
            frm.set_value("approver_name", frappe.session.user);
        }
    },

    validate: function (frm) {
        update_times_from_punches(frm);
        calculate_working_hours(frm);

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

        if (frm.doc.status === "On Leave" && !frm.doc.leave_type) {
            frappe.msgprint(__('Please select a Leave Type when status is On Leave'));
            frappe.validated = false;
            return;
        }

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
// 🔹 Child Table: Attendance Punch
// ============================================================
frappe.ui.form.on("Attendance Punch", {
    punch_time: function (frm) {
        update_times_from_punches(frm);
    },
    punch_type: function (frm) {
        update_times_from_punches(frm);
    },
    attendance_punches_remove: function (frm) {
        update_times_from_punches(frm);
    }
});

function update_times_from_punches(frm) {
    let punches = frm.doc.attendance_punches || [];
    let valid_punches = punches.filter(p => p.punch_time);
    if (!valid_punches.length) return;

    valid_punches.sort((a, b) => (String(a.punch_time) > String(b.punch_time) ? 1 : -1));

    let in_punches = valid_punches.filter(p => p.punch_type === "IN");
    let out_punches = valid_punches.filter(p => p.punch_type === "OUT");

    let first_in = in_punches.length ? in_punches[0] : valid_punches[0];
    let last_out = out_punches.length ? out_punches[out_punches.length - 1] : (valid_punches.length > 1 ? valid_punches[valid_punches.length - 1] : null);

    function extractTime(val) {
        if (!val) return null;
        let parts = String(val).trim().split(" ");
        let t = parts[parts.length - 1];
        if (t.length === 5) t += ":00";
        return t;
    }

    if (first_in) {
        let in_t = extractTime(first_in.punch_time);
        if (in_t && (!frm.doc.manual || !frm.doc.in_time || frm.doc.in_time === "00:00:00")) {
            frm.set_value("in_time", in_t);
        }
    }

    if (last_out) {
        let out_t = extractTime(last_out.punch_time);
        if (out_t && (!frm.doc.manual || !frm.doc.out_time || frm.doc.out_time === "00:00:00")) {
            frm.set_value("out_time", out_t);
        }
    }

    if (!frm.doc.shift && frm.doc.employee) {
        frappe.db.get_value("Employee", frm.doc.employee, "shift", function (r) {
            if (r && r.shift) {
                frm.set_value("shift", r.shift);
            }
            calculate_working_hours(frm);
        });
    } else {
        calculate_working_hours(frm);
    }
}

// ============================================================
// 🔹 Working Hours + Overtime Calculation
// ============================================================

function calculate_working_hours(frm) {
    let inTimeRaw = frm.doc.in_time;
    let outTimeRaw = frm.doc.out_time;

    const isZero = (val) => !val || val === "00:00" || val === "00:00:00";

    // If times are zero or missing, but punches exist, extract from punches
    if (isZero(inTimeRaw) && isZero(outTimeRaw) && frm.doc.attendance_punches && frm.doc.attendance_punches.length > 0) {
        update_times_from_punches(frm);
        return;
    }

    const inTime = isZero(inTimeRaw) ? null : inTimeRaw;
    const outTime = isZero(outTimeRaw) ? null : outTimeRaw;

    reset_hours(frm);

    if (!inTime && !outTime) {
        if (frm.doc.leave_type) {
            frm.set_value("status", "On Leave");
        } else {
            frm.set_value("status", "Absent");
        }
        return;
    }

    if ((inTime && !outTime) || (!inTime && outTime)) {
        if (frm.doc.leave_type) {
            frm.set_value("status", "On Leave");
        } else {
            frm.set_value("status", "Missing");
        }
        return;
    }

    let start = moment(inTime, "HH:mm:ss");
    let end = moment(outTime, "HH:mm:ss");

    if (!start.isValid() || !end.isValid()) return;
    if (end.isBefore(start)) end.add(1, "day");

    let total_minutes = end.diff(start, "minutes");
    if (total_minutes <= 0) {
        frm.set_value("status", "Missing");
        return;
    }

    function parseDurationMinutes(timeStr) {
        if (!timeStr || timeStr === "00:00" || timeStr === "00:00:00") return 0;
        let parts = String(timeStr).split(":");
        let h = parseInt(parts[0]) || 0;
        let m = parseInt(parts[1]) || 0;
        return h * 60 + m;
    }

    function applyHoursAndOvertime(shift) {
        let totalBreakMinutes = 0;
        if (shift) {
            totalBreakMinutes = parseDurationMinutes(shift.lunch_hours) + parseDurationMinutes(shift.break_hours);
        }

        let netWorkingMinutes = total_minutes > totalBreakMinutes ? (total_minutes - totalBreakMinutes) : total_minutes;

        let reg_hours = Math.floor(netWorkingMinutes / 60);
        let reg_minutes = netWorkingMinutes % 60;
        let hours_decimal = (netWorkingMinutes / 60).toFixed(2);

        frm.set_value("working_hours_display", `${reg_hours}:${reg_minutes.toString().padStart(2, '0')}`);
        frm.set_value("working_hours_decimal", hours_decimal);

        if (!frm.doc.leave_type) {
            if (netWorkingMinutes < 4 * 60) {
                frm.set_value("status", "Half Day");
            } else {
                frm.set_value("status", "Present");
            }
        }

        if (shift && shift.end_time) {
            let s_end = moment(shift.end_time, "HH:mm:ss");
            let s_duration_mins = 9 * 60;
            if (shift.start_time) {
                let s_start = moment(shift.start_time, "HH:mm:ss");
                if (s_end.isBefore(s_start)) s_end.add(1, "day");
                s_duration_mins = s_end.diff(s_start, "minutes");
            }
            let shift_standard_mins = Math.max(0, s_duration_mins - totalBreakMinutes);
            let post_shift_mins = Math.max(0, end.diff(s_end, "minutes"));
            let excess_worked_mins = Math.max(0, netWorkingMinutes - shift_standard_mins);

            let extra_mins = post_shift_mins > 0 ? Math.min(post_shift_mins, excess_worked_mins) : 0;
            let min_thresh = parseInt(shift.min_overtime_minutes) || 0;
            if (extra_mins < min_thresh) extra_mins = 0;

            let unoff_h = Math.floor(extra_mins / 60);
            let unoff_m = extra_mins % 60;
            frm.set_value("unofficial_overtime", `${unoff_h}:${unoff_m.toString().padStart(2, '0')}`);

            let off_mins = 0;
            if (shift.allow_overtime) {
                let max_off = (parseFloat(shift.overtime_hours) || 0) * 60;
                off_mins = Math.min(extra_mins, max_off);
            }
            let off_h = Math.floor(off_mins / 60);
            let off_m = off_mins % 60;
            frm.set_value("official_overtime", `${off_h}:${off_m.toString().padStart(2, '0')}`);
        } else {
            let overtime_minutes = Math.max(0, netWorkingMinutes - 9 * 60);
            let ot_hours = Math.floor(overtime_minutes / 60);
            let ot_mins = overtime_minutes % 60;
            frm.set_value("official_overtime", `${ot_hours}:${ot_mins.toString().padStart(2, '0')}`);
            frm.set_value("unofficial_overtime", `${ot_hours}:${ot_mins.toString().padStart(2, '0')}`);
        }
    }

    if (frm.doc.shift) {
        frappe.db.get_value("Shift", frm.doc.shift, ["start_time", "end_time", "lunch_hours", "break_hours", "allow_overtime", "overtime_hours", "min_overtime_minutes"], function (shift) {
            applyHoursAndOvertime(shift);
        });
    } else {
        applyHoursAndOvertime(null);
    }
}

function reset_hours(frm) {
    frm.set_value("working_hours_display", "0:00");
    frm.set_value("working_hours_decimal", 0);
    frm.set_value("official_overtime", "0:00");
    frm.set_value("unofficial_overtime", "0:00");
}
