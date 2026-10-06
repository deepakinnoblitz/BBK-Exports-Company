import json
import math
import frappe
from frappe import _
from datetime import datetime, timedelta
from frappe.utils import cint, flt, get_first_day, get_last_day, getdate, formatdate
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
                emp_type = (self.employee_type or "").lower()
                if "north indian" in emp_type:
                    print_format = "North Indian Form 25B Pay Slip"
                elif "worker" in emp_type:
                    print_format = "Worker Form 25B Pay Slip"
                else:
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
    ot_h = round(flt(ot_hours), 2)
    if ot_h <= 0:
        return 0.0
    
    emp_type = (emp.get("employee_type") or "").lower()

    if "staff" in emp_type:
        return 0.0
    
    if "worker" in emp_type:
        multiplier = flt(getattr(settings, "workers_ot_rate_multiplier", 2.0)) or 2.0
        # Formula: (Gross Salary / 26 / 8) * OT Hours * multiplier
        hourly_rate = flt(gross_salary) / 26.0 / 8.0
        return round(hourly_rate * ot_h * multiplier, 2)
    elif "north indian" in emp_type:
        rate = flt(getattr(settings, "north_indian_ot_rate", 100.0)) or 100.0
        # Formula: rate * OT Hours
        return round(rate * ot_h, 2)
    return 0.0


def calculate_attendance_bonus(emp, absent_days, settings):
    emp_type = (emp.get("employee_type") or "").lower()
    
    if "worker" in emp_type and flt(absent_days) <= 0.0:
        return flt(getattr(settings, "workers_attendance_bonus", 1500.0)) or 1500.0
    return 0.0


def calculate_employee_pf(emp, earned_gross_salary, earned_basic_da, settings, prorated_earnings=None):
    """
    Calculate Employee PF deduction based on HRMS Settings and Excel formula:
    =ROUND(+IF(AND(AF6>15000),1800,IF(AND(AF6<15000),AF6*12%)),0)
    
    Supports dynamic selected salary components for wage basis.
    """
    enable_pf = cint(getattr(settings, "enable_auto_pf", 1) if getattr(settings, "enable_auto_pf", None) is not None else 1)
    if not enable_pf:
        return None

    pf_no = emp.get("pf_number") if hasattr(emp, "get") else getattr(emp, "pf_number", None)
    has_pf_component = False
    if hasattr(emp, "deductions"):
        for d in emp.deductions:
            c_name = (d.component_name or d.salary_component or "").lower() if hasattr(d, "component_name") else (d.get("component_name") or d.get("salary_component") or "").lower()
            if any(k in c_name for k in ["pf", "provident fund", "epf"]) and "employer" not in c_name and "admin" not in c_name:
                has_pf_component = True
                break

    # If employee has no PF number and PF is not in their deduction structure, return 0
    if not pf_no and not has_pf_component:
        return 0.0

    pf_rate = flt(getattr(settings, "employee_pf_rate", 12.0) if getattr(settings, "employee_pf_rate", None) is not None else 12.0) / 100.0
    pf_ceiling = flt(getattr(settings, "pf_wage_ceiling", 15000.0) if getattr(settings, "pf_wage_ceiling", None) is not None else 15000.0)
    pf_basis_raw = getattr(settings, "pf_wage_basis", None)

    # Dynamic selected components parsing
    selected_components = []
    if pf_basis_raw:
        if isinstance(pf_basis_raw, list):
            selected_components = [str(x).strip().lower() for x in pf_basis_raw if str(x).strip()]
        elif isinstance(pf_basis_raw, str):
            try:
                parsed = json.loads(pf_basis_raw)
                if isinstance(parsed, list):
                    selected_components = [str(x).strip().lower() for x in parsed if str(x).strip()]
            except Exception:
                if pf_basis_raw.strip() == "Earned Basic + DA":
                    selected_components = ["basic pay", "da", "basic", "dearness"]
                elif "," in pf_basis_raw:
                    selected_components = [x.strip().lower() for x in pf_basis_raw.split(",") if x.strip()]

    if selected_components and prorated_earnings:
        matching_total = sum(
            flt(e.get("amount") if isinstance(e, dict) else getattr(e, "amount", 0.0))
            for e in prorated_earnings
            if (
                ((e.get("component_name") or e.get("salary_component") or "") if isinstance(e, dict)
                 else (getattr(e, "component_name", None) or getattr(e, "salary_component", None) or "")).lower().strip() in selected_components
                or any(
                    sc in ((e.get("component_name") or e.get("salary_component") or "").lower() if isinstance(e, dict)
                           else (getattr(e, "component_name", None) or getattr(e, "salary_component", None) or "").lower())
                    for sc in selected_components
                )
            )
        )
        base_wage = matching_total
    elif selected_components and not prorated_earnings and (selected_components == ["basic pay", "da", "basic", "dearness"] or "basic" in selected_components and "other allowance" not in selected_components):
        base_wage = flt(earned_basic_da)
    elif pf_basis_raw == "Earned Basic + DA":
        base_wage = flt(earned_basic_da)
    else:
        base_wage = flt(earned_gross_salary)

    eligible_wage = min(base_wage, pf_ceiling) if pf_ceiling > 0 else base_wage
    return round(eligible_wage * pf_rate)


def calculate_employee_esi(emp, grand_gross_pay, earned_gross_salary, settings):
    """
    Calculate Employee ESI deduction based on HRMS Settings and Excel formula:
    =ROUNDUP(AK6 * $AM$5, 0) -> Total Gross Earnings (AK6) * 0.75%
    
    Returns rounded deduction amount or None if auto calculation is disabled.
    """
    enable_esi = cint(getattr(settings, "enable_auto_esi", 1) if getattr(settings, "enable_auto_esi", None) is not None else 1)
    if not enable_esi:
        return None

    esi_no = emp.get("esi_no") if hasattr(emp, "get") else getattr(emp, "esi_no", None)
    has_esi_component = False
    if hasattr(emp, "deductions"):
        for d in emp.deductions:
            c_name = (d.component_name or d.salary_component or "").lower() if hasattr(d, "component_name") else (d.get("component_name") or d.get("salary_component") or "").lower()
            if any(k in c_name for k in ["esi", "esic"]) and "employer" not in c_name:
                has_esi_component = True
                break

    # If employee has no ESI number and ESI is not in their deduction structure, return 0
    if not esi_no and not has_esi_component:
        return 0.0

    esi_ceiling = flt(getattr(settings, "esi_wage_ceiling", 21000.0) if getattr(settings, "esi_wage_ceiling", None) is not None else 21000.0)
    
    # Statutory gross wage eligibility check (Gross <= ₹21,000)
    std_earnings = flt(emp.get("total_earnings") or 0.0) if hasattr(emp, "get") else flt(getattr(emp, "total_earnings", 0.0))
    if esi_ceiling > 0 and earned_gross_salary > esi_ceiling and std_earnings > esi_ceiling:
        return 0.0

    esi_rate = flt(getattr(settings, "employee_esi_rate", 0.75) if getattr(settings, "employee_esi_rate", None) is not None else 0.75) / 100.0
    rounding_method = getattr(settings, "esi_rounding_method", "Round Up to Next Rupee (ROUNDUP / CEIL)") or "Round Up to Next Rupee (ROUNDUP / CEIL)"

    raw_esi = flt(grand_gross_pay) * esi_rate
    if "Round Up" in rounding_method or "ROUNDUP" in rounding_method or "CEIL" in rounding_method:
        return float(math.ceil(raw_esi))
    else:
        return float(round(raw_esi))


