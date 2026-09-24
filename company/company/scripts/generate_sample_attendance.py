import random
import time
from datetime import date, datetime, timedelta
import frappe
from frappe.utils import getdate, cint

def run(count=100000, batch_size=5000):
    """
    Generates realistic sample attendance records across existing employees.
    Usage:
        bench --site <site> execute company.company.scripts.generate_sample_attendance.run --args "(100000, 5000)"
    """
    count = int(count)
    batch_size = int(batch_size)
    print("\n=======================================================")
    print(f" Starting High-Performance Attendance Generator: {count:,} records")
    print("=======================================================")
    start_time = time.time()

    # 1. Fetch Employees
    employees = frappe.db.get_all(
        "Employee",
        fields=["name", "employee_name", "employee_id", "shift", "status", "date_of_joining"],
        order_by="name asc"
    )
    if not employees:
        print("No employees found in database! Please generate employees first.")
        return

    emp_lookup = {e.name: e for e in employees}
    total_emps = len(employees)
    print(f"Loaded {total_emps} employees from database.")

    # 2. Fetch Active Holidays
    holidays = {
        h.holiday_date: (h.description or "Public Holiday")
        for h in frappe.db.get_all("Holidays", filters={"is_working_day": 0}, fields=["holiday_date", "description"])
    }
    print(f"Loaded {len(holidays)} public holiday records.")

    # 3. Leave Types
    leave_types = [l.name for l in frappe.db.get_all("Leave Type")] or ["Casual Leave"]

    # 4. Check existing (employee, attendance_date) to avoid duplicates
    existing_records = frappe.db.sql("SELECT employee, attendance_date FROM `tabAttendance`")
    existing_set = {(r[0], getdate(r[1])) for r in existing_records}
    print(f"Found {len(existing_set)} existing attendance records in database.")

    # 5. Determine Current Series for ATD
    series_res = frappe.db.sql("SELECT current FROM `tabSeries` WHERE name = 'ATD'")
    current_series = cint(series_res[0][0]) if series_res else 0
    next_series_num = current_series + 1
    print(f"Starting ATD naming series from: ATD{next_series_num:05d}")

    # 6. Generate Dates List
    # We want approx count // total_emps days
    days_needed = (count // total_emps) + 20
    # End date: 2026-09-22, going backwards
    anchor_end_date = date(2026, 9, 22)
    dates_list = [anchor_end_date - timedelta(days=d) for d in range(days_needed)]

    # 7. Shift Timing Profiles
    shift_timings = {
        "Morning Shift": {
            "in_base": (9, 30),
            "out_base": (18, 30),
            "in_variance": (-15, 10),
            "out_variance": (-5, 45)
        },
        "Afternoon Shift": {
            "in_base": (14, 0),
            "out_base": (22, 0),
            "in_variance": (-15, 10),
            "out_variance": (-5, 40)
        },
        "Night Shift": {
            "in_base": (18, 0),
            "out_base": (2, 0),
            "in_variance": (-15, 10),
            "out_variance": (-5, 40)
        }
    }
    default_shift = "Morning Shift"

    # Columns to insert into tabAttendance
    cols = [
        "name", "creation", "modified", "modified_by", "owner",
        "docstatus", "idx", "employee", "employee_name", "employee_id",
        "attendance_date", "status", "half_day_status", "leave_type",
        "in_time", "out_time", "working_hours_display", "working_hours_decimal",
        "overtime_display", "overtime_decimal", "official_overtime", "unofficial_overtime",
        "manual", "attendance_source", "shift"
    ]
    col_str = ", ".join(f"`{c}`" for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    insert_sql = f"INSERT INTO `tabAttendance` ({col_str}) VALUES ({placeholders})"

    now_ts = datetime.now()
    batch_values = []
    total_generated = 0
    series_counter = next_series_num

    print("\nStarting generation loop...")

    # Iterate day by day, employee by employee
    for cur_date in dates_list:
        if total_generated >= count:
            break

        is_sunday = (cur_date.weekday() == 6)
        is_holiday = (cur_date in holidays)
        d_str = cur_date.strftime("%Y-%m-%d")

        for emp in employees:
            if total_generated >= count:
                break

            # Skip if attendance already exists
            if (emp.name, cur_date) in existing_set:
                continue

            # Check joining date
            if emp.date_of_joining and cur_date < getdate(emp.date_of_joining):
                continue

            doc_name = f"ATD{series_counter:05d}"
            series_counter += 1

            emp_shift = emp.shift or default_shift
            timing = shift_timings.get(emp_shift, shift_timings[default_shift])

            # Determine Status & Timings
            if is_holiday:
                status = "Holiday"
                half_day_status = None
                leave_type = None
                in_time = None
                out_time = None
                wh_display = "0:00"
                wh_dec = 0.0
                ot_disp = "0:00"
                ot_dec = 0.0
            elif is_sunday:
                # 90% chance Sunday is off/Holiday, 10% Sunday shift overtime work
                if random.random() < 0.90:
                    status = "Holiday"
                    half_day_status = None
                    leave_type = None
                    in_time = None
                    out_time = None
                    wh_display = "0:00"
                    wh_dec = 0.0
                    ot_disp = "0:00"
                    ot_dec = 0.0
                else:
                    status = "Present"
                    half_day_status = None
                    leave_type = None
                    in_m = timing["in_base"][0] * 60 + timing["in_base"][1] + random.randint(*timing["in_variance"])
                    out_m = timing["out_base"][0] * 60 + timing["out_base"][1] + random.randint(*timing["out_variance"])
                    in_time = f"{in_m // 60:02d}:{in_m % 60:02d}:{random.randint(0, 59):02d}"
                    out_time = f"{out_m // 60:02d}:{out_m % 60:02d}:{random.randint(0, 59):02d}"
                    work_mins = 8 * 60 + random.randint(15, 60)
                    wh_display = f"{work_mins // 60}:{work_mins % 60:02d}"
                    wh_dec = round(work_mins / 60.0, 2)
                    ot_mins = work_mins - 480
                    ot_disp = f"{ot_mins // 60}:{ot_mins % 60:02d}"
                    ot_dec = round(ot_mins / 60.0, 2)
            else:
                # Normal Workday Distribution
                rand_val = random.random()
                if rand_val < 0.91:
                    # Present (~91%)
                    status = "Present"
                    half_day_status = None
                    leave_type = None

                    in_m = timing["in_base"][0] * 60 + timing["in_base"][1] + random.randint(*timing["in_variance"])
                    out_m = timing["out_base"][0] * 60 + timing["out_base"][1] + random.randint(*timing["out_variance"])
                    in_time = f"{in_m // 60:02d}:{in_m % 60:02d}:{random.randint(0, 59):02d}"
                    out_time = f"{out_m // 60:02d}:{out_m % 60:02d}:{random.randint(0, 59):02d}"

                    # Working hours around 8h to 9.5h
                    work_mins = random.randint(460, 560)
                    wh_display = f"{work_mins // 60}:{work_mins % 60:02d}"
                    wh_dec = round(work_mins / 60.0, 2)

                    if work_mins > 480:
                        ot_mins = work_mins - 480
                        ot_disp = f"{ot_mins // 60}:{ot_mins % 60:02d}"
                        ot_dec = round(ot_mins / 60.0, 2)
                    else:
                        ot_disp = "0:00"
                        ot_dec = 0.0

                elif rand_val < 0.95:
                    # On Leave (~4%)
                    status = "On Leave"
                    half_day_status = None
                    leave_type = random.choice(leave_types)
                    in_time = None
                    out_time = None
                    wh_display = "0:00"
                    wh_dec = 0.0
                    ot_disp = "0:00"
                    ot_dec = 0.0

                elif rand_val < 0.975:
                    # Half Day (~2.5%)
                    status = "Half Day"
                    half_day_status = "Present"
                    leave_type = random.choice(leave_types)
                    in_m = timing["in_base"][0] * 60 + timing["in_base"][1] + random.randint(-10, 10)
                    out_m = in_m + 240 + random.randint(-5, 10)
                    in_time = f"{in_m // 60:02d}:{in_m % 60:02d}:{random.randint(0, 59):02d}"
                    out_time = f"{out_m // 60:02d}:{out_m % 60:02d}:{random.randint(0, 59):02d}"
                    wh_display = "4:00"
                    wh_dec = 4.0
                    ot_disp = "0:00"
                    ot_dec = 0.0

                else:
                    # Absent (~2.5%)
                    status = "Absent"
                    half_day_status = None
                    leave_type = None
                    in_time = None
                    out_time = None
                    wh_display = "0:00"
                    wh_dec = 0.0
                    ot_disp = "0:00"
                    ot_dec = 0.0

            row_tuple = (
                doc_name, now_ts, now_ts, "Administrator", "Administrator",
                0, 0, emp.name, emp.employee_name, emp.employee_id,
                d_str, status, half_day_status, leave_type,
                in_time, out_time, wh_display, wh_dec,
                ot_disp, ot_dec, ot_disp, "0:00",
                0, "Biometric", emp_shift
            )
            batch_values.append(row_tuple)
            total_generated += 1

            # Insert in chunks
            if len(batch_values) >= batch_size:
                frappe.db.bulk_insert("Attendance", cols, batch_values, chunk_size=batch_size)
                frappe.db.commit()
                batch_values = []
                elapsed = time.time() - start_time
                rate = total_generated / elapsed if elapsed > 0 else 0
                pct = (total_generated / count) * 100
                print(f"  [Progress] {total_generated:,}/{count:,} ({pct:.1f}%) inserted - {rate:,.0f} records/sec")

    # Insert remaining rows
    if batch_values:
        frappe.db.bulk_insert("Attendance", cols, batch_values, chunk_size=batch_size)
        frappe.db.commit()

    # Update Series
    frappe.db.sql("UPDATE `tabSeries` SET current = %s WHERE name = 'ATD'", (series_counter - 1,))
    frappe.db.commit()

    # Automatically generate biometric multiple punches
    try:
        from company.company.scripts.generate_sample_punches import run as generate_punches
        generate_punches()
    except Exception as e:
        print(f"Warning: Failed to generate punches automatically: {e}")

    total_elapsed = time.time() - start_time
    total_db_count = frappe.db.count("Attendance")

    print("\n=======================================================")
    print(" Successfully Completed Attendance Generation!")
    print(f" Total Inserted: {total_generated:,}")
    print(f" Elapsed Time  : {total_elapsed:.2f} seconds ({total_generated/total_elapsed:,.0f} rec/sec)")
    print(f" Total in DB   : {total_db_count:,} attendance records")
    print("=======================================================\n")

    return {
        "inserted": total_generated,
        "total_in_db": total_db_count,
        "elapsed_seconds": round(total_elapsed, 2)
    }
