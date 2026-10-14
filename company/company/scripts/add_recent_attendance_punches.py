import random
import time
from datetime import date, datetime, timedelta
import frappe
from frappe.utils import getdate

def run():
    print("\n=======================================================")
    print(" Adding Attendance & Multiple Punches for Oct 5 - Oct 8")
    print("=======================================================")
    start_time = time.time()

    # 1. Target dates: Today (Oct 8) and Last 3 Days (Oct 7, Oct 6, Oct 5)
    target_dates = [
        date(2026, 10, 5),
        date(2026, 10, 6),
        date(2026, 10, 7),
        date(2026, 10, 8)
    ]
    print(f"Target Dates: {[d.strftime('%Y-%m-%d') for d in target_dates]}")

    # 2. Fetch all Active Employees
    employees = frappe.db.sql("""
        SELECT name, employee_name, employee_id, shift, employee_type
        FROM `tabEmployee`
        WHERE status = 'Active'
        ORDER BY name ASC
    """, as_dict=True)

    total_emps = len(employees)
    print(f"Found {total_emps:,} active employees.")
    if not total_emps:
        print("No active employees found.")
        return

    # 3. Biometric Device
    device_row = frappe.db.get_value("Biometric Device", {}, ["name", "serial_number"], as_dict=True)
    device_id = device_row.name if device_row else "D00001"
    serial_no = device_row.serial_number if device_row else "12345"
    print(f"Using Biometric Device: {device_id} (Serial: {serial_no})")

    # 4. Get current max punch id
    max_id_res = frappe.db.sql("SELECT MAX(name) FROM `tabAttendance Punch`")
    current_punch_id = int(max_id_res[0][0]) if (max_id_res and max_id_res[0][0]) else 360000
    print(f"Starting Attendance Punch ID from: {current_punch_id + 1}")

    # 5. Fetch existing attendance records for target dates to avoid duplicates
    existing_att = {}
    records = frappe.db.sql("""
        SELECT name, employee, attendance_date
        FROM `tabAttendance`
        WHERE attendance_date BETWEEN '2026-10-05' AND '2026-10-08'
    """, as_dict=True)
    for r in records:
        d_str = str(getdate(r["attendance_date"]))
        existing_att[(r["employee"], d_str)] = r["name"]

    print(f"Found {len(existing_att)} pre-existing attendance records for these dates.")

    # 6. Fetch next Attendance series ID
    # In tabSeries for Attendance or max ATD.#####
    series_res = frappe.db.sql("SELECT MAX(name) FROM `tabAttendance` WHERE name LIKE 'ATD.%'")
    max_series_num = 0
    if series_res and series_res[0][0]:
        try:
            max_series_num = int(series_res[0][0].replace("ATD.", "").replace("ATD-", "").strip())
        except Exception:
            max_series_num = 100000

    if max_series_num < 100000:
        max_series_num = 100000

    now_ts = datetime.now()
    att_cols = [
        "name", "creation", "modified", "modified_by", "owner",
        "docstatus", "idx", "employee", "employee_name", "employee_id",
        "attendance_date", "status", "half_day_status", "leave_type",
        "in_time", "out_time", "shift", "working_hours_display",
        "working_hours_decimal", "official_overtime", "unofficial_overtime",
        "manual", "attendance_source"
    ]

    punch_cols = [
        "name", "creation", "modified", "modified_by", "owner",
        "docstatus", "idx", "punch_time", "punch_type", "device",
        "serial_number", "biometric_log", "source", "parent",
        "parentfield", "parenttype"
    ]

    new_att_batch = []
    new_punch_batch = []
    att_names_to_clear_punches = []

    total_att_created = 0
    total_att_updated = 0
    total_punches_created = 0

    for emp_idx, emp in enumerate(employees, start=1):
        emp_code = emp["name"]
        emp_name = emp["employee_name"]
        emp_id = emp["employee_id"] or emp_code
        shift = emp["shift"] or "Morning Shift"

        # Unique random offset per employee for natural-looking variations
        base_offset_min = (hash(emp_code) % 20) - 10 # -10 to +10 mins

        for att_date in target_dates:
            d_str = att_date.strftime("%Y-%m-%d")

            # Punch 1: Shift IN (approx 09:00 - 09:15)
            in_min = 5 + base_offset_min + random.randint(0, 5)
            p1 = datetime.combine(att_date, datetime.min.time()) + timedelta(hours=9, minutes=max(0, min(59, in_min)), seconds=random.randint(0, 59))

            # Punch 2: Lunch OUT (approx 13:00)
            lunch_out_min = base_offset_min + random.randint(0, 5)
            p2 = datetime.combine(att_date, datetime.min.time()) + timedelta(hours=13, minutes=max(0, min(59, lunch_out_min)), seconds=random.randint(0, 59))

            # Punch 3: Lunch IN (approx 13:45)
            lunch_duration = random.randint(40, 48)
            p3 = p2 + timedelta(minutes=lunch_duration, seconds=random.randint(0, 59))

            # Punch 4: Shift OUT (approx 18:00 - 18:15)
            out_min = 5 + base_offset_min + random.randint(0, 10)
            p4 = datetime.combine(att_date, datetime.min.time()) + timedelta(hours=18, minutes=max(0, min(59, out_min)), seconds=random.randint(0, 59))

            # Calculate working hours (Total duration minus lunch)
            total_work_sec = (p4 - p1).total_seconds() - (p3 - p2).total_seconds()
            work_hours = total_work_sec / 3600.0
            work_h_int = int(work_hours)
            work_m_int = int((work_hours - work_h_int) * 60)
            working_hours_display = f"{work_h_int}:{work_m_int:02d}"
            working_hours_decimal = round(work_hours, 2)

            in_time_str = p1.strftime("%H:%M:%S")
            out_time_str = p4.strftime("%H:%M:%S")

            punch_list = [
                ("IN", p1),
                ("OUT", p2),
                ("IN", p3),
                ("OUT", p4)
            ]

            existing_name = existing_att.get((emp_code, d_str))

            if existing_name:
                att_name = existing_name
                frappe.db.sql("""
                    UPDATE `tabAttendance`
                    SET status = 'Present',
                        in_time = %s,
                        out_time = %s,
                        working_hours_display = %s,
                        working_hours_decimal = %s,
                        attendance_source = 'Biometric',
                        shift = %s,
                        employee_name = %s,
                        employee_id = %s,
                        modified = NOW()
                    WHERE name = %s
                """, (
                    in_time_str, out_time_str, working_hours_display,
                    working_hours_decimal, shift, emp_name, emp_id, att_name
                ))
                att_names_to_clear_punches.append(att_name)
                total_att_updated += 1
            else:
                max_series_num += 1
                att_name = f"ATD.{max_series_num:05d}"
                new_att_batch.append((
                    att_name, now_ts, now_ts, "Administrator", "Administrator",
                    0, 0, emp_code, emp_name, emp_id,
                    d_str, "Present", "", None,
                    in_time_str, out_time_str, shift, working_hours_display,
                    working_hours_decimal, "0:00", "0:00",
                    0, "Biometric"
                ))
                total_att_created += 1

            # Prepare 4 punches
            for p_idx, (p_type, p_dt) in enumerate(punch_list, start=1):
                current_punch_id += 1
                new_punch_batch.append((
                    current_punch_id, now_ts, now_ts, "Administrator", "Administrator",
                    0, p_idx, p_dt.strftime("%Y-%m-%d %H:%M:%S"), p_type, device_id,
                    serial_no, None, "Biometric", att_name,
                    "attendance_punches", "Attendance"
                ))
                total_punches_created += 1

    # Bulk delete existing punches for updated records
    if att_names_to_clear_punches:
        print(f"Clearing old punches for {len(att_names_to_clear_punches)} existing attendance records...")
        for i in range(0, len(att_names_to_clear_punches), 500):
            chunk = att_names_to_clear_punches[i:i+500]
            format_strings = ','.join(['%s'] * len(chunk))
            frappe.db.sql(f"DELETE FROM `tabAttendance Punch` WHERE parent IN ({format_strings})", tuple(chunk))

    # Bulk insert new Attendance records
    if new_att_batch:
        print(f"Inserting {len(new_att_batch):,} new Attendance records...")
        frappe.db.bulk_insert("Attendance", att_cols, new_att_batch, chunk_size=2000)

    # Bulk insert new Attendance Punch records
    if new_punch_batch:
        print(f"Inserting {len(new_punch_batch):,} new Attendance Punch records...")
        frappe.db.bulk_insert("Attendance Punch", punch_cols, new_punch_batch, chunk_size=4000)

    # Update series counter in tabSeries
    frappe.db.sql("INSERT INTO `tabSeries` (name, current) VALUES ('ATD.', %s) ON DUPLICATE KEY UPDATE current = %s", (max_series_num, max_series_num))

    frappe.db.commit()
    elapsed = time.time() - start_time
    print("\n=======================================================")
    print(f" Successfully completed in {elapsed:.2f} seconds!")
    print(f" • New Attendance Created: {total_att_created:,}")
    print(f" • Attendance Updated: {total_att_updated:,}")
    print(f" • Total Punches Created: {total_punches_created:,}")
    print(f" • Target Dates: 2026-10-05, 2026-10-06, 2026-10-07, 2026-10-08")
    print("=======================================================")

if __name__ == "__main__":
    run()
