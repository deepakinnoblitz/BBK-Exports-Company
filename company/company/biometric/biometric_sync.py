# Copyright (c) 2026, Innoblitz and contributors
# For license information, please see license.txt

import hashlib
from datetime import datetime, timedelta
import frappe
from frappe.utils import now_datetime, get_datetime, format_datetime, getdate

from company.company.biometric.smartoffice_client import SmartOfficeClient


def compute_external_hash(employee_code: str, log_datetime, punch_direction: str, serial_number: str) -> str:
    """
    Generate a deterministic SHA-256 hash for deduplicating biometric punches.
    """
    if isinstance(log_datetime, datetime):
        dt_str = log_datetime.strftime("%Y-%m-%d %H:%M:%S")
    else:
        dt_str = str(log_datetime or "").strip()
    raw_key = f"{str(employee_code).strip()}|{dt_str}|{str(punch_direction).strip().upper()}|{str(serial_number or '').strip()}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def find_employee_by_code(employee_code: str):
    """
    Look up Employee by employee_id (HRMS employee_id == SmartOffice employee_code).
    """
    if not employee_code:
        return None
    code = str(employee_code).strip()
    return frappe.db.get_value(
        "Employee",
        {"employee_id": code, "status": ["!=", "Left"]},
        ["name", "employee_name", "employee_id"],
        as_dict=True
    ) or frappe.db.get_value(
        "Employee",
        {"employee_id": code},
        ["name", "employee_name", "employee_id"],
        as_dict=True
    )


def find_device_by_serial(serial_number: str):
    """
    Look up Biometric Device by serial_number.
    """
    if not serial_number:
        return None
    return frappe.db.get_value(
        "Biometric Device",
        {"serial_number": str(serial_number).strip(), "enabled": 1},
        "name"
    )


def sync_smartoffice_logs(from_datetime=None, to_datetime=None, sync_type="Manual"):
    """
    Orchestrate fetching logs from SmartOffice API, deduplicating,
    saving to Biometric Log, and processing into Attendance records.
    """
    settings = frappe.get_single("Biometric Settings")
    if not settings.enabled:
        raise frappe.ValidationError("Biometric Integration is disabled in Biometric Settings.")

    now = now_datetime()
    overlap_minutes = settings.overlap_minutes or 15

    # Determine sync time window
    if not from_datetime:
        if settings.last_successful_sync:
            from_dt = get_datetime(settings.last_successful_sync) - timedelta(minutes=overlap_minutes)
        else:
            from_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        from_dt = get_datetime(from_datetime)

    if not to_datetime:
        to_dt = now
    else:
        to_dt = get_datetime(to_datetime)

    # Initialize Sync Log
    sync_log = frappe.get_doc({
        "doctype": "Attendance Sync Log",
        "started_at": now,
        "from_date": from_dt,
        "to_date": to_dt,
        "sync_type": sync_type,
        "status": "Started",
        "records_received": 0,
        "records_created": 0,
        "duplicates_skipped": 0,
        "processed_count": 0,
        "error_count": 0
    })
    sync_log.insert(ignore_permissions=True)
    frappe.db.commit()

    records_received = 0
    records_created = 0
    duplicates_skipped = 0
    error_count = 0
    affected_employee_dates = set()

    try:
        client = SmartOfficeClient()
        raw_logs = client.get_device_logs(from_dt, to_dt)
        records_received = len(raw_logs)

        # Cache existing device map to avoid repeated queries
        devices = frappe.get_all("Biometric Device", fields=["name", "serial_number"])
        device_map = {d.serial_number.strip(): d.name for d in devices if d.serial_number}

        for item in raw_logs:
            emp_code = item["employee_code"]
            log_dt = item["log_datetime"]
            direction = item["punch_direction"]
            serial = item["serial_number"]

            ext_hash = compute_external_hash(emp_code, log_dt, direction, serial)

            # Check deduplication
            if frappe.db.exists("Biometric Log", {"external_hash": ext_hash}):
                duplicates_skipped += 1
                continue

            emp_info = find_employee_by_code(emp_code)
            device_name = device_map.get(serial) if serial else None

            log_doc = frappe.new_doc("Biometric Log")
            log_doc.employee_code = emp_code
            log_doc.log_datetime = log_dt
            log_doc.punch_direction = direction
            log_doc.serial_number = serial
            log_doc.device = device_name
            log_doc.temperature = item.get("temperature")
            log_doc.temperature_state = item.get("temperature_state")
            log_doc.external_hash = ext_hash
            log_doc.sync_time = now

            if emp_info:
                log_doc.employee = emp_info.name
                log_doc.employee_name = emp_info.employee_name
                log_doc.processing_status = "Pending"
                log_doc.processed = 0
                affected_employee_dates.add((emp_info.name, log_dt.date()))
            else:
                log_doc.processing_status = "Error"
                log_doc.error_message = f"No active Employee found with employee_id '{emp_code}'"
                log_doc.processed = 0
                error_count += 1

            log_doc.insert(ignore_permissions=True)
            records_created += 1

        frappe.db.commit()

        # Process punches into Attendance records
        processed_punches = process_punches_for_employee_dates(affected_employee_dates)

        # Update sync log with success
        sync_log.reload()
        sync_log.completed_at = now_datetime()
        sync_log.records_received = records_received
        sync_log.records_created = records_created
        sync_log.duplicates_skipped = duplicates_skipped
        sync_log.processed_count = processed_punches
        sync_log.error_count = error_count
        sync_log.status = "Completed"
        sync_log.save(ignore_permissions=True)

        # Update Biometric Settings history
        settings.reload()
        settings.last_successful_sync = now_datetime()
        settings.last_sync_from = from_dt
        settings.last_sync_to = to_dt
        settings.last_sync_status = "Success"
        settings.last_error_message = ""
        settings.save(ignore_permissions=True)

        frappe.db.commit()

        return {
            "status": "success",
            "sync_log": sync_log.name,
            "records_received": records_received,
            "records_created": records_created,
            "duplicates_skipped": duplicates_skipped,
            "processed_punches": processed_punches,
            "errors": error_count
        }

    except Exception as e:
        frappe.db.rollback()
        err_msg = str(e)
        frappe.log_error(f"Biometric Sync Error: {err_msg}", "Biometric Sync")

        try:
            sync_log.reload()
            sync_log.completed_at = now_datetime()
            sync_log.status = "Failed"
            sync_log.error_details = err_msg
            sync_log.records_received = records_received
            sync_log.records_created = records_created
            sync_log.duplicates_skipped = duplicates_skipped
            sync_log.error_count = error_count + 1
            sync_log.save(ignore_permissions=True)

            settings.reload()
            settings.last_sync_status = "Failed"
            settings.last_error_message = err_msg
            settings.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            pass

        raise e