def calculate_professional_tax(gross_salary, pay_period_start, settings, employee=None, emp_doc=None, current_slip_name=None):
    pay_period_start = getdate(pay_period_start)
    gross = flt(gross_salary)

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

    def get_slab_tax(eval_gross):
        slab_amount = 0.0
        if slabs_list and isinstance(slabs_list, list):
            for slab in slabs_list:
                if not isinstance(slab, dict):
                    continue
                from_amt = flt(slab.get("from_amount", 0))
                to_amt_raw = slab.get("to_amount")
                to_amt = flt(to_amt_raw) if to_amt_raw is not None and str(to_amt_raw).strip() != "" and str(to_amt_raw).lower() != "null" else None
                tax_amt = flt(slab.get("tax_amount", 0))

                if to_amt is not None:
                    if from_amt <= eval_gross <= to_amt:
                        slab_amount = tax_amt
                        break
                else:
                    if eval_gross >= from_amt:
                        slab_amount = tax_amt
                        break
        return slab_amount

    frequency = getattr(settings, "pt_deduction_frequency", "Half-Yearly Deduction") or "Half-Yearly Deduction"
    if frequency == "Every Month Deduction":
        return get_slab_tax(gross)

    # 2. Cumulative Progressive Half-Yearly Deduction
    # Determine 6-Month Cycle Date Range
    cur_year = pay_period_start.year
    cur_month = pay_period_start.month

    if cur_month in [4, 5, 6, 7, 8, 9]:
        cycle_start = getdate(f"{cur_year}-04-01")
        cycle_end = getdate(f"{cur_year}-09-30")
    elif cur_month in [10, 11, 12]:
        cycle_start = getdate(f"{cur_year}-10-01")
        cycle_end = getdate(f"{cur_year + 1}-03-31")
    else:  # [1, 2, 3]
        cycle_start = getdate(f"{cur_year - 1}-10-01")
        cycle_end = getdate(f"{cur_year}-03-31")

    # Check Employee Date of Joining (DOJ) & Date of Leaving (DOL)
    doj = None
    dol = None
    std_monthly_earnings = 0.0

    emp_id = employee or (emp_doc.get("name") if hasattr(emp_doc, "get") else getattr(emp_doc, "name", None))

    if emp_doc:
        doj = getdate(emp_doc.get("date_of_joining")) if emp_doc.get("date_of_joining") else None
        dol = getdate(emp_doc.get("relieving_date") or emp_doc.get("date_of_leaving")) if (emp_doc.get("relieving_date") or emp_doc.get("date_of_leaving")) else None
        std_monthly_earnings = flt(emp_doc.get("total_earnings") or 0.0)
    elif emp_id:
        emp_data = frappe.db.get_value("Employee", emp_id, ["date_of_joining", "relieving_date", "date_of_leaving", "total_earnings"], as_dict=True)
        if emp_data:
            doj = getdate(emp_data.get("date_of_joining")) if emp_data.get("date_of_joining") else None
            dol = getdate(emp_data.get("relieving_date") or emp_data.get("date_of_leaving")) if (emp_data.get("relieving_date") or emp_data.get("date_of_leaving")) else None
            std_monthly_earnings = flt(emp_data.get("total_earnings") or 0.0)

    # If employee has not joined yet or already left prior to this pay period
    if doj and doj > get_last_day(pay_period_start):
        return 0.0
    if dol and dol < pay_period_start:
        return 0.0

    effective_cycle_start = cycle_start
    if doj and doj > cycle_start:
        effective_cycle_start = getdate(f"{doj.year}-{doj.month:02d}-01")

    # Fetch prior salary slips in this cycle for this employee strictly before this pay period
    past_gross = 0.0
    past_pt = 0.0
    recorded_past_months = set()

    if emp_id:
        past_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": emp_id,
                "docstatus": ["<", 2],
                "pay_period_start": [">=", effective_cycle_start],
                "pay_period_end": ["<", pay_period_start],
            },
            fields=["name", "gross_pay", "grand_gross_pay", "pt_amount", "pay_period_start"]
        )

        for ps in past_slips:
            if current_slip_name and ps.name == current_slip_name:
                continue
            ps_start = getdate(ps.pay_period_start)
            if ps_start >= pay_period_start:
                continue
            past_gross += flt(ps.grand_gross_pay or ps.gross_pay)
            past_pt += flt(ps.pt_amount)
            recorded_past_months.add((ps_start.year, ps_start.month))

        # Check for un-generated past active months within this cycle
        iter_dt = effective_cycle_start
        while (iter_dt.year, iter_dt.month) < (pay_period_start.year, pay_period_start.month):
            m_key = (iter_dt.year, iter_dt.month)
            if m_key not in recorded_past_months:
                # Use standard monthly earnings as estimate for missing past month
                past_gross += std_monthly_earnings
            # Advance to next month
            if iter_dt.month == 12:
                iter_dt = iter_dt.replace(year=iter_dt.year + 1, month=1, day=1)
            else:
                iter_dt = iter_dt.replace(month=iter_dt.month + 1, day=1)

    # Cumulative gross in this cycle including current month
    cumulative_gross = round(past_gross + gross, 2)

    # Target cumulative PT up to this month according to slab tiers
    target_cumulative_pt = get_slab_tax(cumulative_gross)

    # Net PT payable in this month after subtracting past PT already deducted
    current_month_pt = max(0.0, round(target_cumulative_pt - past_pt, 2))
    return current_month_pt


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
    leave_calc_source = getattr(settings, "salary_leave_calculation_source", None) or "Via Leave Application"
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
    holiday_desc_map = {}
    holidays_details = []
    if holiday_list:
        holiday_doc = frappe.get_doc("Holiday List", holiday_list[0].name)
        for row in holiday_doc.holidays:
            if not row.is_working_day:
                h_date = getdate(row.holiday_date)
                if start_date <= h_date <= end_date:
                    holiday_dates.append(h_date)
                    holiday_desc_map[h_date] = row.description or "Holiday"
                    holidays_details.append({
                        "date": h_date.strftime("%Y-%m-%d"),
                        "description": row.description or "Holiday",
                        "status": "Holiday"
                    })

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

    # Fetch Direct Leave Allocations if configured
    direct_paid_allocated = 0.0
    direct_unpaid_allocated = 0.0
    if leave_calc_source == "Via Direct Allocation":
        leave_allocations = frappe.get_all(
            "Leave Allocation",
            filters={
                "employee": emp.name,
                "docstatus": ["<", 2],
                "from_date": ["<=", end_date],
                "to_date": [">=", start_date]
            },
            fields=["name", "leave_type", "total_leaves_allocated", "total_leaves_taken"]
        )
        for alloc in leave_allocations:
            taken = flt(alloc.get("total_leaves_taken") or 0)
            if taken > 0:
                if is_paid_map.get(alloc.leave_type, 1):
                    direct_paid_allocated += taken
                else:
                    direct_unpaid_allocated += taken

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
    total_absent_days = 0
    paid_leave_days = 0
    comp_off_days = 0
    total_leave_days = 0
    unpaid_leave_days = 0
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
        comp_off_val = 0.0
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
                comp_off_val = 1.0
            
        # Determine Holiday Recognition
        holiday_val = 0
        if is_holiday and (physical_val + comp_off_val + leave_val) < 1.0:
            if holiday_handling == "Include in Working Days":
                holiday_val = 1.0 - (physical_val + comp_off_val + leave_val)

        # Determine Leave Recognition
        if leave_calc_source != "Via Direct Allocation":
            if day_leave and (physical_val + comp_off_val + holiday_val + leave_val) < 1.0:
                leave_unit = 0.5 if flt(day_leave.half_day) else 1.0
                if leave_unit == 0.5:
                    half_day_count += 1
                leave_val = min(leave_unit, 1.0 - (physical_val + comp_off_val + holiday_val))
                is_paid_leave = bool(is_paid_map.get(day_leave.leave_type, 1))

        # Update Counters
        physical_attendance_days += physical_val
        comp_off_days += comp_off_val
        
        # Diagnostic tracking
        components = []
        if physical_val > 0:
            components.append(f"Work ({physical_val})")
        if comp_off_val > 0:
            components.append(f"Compensatory Off ({comp_off_val})")
        if leave_val > 0:
            components.append(f"{'Paid' if is_paid_leave else 'Unpaid'} Leave ({leave_val})")
        if holiday_val > 0:
            components.append("Holiday" if holiday_val >= 1.0 else f"Holiday ({holiday_val})")
            
        absent_val = round(max(0.0, 1.0 - (physical_val + comp_off_val + leave_val + holiday_val)), 2)
        if absent_val > 0:
            if leave_calc_source != "Via Direct Allocation":
                components.append(f"Unpaid Leave ({absent_val})" if absent_val < 1.0 else "Unpaid Leave")
                unpaid_leave_days += absent_val
                total_leave_days += absent_val
            else:
                components.append(f"Absent ({absent_val})" if absent_val < 1.0 else "Absent")
            total_absent_days += absent_val
            
        day_status = " + ".join(components) if components else "Absent"
        
        days_breakdown.append({
            "date": single_day_date.strftime("%Y-%m-%d"),
            "status": day_status,
            "is_holiday": is_holiday,
            "holiday_desc": holiday_desc_map.get(single_day_date, ""),
            "hours": round(day_hours, 2),
            "ot_hours": round(day_ot, 2)
        })
        
        # Present Days = Work + Comp Off + Paid Leave (Holidays are tracked separately)
        present_days += physical_val + comp_off_val
        if is_paid_leave:
            present_days += leave_val
            paid_leave_days += leave_val
            total_leave_days += leave_val
        elif leave_val > 0:
            unpaid_leave_days += leave_val
            total_leave_days += leave_val

    # 5. Calculate Earnings & Deductions
    if leave_calc_source == "Via Direct Allocation":
        direct_credit = min(total_absent_days, direct_paid_allocated)
        paid_leave_days += direct_credit
        total_leave_days = paid_leave_days + direct_unpaid_allocated
        unpaid_leave_days = direct_unpaid_allocated
        present_days += direct_credit
        lop_days = max(0.0, total_absent_days - direct_credit)
    else:
        lop_days = unpaid_leave_days
    
    is_full_month = (start_date == m_start and end_date == m_end)
    if is_full_month:
        payable_days = max(0.0, month_working_days - lop_days) if month_working_days else 0.0
        period_factor = (payable_days / month_working_days) if month_working_days else 1.0
    else:
        payable_days = max(0.0, present_days)
        period_factor = (payable_days / month_working_days) if month_working_days else 1.0

    gross_pay = flt(emp.total_earnings)
    base_deductions = flt(emp.total_deductions)
    
    # Calculate individual components based on period factor (prorated for payable/present days)
    prorated_earnings = []
    base_gross_total = 0.0
    for e in emp.earnings:
        c_name = e.component_name or e.salary_component or ""
        # Skip legacy auto-calculated dynamic components from employee structure
        if c_name in ["Overtime Pay (OT)", "Overtime Allowance", "Attendance Bonus"]:
            continue
        item = e.as_dict()
        item["standard_amount"] = flt(e.amount)
        item["amount"] = round(flt(e.amount) * period_factor, 2)
        base_gross_total += flt(e.amount)
        prorated_earnings.append(item)

    # 5.1. Overtime Pay Calculation
    emp_type = (emp.get("employee_type") or "").lower()
    is_staff = "staff" in emp_type
    total_ot_hours = round(total_ot_hours, 2)

    if is_staff:
        ot_amount = 0.0
    else:
        ot_amount = calculate_overtime_pay(emp, gross_pay, total_ot_hours, settings)

    if ot_amount > 0:
        prorated_earnings.append({
            "component_name": "Overtime Pay (OT)",
            "salary_component": "Overtime Pay (OT)",
            "type": "Earning",
            "standard_amount": 0.0,
            "amount": ot_amount
        })

    # 5.2. Workers Attendance Bonus Calculation
    attendance_bonus = calculate_attendance_bonus(emp, lop_days, settings)
    if attendance_bonus > 0:
        prorated_earnings.append({
            "component_name": "Attendance Bonus",
            "salary_component": "Attendance Bonus",
            "type": "Earning",
            "standard_amount": 0.0,
            "amount": attendance_bonus
        })

    # 5.3. Workers Tea Allowance Calculation (Days Worked x Rate/Day)
    tea_allowance = 0.0
    tea_rate = flt(getattr(settings, "workers_tea_allowance_per_day", 5.0) if getattr(settings, "workers_tea_allowance_per_day", None) is not None else 5.0)
    if "worker" in emp_type:
        tea_allowance = round(flt(present_days) * tea_rate, 2)
        has_tea = any("tea" in (e.get("component_name") or e.get("salary_component") or "").lower() for e in prorated_earnings)
        if not has_tea and tea_allowance > 0:
            prorated_earnings.append({
                "component_name": "Tea Allowance",
                "salary_component": "Tea Allowance",
                "type": "Earning",
                "standard_amount": 0.0,
                "amount": tea_allowance
            })

    # 5.4. Calculate Earned Gross Pay (AF6: Earned Gross before dynamic OT/Bonus/Tea) & Grand Gross Pay (AK6)
    earned_gross_salary = round(sum(
        flt(e["amount"]) for e in prorated_earnings
        if (e.get("component_name") or e.get("salary_component") or "") not in ["Overtime Pay (OT)", "Overtime Allowance", "Attendance Bonus", "Tea Allowance"]
    ), 2)
    grand_gross_pay = round(sum(flt(e["amount"]) for e in prorated_earnings), 2)

    earned_basic_da = sum(
        flt(e.get("amount", 0)) for e in prorated_earnings 
        if any(k in (e.get("component_name") or e.get("salary_component") or "").lower() for k in ["basic", "da", "dearness"])
    )
    if earned_basic_da <= 0:
        earned_basic_da = earned_gross_salary

    # 5.5. Deductions & Professional Tax, PF, ESI
    pt_amount = calculate_professional_tax(grand_gross_pay, start_date, settings, employee=emp.name, emp_doc=emp)
    emp_pf = calculate_employee_pf(emp, earned_gross_salary, earned_basic_da, settings, prorated_earnings=prorated_earnings)
    emp_esi = calculate_employee_esi(emp, grand_gross_pay, earned_gross_salary, settings)

    prorated_deductions = []
    base_deductions_total = 0.0
    for d in emp.deductions:
        c_name = d.component_name or d.salary_component or ""
        item = d.as_dict()
        item["standard_amount"] = flt(d.amount)
        base_deductions_total += flt(d.amount)
        c_lower = c_name.lower()
        if c_name in ["Prof.Tax", "Professional Tax", "PT"]:
            # Override PT amount according to slab and cycle
            item["amount"] = pt_amount
        elif any(k in c_lower for k in ["pf", "provident fund", "epf"]) and "employer" not in c_lower and "admin" not in c_lower:
            if emp_pf is not None:
                item["amount"] = emp_pf
            else:
                item["amount"] = flt(d.amount)
        elif any(k in c_lower for k in ["esi", "esic"]) and "employer" not in c_lower:
            if emp_esi is not None:
                item["amount"] = emp_esi
            else:
                item["amount"] = flt(d.amount)
        else:
            item["amount"] = flt(d.amount)
        prorated_deductions.append(item)

    # If Prof.Tax wasn't in employee structure but pt_amount > 0, add it
    has_pt = any((d.get("component_name") or d.get("salary_component")) in ["Prof.Tax", "Professional Tax", "PT"] for d in prorated_deductions)
    if not has_pt and pt_amount > 0:
        prorated_deductions.append({
            "component_name": "Prof.Tax",
            "salary_component": "Prof.Tax",
            "type": "Deduction",
            "standard_amount": 0.0,
            "amount": pt_amount
        })

    # If PF wasn't in employee structure but emp_pf > 0, add it
    has_pf = any(any(k in (d.get("component_name") or d.get("salary_component") or "").lower() for k in ["pf", "provident fund", "epf"]) and "employer" not in (d.get("component_name") or d.get("salary_component") or "").lower() for d in prorated_deductions)
    if not has_pf and emp_pf is not None and emp_pf > 0:
        prorated_deductions.append({
            "component_name": "PF",
            "salary_component": "PF",
            "type": "Deduction",
            "standard_amount": 0.0,
            "amount": emp_pf
        })

    # If ESI wasn't in employee structure but emp_esi > 0, add it
    has_esi = any(any(k in (d.get("component_name") or d.get("salary_component") or "").lower() for k in ["esi", "esic"]) and "employer" not in (d.get("component_name") or d.get("salary_component") or "").lower() for d in prorated_deductions)
    if not has_esi and emp_esi is not None and emp_esi > 0:
        prorated_deductions.append({
            "component_name": "ESI",
            "salary_component": "ESI",
            "type": "Deduction",
            "standard_amount": 0.0,
            "amount": emp_esi
        })

    # LOP amount for informational and display breakdown purposes
    lop_amount = round(gross_pay * (lop_days / month_working_days), 2) if month_working_days else 0.0
    
    total_deductions = round(sum(flt(d["amount"]) for d in prorated_deductions), 2)
    grand_net_pay = round(grand_gross_pay - total_deductions, 2)

    # 5.6. Employer Statutory Contributions & Total Monthly Cost to Company (CTC)
    pf_rate = flt(getattr(settings, "employer_pf_rate", None) if getattr(settings, "employer_pf_rate", None) is not None else 12.0) / 100.0
    pf_admin_rate = flt(getattr(settings, "pf_admin_rate", None) if getattr(settings, "pf_admin_rate", None) is not None else 0.5) / 100.0
    edli_rate = flt(getattr(settings, "edli_rate", None) if getattr(settings, "edli_rate", None) is not None else 0.5) / 100.0
    esi_rate = flt(getattr(settings, "employer_esi_rate", None) if getattr(settings, "employer_esi_rate", None) is not None else 3.25) / 100.0
    pf_ceiling = flt(getattr(settings, "pf_wage_ceiling", 15000.0) if getattr(settings, "pf_wage_ceiling", None) is not None else 15000.0)
    esi_ceiling = flt(getattr(settings, "esi_wage_ceiling", 21000.0) if getattr(settings, "esi_wage_ceiling", None) is not None else 21000.0)
    
    # Dynamic PF base for Employer
    pf_basis_raw = getattr(settings, "pf_wage_basis", None)
    selected_pf_components = []
    if pf_basis_raw:
        if isinstance(pf_basis_raw, list):
            selected_pf_components = [str(x).strip().lower() for x in pf_basis_raw if str(x).strip()]
        elif isinstance(pf_basis_raw, str):
            try:
                parsed = json.loads(pf_basis_raw)
                if isinstance(parsed, list):
                    selected_pf_components = [str(x).strip().lower() for x in parsed if str(x).strip()]
            except Exception:
                if pf_basis_raw.strip() == "Earned Basic + DA":
                    selected_pf_components = ["basic pay", "da", "basic", "dearness"]

    if selected_pf_components and prorated_earnings:
        pf_base_for_employer = sum(
            flt(e.get("amount") if isinstance(e, dict) else getattr(e, "amount", 0.0))
            for e in prorated_earnings
            if (
                ((e.get("component_name") or e.get("salary_component") or "") if isinstance(e, dict)
                 else (getattr(e, "component_name", None) or getattr(e, "salary_component", None) or "")).lower().strip() in selected_pf_components
                or any(
                    sc in ((e.get("component_name") or e.get("salary_component") or "").lower() if isinstance(e, dict)
                           else (getattr(e, "component_name", None) or getattr(e, "salary_component", None) or "").lower())
                    for sc in selected_pf_components
                )
            )
        )
    elif pf_basis_raw == "Earned Basic + DA":
        pf_base_for_employer = earned_basic_da
    else:
        pf_base_for_employer = earned_gross_salary

    enable_bonus = cint(getattr(settings, "enable_bonus_provision", 1) if getattr(settings, "enable_bonus_provision", None) is not None else 1)
    bonus_rate = (flt(getattr(settings, "bonus_provision_rate", 8.33) if getattr(settings, "bonus_provision_rate", None) is not None else 8.33) / 100.0) if enable_bonus else 0.0
    enable_el = cint(getattr(settings, "enable_el_provision", 1) if getattr(settings, "enable_el_provision", None) is not None else 1)
    el_days = flt(getattr(settings, "el_provision_days_per_year", 15.6) if getattr(settings, "el_provision_days_per_year", None) is not None else 15.6) if enable_el else 0.0

    employer_pf = round(min(pf_base_for_employer, pf_ceiling) * pf_rate, 2)
    pf_admin_charges = round(pf_base_for_employer * pf_admin_rate, 2)
    edli_charges = round(pf_base_for_employer * edli_rate, 2)
    employer_esi = round(grand_gross_pay * esi_rate, 2) if (earned_gross_salary <= esi_ceiling or grand_gross_pay <= esi_ceiling) else 0.0
    tea_expenses = round(flt(present_days) * tea_rate, 2) if "worker" in emp_type else 0.0
    total_employer_contrib = round(employer_pf + pf_admin_charges + edli_charges + employer_esi + tea_expenses, 2)

    bonus_provision = round(earned_basic_da * bonus_rate, 2) if enable_bonus else 0.0
    el_provision = round((earned_basic_da / 26.0) * (el_days / 12.0), 2) if (enable_el and month_working_days) else 0.0
    total_monthly_ctc = round(grand_gross_pay + total_employer_contrib + bonus_provision + el_provision, 2)

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
        "no_of_leave": unpaid_leave_days,
        "no_of_paid_leave": paid_leave_days,
        "no_of_comp_off": comp_off_days,
        "base_gross_pay": base_gross_total if base_gross_total > 0 else gross_pay,
        "base_total_deduction": base_deductions_total,
        "base_net_pay": (base_gross_total if base_gross_total > 0 else gross_pay) - base_deductions_total,
        "gross_pay": grand_gross_pay,
        "grand_gross_pay": grand_gross_pay,
        "earned_gross_salary": earned_gross_salary,
        "emp_pf": emp_pf if emp_pf is not None else 0.0,
        "emp_esi": emp_esi if emp_esi is not None else 0.0,
        "net_pay": grand_net_pay,
        "grand_net_pay": grand_net_pay,
        "total_deduction": total_deductions,
        "total_working_days": month_working_days,
        "lop": lop_amount,
        "lop_days": lop_days,
        "absent_days": total_absent_days,
        "ot_hours": round(total_ot_hours, 2),
        "ot_amount": ot_amount,
        "attendance_bonus": attendance_bonus,
        "tea_allowance": tea_allowance,
        "pt_amount": pt_amount,
        "earnings": prorated_earnings,
        "deductions": prorated_deductions,
        # Employer Contributions & CTC
        "employer_pf": employer_pf,
        "pf_admin_charges": pf_admin_charges,
        "edli_charges": edli_charges,
        "employer_esi": employer_esi,
        "tea_expenses": tea_expenses,
        "total_employer_contribution": total_employer_contrib,
        "bonus_provision": bonus_provision,
        "el_provision": el_provision,
        "total_monthly_ctc": total_monthly_ctc,
        "employer_pf_rate": round(pf_rate * 100.0, 2),
        "pf_admin_rate": round(pf_admin_rate * 100.0, 2),
        "edli_rate": round(edli_rate * 100.0, 2),
        "employer_esi_rate": round(esi_rate * 100.0, 2),
        "enable_bonus_provision": enable_bonus,
        "bonus_provision_rate": round(bonus_rate * 100.0, 2) if enable_bonus else 0.0,
        "enable_el_provision": enable_el,
        "el_provision_days_per_year": el_days if enable_el else 0.0,
        # Detailed Breakdown Fields
        "total_days_in_period": total_days,
        "holiday_count": len(holiday_dates),
        "holiday_working_days": total_days - len(holiday_dates),
        "holidays_details": holidays_details,
        "actual_present_days": present_days,
        "physical_attendance_days": physical_attendance_days,
        "unpaid_leave_days": unpaid_leave_days,
        "half_day_count": half_day_count,
        "calc_source": calc_source,
        "leave_calc_source": leave_calc_source,
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

    emp_earnings_map = {}
    emp_deductions_map = {}
    base_gross_total = 0.0
    base_deductions_total = 0.0

    if doc.employee:
        try:
            emp = frappe.get_doc("Employee", doc.employee)
            emp_earnings_map = { (e.component_name or e.salary_component or ""): flt(e.amount) for e in emp.earnings }
            emp_deductions_map = { (d.component_name or d.salary_component or ""): flt(d.amount) for d in emp.deductions }
            base_gross_total = round(sum(flt(e.amount) for e in emp.earnings), 2)
            base_deductions_total = round(sum(flt(d.amount) for d in emp.deductions), 2)
        except Exception:
            pass

    enriched_earnings = []
    for e in doc.earnings:
        item = e.as_dict()
        c_name = e.component_name or e.salary_component or ""
        item["standard_amount"] = emp_earnings_map.get(c_name, 0.0)
        enriched_earnings.append(item)
    res["earnings"] = enriched_earnings

    enriched_deductions = []
    for d in doc.deductions:
        item = d.as_dict()
        c_name = d.component_name or d.salary_component or ""
        item["standard_amount"] = emp_deductions_map.get(c_name, 0.0)
        enriched_deductions.append(item)
    res["deductions"] = enriched_deductions

    res["base_gross_pay"] = base_gross_total or sum(
        flt(e.amount) for e in doc.earnings
        if (e.component_name or e.salary_component or "") not in ["Overtime Pay (OT)", "Overtime Allowance", "Attendance Bonus"]
    )
    res["base_total_deduction"] = base_deductions_total
    res["base_net_pay"] = res["base_gross_pay"] - res["base_total_deduction"]

    # ── Employer Contributions & CTC ──────────────────────────────────────────
    emp_type = (res.get("employee_type") or "").lower()
    gross_val = flt(doc.grand_gross_pay or doc.gross_pay or 0.0)
    earned_gross_salary = round(sum(
        flt(e.amount or 0) for e in doc.earnings
        if (e.component_name or e.salary_component or "") not in ["Overtime Pay (OT)", "Overtime Allowance", "Attendance Bonus", "Tea Allowance"]
    ), 2)

    earned_basic_da = sum(
        flt(e.amount or 0) for e in doc.earnings
        if any(k in (e.component_name or e.salary_component or "").lower() for k in ["basic", "da", "dearness"])
    )
    if earned_basic_da <= 0:
        ot_amt = flt(getattr(doc, "ot_amount", 0.0))
        att_b = flt(getattr(doc, "attendance_bonus", 0.0))
        earned_basic_da = max(0.0, gross_val - ot_amt - att_b)

    present_days_val = flt(getattr(doc, "actual_present_days", None) or getattr(doc, "total_working_days", 0.0))
    settings = frappe.get_single("HRMS Settings")
    pf_rate = flt(getattr(settings, "employer_pf_rate", None) if getattr(settings, "employer_pf_rate", None) is not None else 12.0) / 100.0
    pf_admin_rate = flt(getattr(settings, "pf_admin_rate", None) if getattr(settings, "pf_admin_rate", None) is not None else 0.5) / 100.0
    edli_rate = flt(getattr(settings, "edli_rate", None) if getattr(settings, "edli_rate", None) is not None else 0.5) / 100.0
    esi_rate = flt(getattr(settings, "employer_esi_rate", None) if getattr(settings, "employer_esi_rate", None) is not None else 3.25) / 100.0
    pf_ceiling = flt(getattr(settings, "pf_wage_ceiling", 15000.0) if getattr(settings, "pf_wage_ceiling", None) is not None else 15000.0)
    esi_ceiling = flt(getattr(settings, "esi_wage_ceiling", 21000.0) if getattr(settings, "esi_wage_ceiling", None) is not None else 21000.0)
    pf_basis_raw = getattr(settings, "pf_wage_basis", None)
    selected_components = []
    if pf_basis_raw:
        if isinstance(pf_basis_raw, list):
            selected_components = [str(x).strip().lower() for x in pf_basis_raw if str(x).strip()]
        elif isinstance(pf_basis_raw, str):
            try:
                parsed = json.loads(pf_basis_raw)
                if isinstance(parsed, list):
                    selected_components = [str(x).strip().lower() for x in parsed if str(x).strip()]
            except Exception:
                if pf_basis_raw.strip() == "Earned Basic + DA":
                    selected_components = ["basic pay", "da", "basic", "dearness"]
                elif "," in pf_basis_raw:
                    selected_components = [x.strip().lower() for x in pf_basis_raw.split(",") if x.strip()]

    if selected_components and doc.earnings:
        matching_total = sum(
            flt(e.amount or 0)
            for e in doc.earnings
            if (
                (getattr(e, "component_name", None) or getattr(e, "salary_component", None) or "").lower().strip() in selected_components
                or any(
                    sc in (getattr(e, "component_name", None) or getattr(e, "salary_component", None) or "").lower()
                    for sc in selected_components
                )
            )
        )
        pf_base_for_employer = matching_total
    elif pf_basis_raw == "Earned Basic + DA":
        pf_base_for_employer = earned_basic_da
    else:
        pf_base_for_employer = earned_gross_salary

    enable_bonus = cint(getattr(settings, "enable_bonus_provision", 1) if getattr(settings, "enable_bonus_provision", None) is not None else 1)
    bonus_rate = (flt(getattr(settings, "bonus_provision_rate", 8.33) if getattr(settings, "bonus_provision_rate", None) is not None else 8.33) / 100.0) if enable_bonus else 0.0
    enable_el = cint(getattr(settings, "enable_el_provision", 1) if getattr(settings, "enable_el_provision", None) is not None else 1)
    el_days = flt(getattr(settings, "el_provision_days_per_year", 15.6) if getattr(settings, "el_provision_days_per_year", None) is not None else 15.6) if enable_el else 0.0

    tea_rate = flt(getattr(settings, "workers_tea_allowance_per_day", 5.0) if getattr(settings, "workers_tea_allowance_per_day", None) is not None else 5.0)
    employer_pf = round(min(pf_base_for_employer, pf_ceiling) * pf_rate, 2)
    pf_admin_charges = round(pf_base_for_employer * pf_admin_rate, 2)
    edli_charges = round(pf_base_for_employer * edli_rate, 2)
    employer_esi = round(gross_val * esi_rate, 2) if (earned_gross_salary <= esi_ceiling or gross_val <= esi_ceiling) else 0.0
    tea_expenses = round(present_days_val * tea_rate, 2) if "worker" in emp_type else 0.0
    total_employer_contrib = round(employer_pf + pf_admin_charges + edli_charges + employer_esi + tea_expenses, 2)

    bonus_provision = round(earned_basic_da * bonus_rate, 2) if enable_bonus else 0.0
    el_provision = round((earned_basic_da / 26.0) * (el_days / 12.0), 2) if enable_el else 0.0
    total_monthly_ctc = round(gross_val + total_employer_contrib + bonus_provision + el_provision, 2)

    res.update({
        "earned_gross_salary": earned_gross_salary,
        "employer_pf": employer_pf,
        "pf_admin_charges": pf_admin_charges,
        "edli_charges": edli_charges,
        "employer_esi": employer_esi,
        "tea_expenses": tea_expenses,
        "total_employer_contribution": total_employer_contrib,
        "bonus_provision": bonus_provision,
        "el_provision": el_provision,
        "total_monthly_ctc": total_monthly_ctc,
        "employer_pf_rate": round(pf_rate * 100.0, 2),
        "pf_admin_rate": round(pf_admin_rate * 100.0, 2),
        "edli_rate": round(edli_rate * 100.0, 2),
        "employer_esi_rate": round(esi_rate * 100.0, 2),
        "enable_bonus_provision": enable_bonus,
        "bonus_provision_rate": round(bonus_rate * 100.0, 2) if enable_bonus else 0.0,
        "enable_el_provision": enable_el,
        "el_provision_days_per_year": el_days if enable_el else 0.0,
    })

    # ── Days Breakdown (mirrors preview_salary_slip) ──────────────────────────
    start_date = getdate(doc.pay_period_start)
    end_date   = getdate(doc.pay_period_end)

    settings          = frappe.get_single("HRMS Settings")
    calc_source       = getattr(doc, "calc_source", None) or settings.salary_calculation_source or "Attendance"
    leave_calc_source = getattr(settings, "salary_leave_calculation_source", None) or "Via Leave Application"
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

    direct_paid_remaining = 0.0
    direct_unpaid_remaining = 0.0
    if leave_calc_source == "Via Direct Allocation":
        leave_allocations = frappe.get_all(
            "Leave Allocation",
            filters={
                "employee": doc.employee,
                "docstatus": ["<", 2],
                "from_date": ["<=", end_date],
                "to_date": [">=", start_date]
            },
            fields=["name", "leave_type", "total_leaves_allocated", "total_leaves_taken"]
        )
        for alloc in leave_allocations:
            taken = flt(alloc.get("total_leaves_taken") or 0)
            if taken > 0:
                if is_paid_map.get(alloc.leave_type, 1):
                    direct_paid_remaining += taken
                else:
                    direct_unpaid_remaining += taken

    days_breakdown = []
    total_absent_days = 0.0
    paid_leave_days = 0.0
    comp_off_days = 0.0
    unpaid_leave_days = 0.0
    present_days = 0.0
    physical_attendance_days = 0.0
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
        leave_val = 0.0
        comp_off_val = 0.0
        is_paid_leave = False

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
            elif day_attendance["status"] == "Compensatory Off":
                comp_off_val = 1.0

        holiday_val = 0
        if is_holiday and (physical_val + comp_off_val + leave_val) < 1.0:
            if holiday_handling == "Include in Working Days":
                holiday_val = 1.0 - (physical_val + comp_off_val + leave_val)

        if leave_calc_source != "Via Direct Allocation":
            if day_leave and (physical_val + comp_off_val + holiday_val + leave_val) < 1.0:
                leave_unit    = 0.5 if flt(day_leave.half_day) else 1.0
                leave_val     = min(leave_unit, 1.0 - (physical_val + comp_off_val + holiday_val))
                is_paid_leave = bool(is_paid_map.get(day_leave.leave_type, 1))

        if is_paid_leave:
            paid_leave_days += leave_val
            present_days += leave_val
        elif leave_val > 0:
            unpaid_leave_days += leave_val

        physical_attendance_days += physical_val
        comp_off_days += comp_off_val
        present_days += physical_val + comp_off_val

        components = []
        if physical_val > 0:
            components.append(f"Work ({physical_val})")
        if comp_off_val > 0:
            components.append(f"Compensatory Off ({comp_off_val})")
        if leave_val > 0:
            components.append(f"{'Paid' if is_paid_leave else 'Unpaid'} Leave ({leave_val})")
        if holiday_val > 0:
            components.append("Holiday" if holiday_val >= 1.0 else f"Holiday ({holiday_val})")
            
        absent_val = round(max(0.0, 1.0 - (physical_val + comp_off_val + leave_val + holiday_val)), 2)
        if absent_val > 0:
            if leave_calc_source != "Via Direct Allocation":
                components.append(f"Unpaid Leave ({absent_val})" if absent_val < 1.0 else "Unpaid Leave")
            else:
                components.append(f"Absent ({absent_val})" if absent_val < 1.0 else "Absent")
            total_absent_days += absent_val
            
        day_status = " + ".join(components) if components else "Absent"

        days_breakdown.append({
            "date":   single_day_date.strftime("%Y-%m-%d"),
            "status": day_status,
            "is_holiday": is_holiday,
            "holiday_desc": holiday_desc_map.get(single_day_date, "") if "holiday_desc_map" in locals() else "",
            "hours":  round(day_hours, 2),
            "ot_hours": round(day_ot, 2)
        })

    if leave_calc_source == "Via Direct Allocation":
        direct_credit = min(total_absent_days, direct_paid_remaining)
        paid_leave_days += direct_credit
        present_days += direct_credit
        unpaid_leave_days = direct_unpaid_remaining
        lop_days = max(0.0, total_absent_days - direct_credit)
    else:
        lop_days = unpaid_leave_days

    res["days_breakdown"] = days_breakdown
    res["leave_calc_source"] = leave_calc_source
    res["absent_days"] = total_absent_days
    res["no_of_paid_leave"] = paid_leave_days
    res["no_of_comp_off"] = comp_off_days
    res["no_of_leave"] = unpaid_leave_days
    res["lop_days"] = lop_days
    res["holiday_count"] = len(holiday_dates)
    res["holiday_working_days"] = total_days - len(holiday_dates)
    res["actual_present_days"] = present_days
    res["physical_attendance_days"] = physical_attendance_days
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
                "no_of_comp_off": data.get("no_of_comp_off", 0.0),
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


