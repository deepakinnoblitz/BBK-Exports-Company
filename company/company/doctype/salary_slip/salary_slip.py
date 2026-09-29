import json
import frappe
from frappe import _
from datetime import datetime, timedelta
from frappe.utils import flt, get_first_day, get_last_day, getdate, formatdate
from frappe.model.document import Document
from calendar import monthrange

class SalarySlip(Document):
    def on_submit(self):
        """Triggered automatically when a Salary Slip is submitted (approved)."""
        self.send_email_notification()

    def send_email_notification(self):
        """Send salary slip PDF via email to the employee."""
        try:
            recipients = []
            if self.email:
                recipients.append(self.email)
            if self.personal_email:
                recipients.append(self.personal_email)

            if recipients:
                month_year = formatdate(self.pay_period_start, "MMMM YYYY")
                print_format = frappe.get_meta("Salary Slip").default_print_format or "Standard"
                pdf_content = frappe.get_print(
                    "Salary Slip",
                    self.name,
                    print_format=print_format,
                    as_pdf=True
                )

                message = f"""
                <div style="font-family: 'Montserrat', 'Segoe UI', Arial, sans-serif; background:#f4f6f8; padding:30px;">
                    <div style="max-width:600px; margin:auto; background:white; border-radius:12px;
                                box-shadow:0 2px 8px rgba(0,0,0,0.08); overflow:hidden;">
                        <div style="background:#007bff; color:white; padding:18px 24px; font-size:18px; font-weight:600; text-align:center;">
                            Your Salary Slip for {month_year}
                        </div>
                        <div style="padding:24px; color:#333; font-size:14px; line-height:1.6;">
                            <p>Dear <b>{self.employee_name}</b>,</p>
                            <p>Your salary slip for <b>{month_year}</b> has been Released. Please find the attached PDF below.</p>
                            <p style="margin-top:20px;">Best regards,<br>
                            <b style="color:#007bff;">HR Team</b></p>
                        </div>
                    </div>
                </div>
                """

                frappe.sendmail(
                    recipients=recipients,
                    subject=f"Salary Slip for {month_year}",
                    message=message,
                    attachments=[{
                        "fname": f"Salary_Slip_{self.employee}_{month_year.replace(' ', '_')}.pdf",
                        "fcontent": pdf_content
                    }],
                    reference_doctype="Salary Slip",
                    reference_name=self.name
                )

        except Exception as e:
            frappe.log_error(message=frappe.get_traceback(), title=f"Email Error for {self.employee_name}")


def parse_time_to_hours(val):
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        return flt(val)
    if isinstance(val, timedelta):
        return val.total_seconds() / 3600.0
    val_str = str(val).strip()
    if ":" in val_str:
        parts = val_str.split(":")
        try:
            return flt(parts[0]) + (flt(parts[1]) / 60.0)
        except Exception:
            return 0.0
    return flt(val_str)


def calculate_overtime_pay(emp, gross_salary, ot_hours, settings):
    ot_h = flt(ot_hours)
    if ot_h <= 0:
        return 0.0
    
    emp_type = (emp.get("employee_type") or "").lower()
    designation = (emp.get("designation") or "").lower()
    
    if "worker" in emp_type or "worker" in designation:
        multiplier = flt(getattr(settings, "workers_ot_rate_multiplier", 2.0)) or 2.0
        # Formula: (Gross Salary / 26 / 8) * OT Hours * multiplier
        hourly_rate = flt(gross_salary) / 26.0 / 8.0
        return round(hourly_rate * ot_h * multiplier, 2)
    elif "north indian" in emp_type or "north indian" in designation:
        rate = flt(getattr(settings, "north_indian_ot_rate", 100.0)) or 100.0
        # Formula: rate * OT Hours
        return round(rate * ot_h, 2)
    return 0.0


def calculate_attendance_bonus(emp, absent_days, settings):
    emp_type = (emp.get("employee_type") or "").lower()
    designation = (emp.get("designation") or "").lower()
    
    if ("worker" in emp_type or "worker" in designation) and flt(absent_days) <= 0.0:
        return flt(getattr(settings, "workers_attendance_bonus", 1500.0)) or 1500.0
    return 0.0