def process_punches_for_employee_dates(employee_date_pairs):
    """
    Process punches for given (employee, date) pairs into Attendance documents.
    Protects manual edits (manual == 1).
    """
    total_processed = 0

    for employee, punch_date in employee_date_pairs:
        # Check if Attendance exists and whether it's marked as manual
        existing_attendance = frappe.db.get_value(
            "Attendance",
            {"employee": employee, "attendance_date": punch_date},
            ["name", "manual", "status"],
            as_dict=True
        )

        date_str = str(punch_date)
        start_dt = f"{date_str} 00:00:00"
        end_dt = f"{date_str} 23:59:59"

        # Fetch all biometric logs for this employee on this date
        logs = frappe.get_all(
            "Biometric Log",
            filters={
                "employee": employee,
                "log_datetime": ["between", [start_dt, end_dt]],
                "processing_status": ["in", ["Pending", "Processed"]]
            },
            fields=["name", "log_datetime", "punch_direction", "serial_number", "device"],
            order_by="log_datetime asc"
        )

        if not logs:
            continue

        if existing_attendance and existing_attendance.manual == 1:
            # DO NOT overwrite manual attendance!
            # Only update Biometric Log status with informative note
            for l in logs:
                frappe.db.set_value(
                    "Biometric Log",
                    l.name,
                    {
                        "processed": 1,
                        "processing_status": "Processed",
                        "error_message": f"Attendance on {punch_date} is protected (manual edit enabled)."
                    },
                    update_modified=False
                )
            total_processed += len(logs)
            continue

        # Determine IN and OUT time from punches
        in_time, out_time, punches_data = pair_punches(logs)

        if existing_attendance:
            att_doc = frappe.get_doc("Attendance", existing_attendance.name)
        else:
            att_doc = frappe.new_doc("Attendance")
            att_doc.employee = employee
            att_doc.attendance_date = punch_date
            att_doc.status = "Present"  # Default, calculate_working_hours recomputes

        att_doc.in_time = in_time
        att_doc.out_time = out_time
        att_doc.attendance_source = "Biometric"
        att_doc.manual = 0
        if not att_doc.shift:
            att_doc.shift = frappe.db.get_value("Employee", employee, "shift")

        # Populate child table attendance_punches
        att_doc.set("attendance_punches", [])
        for p in punches_data:
            att_doc.append("attendance_punches", {
                "punch_time": p["punch_time"],
                "punch_type": p["punch_type"],
                "device": p.get("device"),
                "serial_number": p.get("serial_number"),
                "biometric_log": p.get("biometric_log"),
                "source": "Biometric"
            })

        att_doc.save(ignore_permissions=True)

        # Mark logs as processed
        for l in logs:
            frappe.db.set_value(
                "Biometric Log",
                l.name,
                {
                    "processed": 1,
                    "processing_status": "Processed",
                    "error_message": None
                },
                update_modified=False
            )

        total_processed += len(logs)

    return total_processed


