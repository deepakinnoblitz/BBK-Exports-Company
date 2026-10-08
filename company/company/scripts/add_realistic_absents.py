import random
import time
from datetime import date
import frappe
from frappe.utils import getdate

def run():
    print("\n=======================================================")
    print(" Adding Realistic Absent Records for Oct 5 - Oct 8")
    print("=======================================================")
    start_time = time.time()

    target_dates = [
        date(2026, 10, 5),
        date(2026, 10, 6),
        date(2026, 10, 7),
        date(2026, 10, 8)
    ]

    # Fetch all Active Employees excluding test ones like BEPL01973, BEPL0002
    employees = frappe.db.sql("""
        SELECT name, employee_name, employee_id
        FROM `tabEmployee`
        WHERE status = 'Active' 
          AND name NOT IN ('BEPL01973', 'BEPL01974', 'BEPL0002', 'BEPL0175')
        ORDER BY name ASC
    """, as_dict=True)

    total_emps = len(employees)
    print(f"Total eligible active employees: {total_emps}")

    # Randomly select ~40 to 60 absents per day (approx 4.5% - 6% absent rate)
    for att_date in target_dates:
        d_str = att_date.strftime("%Y-%m-%d")
        
        # Determine number of absents for this day (e.g. Monday slightly higher ~55, Thu ~42)
        if att_date.weekday() == 0: # Monday
            num_absent = random.randint(48, 62)
        elif att_date.weekday() == 3: # Thursday
            num_absent = random.randint(38, 48)
        else:
            num_absent = random.randint(40, 52)

        # Pick random sample of employees for this day
        absent_sample = random.sample(employees, num_absent)
        emp_names = [e["name"] for e in absent_sample]

        # 1. Update Attendance records to Absent
        placeholders = ', '.join(['%s'] * len(emp_names))
        frappe.db.sql(f"""
            UPDATE `tabAttendance`
            SET status = 'Absent',
                in_time = NULL,
                out_time = NULL,
                working_hours_display = '0:00',
                working_hours_decimal = 0.0,
                official_overtime = '0:00',
                unofficial_overtime = '0:00',
                modified = NOW()
            WHERE attendance_date = %s
              AND employee IN ({placeholders})
        """, (d_str, *emp_names))

        # 2. Get the attendance doc names for these records to remove their punches
        att_docs = frappe.db.sql(f"""
            SELECT name FROM `tabAttendance`
            WHERE attendance_date = %s
              AND employee IN ({placeholders})
        """, (d_str, *emp_names), as_dict=True)

        att_names = [r["name"] for r in att_docs]
        if att_names:
            att_placeholders = ', '.join(['%s'] * len(att_names))
            frappe.db.sql(f"""
                DELETE FROM `tabAttendance Punch`
                WHERE parent IN ({att_placeholders})
            """, tuple(att_names))

        print(f" • {d_str} ({att_date.strftime('%a')}): Set {len(att_names)} employees to ABSENT (punches cleared).")

    frappe.db.commit()
    elapsed = time.time() - start_time
    print("\n=======================================================")
    print(f" Successfully updated absent attendance in {elapsed:.2f}s!")
    print("=======================================================")

if __name__ == "__main__":
    run()