@frappe.whitelist()
def cancel_salary_slip(name):
    doc = frappe.get_doc("Salary Slip", name)
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted salary slips can be cancelled. Current status of {0} is {1}").format(name, doc.docstatus))
    doc.cancel()
    return doc.as_dict()


@frappe.whitelist()
def save_salary_slip(doc):
    if isinstance(doc, str):
        import json
        doc = json.loads(doc)
    doc_name = doc.get("name")
    if doc_name and frappe.db.exists("Salary Slip", doc_name):
        current_docstatus = frappe.db.get_value("Salary Slip", doc_name, "docstatus")
        if current_docstatus == 2:
            frappe.db.set_value("Salary Slip", doc_name, "docstatus", 0)
            frappe.db.commit()
            doc["docstatus"] = 0

    salary_slip_doc = frappe.get_doc(doc)
    if salary_slip_doc.docstatus == 2:
        salary_slip_doc.docstatus = 0
    salary_slip_doc.flags.ignore_validate_update_after_submit = True
    salary_slip_doc.save()
    return salary_slip_doc.as_dict()


@frappe.whitelist()
def delete_salary_slip(name):
    doc = frappe.get_doc("Salary Slip", name)
    if doc.docstatus == 1:
        frappe.throw(_("Cannot delete a submitted salary slip. Please cancel it first."))
    frappe.delete_doc("Salary Slip", name, force=1)
    return {"status": "success", "name": name}