def pair_punches(logs):
    """
    Analyze sorted biometric logs and determine in_time, out_time,
    and structured punches for child table.
    """
    punches_data = []

    # Dedup logs within 60 seconds from same device
    filtered_logs = []
    last_dt = None
    for l in logs:
        curr_dt = get_datetime(l.log_datetime)
        if last_dt and (curr_dt - last_dt).total_seconds() < 60:
            continue
        filtered_logs.append(l)
        last_dt = curr_dt

    if not filtered_logs:
        filtered_logs = logs

    # Check if we have explicit IN and OUT directions
    has_explicit_in = any(l.punch_direction == "IN" for l in filtered_logs)
    has_explicit_out = any(l.punch_direction == "OUT" for l in filtered_logs)

    in_time = None
    out_time = None

    if has_explicit_in or has_explicit_out:
        # User/device has explicit direction
        in_logs = [l for l in filtered_logs if l.punch_direction == "IN"]
        out_logs = [l for l in filtered_logs if l.punch_direction == "OUT"]

        if in_logs:
            in_dt = get_datetime(in_logs[0].log_datetime)
            in_time = in_dt.strftime("%H:%M:%S")
        elif filtered_logs:
            in_dt = get_datetime(filtered_logs[0].log_datetime)
            in_time = in_dt.strftime("%H:%M:%S")

        if out_logs:
            out_dt = get_datetime(out_logs[-1].log_datetime)
            out_time = out_dt.strftime("%H:%M:%S")
        elif len(filtered_logs) > 1:
            out_dt = get_datetime(filtered_logs[-1].log_datetime)
            out_time = out_dt.strftime("%H:%M:%S")

        for l in filtered_logs:
            ptype = l.punch_direction if l.punch_direction in ["IN", "OUT"] else "IN"
            punches_data.append({
                "punch_time": l.log_datetime,
                "punch_type": ptype,
                "device": l.device,
                "serial_number": l.serial_number,
                "biometric_log": l.name
            })

    else:
        # All directions are AUTO or unspecified
        count = len(filtered_logs)
        first_dt = get_datetime(filtered_logs[0].log_datetime)
        in_time = first_dt.strftime("%H:%M:%S")

        if count > 1:
            last_dt = get_datetime(filtered_logs[-1].log_datetime)
            out_time = last_dt.strftime("%H:%M:%S")

        for idx, l in enumerate(filtered_logs):
            ptype = "IN" if idx == 0 else "OUT"
            punches_data.append({
                "punch_time": l.log_datetime,
                "punch_type": ptype,
                "device": l.device,
                "serial_number": l.serial_number,
                "biometric_log": l.name
            })

    return in_time, out_time, punches_data


def evaluate_and_run_scheduled_sync():
    """
    Invoked by Frappe scheduler (e.g. all / 5min interval).
    CRITICAL: Respects user-defined sync schedule and auto_sync_enabled flag.
    Exits immediately if auto sync is disabled or manual only.
    """
    try:
        settings = frappe.get_single("Biometric Settings")
    except Exception:
        return

    # Auto sync guard: must be master enabled, auto_sync_enabled checked, and not Manual Only
    if not settings.enabled:
        return
    if not getattr(settings, "auto_sync_enabled", 0):
        return
    if getattr(settings, "sync_mode", "Manual Only") == "Manual Only":
        return

    now = now_datetime()
    sync_mode = settings.sync_mode

    if sync_mode == "Interval in Minutes":
        interval = settings.sync_interval_minutes or 15
        if settings.last_successful_sync:
            last_sync = get_datetime(settings.last_successful_sync)
            diff_minutes = (now - last_sync).total_seconds() / 60
            if diff_minutes < interval:
                return

        # Trigger interval sync
        sync_smartoffice_logs(sync_type="Scheduled Interval")

    elif sync_mode == "Specific Times Daily":
        times_raw = settings.daily_sync_times or ""
        scheduled_times = [t.strip() for t in times_raw.split(",") if t.strip()]
        if not scheduled_times:
            return

        current_time_str = now.strftime("%H:%M")
        current_minute = now.hour * 60 + now.minute

        for t_str in scheduled_times:
            try:
                parts = t_str.split(":")
                target_minute = int(parts[0]) * 60 + int(parts[1])
                # Window of 4 minutes to trigger
                if 0 <= (current_minute - target_minute) < 5:
                    # Check if already synced today within this slot
                    if settings.last_successful_sync:
                        last_sync = get_datetime(settings.last_successful_sync)
                        if last_sync.date() == now.date():
                            last_minute = last_sync.hour * 60 + last_sync.minute
                            if abs(last_minute - target_minute) < 10:
                                # Already ran for this time slot today
                                continue

                    # Trigger daily scheduled sync for today
                    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    sync_smartoffice_logs(from_datetime=today_start, to_datetime=now, sync_type="Scheduled Daily Time")
                    break
            except Exception:
                continue