def calculate_professional_tax(gross_salary, pay_period_start, settings):
    gross = flt(gross_salary)
    slab_amount = 0.0

    # 1. Load dynamic slabs from settings if available
    configured_slabs = getattr(settings, "pt_slabs", None)
    slabs_list = []
    if configured_slabs:
        if isinstance(configured_slabs, str):
            try:
                slabs_list = json.loads(configured_slabs)
            except Exception:
                slabs_list = []
        elif isinstance(configured_slabs, list):
            slabs_list = configured_slabs

    if slabs_list and isinstance(slabs_list, list):
        for slab in slabs_list:
            if not isinstance(slab, dict):
                continue
            from_amt = flt(slab.get("from_amount", 0))
            to_amt_raw = slab.get("to_amount")
            to_amt = flt(to_amt_raw) if to_amt_raw is not None and str(to_amt_raw).strip() != "" and str(to_amt_raw).lower() != "null" else None
            tax_amt = flt(slab.get("tax_amount", 0))

            if to_amt is not None:
                if from_amt <= gross <= to_amt:
                    slab_amount = tax_amt
                    break
            else:
                if gross >= from_amt:
                    slab_amount = tax_amt
                    break

    frequency = getattr(settings, "pt_deduction_frequency", "Half-Yearly Deduction") or "Half-Yearly Deduction"
    if frequency == "Every Month Deduction":
        return slab_amount
    
    # Half-Yearly Deduction
    cycle_months_str = getattr(settings, "pt_half_yearly_months", "April, September") or "April, September"
    month_name = formatdate(pay_period_start, "MMMM")
    cycle_months = [m.strip().lower() for m in cycle_months_str.split(",")]
    
    if month_name.lower() in cycle_months:
        return slab_amount
    return 0.0


