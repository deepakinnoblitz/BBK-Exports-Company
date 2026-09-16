frappe.ui.form.on('WFH Attendance', {
    refresh(frm) {
        // 🗓️ Auto-set today's date when creating a new form
        if (frm.is_new() && !frm.doc.date) {
            const today = frappe.datetime.get_today();
            frm.set_value('date', today);
        }
    },

    from_time(frm) {
        calculate_total_hours(frm);
    },

    to_time(frm) {
        calculate_total_hours(frm);
    }
});

function calculate_total_hours(frm) {
    const from_time = frm.doc.from_time;
    const to_time = frm.doc.to_time;

    if (from_time && to_time) {
        const start = moment(from_time, ["HH:mm:ss", "HH:mm"]);
        const end = moment(to_time, ["HH:mm:ss", "HH:mm"]);

        let duration = moment.duration(end.diff(start));

        // Handle overnight (e.g., 22:00 → 02:00)
        if (duration.asMinutes() < 0) {
            duration = moment.duration(moment(to_time, ["HH:mm:ss", "HH:mm"]).add(1, "day").diff(start));
        }

        const hours = Math.floor(duration.asHours());
        const minutes = Math.floor(duration.asMinutes() % 60);

        // Format like 7:52
        const formatted = `${hours}:${minutes.toString().padStart(2, "0")}`;

        frm.set_value("total_hours", formatted);
        frm.refresh_field("total_hours");
    } else {
        frm.set_value("total_hours", "");
    }
}
