import frappe
from frappe.utils import getdate
from calendar import monthrange
from datetime import date, datetime, timedelta

def run():
    # 1. Device lookup
    device_row = frappe.db.get_value("Biometric Device", {}, ["name", "serial_number"], as_dict=True)
    device_id = device_row.name if device_row else "D00001"
    serial_no = device_row.serial_number if device_row else "12345"

    employees_config = [
        {
            "employee": "BEPL01973",
            "name": "Ravi Ganesan",
            "id": "1003",
        },
        {
            "employee": "BEPL01974",
            "name": "Radha Dayalan",
            "id": "1004",
        }
    ]

    year = 2026
    month = 9
    num_days = monthrange(year, month)[1]

    # Get max punch ID
    max_id_res = frappe.db.sql("SELECT MAX(name) FROM `tabAttendance Punch`")
    current_punch_id = int(max_id_res[0][0]) if (max_id_res and max_id_res[0][0]) else 0

    for cfg in employees_config:
        emp_code = cfg["employee"]
        emp_doc = frappe.get_doc("Employee", emp_code)
        emp_name = emp_doc.employee_name
        emp_id = emp_doc.employee_id or cfg["id"]
        shift = emp_doc.shift or "Morning Shift"

        print(f"\n==========================================")
        print(f"Setting ALL PRESENT attendance & punches for {emp_name} ({emp_code})")
        print(f"==========================================")

        for day in range(1, num_days + 1):
            att_date = date(year, month, day)
            weekday = att_date.weekday() # Monday=0, Sunday=6

            # Check if there is an existing record
            existing = frappe.db.get_value(
                "Attendance",
                {"employee": emp_code, "attendance_date": att_date},
                "name"
            )

            # Sundays: No attendance record needed (Holiday computed from Holiday List)
            if weekday == 6:
                if existing:
                    frappe.db.sql("DELETE FROM `tabAttendance Punch` WHERE parent = %s", (existing,))
                    frappe.db.sql("DELETE FROM `tabAttendance` WHERE name = %s", (existing,))
                    print(f"Deleted Sunday Holiday record for {att_date} ({existing})")
                continue

            # All Working Days -> Present with Multiple Punches
            status = "Present"
            half_day_status = ""
            in_time = "09:30:00"
            out_time = "18:30:00"
            working_hours_display = "9:00"
            working_hours_decimal = 9.0
            leave_type = None

            # Multiple punches: 4 punches (IN, OUT-lunch, IN-lunch, OUT-day-end)
            p1 = datetime.combine(att_date, datetime.min.time()) + timedelta(hours=9, minutes=30)
            p2 = datetime.combine(att_date, datetime.min.time()) + timedelta(hours=13, minutes=0)
            p3 = datetime.combine(att_date, datetime.min.time()) + timedelta(hours=13, minutes=45)
            p4 = datetime.combine(att_date, datetime.min.time()) + timedelta(hours=18, minutes=30)
            punch_list = [("IN", p1), ("OUT", p2), ("IN", p3), ("OUT", p4)]

            if existing:
                att_name = existing
                frappe.db.set_value("Attendance", att_name, {
                    "status": status,
                    "half_day_status": half_day_status,
                    "leave_type": leave_type,
                    "in_time": in_time,
                    "out_time": out_time,
                    "working_hours_display": working_hours_display,
                    "working_hours_decimal": working_hours_decimal,
                    "attendance_source": "Biometric",
                    "shift": shift,
                    "employee_name": emp_name,
                    "employee_id": emp_id,
                })
                print(f"Updated {att_date} -> {status} ({att_name})")
            else:
                doc = frappe.new_doc("Attendance")
                doc.employee = emp_code
                doc.employee_name = emp_name
                doc.employee_id = emp_id
                doc.attendance_date = att_date
                doc.status = status
                doc.half_day_status = half_day_status
                doc.leave_type = leave_type
                doc.in_time = in_time
                doc.out_time = out_time
                doc.working_hours_display = working_hours_display
                doc.working_hours_decimal = working_hours_decimal
                doc.attendance_source = "Biometric"
                doc.shift = shift
                doc.insert(ignore_permissions=True)
                att_name = doc.name
                print(f"Created {att_date} -> {status} ({att_name})")

            # Update child table tabAttendance Punch
            # Delete existing punches for this attendance doc
            frappe.db.sql("DELETE FROM `tabAttendance Punch` WHERE parent = %s", (att_name,))

            # Insert new multiple punches
            for idx, (p_type, p_dt) in enumerate(punch_list, start=1):
                current_punch_id += 1
                frappe.db.sql("""
                    INSERT INTO `tabAttendance Punch` (
                        `name`, `creation`, `modified`, `modified_by`, `owner`,
                        `docstatus`, `idx`, `punch_time`, `punch_type`, `device`,
                        `serial_number`, `biometric_log`, `source`, `parent`,
                        `parentfield`, `parenttype`
                    ) VALUES (
                        %s, NOW(), NOW(), 'Administrator', 'Administrator',
                        0, %s, %s, %s, %s,
                        %s, NULL, 'Biometric', %s,
                        'attendance_punches', 'Attendance'
                    )
                """, (
                    str(current_punch_id), idx, p_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    p_type, device_id, serial_no, att_name
                ))

    frappe.db.commit()
    print("\nSuccessfully updated all working days to PRESENT with multiple punches (Sundays skipped)!")
