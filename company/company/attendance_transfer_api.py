import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, cstr, flt

def is_user_super_admin(user=None):
    """
    Super Admin Rule: User must have BOTH ('HR' or 'HR Manager') AND 'System Manager' roles,
    OR be the 'Administrator'.
    """
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False
    roles = frappe.get_roles(user)
    if "Administrator" in roles:
        return True
    has_hr = ("HR" in roles or "HR Manager" in roles)
    has_sm = "System Manager" in roles
    return bool(has_hr and has_sm)

def validate_super_admin():
    if not is_user_super_admin():
        frappe.throw(
            _("Access Denied: Only Super Admin (users with both HR and System Manager roles) can access Attendance Transfer features."),
            frappe.PermissionError
        )

@frappe.whitelist()
def check_super_admin_status():
    """Returns whether current user is Super Admin."""
    return {"is_super_admin": is_user_super_admin()}

@frappe.whitelist()
def get_eligible_transfer_employees(source_date, target_date, department=None, search=None):
    """
    Finds employees who worked on source_date (Sunday / Non-working day)
    and are eligible to transfer to target_date (e.g. Absent or unmarked on target_date).
    """
    validate_super_admin()

    if not source_date or not target_date:
        frappe.throw(_("Both Source Date and Target Date are required."))

    src_date = getdate(source_date)
    tgt_date = getdate(target_date)

    if src_date == tgt_date:
        frappe.throw(_("Source Date and Target Date cannot be the same date."))

    # 1. Fetch all attendance records on source_date where status is Present / Half Day
    # and has NOT been transferred yet.
    conds = ["a.attendance_date = %s", "IFNULL(a.is_transferred, 0) = 0", "a.status IN ('Present', 'Half Day')"]
    params = [src_date]

    if department:
        conds.append("e.department = %s")
        params.append(department)

    if search:
        conds.append("(e.name LIKE %s OR e.employee_name LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    sql = f"""
        SELECT 
            a.name AS source_attendance,
            a.employee,
            e.employee_name,
            e.department,
            e.designation,
            e.shift,
            a.in_time,
            a.out_time,
            a.working_hours_display,
            a.working_hours_decimal,
            a.status AS source_status
        FROM `tabAttendance` a
        JOIN `tabEmployee` e ON a.employee = e.name
        WHERE {" AND ".join(conds)}
        ORDER BY e.employee_name ASC
    """
    source_records = frappe.db.sql(sql, params, as_dict=True)

    if not source_records:
        return {
            "employees": [],
            "message": _("No eligible worked attendance found on the selected source date.")
        }

    employee_ids = [r.employee for r in source_records]

    # 2. Check target_date attendance for these employees
    placeholders = ", ".join(["%s"] * len(employee_ids))
    tgt_records = frappe.db.sql(f"""
        SELECT 
            name AS target_attendance,
            employee,
            status,
            in_time,
            out_time,
            is_transferred,
            transferred_from_date
        FROM `tabAttendance`
        WHERE attendance_date = %s AND employee IN ({placeholders})
    """, [tgt_date] + employee_ids, as_dict=True)

    tgt_map = {r.employee: r for r in tgt_records}

    eligible_candidates = []
    for rec in source_records:
        emp_id = rec.employee
        tgt_att = tgt_map.get(emp_id)

        # Check if already Present on target date without transfer
        if tgt_att and tgt_att.status == "Present" and not tgt_att.is_transferred:
            # Employee already worked normally on target date -> cannot transfer
            continue

        prev_status = tgt_att.status if tgt_att else "Not Marked"

        eligible_candidates.append({
            "employee": emp_id,
            "employee_name": rec.employee_name,
            "department": rec.department or "",
            "designation": rec.designation or "",
            "shift": rec.shift or "",
            "source_attendance": rec.source_attendance,
            "source_in_time": str(rec.in_time or ""),
            "source_out_time": str(rec.out_time or ""),
            "source_working_hours": flt(rec.working_hours_decimal or 0),
            "source_working_hours_display": rec.working_hours_display or "0:00",
            "target_attendance": tgt_att.name if tgt_att else None,
            "previous_target_status": prev_status,
            "is_eligible": True
        })

    return {
        "employees": eligible_candidates
    }

@frappe.whitelist()
def execute_bulk_attendance_transfer(source_date, target_date, employee_data, reason):
    """
    Executes bulk attendance transfer in an atomic transaction:
    - Creates Attendance Transfer audit doc
    - Updates target attendance to Present (Transferred)
    - Updates source attendance to Transferred (No double counting)
    - Copies/references punches
    """
    validate_super_admin()

    if not reason or not reason.strip():
        frappe.throw(_("Administrative Reason / Remarks is mandatory for Attendance Transfer."))

    if isinstance(employee_data, str):
        import json
        employee_data = json.loads(employee_data)

    if not employee_data:
        frappe.throw(_("No employees selected for transfer."))

    src_date = getdate(source_date)
    tgt_date = getdate(target_date)

    user_full_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

    # Create the parent Attendance Transfer document
    transfer_doc = frappe.new_doc("Attendance Transfer")
    transfer_doc.source_date = src_date
    transfer_doc.target_date = tgt_date
    transfer_doc.transferred_by = frappe.session.user
    transfer_doc.transferred_by_name = user_full_name
    transfer_doc.transfer_datetime = now_datetime()
    transfer_doc.reason = reason.strip()
    transfer_doc.status = "Submitted"
    transfer_doc.total_employees = len(employee_data)

    # Process each employee: Shift attendance date in-place (Single Record transfer)
    for item in employee_data:
        emp_id = item.get("employee")
        src_att_name = item.get("source_attendance")

        if not emp_id or not src_att_name:
            continue

        src_att = frappe.get_doc("Attendance", src_att_name)
        if src_att.is_transferred:
            frappe.throw(_(f"Employee {emp_id}'s attendance has already been transferred."))

        # 1. Target Attendance Record: Check existing record on target date
        existing_tgt_name = frappe.db.get_value("Attendance", {
            "employee": emp_id,
            "attendance_date": tgt_date
        }, "name")

        prev_status = "Not Marked"
        if existing_tgt_name:
            tgt_att = frappe.get_doc("Attendance", existing_tgt_name)
            prev_status = tgt_att.status
            if tgt_att.status == "Present" and not tgt_att.is_transferred:
                frappe.throw(_(f"Employee {emp_id} already worked and is marked Present on {tgt_date}."))

            # Cleanly remove the placeholder attendance (e.g. Absent) on target date
            # to allow shifting src_att to tgt_date without duplicate key conflict
            frappe.db.sql("DELETE FROM `tabAttendance Punch` WHERE parent = %s", (existing_tgt_name,))
            frappe.delete_doc("Attendance", existing_tgt_name, ignore_permissions=True, force=True)

        # 2. Shift the Source Attendance Record directly to Target Date
        # No duplicate document is created; the single record is moved in-place with all punches intact.
        src_att.attendance_date = tgt_date
        src_att.is_transferred = 1
        src_att.transfer_type = "Target (Adjusted Working)"
        src_att.transferred_from_date = src_date
        src_att.transferred_to_date = None
        src_att.save(ignore_permissions=True)

        # 3. Add to Attendance Transfer Item child table
        transfer_doc.append("items", {
            "employee": emp_id,
            "employee_name": item.get("employee_name") or src_att.employee_name,
            "department": item.get("department") or src_att.get("department") or "",
            "designation": item.get("designation") or "",
            "source_attendance": src_att.name,
            "source_in_time": src_att.in_time,
            "source_out_time": src_att.out_time,
            "source_working_hours": flt(src_att.working_hours_decimal or 0),
            "target_attendance": src_att.name,
            "previous_target_status": prev_status,
            "new_target_status": "Present"
        })

    transfer_doc.insert(ignore_permissions=True)

    # Now that transfer_doc.name is generated, link all transferred attendance records to it
    for it in transfer_doc.items:
        if it.source_attendance:
            frappe.db.set_value("Attendance", it.source_attendance, "attendance_transfer_ref", transfer_doc.name, update_modified=False)
        if it.target_attendance and it.target_attendance != it.source_attendance:
            frappe.db.set_value("Attendance", it.target_attendance, "attendance_transfer_ref", transfer_doc.name, update_modified=False)

    frappe.db.commit()

    return {
        "success": True,
        "transfer_id": transfer_doc.name,
        "total_transferred": len(transfer_doc.items),
        "message": _(f"Successfully transferred attendance for {len(transfer_doc.items)} employees from {src_date} to {tgt_date}.")
    }

@frappe.whitelist()
def get_attendance_transfer_history(page=1, page_size=20, pageSize=None, search=None, from_date=None, fromDate=None, to_date=None, toDate=None, status=None):
    """Returns paginated transfer history for Super Admin verification."""
    validate_super_admin()

    page = int(page or 1)
    page_size = int(pageSize or page_size or 20)
    from_date = from_date or fromDate
    to_date = to_date or toDate
    offset = (page - 1) * page_size

    conds = ["1=1"]
    params = []

    if search:
        conds.append("(name LIKE %s OR reason LIKE %s OR transferred_by_name LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if from_date:
        conds.append("source_date >= %s")
        params.append(getdate(from_date))

    if to_date:
        conds.append("source_date <= %s")
        params.append(getdate(to_date))

    if status:
        conds.append("status = %s")
        params.append(status)

    where_clause = " AND ".join(conds)

    total = frappe.db.sql(f"SELECT COUNT(*) FROM `tabAttendance Transfer` WHERE {where_clause}", params)[0][0]

    transfers = frappe.db.sql(f"""
        SELECT 
            name,
            source_date,
            target_date,
            total_employees,
            status,
            transferred_by,
            transferred_by_name,
            transfer_datetime,
            reason,
            reverted_by_name,
            revert_datetime,
            revert_reason
        FROM `tabAttendance Transfer`
        WHERE {where_clause}
        ORDER BY creation DESC
        LIMIT %s OFFSET %s
    """, params + [page_size, offset], as_dict=True)

    return {
        "data": transfers,
        "total": total,
        "page": page,
        "page_size": page_size
    }

@frappe.whitelist()
def get_attendance_transfer_details(transfer_id=None, attendance_id=None):
    """Returns details and all employee items for a specific Attendance Transfer batch."""
    if not is_user_super_admin():
        if not (frappe.has_permission("Attendance", "read") or frappe.has_permission("Attendance Transfer", "read")):
            validate_super_admin()

    if not transfer_id and attendance_id:
        transfer_id = frappe.db.get_value("Attendance", attendance_id, "attendance_transfer_ref")
        if not transfer_id:
            transfer_id = frappe.db.get_value(
                "Attendance Transfer Item",
                {"source_attendance": attendance_id},
                "parent"
            ) or frappe.db.get_value(
                "Attendance Transfer Item",
                {"target_attendance": attendance_id},
                "parent"
            )
            if transfer_id:
                frappe.db.set_value("Attendance", attendance_id, "attendance_transfer_ref", transfer_id, update_modified=False)
                frappe.db.commit()

    if not transfer_id:
        frappe.throw(_("Transfer ID or Attendance ID is required."))

    doc = frappe.get_doc("Attendance Transfer", transfer_id)
    doc_dict = doc.as_dict()

    return doc_dict

@frappe.whitelist()
def revert_attendance_transfer(transfer_id, revert_reason):
    """
    Rolls back an Attendance Transfer batch:
    - Restores target attendance to its previous status (e.g. Absent or removes record if Not Marked)
    - Clears transfer flags on source attendance
    - Marks transfer record as Reverted with audit trail
    """
    validate_super_admin()

    if not transfer_id:
        frappe.throw(_("Transfer ID is required."))

    if not revert_reason or not revert_reason.strip():
        frappe.throw(_("Reversal reason is mandatory."))

    transfer_doc = frappe.get_doc("Attendance Transfer", transfer_id)

    if transfer_doc.status == "Reverted":
        frappe.throw(_("This attendance transfer has already been reverted."))

    user_full_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

    for item in transfer_doc.items:
        # 1. Restore the worked Attendance record back to Source Date
        att_name = item.target_attendance or item.source_attendance
        if att_name and frappe.db.exists("Attendance", att_name):
            att = frappe.get_doc("Attendance", att_name)
            att.attendance_date = transfer_doc.source_date
            att.is_transferred = 0
            att.transfer_type = None
            att.transferred_from_date = None
            att.transferred_to_date = None
            att.attendance_transfer_ref = None
            att.save(ignore_permissions=True)

        # 2. Re-create previous target attendance (e.g. Absent) on target_date if it was marked
        if item.previous_target_status and item.previous_target_status not in ["Not Marked", "Missing"]:
            if not frappe.db.exists("Attendance", {"employee": item.employee, "attendance_date": transfer_doc.target_date}):
                restored_tgt = frappe.new_doc("Attendance")
                restored_tgt.employee = item.employee
                restored_tgt.employee_name = item.employee_name
                restored_tgt.attendance_date = transfer_doc.target_date
                restored_tgt.status = item.previous_target_status
                restored_tgt.insert(ignore_permissions=True)

    transfer_doc.status = "Reverted"
    transfer_doc.reverted_by = frappe.session.user
    transfer_doc.reverted_by_name = user_full_name
    transfer_doc.revert_datetime = now_datetime()
    transfer_doc.revert_reason = revert_reason.strip()
    transfer_doc.flags.ignore_links = True
    transfer_doc.save(ignore_permissions=True)

    frappe.db.commit()

    return {
        "success": True,
        "message": _(f"Transfer {transfer_id} has been reverted successfully.")
    }