@frappe.whitelist()
def export_bob_neft_file(start_date=None, end_date=None, salary_slips=None):
    """
    Generate Bank of Baroda (ECS-BOB) NEFT disbursement data matching Excel template format.
    """
    import json
    filters = {}
    if salary_slips:
        if isinstance(salary_slips, str):
            salary_slips = json.loads(salary_slips)
        filters["name"] = ["in", salary_slips]
    else:
        if start_date:
            filters["pay_period_start"] = [">=", getdate(start_date)]
        if end_date:
            filters["pay_period_end"] = ["<=", getdate(end_date)]

    slips = frappe.get_all(
        "Salary Slip",
        filters=filters,
        fields=["name", "employee", "employee_name", "net_pay", "grand_net_pay", "pay_period_start", "pay_period_end", "docstatus"],
        order_by="employee asc"
    )

    p_start = getdate(start_date) if start_date else (getdate(slips[0].pay_period_start) if slips else getdate())
    narration_prefix = f"WAG{p_start.strftime('%b').upper()}{p_start.strftime('%y')}"

    records = []
    total_amount = 0.0

    for idx, s in enumerate(slips, start=1):
        emp_id = s.employee
        emp = frappe.get_doc("Employee", emp_id) if emp_id else None
        
        acc_no = ""
        ifsc = "BARB0KANCHE"
        bank_name = "Bank of Baroda"
        branch = "Kancheepuram"

        if emp and emp.bank_account:
            try:
                ba = frappe.get_doc("Bank Account", emp.bank_account)
                acc_no = ba.account_number or ""
                ifsc = ba.ifsc_code or ifsc
                bank_name = ba.bank_name or bank_name
                branch = ba.branch or branch
            except Exception:
                pass

        amt = flt(s.grand_net_pay or s.net_pay or 0.0)
        total_amount += amt
        narration = f"{narration_prefix}{idx:04d}"

        records.append({
            "s_no": idx,
            "employee": emp.employee_id if (emp and emp.employee_id) else s.employee,
            "employee_name": s.employee_name,
            "account_no": acc_no,
            "ifsc_code": ifsc,
            "bank_name": bank_name,
            "branch": branch,
            "amount": amt,
            "narration": narration
        })

    return {
        "period": f"{p_start.strftime('%B %Y')}",
        "total_employees": len(records),
        "total_amount": round(total_amount, 2),
        "records": records
    }


