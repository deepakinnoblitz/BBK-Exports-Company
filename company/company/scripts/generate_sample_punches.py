import random
import time
from datetime import date, datetime, timedelta
import frappe
from frappe.utils import getdate

def to_seconds(t):
    if not t:
        return 0
    if isinstance(t, timedelta):
        return int(t.total_seconds())
    if isinstance(t, str):
        parts = t.strip().split(":")
        h = int(parts[0]) if len(parts) > 0 else 0
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(float(parts[2])) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s
    if hasattr(t, "hour"):
        return t.hour * 3600 + t.minute * 60 + t.second
    return 0

def run(batch_size=10000):
    """
    Generates realistic multiple biometric punches for all Attendance records that have in_time and out_time.
    Usage:
        bench --site <site> execute company.company.scripts.generate_sample_punches.run
    """
    print("\n=======================================================")
    print(" Starting Biometric Multiple Punches Generator")
    print("=======================================================")
    start_time = time.time()

    # 1. Fetch attendance records needing punches
    print("Finding attendance records without punches...")
    records = frappe.db.sql("""
        SELECT a.name, a.attendance_date, a.in_time, a.out_time, a.status
        FROM `tabAttendance` a
        LEFT JOIN (SELECT DISTINCT parent FROM `tabAttendance Punch`) p ON a.name = p.parent
        WHERE a.in_time IS NOT NULL 
          AND a.out_time IS NOT NULL
          AND p.parent IS NULL
        ORDER BY a.attendance_date ASC, a.name ASC
    """, as_dict=True)

    total_records = len(records)
    print(f"Found {total_records:,} attendance records needing punches.")
    if not total_records:
        print("All attendance records already have punches!")
        return

    # 2. Get current max punch id
    max_id_res = frappe.db.sql("SELECT MAX(name) FROM `tabAttendance Punch`")
    current_punch_id = max_id_res[0][0] if (max_id_res and max_id_res[0][0]) else 0
    print(f"Current max Attendance Punch ID: {current_punch_id}")

    # 3. Check for biometric device
    device_row = frappe.db.get_value("Biometric Device", {"device_name": "Main Gate"}, ["name", "serial_number"], as_dict=True)
    if not device_row:
        device_row = frappe.db.get_value("Biometric Device", {}, ["name", "serial_number"], as_dict=True)
    
    device_id = device_row.name if device_row else "D00001"
    serial_no = device_row.serial_number if device_row else "12345"
    print(f"Using Biometric Device: {device_id} (Serial: {serial_no})")

    cols = [
        "name", "creation", "modified", "modified_by", "owner",
        "docstatus", "idx", "punch_time", "punch_type", "device",
        "serial_number", "biometric_log", "source", "parent",
        "parentfield", "parenttype"
    ]

    now_ts = datetime.now()
    batch_values = []
    punch_counter = current_punch_id
    total_punches = 0
    records_processed = 0

    print("Generating multiple punches...")

    for row in records:
        att_name = row["name"]
        att_date = getdate(row["attendance_date"])
        in_sec = to_seconds(row["in_time"])
        out_sec = to_seconds(row["out_time"])
        status = row.get("status", "Present")

        in_dt = datetime.combine(att_date, datetime.min.time()) + timedelta(seconds=in_sec)
        if out_sec < in_sec:
            out_dt = datetime.combine(att_date + timedelta(days=1), datetime.min.time()) + timedelta(seconds=out_sec)
        else:
            out_dt = datetime.combine(att_date, datetime.min.time()) + timedelta(seconds=out_sec)

        duration_sec = (out_dt - in_dt).total_seconds()

        punches_for_row = []

        # Always Punch 1: IN
        punches_for_row.append(("IN", in_dt))

        # Multiple punches check (Lunch break / mid break for shifts >= 6 hours)
        # ~85% of full-day shifts have a 4-punch sequence (IN -> Lunch OUT -> Lunch IN -> OUT)
        if status != "Half Day" and duration_sec >= 5.5 * 3600 and random.random() < 0.85:
            # Mid-day break around 3.5 to 4.2 hours into the shift
            lunch_offset_mins = random.randint(210, 255)
            lunch_out_dt = in_dt + timedelta(minutes=lunch_offset_mins, seconds=random.randint(0, 59))
            
            # Lunch duration: 35 to 55 minutes
            lunch_duration_mins = random.randint(35, 55)
            lunch_in_dt = lunch_out_dt + timedelta(minutes=lunch_duration_mins, seconds=random.randint(0, 59))

            # Ensure lunch falls strictly between in_dt and out_dt
            if lunch_out_dt < lunch_in_dt and lunch_in_dt < (out_dt - timedelta(minutes=30)):
                punches_for_row.append(("OUT", lunch_out_dt))
                punches_for_row.append(("IN", lunch_in_dt))

        # Final Punch: OUT
        punches_for_row.append(("OUT", out_dt))

        # Add to batch
        for idx, (p_type, p_time) in enumerate(punches_for_row, start=1):
            punch_counter += 1
            batch_values.append((
                punch_counter,
                now_ts,
                now_ts,
                "Administrator",
                "Administrator",
                0,
                idx,
                p_time.strftime("%Y-%m-%d %H:%M:%S"),
                p_type,
                device_id,
                serial_no,
                None,
                "Biometric",
                att_name,
                "attendance_punches",
                "Attendance"
            ))
            total_punches += 1

        records_processed += 1

        # Bulk insert batch
        if len(batch_values) >= batch_size:
            frappe.db.bulk_insert("Attendance Punch", cols, batch_values, chunk_size=batch_size)
            frappe.db.commit()
            batch_values = []
            elapsed = time.time() - start_time
            print(f" Progress: {records_processed:,}/{total_records:,} records ({total_punches:,} punches) in {elapsed:.1f}s")

    # Flush remaining
    if batch_values:
        frappe.db.bulk_insert("Attendance Punch", cols, batch_values, chunk_size=batch_size)
        frappe.db.commit()

    # Update sequence in database and tabSeries
    try:
        from frappe.database.sequence import set_next_val
        set_next_val("Attendance Punch", punch_counter + 1, is_val_used=False)
    except Exception as e:
        print(f"Warning: Failed to set sequence nextval: {e}")

    frappe.db.sql("INSERT INTO `tabSeries` (`name`, `current`) VALUES ('', %s) ON DUPLICATE KEY UPDATE `current` = GREATEST(`current`, %s)", (punch_counter, punch_counter))
    frappe.db.commit()

    total_time = time.time() - start_time
    print("\n=======================================================")
    print(f" SUCCESS! Generated {total_punches:,} punches for {records_processed:,} attendance records in {total_time:.2f} seconds!")
    print(f" Punch ID range: {current_punch_id + 1} -> {punch_counter}")
    print("=======================================================\n")