@frappe.whitelist()
def preview_salary_slip(employee, start_date, end_date):
    """
    Preview Salary Slip calculations for a specific employee and period.
    Returns a dictionary with calculated values without creating a document.
    """
    start_date = getdate(start_date)
    end_date = getdate(end_date)
    
    # 0. Fetch Settings
    settings = frappe.get_single("HRMS Settings")
    calc_source = settings.salary_calculation_source or "Attendance"
    working_days_basis = settings.salary_working_days_basis or "Actual Days in Month"
    fixed_working_days = flt(settings.salary_fixed_working_days) or 26.0
    holiday_handling = settings.salary_holiday_handling or "Include in Working Days"
    present_threshold = flt(settings.salary_slip_present_threshold) or 5.0
    half_day_threshold = flt(settings.salary_slip_half_day_threshold) or 3.0
    absent_threshold = flt(settings.salary_slip_absent_threshold) or 3.0

    # 1. Fetch Employee Details
    emp = frappe.get_doc("Employee", employee)
    
    # 2. Fetch Holidays
    year = start_date.year
    month = start_date.month
    
    holiday_list = frappe.get_all("Holiday List",
        filters={"year": year, "month_year": month},
        fields=["name"]
    )
    
    holiday_dates = []
    if holiday_list:
        holiday_doc = frappe.get_doc("Holiday List", holiday_list[0].name)
        for row in holiday_doc.holidays:
            if not row.is_working_day:
                h_date = getdate(row.holiday_date)
                if start_date <= h_date <= end_date:
                    holiday_dates.append(h_date)

    # 3. Fetch Data based on source
    attendance_records = []
    daily_sessions = []
    
    if calc_source == "Attendance":
        attendance_records = frappe.get_all(
            "Attendance",
            filters={
                "employee": emp.name,
                "attendance_date": ["between", [start_date, end_date]],
                "docstatus": ["in", [0, 1]]
            },
            fields=["status", "attendance_date", "official_overtime", "unofficial_overtime", "working_hours_decimal"]
        )
    else:
        daily_sessions = frappe.get_all(
            "Employee Session",
            filters={
                "employee": emp.name,
                "login_date": ["between", [start_date, end_date]]
            },
            fields=["login_date", "total_work_hours"]
        )
    
    # 3.1. Fetch Leave Applications
    leave_applications = frappe.get_all(
        "Leave Application",
        filters={
            "employee": emp.name,
            "workflow_state": "Approved",
            "from_date": ["<=", end_date],
            "to_date": [">=", start_date]
        },
        fields=["from_date", "to_date", "leave_type", "half_day"]
    )
    
    # Cache Leave Type "is_paid" status
    leave_types = frappe.get_all("Leave Type", fields=["name", "is_paid"])
    is_paid_map = {lt.name: flt(lt.is_paid) for lt in leave_types}

    # 4. Calculate Periods
    total_days = (end_date - start_date).days + 1
    
    # Calculate Full Month Working Days (The Denominator)
    m_start = get_first_day(start_date)
    m_end = get_last_day(start_date)
    total_month_days = (m_end - m_start).days + 1
    
    # Calculate Holidays in the full month for the Denominator
    month_holiday_list = frappe.get_all("Holiday List",
        filters={"year": m_start.year, "month_year": m_start.month},
        fields=["name"]
    )
    month_holiday_dates = []
    if month_holiday_list:
        mh_doc = frappe.get_doc("Holiday List", month_holiday_list[0].name)
        month_holiday_dates = [getdate(row.holiday_date) for row in mh_doc.holidays if not row.is_working_day and m_start <= getdate(row.holiday_date) <= m_end]

    if working_days_basis == "Fixed Number of Days":
        month_working_days = fixed_working_days
    else:
        month_working_days = total_month_days
        if holiday_handling == "Exclude from Working Days":
            month_working_days -= len(month_holiday_dates)

    present_days = 0
    absent_days = 0
    paid_leave_days = 0
    total_leave_days = 0
    half_day_count = 0
    physical_attendance_days = 0
    total_ot_hours = 0.0

    days_breakdown = []
    for i in range(total_days):
        single_day_date = start_date + timedelta(days=i)
        
        # --- DAY CALCULATION START ---
        is_holiday = single_day_date in holiday_dates
        day_leave = next((l for l in leave_applications if l.from_date <= single_day_date <= l.to_date), None)
        day_hours = 0
        day_attendance = None
        day_ot = 0.0
        leave_val = 0.0
        is_paid_leave = False
        
        if calc_source == "Daily Log":
            day_hours = sum(flt(s["total_work_hours"]) for s in daily_sessions if getdate(s["login_date"]) == single_day_date)
            if day_hours > 8.0:
                day_ot = day_hours - 8.0
        elif calc_source == "Attendance":
            day_attendance = next((a for a in attendance_records if getdate(a["attendance_date"]) == single_day_date), None)
            if day_attendance:
                day_hours = flt(day_attendance.get("working_hours_decimal") or 0)
                ot_raw = day_attendance.get("official_overtime") or day_attendance.get("unofficial_overtime")
                day_ot = parse_time_to_hours(ot_raw)

        total_ot_hours += day_ot

        # Determine Physical Recognition
        physical_val = 0
        if calc_source == "Daily Log":
            if day_hours >= present_threshold:
                physical_val = 1.0
            elif day_hours >= half_day_threshold:
                physical_val = 0.5
                half_day_count += 1
        elif calc_source == "Attendance" and day_attendance:
            if day_attendance["status"] == "Present":
                physical_val = 1.0
            elif day_attendance["status"] == "Half Day":
                physical_val = 0.5
                half_day_count += 1
            elif day_attendance["status"] == "Compensatory Off":
                leave_val = 1.0
                is_paid_leave = True
            
        # Determine Holiday Recognition
        holiday_val = 0
        if is_holiday and (physical_val + leave_val) < 1.0:
            if holiday_handling == "Include in Working Days":
                holiday_val = 1.0 - (physical_val + leave_val)

        # Determine Leave Recognition
        if day_leave and (physical_val + holiday_val + leave_val) < 1.0:
            leave_unit = 0.5 if flt(day_leave.half_day) else 1.0
            if leave_unit == 0.5:
                half_day_count += 1
            leave_val = min(leave_unit, 1.0 - (physical_val + holiday_val))
            is_paid_leave = bool(is_paid_map.get(day_leave.leave_type, 1))

        # Update Counters
        physical_attendance_days += physical_val
        
        # Diagnostic tracking
        components = []
        if physical_val > 0:
            components.append(f"Work ({physical_val})")
        if leave_val > 0:
            if day_attendance and day_attendance.get("status") == "Compensatory Off":
                components.append(f"Compensatory Off ({leave_val})")
            else:
                components.append(f"{'Paid' if is_paid_leave else 'Unpaid'} Leave ({leave_val})")
        if holiday_val > 0:
            components.append("Holiday" if holiday_val >= 1.0 else f"Holiday ({holiday_val})")
            
        absent_val = round(max(0.0, 1.0 - (physical_val + leave_val + holiday_val)), 2)
        if absent_val > 0:
            components.append(f"Absent ({absent_val})" if absent_val < 1.0 else "Absent")
            
        day_status = " + ".join(components) if components else "Absent"
        
        days_breakdown.append({
            "date": single_day_date.strftime("%Y-%m-%d"),
            "status": day_status,
            "hours": round(day_hours, 2),
            "ot_hours": round(day_ot, 2)
        })
        
        # Present Days = Work + Paid Leave + Holiday
        present_days += physical_val
        if is_paid_leave:
            present_days += leave_val
            paid_leave_days += leave_val
        else:
            absent_days += leave_val
            total_leave_days += leave_val
            
        present_days += holiday_val

        day_total = physical_val + leave_val + holiday_val
        if day_total < 1.0:
            gap = 1.0 - day_total
            absent_days += gap

    # 5. Calculate Earnings & Deductions
    unpaid_leave_days = total_leave_days - paid_leave_days
    
    is_full_month = (start_date == m_start and end_date == m_end)
    if is_full_month:
        period_factor = 1.0
    else:
        period_factor = min(1.0, total_days / month_working_days) if month_working_days else 1.0

    gross_pay = flt(emp.total_earnings)
    base_deductions = flt(emp.total_deductions)
    
    # Calculate individual components based on period factor
    prorated_earnings = []
    for e in emp.earnings:
        c_name = e.component_name or e.salary_component or ""
        # Skip legacy auto-calculated dynamic components from employee structure
        if c_name in ["Overtime Pay (OT)", "Overtime Allowance", "Attendance Bonus"]:
            continue
        item = e.as_dict()
        item["amount"] = flt(e.amount) * period_factor
        prorated_earnings.append(item)

    # 5.1. Overtime Pay Calculation
    ot_amount = calculate_overtime_pay(emp, gross_pay, total_ot_hours, settings)
    if ot_amount > 0:
        prorated_earnings.append({
            "component_name": "Overtime Pay (OT)",
            "salary_component": "Overtime Pay (OT)",
            "type": "Earning",
            "amount": ot_amount
        })

    # 5.2. Workers Attendance Bonus Calculation
    attendance_bonus = calculate_attendance_bonus(emp, absent_days, settings)
    if attendance_bonus > 0:
        prorated_earnings.append({
            "component_name": "Attendance Bonus",
            "salary_component": "Attendance Bonus",
            "type": "Earning",
            "amount": attendance_bonus
        })

    # 5.3. Deductions & Professional Tax
    pt_amount = calculate_professional_tax(gross_pay, start_date, settings)

    prorated_deductions = []
    for d in emp.deductions:
        c_name = d.component_name or d.salary_component or ""
        item = d.as_dict()
        if c_name in ["Prof.Tax", "Professional Tax", "PT"]:
            # Override PT amount according to slab and cycle
            item["amount"] = pt_amount
        else:
            item["amount"] = flt(d.amount) * period_factor
        prorated_deductions.append(item)

    # If Prof.Tax wasn't in employee structure but pt_amount > 0, add it
    has_pt = any((d.get("component_name") or d.get("salary_component")) in ["Prof.Tax", "Professional Tax", "PT"] for d in prorated_deductions)
    if not has_pt and pt_amount > 0:
        prorated_deductions.append({
            "component_name": "Prof.Tax",
            "salary_component": "Prof.Tax",
            "type": "Deduction",
            "amount": pt_amount
        })

    # LOP is applied for any absent/unpaid days within the period
    lop_amount = gross_pay * (absent_days / month_working_days) if month_working_days else 0
    
    grand_gross_pay = sum(flt(e["amount"]) for e in prorated_earnings)
    total_deductions = sum(flt(d["amount"]) for d in prorated_deductions) + lop_amount
    grand_net_pay = grand_gross_pay - total_deductions

    res = {
        "employee": emp.name,
        "employee_id": emp.employee_id,
        "employee_name": emp.employee_name,
        "father_husband_name": emp.father_husband_name,
        "employee_type": emp.employee_type,
        "phone_number": emp.phone,
        "designation": emp.designation,
        "department": emp.department,
        "date_of_joining": emp.date_of_joining,
        "email": emp.email,
        "personal_email": emp.personal_email,
        "pay_period_start": start_date,
        "pay_period_end": end_date,
        "no_of_leave": total_leave_days,
        "no_of_paid_leave": paid_leave_days,
        "gross_pay": grand_gross_pay,
        "grand_gross_pay": grand_gross_pay,
        "net_pay": grand_net_pay,
        "grand_net_pay": grand_net_pay,
        "total_deduction": total_deductions,
        "total_working_days": month_working_days,
        "lop": lop_amount,
        "lop_days": absent_days,
        "ot_hours": round(total_ot_hours, 2),
        "ot_amount": ot_amount,
        "attendance_bonus": attendance_bonus,
        "pt_amount": pt_amount,
        "earnings": prorated_earnings,
        "deductions": prorated_deductions,
        # Detailed Breakdown Fields
        "total_days_in_period": total_days,
        "holiday_count": len(holiday_dates),
        "actual_present_days": present_days,
        "physical_attendance_days": physical_attendance_days,
        "unpaid_leave_days": unpaid_leave_days,
        "half_day_count": half_day_count,
        "calc_source": calc_source,
        "holiday_handling": holiday_handling,
        "working_days_basis": working_days_basis,
        "fixed_working_days": fixed_working_days if working_days_basis == "Fixed Number of Days" else None,
        "days_breakdown": days_breakdown
    }

    res.update({
        "bank_account_name": "",
        "account_number": "",
        "bank_name": "",
        "branch": "",
        "ifsc_code": "",
    })

    if emp.bank_account:
        try:
            ba = frappe.get_doc("Bank Account", emp.bank_account)
            res.update({
                "bank_account_name": ba.bank_account_name or "",
                "account_number": ba.account_number or "",
                "bank_name": ba.bank_name or "",
                "branch": ba.branch or "",
                "ifsc_code": ba.ifsc_code or "",
            })
        except frappe.DoesNotExistError:
            pass

    return res