@frappe.whitelist()
def export_cheque_register(start_date=None, end_date=None, salary_slips=None):
    """
    Generate Cheque Disbursement Register for employees without valid bank accounts.
    """
    import json
    filters = {}
    if salary_slips:
        if isinstance(salary_slips, str):
            salary_slips = json.loads(salary_slips)
        filters["name"] = ["in", salary_slips]
    else:
        if start_date:
            filters["pay_period_start"] = [">=", getdate(start_date)]
        if end_date:
            filters["pay_period_end"] = ["<=", getdate(end_date)]

    slips = frappe.get_all(
        "Salary Slip",
        filters=filters,
        fields=["name", "employee", "employee_name", "net_pay", "grand_net_pay", "pay_period_start"],
        order_by="employee asc"
    )

    cheque_records = []
    total_amount = 0.0
    idx = 1

    for s in slips:
        emp = frappe.get_doc("Employee", s.employee) if s.employee else None
        has_bank = bool(emp and emp.bank_account)
        if not has_bank:
            amt = flt(s.grand_net_pay or s.net_pay or 0.0)
            total_amount += amt
            cheque_records.append({
                "s_no": idx,
                "employee": emp.employee_id if (emp and emp.employee_id) else s.employee,
                "employee_name": s.employee_name,
                "reason": "Bank Account Not Provided / Cheque Payment",
                "amount": amt
            })
            idx += 1

    return {
        "total_count": len(cheque_records),
        "total_amount": round(total_amount, 2),
        "records": cheque_records
    }