# -------------------------------------------------------------
# Whitelisted API Endpoints for Frontend / Client Call
# -------------------------------------------------------------

@frappe.whitelist()
def trigger_manual_sync(from_date=None, to_date=None):
    """
    Manual trigger from frontend Biometric Settings or Attendance dashboard.
    """
    frappe.only_for(["System Manager", "HR"])
    return sync_smartoffice_logs(from_datetime=from_date, to_datetime=to_date, sync_type="Manual")


@frappe.whitelist()
def test_connection():
    """
    Test SmartOffice WebAPI connectivity using current or stored credentials.
    """
    frappe.only_for(["System Manager", "HR"])
    try:
        client = SmartOfficeClient()
        # Query 1 minute window just to verify authentication & endpoint responsiveness
        now = now_datetime()
        one_min_ago = now - timedelta(minutes=1)
        client.get_device_logs(one_min_ago, now)
        return {
            "status": "success",
            "message": "Connected to SmartOffice WebAPI successfully!"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist()
def reprocess_unmapped_logs():
    """
    Reprocess biometric logs that had error status due to unmapped employee_id.
    """
    frappe.only_for(["System Manager", "HR"])
    unmapped_logs = frappe.get_all(
        "Biometric Log",
        filters={"processing_status": "Error", "employee": ["is", "not set"]},
        fields=["name", "employee_code", "log_datetime"]
    )

    resolved_count = 0
    affected_pairs = set()

    for item in unmapped_logs:
        emp = find_employee_by_code(item.employee_code)
        if emp:
            frappe.db.set_value(
                "Biometric Log",
                item.name,
                {
                    "employee": emp.name,
                    "employee_name": emp.employee_name,
                    "processing_status": "Pending",
                    "error_message": None
                }
            )
            log_dt = get_datetime(item.log_datetime)
            affected_pairs.add((emp.name, log_dt.date()))
            resolved_count += 1

    frappe.db.commit()

    processed_punches = 0
    if affected_pairs:
        processed_punches = process_punches_for_employee_dates(affected_pairs)
        frappe.db.commit()

    return {
        "status": "success",
        "resolved_logs": resolved_count,
        "processed_punches": processed_punches
    }


@frappe.whitelist()
def get_biometric_status():
    """
    Returns high-level statistics for the Biometric integration dashboard/settings.
    """
    frappe.only_for(["System Manager", "HR"])
    settings = frappe.get_single("Biometric Settings")
    
    total_logs = frappe.db.count("Biometric Log")
    pending_logs = frappe.db.count("Biometric Log", {"processing_status": "Pending"})
    error_logs = frappe.db.count("Biometric Log", {"processing_status": "Error"})
    devices_count = frappe.db.count("Biometric Device", {"enabled": 1})

    recent_syncs = frappe.get_all(
        "Attendance Sync Log",
        fields=["name", "started_at", "completed_at", "sync_type", "records_received", "records_created", "status"],
        order_by="started_at desc",
        limit=5
    )

    return {
        "enabled": settings.enabled,
        "auto_sync_enabled": getattr(settings, "auto_sync_enabled", 0),
        "sync_mode": getattr(settings, "sync_mode", "Manual Only"),
        "sync_interval_minutes": getattr(settings, "sync_interval_minutes", 15),
        "daily_sync_times": getattr(settings, "daily_sync_times", ""),
        "last_successful_sync": settings.last_successful_sync,
        "last_sync_status": settings.last_sync_status,
        "last_error_message": settings.last_error_message,
        "total_logs": total_logs,
        "pending_logs": pending_logs,
        "error_logs": error_logs,
        "devices_count": devices_count,
        "recent_syncs": recent_syncs
    }