@frappe.whitelist()
def get_salary_slip_with_details(name):
    """
    Fetch Salary Slip document and enrich it with dynamic Employee details (like bank info)
    and a per-day days_breakdown identical to the one produced by preview_salary_slip.
    """
    doc = frappe.get_doc("Salary Slip", name)
    res = doc.as_dict()

    # Enrich with Employee Details (Bank Account, etc.)
    if doc.employee:
        emp = frappe.get_doc("Employee", doc.employee)

        res.update({
            "father_husband_name": emp.father_husband_name,
            "employee_type": emp.employee_type,
            "personal_email": emp.personal_email,
            "phone_number": emp.phone,
            "date_of_joining": emp.date_of_joining,
            "bank_account_name": "",
            "account_number": "",
            "bank_name": "",
            "branch": "",
            "ifsc_code": "",
        })

        if emp.bank_account:
            try:
                ba = frappe.get_doc("Bank Account", emp.bank_account)
                res.update({
                    "bank_account_name": ba.bank_account_name or "",
                    "account_number": ba.account_number or "",
                    "bank_name": ba.bank_name or "",
                    "branch": ba.branch or "",
                    "ifsc_code": ba.ifsc_code or "",
                })
            except frappe.DoesNotExistError:
                frappe.log_error(
                    frappe.get_traceback(),
                    "Salary Slip - Invalid Bank Account"
                )

    # ── Days Breakdown (mirrors preview_salary_slip) ──────────────────────────
    start_date = getdate(doc.pay_period_start)
    end_date   = getdate(doc.pay_period_end)

    settings          = frappe.get_single("HRMS Settings")
    calc_source       = getattr(doc, "calc_source", None) or settings.salary_calculation_source or "Attendance"
    holiday_handling  = getattr(doc, "holiday_handling", None) or settings.salary_holiday_handling or "Include in Working Days"
    working_days_basis = getattr(doc, "working_days_basis", None) or settings.salary_working_days_basis or "Actual Days in Month"
    fixed_working_days = getattr(doc, "fixed_working_days", None) or flt(settings.salary_fixed_working_days) or 26.0
    present_threshold = flt(settings.salary_slip_present_threshold) or 5.0
    half_day_threshold= flt(settings.salary_slip_half_day_threshold) or 3.0

    holiday_list = frappe.get_all(
        "Holiday List",
        filters={"year": start_date.year, "month_year": start_date.month},
        fields=["name"]
    )
    holiday_dates = []
    if holiday_list:
        h_doc = frappe.get_doc("Holiday List", holiday_list[0].name)
        for row in h_doc.holidays:
            if not row.is_working_day:
                h_date = getdate(row.holiday_date)
                if start_date <= h_date <= end_date:
                    holiday_dates.append(h_date)

    total_days = (end_date - start_date).days + 1
    attendance_records = []
    daily_sessions     = []

    if calc_source == "Attendance":
        attendance_records = frappe.get_all(
            "Attendance",
            filters={
                "employee": doc.employee,
                "attendance_date": ["between", [start_date, end_date]],
                "docstatus": ["in", [0, 1]]
            },
            fields=["status", "attendance_date", "official_overtime", "unofficial_overtime", "working_hours_decimal"]
        )
    else:
        daily_sessions = frappe.get_all(
            "Employee Session",
            filters={
                "employee": doc.employee,
                "login_date": ["between", [start_date, end_date]]
            },
            fields=["login_date", "total_work_hours"]
        )

    leave_applications = frappe.get_all(
        "Leave Application",
        filters={
            "employee": doc.employee,
            "workflow_state": "Approved",
            "from_date": ["<=", end_date],
            "to_date": [">=", start_date]
        },
        fields=["from_date", "to_date", "leave_type", "half_day"]
    )

    leave_types   = frappe.get_all("Leave Type", fields=["name", "is_paid"])
    is_paid_map   = {lt.name: flt(lt.is_paid) for lt in leave_types}

    days_breakdown = []
    for i in range(total_days):
        single_day_date = start_date + timedelta(days=i)

        is_holiday = single_day_date in holiday_dates
        day_leave  = next(
            (l for l in leave_applications if l.from_date <= single_day_date <= l.to_date),
            None
        )
        day_hours = 0
        day_ot = 0.0
        day_attendance = None

        if calc_source == "Daily Log":
            day_hours = sum(
                flt(s["total_work_hours"])
                for s in daily_sessions
                if getdate(s["login_date"]) == single_day_date
            )
            if day_hours > 8.0:
                day_ot = day_hours - 8.0
        elif calc_source == "Attendance":
            day_attendance = next((a for a in attendance_records if getdate(a["attendance_date"]) == single_day_date), None)
            if day_attendance:
                day_hours = flt(day_attendance.get("working_hours_decimal") or 0)
                ot_raw = day_attendance.get("official_overtime") or day_attendance.get("unofficial_overtime")
                day_ot = parse_time_to_hours(ot_raw)

        physical_val = 0
        if calc_source == "Daily Log":
            if day_hours >= present_threshold:
                physical_val = 1.0
            elif day_hours >= half_day_threshold:
                physical_val = 0.5
        elif calc_source == "Attendance" and day_attendance:
            if day_attendance["status"] == "Present":
                physical_val = 1.0
            elif day_attendance["status"] == "Half Day":
                physical_val = 0.5

        holiday_val = 0
        if is_holiday and physical_val < 1.0:
            if holiday_handling == "Include in Working Days":
                holiday_val = 1.0 - physical_val

        leave_val    = 0
        is_paid_leave = False
        if day_leave and (physical_val + holiday_val) < 1.0:
            leave_unit    = 0.5 if flt(day_leave.half_day) else 1.0
            leave_val     = min(leave_unit, 1.0 - (physical_val + holiday_val))
            is_paid_leave = bool(is_paid_map.get(day_leave.leave_type, 1))

        components = []
        if physical_val > 0:
            components.append(f"Work ({physical_val})")
        if leave_val > 0:
            components.append(f"{'Paid' if is_paid_leave else 'Unpaid'} Leave ({leave_val})")
        if holiday_val > 0:
            components.append("Holiday" if holiday_val >= 1.0 else f"Holiday ({holiday_val})")
            
        absent_val = round(max(0.0, 1.0 - (physical_val + leave_val + holiday_val)), 2)
        if absent_val > 0:
            components.append(f"Absent ({absent_val})" if absent_val < 1.0 else "Absent")
            
        day_status = " + ".join(components) if components else "Absent"

        days_breakdown.append({
            "date":   single_day_date.strftime("%Y-%m-%d"),
            "status": day_status,
            "hours":  round(day_hours, 2),
            "ot_hours": round(day_ot, 2)
        })

    res["days_breakdown"] = days_breakdown
    return res