@frappe.whitelist()
def get_wages_reconciliation_statement(current_start_date, current_end_date, prev_start_date=None, prev_end_date=None):
    """
    Month-on-Month Payroll Reconciliation Statement comparing Current Period against Previous Period.
    """
    c_start = getdate(current_start_date)
    c_end = getdate(current_end_date)

    if not prev_start_date or not prev_end_date:
        p_end = c_start - timedelta(days=1)
        p_start = getdate(f"{p_end.year}-{p_end.month}-01")
    else:
        p_start = getdate(prev_start_date)
        p_end = getdate(prev_end_date)

    curr_slips = frappe.get_all(
        "Salary Slip",
        filters={"pay_period_start": [">=", c_start], "pay_period_end": ["<=", c_end]},
        fields=["name", "employee", "employee_name", "gross_pay", "grand_gross_pay", "net_pay", "grand_net_pay", "total_deduction", "ot_amount", "lop_days"]
    )

    prev_slips = frappe.get_all(
        "Salary Slip",
        filters={"pay_period_start": [">=", p_start], "pay_period_end": ["<=", p_end]},
        fields=["name", "employee", "employee_name", "gross_pay", "grand_gross_pay", "net_pay", "grand_net_pay", "total_deduction", "ot_amount", "lop_days"]
    )

    curr_emp_map = { s.employee: s for s in curr_slips }
    prev_emp_map = { s.employee: s for s in prev_slips }

    new_additions = [curr_emp_map[e] for e in curr_emp_map if e not in prev_emp_map]
    exits = [prev_emp_map[e] for e in prev_emp_map if e not in curr_emp_map]

    prev_gross = sum(flt(s.grand_gross_pay or s.gross_pay or 0) for s in prev_slips)
    curr_gross = sum(flt(s.grand_gross_pay or s.gross_pay or 0) for s in curr_slips)

    prev_net = sum(flt(s.grand_net_pay or s.net_pay or 0) for s in prev_slips)
    curr_net = sum(flt(s.grand_net_pay or s.net_pay or 0) for s in curr_slips)

    prev_ot = sum(flt(s.ot_amount or 0) for s in prev_slips)
    curr_ot = sum(flt(s.ot_amount or 0) for s in curr_slips)

    return {
        "previous_period": f"{p_start.strftime('%B %Y')}",
        "current_period": f"{c_start.strftime('%B %Y')}",
        "previous_headcount": len(prev_slips),
        "current_headcount": len(curr_slips),
        "headcount_delta": len(curr_slips) - len(prev_slips),
        "additions_count": len(new_additions),
        "exits_count": len(exits),
        "new_additions": new_additions,
        "exits": exits,
        "previous_total_gross": round(prev_gross, 2),
        "current_total_gross": round(curr_gross, 2),
        "gross_delta": round(curr_gross - prev_gross, 2),
        "previous_total_net": round(prev_net, 2),
        "current_total_net": round(curr_net, 2),
        "net_delta": round(curr_net - prev_net, 2),
        "ot_variance": round(curr_ot - prev_ot, 2)
    }