# =================== SALARY SLIP GENERATION ===================

@frappe.whitelist()
def generate_salary_slips_from_employee(year=None, month=None, employees=None, start_date=None, end_date=None):
    import json

    if not year or not month:
        frappe.throw(_("Please provide year and month"))

    year = int(year)
    month = int(month)

    if start_date and end_date:
        start_date = getdate(start_date)
        end_date = getdate(end_date)
    else:
        start_date = getdate(f"{year}-{month}-01")
        end_date = getdate(f"{year}-{month}-{monthrange(year, month)[1]}")

    if isinstance(employees, str):
        employees = json.loads(employees)

    if not employees:
        frappe.throw(_("Please provide employees list"))

    created_count = 0
    skipped_count = 0
    errors = []

    for emp_id in employees:
        try:
            data = preview_salary_slip(emp_id, start_date, end_date)

            if frappe.db.exists("Salary Slip", {
                "employee": emp_id,
                "pay_period_start": start_date,
                "pay_period_end": end_date
            }):
                skipped_count += 1
                continue

            slip = frappe.get_doc({
                "doctype": "Salary Slip",
                "employee": data["employee"],
                "employee_name": data["employee_name"],
                "father_husband_name": data.get("father_husband_name"),
                "employee_type": data.get("employee_type"),
                "email": data.get("email"),
                "bank_account": data.get("account_number"),
                "personal_email": data.get("personal_email"),
                "pay_period_start": start_date,
                "pay_period_end": end_date,
                "no_of_leave": data["no_of_leave"],
                "no_of_paid_leave": data["no_of_paid_leave"],
                "total_days_in_period": data["total_days_in_period"],
                "holiday_count": data["holiday_count"],
                "actual_present_days": data["actual_present_days"],
                "physical_attendance_days": data["physical_attendance_days"],
                "unpaid_leave_days": data["unpaid_leave_days"],
                "half_day_count": data["half_day_count"],
                "calc_source": data["calc_source"],
                "holiday_handling": data["holiday_handling"],
                "working_days_basis": data.get("working_days_basis"),
                "fixed_working_days": data.get("fixed_working_days"),
                "ot_hours": data.get("ot_hours", 0.0),
                "ot_amount": data.get("ot_amount", 0.0),
                "attendance_bonus": data.get("attendance_bonus", 0.0),
                "pt_amount": data.get("pt_amount", 0.0),
                "gross_pay": data["gross_pay"],
                "grand_gross_pay": data["grand_gross_pay"],
                "net_pay": data["net_pay"],
                "grand_net_pay": data["grand_net_pay"],
                "total_deduction": data["total_deduction"],
                "total_working_days": data["total_working_days"],
                "lop": data["lop"],
                "lop_days": data["lop_days"],
                "status": "Draft"
            })

            for e in data.get("earnings", []):
                slip.append("earnings", e)

            for d in data.get("deductions", []):
                slip.append("deductions", d)

            slip.insert(ignore_permissions=True)
            created_count += 1

        except Exception as e:
            errors.append(f"{emp_id}: {str(e)}")

    result_msg = f"Salary Slips Created: {created_count}, Skipped: {skipped_count}"
    if errors:
        result_msg += "\n Errors:\n" + "\n".join(errors)

    return result_msg


@frappe.whitelist()
def submit_salary_slip(name):
    doc = frappe.get_doc("Salary Slip", name)
    if doc.docstatus != 0:
        frappe.throw(_("Draft salary slip not found with ID: {0}").format(name))
    doc.submit()
    return doc.as_dict()