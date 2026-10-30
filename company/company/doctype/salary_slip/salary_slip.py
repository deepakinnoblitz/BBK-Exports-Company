import json
import math
from decimal import Decimal, ROUND_HALF_UP
import frappe
from frappe import _
from datetime import datetime, timedelta
from frappe.utils import cint, flt, get_first_day, get_last_day, getdate, formatdate
from frappe.model.document import Document
from calendar import monthrange


def excel_round(val):
    """Exact Excel ROUND(val, 0) arithmetic half-up rounding."""
    if val is None:
        return 0.0
    try:
        return float(Decimal(str(round(flt(val), 8))).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except Exception:
        return float(round(flt(val)))

class SalarySlip(Document):
    def validate(self):
        """Ensure leave_details, cl_cycle_period, cl_allocated, cl_taken, cl_balance are set."""
        if self.employee and self.pay_period_start and self.pay_period_end:
            try:
                res = get_employee_leave_balances(self.employee, self.pay_period_start, self.pay_period_end)
                self.leave_details = json.dumps(res.get("balances", []))
                self.cl_cycle_period = res.get("cl_cycle_period") or ""
                self.cl_allocated = flt(res.get("cl_allocated", 0.0))
                self.cl_taken = flt(res.get("cl_taken", 0.0))
                self.cl_balance = flt(res.get("cl_balance", 0.0))
            except Exception:
                pass

    def on_submit(self):
        """Triggered automatically when a Salary Slip is submitted (approved)."""
        self.send_email_notification()

    def send_email_notification(self):
        """Send salary slip PDF via email to the employee."""
        try:
            from company.company.api import is_hrms_notification_enabled
            if not is_hrms_notification_enabled("salary_slip_notification"):
                return

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
                elif "driver" in emp_type:
                    print_format = "Driver Form 25B Pay Slip"
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


def get_category_setting(settings, fieldname, emp_type="", default=None):
    emp_type_clean = (emp_type or "").lower().strip()
    prefixes = []
    if "staff" in emp_type_clean:
        if "non ctc" in emp_type_clean or "non-ctc" in emp_type_clean:
            prefixes = ["staff_non_ctc_", "staff_"]
        elif "ctc" in emp_type_clean:
            prefixes = ["staff_ctc_", "staff_"]
        else:
            prefixes = ["staff_non_ctc_", "staff_ctc_", "staff_"]
    elif "worker" in emp_type_clean:
        prefixes = ["workers_"]
    elif "north indian" in emp_type_clean:
        prefixes = ["north_indian_"]
    elif "driver" in emp_type_clean:
        prefixes = ["drivers_"]
    
    for prefix in prefixes:
        val = getattr(settings, f"{prefix}{fieldname}", None)
        if val is not None and val != "":
            return val
    
    val = getattr(settings, fieldname, None)
    return val if (val is not None and val != "") else default


def calculate_overtime_pay(emp, gross_salary, ot_hours, settings):
    ot_h = round(flt(ot_hours), 2)
    if ot_h <= 0:
        return 0.0
    
    emp_type = (emp.get("employee_type") or "").lower()

    if "staff" in emp_type:
        return 0.0

    def _get_setting_val(f_name, default):
        val = getattr(settings, f_name, None) if not isinstance(settings, dict) else settings.get(f_name, None)
        return flt(val) if (val is not None and val != "") else default
    
    if "worker" in emp_type:
        multiplier = _get_setting_val("workers_ot_rate_multiplier", 2.0)
        # Formula: ROUND(Gross Salary / 26 / 8 * OT Hours, 0) * multiplier
        single_rate_ot = excel_round((flt(gross_salary) / 26.0 / 8.0) * ot_h)
        return excel_round(single_rate_ot * multiplier)
    elif "driver" in emp_type:
        multiplier = _get_setting_val("drivers_ot_rate_multiplier", 2.0)
        # Formula: ROUND(Gross Salary / 26 / 8 * OT Hours, 0) * multiplier
        single_rate_ot = excel_round((flt(gross_salary) / 26.0 / 8.0) * ot_h)
        return excel_round(single_rate_ot * multiplier)
    elif "north indian" in emp_type:
        rate = _get_setting_val("north_indian_ot_rate", 100.0)
        # Formula: rate * OT Hours
        return excel_round(rate * ot_h)
    return 0.0


def calculate_attendance_bonus(emp, absent_days, settings):
    emp_type = (emp.get("employee_type") or "").lower()
    
    if "worker" in emp_type and flt(absent_days) <= 0.0:
        val = getattr(settings, "workers_attendance_bonus", None) if not isinstance(settings, dict) else settings.get("workers_attendance_bonus", None)
        return flt(val) if (val is not None and val != "") else 1500.0
    return 0.0


def get_leaves_taken_in_period(employee_id, leave_type_name, start_date, end_date):
    """Calculate total approved leave days taken in the given cycle."""
    try:
        # 1. Check submitted Leave Applications
        app_res = frappe.db.sql("""
            SELECT COALESCE(SUM(total_days), 0)
            FROM `tabLeave Application`
            WHERE employee = %s 
              AND (leave_type = %s OR leave_type IN (SELECT name FROM `tabLeave Type` WHERE leave_type_name = %s))
              AND docstatus = 1
              AND from_date >= %s 
              AND to_date <= %s
        """, (employee_id, leave_type_name, leave_type_name, start_date, end_date))
        app_days = flt(app_res[0][0]) if app_res else 0.0
        if app_days > 0:
            return app_days
        
        # 2. Check Attendance records
        att_res = frappe.db.sql("""
            SELECT COALESCE(SUM(CASE WHEN status = 'Half Day' THEN 0.5 ELSE 1.0 END), 0)
            FROM `tabAttendance`
            WHERE employee = %s
              AND (leave_type = %s OR leave_type IN (SELECT name FROM `tabLeave Type` WHERE leave_type_name = %s))
              AND attendance_date >= %s
              AND attendance_date <= %s
              AND status IN ('On Leave', 'Half Day')
        """, (employee_id, leave_type_name, leave_type_name, start_date, end_date))
        return flt(att_res[0][0]) if att_res else 0.0
    except Exception:
        return 0.0


def get_employee_leave_balances(employee_id, pay_period_start, pay_period_end):
    """
    Calculate active cycle leave balances for an employee based on each Leave Type's encashment cycles.
    
    If slip month is a configured payout month for an encashable Leave Type:
        Resolves to THAT encashed cycle period (e.g. Jan-Jun when slip is in July, Jul-Dec when slip is in January)
        so that the salary slip displays the exact leave period, allocations, taken, and encashed balance
        corresponding to the encashment payout.
    Otherwise:
        Resolves to the current active ongoing cycle (e.g. 01 Jul - 31 Oct 2026).
    """
    start_date = getdate(pay_period_start)
    end_date = getdate(pay_period_end)
    slip_year = start_date.year
    slip_month = start_date.month
    current_month_name = start_date.strftime("%B").lower()

    month_name_to_num = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }

    leave_types = frappe.get_all(
        "Leave Type",
        filters={"status": ["!=", "Inactive"], "is_encashable": 1},
        fields=[
            "name",
            "leave_type_name",
            "is_paid",
            "is_permission",
            "is_encashable",
            "encashment_cycles",
            "encashment_payout_months",
        ],
        order_by="creation asc"
    )

    settings = frappe.get_single("HRMS Settings")
    leave_calc_source = getattr(settings, "salary_leave_calculation_source", None) or "Via Leave Application"

    balances = []
    cl_cycle_period = ""
    cl_allocated = 0.0
    cl_taken = 0.0
    cl_balance = 0.0
    is_cl_payout_month = False

    for lt in leave_types:
        if not cint(lt.is_encashable):
            continue

        lt_name = lt.leave_type_name or lt.name
        is_encashable = cint(lt.is_encashable)
        is_permission = cint(lt.is_permission) or ("permission" in lt_name.lower())

        cycles = []
        if lt.encashment_cycles:
            try:
                cycles = json.loads(lt.encashment_cycles)
            except Exception:
                cycles = []

        if not cycles:
            p_months = [m.strip() for m in (lt.encashment_payout_months or "June, December").split(",") if m.strip()]
            if len(p_months) >= 2:
                cycles = [
                    {"from_month": "January", "to_month": "June", "payout_months": [p_months[0]]},
                    {"from_month": "July", "to_month": "December", "payout_months": [p_months[1]]}
                ]
            elif len(p_months) == 1:
                cycles = [
                    {"from_month": "January", "to_month": "December", "payout_months": p_months}
                ]
            else:
                cycles = [
                    {"from_month": "January", "to_month": "June", "payout_months": ["June"]},
                    {"from_month": "July", "to_month": "December", "payout_months": ["December"]}
                ]

        # 1. Check if the current slip month is a configured Payout Month for an encashment cycle
        is_payout_month = False
        matched_payout_cycle = None

        for cycle in cycles:
            c_payout_months = cycle.get("payout_months") or ([cycle.get("payout_month")] if cycle.get("payout_month") else [])
            normalized_p_months = [str(m).strip().lower() for m in c_payout_months if m]
            if current_month_name in normalized_p_months:
                is_payout_month = True
                matched_payout_cycle = cycle
                break

        # 2. Compute the Current Active Cycle for this slip month
        matched_curr_cycle = None
        for cycle in cycles:
            f_str = str(cycle.get("from_month") or "January").strip().lower()
            t_str = str(cycle.get("to_month") or "December").strip().lower()
            sm = month_name_to_num.get(f_str, 1)
            em = month_name_to_num.get(t_str, 12)

            if sm <= em:
                if sm <= slip_month <= em:
                    matched_curr_cycle = (sm, em, cycle)
                    break
            else:
                if slip_month >= sm or slip_month <= em:
                    matched_curr_cycle = (sm, em, cycle)
                    break

        if matched_curr_cycle:
            sm, em, cycle = matched_curr_cycle
            f_str = str(cycle.get("from_month") or "January").strip().lower()
            t_str = str(cycle.get("to_month") or "December").strip().lower()
            if sm <= em:
                from_year = slip_year
                to_year = slip_year
            else:
                if slip_month <= em:
                    from_year = slip_year - 1
                    to_year = slip_year
                else:
                    from_year = slip_year
                    to_year = slip_year + 1

            cycle_start = getdate(f"{from_year}-{sm:02d}-01")
            last_day = monthrange(to_year, em)[1]
            cycle_end = getdate(f"{to_year}-{em:02d}-{last_day:02d}")
            cycle_label = f"{f_str.capitalize()[:3]} - {t_str.capitalize()[:3]} {to_year}"
        else:
            cycle_start = getdate(f"{slip_year}-01-01")
            cycle_end = getdate(f"{slip_year}-12-31")
            cycle_label = f"Jan - Dec {slip_year}"

        calc_end = end_date
        period_label = f"{cycle_start.strftime('%d %b')} - {end_date.strftime('%d %b %Y')}"

        alloc_res = frappe.db.sql("""
            SELECT COALESCE(SUM(total_leaves_allocated), 0), COALESCE(SUM(total_leaves_taken), 0)
            FROM `tabLeave Allocation`
            WHERE employee = %s
              AND (leave_type = %s OR leave_type IN (SELECT name FROM `tabLeave Type` WHERE leave_type_name = %s))
              AND status = 'Approved'
              AND (
                  (from_date >= %s AND to_date <= %s)
                  OR (from_date <= %s AND to_date >= %s)
              )
        """, (employee_id, lt.name, lt_name, cycle_start, calc_end, calc_end, cycle_start))

        total_alloc = flt(alloc_res[0][0]) if alloc_res else 0.0
        alloc_taken = flt(alloc_res[0][1]) if alloc_res else 0.0

        if leave_calc_source == "Via Direct Allocation":
            total_taken = alloc_taken
        else:
            actual_taken = get_leaves_taken_in_period(employee_id, lt.name, cycle_start, calc_end)
            total_taken = max(alloc_taken, actual_taken)
        balance = max(0.0, total_alloc - total_taken)

        current_item = {
            "leave_type": lt.name,
            "leave_type_name": f"{lt_name} (Current Cycle)" if is_payout_month else lt_name,
            "is_encashable": is_encashable,
            "is_permission": is_permission,
            "is_payout_month": False,
            "cycle_type": "current",
            "cycle_start_date": cycle_start.strftime("%Y-%m-%d"),
            "cycle_end_date": cycle_end.strftime("%Y-%m-%d"),
            "pay_period_end": end_date.strftime("%Y-%m-%d"),
            "cycle_label": cycle_label,
            "period_label": period_label,
            "allocated": total_alloc,
            "taken": total_taken,
            "balance": balance,
            "uom": "Mins" if is_permission else "Days"
        }
        balances.append(current_item)

        if "casual" in lt_name.lower():
            cl_cycle_period = cycle_label
            cl_allocated = total_alloc
            cl_taken = total_taken
            cl_balance = balance

        # 3. If in a payout month, also add the Encashed Cycle card!
        if is_payout_month and matched_payout_cycle:
            p_cycle = matched_payout_cycle
            f_str = str(p_cycle.get("from_month") or "January").strip().lower()
            t_str = str(p_cycle.get("to_month") or "June").strip().lower()
            p_sm = month_name_to_num.get(f_str, 1)
            p_em = month_name_to_num.get(t_str, 6)

            if p_sm <= p_em:
                if slip_month < p_sm:
                    p_from_year = slip_year - 1
                    p_to_year = slip_year - 1
                else:
                    p_from_year = slip_year
                    p_to_year = slip_year
            else:
                if slip_month <= p_em:
                    p_from_year = slip_year - 1
                    p_to_year = slip_year
                else:
                    p_from_year = slip_year
                    p_to_year = slip_year + 1

            p_last_day = monthrange(p_to_year, p_em)[1]
            p_cycle_start = getdate(f"{p_from_year}-{p_sm:02d}-01")
            p_cycle_end = getdate(f"{p_to_year}-{p_em:02d}-{p_last_day:02d}")

            p_alloc_res = frappe.db.sql("""
                SELECT COALESCE(SUM(total_leaves_allocated), 0), COALESCE(SUM(total_leaves_taken), 0)
                FROM `tabLeave Allocation`
                WHERE employee = %s
                  AND (leave_type = %s OR leave_type IN (SELECT name FROM `tabLeave Type` WHERE leave_type_name = %s))
                  AND status = 'Approved'
                  AND (
                      (from_date >= %s AND to_date <= %s)
                      OR (from_date <= %s AND to_date >= %s)
                  )
            """, (employee_id, lt.name, lt_name, p_cycle_start, p_cycle_end, p_cycle_end, p_cycle_start))

            p_total_alloc = flt(p_alloc_res[0][0]) if p_alloc_res else 0.0
            p_alloc_taken = flt(p_alloc_res[0][1]) if p_alloc_res else 0.0

            if leave_calc_source == "Via Direct Allocation":
                p_total_taken = p_alloc_taken
            else:
                p_actual_taken = get_leaves_taken_in_period(employee_id, lt.name, p_cycle_start, p_cycle_end)
                p_total_taken = max(p_alloc_taken, p_actual_taken)
            p_balance = max(0.0, p_total_alloc - p_total_taken)

            encashed_item = {
                "leave_type": lt.name,
                "leave_type_name": f"{lt_name} (Encashed Cycle)",
                "is_encashable": is_encashable,
                "is_permission": is_permission,
                "is_payout_month": True,
                "cycle_type": "encashed",
                "cycle_start_date": p_cycle_start.strftime("%Y-%m-%d"),
                "cycle_end_date": p_cycle_end.strftime("%Y-%m-%d"),
                "pay_period_end": end_date.strftime("%Y-%m-%d"),
                "cycle_label": f"{f_str.capitalize()[:3]} - {t_str.capitalize()[:3]} {p_to_year}",
                "period_label": f"{p_cycle_start.strftime('%d %b')} - {p_cycle_end.strftime('%d %b %Y')}",
                "allocated": p_total_alloc,
                "taken": p_total_taken,
                "balance": p_balance,
                "uom": "Days"
            }
            balances.append(encashed_item)

            if "casual" in lt_name.lower():
                is_cl_payout_month = True

    return {
        "balances": balances,
        "cl_cycle_period": cl_cycle_period,
        "cl_allocated": cl_allocated,
        "cl_taken": cl_taken,
        "cl_balance": cl_balance,
        "is_payout_month": is_cl_payout_month
    }


def calculate_employee_pf(emp, earned_gross_salary, earned_basic_da, settings, prorated_earnings=None):
    """
    Calculate Employee PF deduction based on HRMS Settings and Excel formula:
    - For Staff - CTC: =ROUND((Earned Basic + DA) * 12%, 0) (Uncapped 12%)
    - For Staff - Non CTC / Workers: =ROUND(+IF(AND(AF6>15000),1800,IF(AND(AF6<15000),AF6*12%)),0) (Capped at 1800)
    
    Supports dynamic selected salary components for wage basis and ceiling cap settings.
    """
    emp_type = (emp.get("employee_type") if hasattr(emp, "get") else getattr(emp, "employee_type", "")) or ""
    enable_pf = cint(get_category_setting(settings, "enable_auto_pf", emp_type, default=1))
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

    emp_type_clean = emp_type.lower().strip()
    is_staff_ctc = "staff" in emp_type_clean and "ctc" in emp_type_clean and "non" not in emp_type_clean

    pf_rate = flt(get_category_setting(settings, "employee_pf_rate", emp_type, default=12.0)) / 100.0
    
    # Check if ceiling applies from settings or default for staff ctc
    apply_ceiling_setting = get_category_setting(settings, "apply_pf_ceiling", emp_type, default=None)
    if apply_ceiling_setting is not None and apply_ceiling_setting != "":
        apply_ceiling = cint(apply_ceiling_setting)
    else:
        # Default: Staff - CTC has no ceiling (0), all other categories have ceiling enabled (1)
        apply_ceiling = 0 if is_staff_ctc else 1

    pf_ceiling = flt(get_category_setting(settings, "pf_wage_ceiling", emp_type, default=15000.0 if apply_ceiling else 0.0))
    max_pf_amount = flt(get_category_setting(settings, "employee_pf_max_amount", emp_type, default=(pf_ceiling * pf_rate if pf_ceiling > 0 else 1800.0)))
    pf_basis_raw = get_category_setting(settings, "pf_wage_basis", emp_type)

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
        base_wage = flt(earned_basic_da) if (is_staff_ctc or "staff" in emp_type_clean) else flt(earned_gross_salary)

    if apply_ceiling and pf_ceiling > 0 and base_wage >= pf_ceiling:
        return float(round(max_pf_amount))
    else:
        return float(round(base_wage * pf_rate))


def calculate_employee_esi(emp, grand_gross_pay, earned_gross_salary, settings):
    """
    Calculate Employee ESI deduction based on HRMS Settings and Excel formula:
    =ROUNDUP(AK6 * $AM$5, 0) -> Total Gross Earnings (AK6) * 0.75%
    
    Returns rounded deduction amount or None if auto calculation is disabled.
    """
    emp_type = (emp.get("employee_type") if hasattr(emp, "get") else getattr(emp, "employee_type", "")) or ""
    enable_esi = cint(get_category_setting(settings, "enable_auto_esi", emp_type, default=1))
    if not enable_esi:
        return None

    esi_no = emp.get("esi_no") if hasattr(emp, "get") else getattr(emp, "esi_no", None)
    has_esi_component = False
    custom_esi_amount = None
    if hasattr(emp, "deductions") and emp.deductions:
        for d in emp.deductions:
            c_name = (d.component_name or d.salary_component or "").lower() if hasattr(d, "component_name") else (d.get("component_name") or d.get("salary_component") or "").lower()
            if any(k in c_name for k in ["esi", "esic"]) and "employer" not in c_name:
                has_esi_component = True
                amt = flt(d.amount if hasattr(d, "amount") else d.get("amount", 0.0))
                if amt > 0:
                    custom_esi_amount = amt
                break

    # If employee has no ESI number and ESI is not in their deduction structure, return 0
    if not esi_no and not has_esi_component:
        return 0.0

    esi_ceiling = flt(get_category_setting(settings, "esi_wage_ceiling", emp_type, default=21000.0))
    std_earnings = flt(emp.get("total_earnings") or 0.0) if hasattr(emp, "get") else flt(getattr(emp, "total_earnings", 0.0))
    
    # Statutory gross wage eligibility check (Gross <= ₹21,000)
    if esi_ceiling > 0 and earned_gross_salary > esi_ceiling and std_earnings > esi_ceiling:
        return float(custom_esi_amount) if custom_esi_amount is not None else 0.0

    esi_rate = flt(get_category_setting(settings, "employee_esi_rate", emp_type, default=0.75)) / 100.0
    rounding_method = get_category_setting(settings, "esi_rounding_method", emp_type, default="Round Up to Next Rupee (ROUNDUP / CEIL)")

    raw_esi = flt(grand_gross_pay) * esi_rate
    if "Round Up" in rounding_method or "ROUNDUP" in rounding_method or "CEIL" in rounding_method:
        return float(math.ceil(raw_esi))
    else:
        return float(round(raw_esi))


def calculate_professional_tax(gross_salary, pay_period_start, settings, employee=None, emp_doc=None, current_slip_name=None):
    emp_type = (emp_doc.get("employee_type") if hasattr(emp_doc, "get") else getattr(emp_doc, "employee_type", "")) if emp_doc else ""
    if not emp_type and employee:
        emp_type = frappe.db.get_value("Employee", employee, "employee_type") or ""

    enable_pt = cint(get_category_setting(settings, "enable_pt", emp_type, default=1))
    if not enable_pt:
        return 0.0

    pay_period_start = getdate(pay_period_start)
    gross = flt(gross_salary)

    # 1. Load dynamic slabs from settings if available
    configured_slabs = get_category_setting(settings, "pt_slabs", emp_type)
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

    frequency = get_category_setting(settings, "pt_deduction_frequency", emp_type, default="Half-Yearly (Sep & Feb)")
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


def calculate_lwf(emp, gross_salary, pay_period_start, settings, employee_id=None, current_slip_name=None, prorated_earnings=None, net_pay=None):
    """
    Calculate Tamil Nadu Labour Welfare Fund (LWF) contributions:
    - Employee Contribution: ₹20/year (deducted from employee salary)
    - Employer Contribution: ₹40/year (employer contribution; added to CTC)
    - Configured via HRMS Settings:
        - enable_lwf (default 1)
        - lwf_deduction_month (default "December")
        - lwf_employee_contribution (default 20.00)
        - lwf_employer_contribution (default 40.00)
        - lwf_salary_ceiling (default 25000.00, 0 means no ceiling)
        - lwf_wage_basis (JSON list of earning components)
        - lwf_applicable_categories (JSON list of categories)
    
    Returns: (employee_lwf, employer_lwf, is_eligible)
    """
    def get_setting_val(key, default_val=None):
        if hasattr(settings, "get"):
            v = settings.get(key)
        else:
            v = getattr(settings, key, None)
        return v if (v is not None and v != "") else default_val

    enable_lwf = cint(get_setting_val("enable_lwf", 1))
    if not enable_lwf:
        return 0.0, 0.0, False

    pay_dt = getdate(pay_period_start)
    current_month_name = pay_dt.strftime("%B")  # e.g., "December"
    configured_month = str(get_setting_val("lwf_deduction_month", "December")).strip()

    if current_month_name.lower() != configured_month.lower():
        return 0.0, 0.0, False

    # Check category applicability
    emp_type = (emp.get("employee_type") if hasattr(emp, "get") else getattr(emp, "employee_type", "")) or ""
    emp_type_clean = emp_type.lower().strip()
    
    category_key = "workers"
    if "staff" in emp_type_clean:
        if "non ctc" in emp_type_clean or "non-ctc" in emp_type_clean:
            category_key = "staff_non_ctc"
        else:
            category_key = "staff_ctc"
    elif "north indian" in emp_type_clean:
        category_key = "north_indian"
    elif "driver" in emp_type_clean:
        category_key = "drivers"

    applicable_cats_raw = get_setting_val("lwf_applicable_categories", '["staff_ctc", "staff_non_ctc", "workers", "north_indian", "drivers"]')
    applicable_cats = []
    if isinstance(applicable_cats_raw, list):
        applicable_cats = [str(x).strip().lower() for x in applicable_cats_raw]
    elif isinstance(applicable_cats_raw, str):
        try:
            parsed = json.loads(applicable_cats_raw)
            if isinstance(parsed, list):
                applicable_cats = [str(x).strip().lower() for x in parsed]
        except Exception:
            applicable_cats = ["staff_ctc", "staff_non_ctc", "workers", "north_indian", "drivers"]

    is_all_applicable = (
        not applicable_cats
        or "all" in applicable_cats
        or "all employee types" in applicable_cats
        or "all categories" in applicable_cats
    )
    if not is_all_applicable:
        matched = False
        if emp_type_clean in applicable_cats:
            matched = True
        elif category_key in applicable_cats:
            matched = True
        elif any(cat in emp_type_clean or emp_type_clean in cat for cat in applicable_cats):
            matched = True

        if not matched:
            return 0.0, 0.0, False

    # Dynamic wage basis evaluation for salary ceiling check
    lwf_basis_raw = get_setting_val("lwf_wage_basis")
    selected_lwf_components = []
    if lwf_basis_raw:
        if isinstance(lwf_basis_raw, list):
            selected_lwf_components = [str(x).strip().lower() for x in lwf_basis_raw if str(x).strip()]
        elif isinstance(lwf_basis_raw, str):
            try:
                parsed = json.loads(lwf_basis_raw)
                if isinstance(parsed, list):
                    selected_lwf_components = [str(x).strip().lower() for x in parsed if str(x).strip()]
            except Exception:
                selected_lwf_components = []

    eval_wage = flt(gross_salary)
    is_gross_pay = any(x in ["gross pay", "gross", "gross_pay"] for x in selected_lwf_components)
    is_net_pay = any(x in ["net pay", "net", "net_pay"] for x in selected_lwf_components)
    is_all_components = (
        not selected_lwf_components
        or "all" in selected_lwf_components
        or "all components" in selected_lwf_components
    )

    if is_net_pay:
        if net_pay is not None:
            eval_wage = flt(net_pay)
        else:
            eval_wage = flt(gross_salary) - sum(
                flt(d.get("amount") if isinstance(d, dict) else getattr(d, "amount", 0.0))
                for d in (getattr(emp, "deductions", []) or [])
            )
    elif is_gross_pay or is_all_components:
        eval_wage = flt(gross_salary)
    elif selected_lwf_components and prorated_earnings:
        eval_wage = sum(
            flt(e.get("amount") if isinstance(e, dict) else getattr(e, "amount", 0.0))
            for e in prorated_earnings
            if (
                ((e.get("component_name") or e.get("salary_component") or "") if isinstance(e, dict)
                 else (getattr(e, "component_name", None) or getattr(e, "salary_component", None) or "")).lower().strip() in selected_lwf_components
                or any(
                    sc in ((e.get("component_name") or e.get("salary_component") or "").lower() if isinstance(e, dict)
                           else (getattr(e, "component_name", None) or getattr(e, "salary_component", None) or "").lower())
                    for sc in selected_lwf_components
                )
            )
        )

    # Check salary ceiling threshold
    salary_ceiling = flt(get_setting_val("lwf_salary_ceiling", 25000.0))
    if salary_ceiling > 0 and eval_wage > salary_ceiling:
        # Excluded if earnings exceed ceiling
        return 0.0, 0.0, False

    # Check annual single deduction safeguard: has LWF already been deducted for this employee in the same calendar year?
    e_id = employee_id or (emp.get("name") if hasattr(emp, "get") else getattr(emp, "name", None))
    if e_id:
        cal_year = pay_dt.year
        year_start = f"{cal_year}-01-01"
        year_end = f"{cal_year}-12-31"

        try:
            existing_slips = frappe.db.sql(
                """
                SELECT name, employee_lwf FROM `tabSalary Slip`
                WHERE employee = %s 
                  AND docstatus < 2
                  AND pay_period_start >= %s 
                  AND pay_period_start <= %s
                  AND name != %s
                """,
                (e_id, year_start, year_end, current_slip_name or ""),
                as_dict=True
            )

            for s in existing_slips:
                if flt(s.get("employee_lwf", 0)) > 0:
                    # Already deducted in this calendar year
                    return 0.0, 0.0, False
        except Exception:
            pass

    emp_contrib = flt(get_setting_val("lwf_employee_contribution", 20.0))
    empr_contrib = flt(get_setting_val("lwf_employer_contribution", 40.0))
    return emp_contrib, empr_contrib, True


def evaluate_custom_salary_rules(rules_raw, comp_type, emp, emp_type, start_date, end_date, present_days, total_ot_hours, grand_gross_pay, earned_basic_da, canteen_meals_count, prorated_earnings=None):
    """
    Evaluate custom salary component rules configured in HRMS Settings.
    comp_type: 'Earning' or 'Deduction'
    Returns list of dicts to append to prorated_earnings or prorated_deductions.
    """
    if not rules_raw:
        return []
    
    rules = []
    if isinstance(rules_raw, list):
        rules = rules_raw
    elif isinstance(rules_raw, str):
        try:
            rules = json.loads(rules_raw)
        except Exception:
            return []
            
    if not isinstance(rules, list):
        return []

    emp_id = getattr(emp, "employee_id", None) or (emp.get("employee_id") if isinstance(emp, dict) else "") or (emp.name if hasattr(emp, "name") else "")
    emp_name = getattr(emp, "name", None) or (emp.get("name") if isinstance(emp, dict) else "")
    emp_type_clean = (emp_type or "").lower().strip()
    
    # Pay period YYYY-MM
    p_month_start = str(start_date)[:7] if start_date else ""
    p_month_end = str(end_date)[:7] if end_date else ""

    results = []
    for r in rules:
        if not r or not isinstance(r, dict):
            continue
        if r.get("type") != comp_type:
            continue
        enabled_val = r.get("enabled")
        if not (enabled_val is True or enabled_val == 1 or str(enabled_val).lower() == "true" or enabled_val == "1"):
            continue

        # Check Timing / Month
        app_mode = r.get("applicability", "always_active")
        app_month = (r.get("applicable_month") or "").strip()
        if app_mode == "specific_month" and app_month:
            if app_month not in [p_month_start, p_month_end]:
                continue

        # Check Target Assignees
        target_type = r.get("target_type", "all")
        if target_type == "assignees":
            assigned_ids = [str(x).strip().lower() for x in (r.get("target_employee_ids") or []) if str(x).strip()]
            if emp_id.lower() not in assigned_ids and emp_name.lower() not in assigned_ids:
                continue
        elif target_type == "categories":
            assigned_cats = [str(x).strip().lower() for x in (r.get("target_categories") or []) if str(x).strip()]
            if not any(c in emp_type_clean for c in assigned_cats):
                continue

        # Calculate Amount
        calc_mode = r.get("calculation_mode", "fixed")
        rate_val = flt(r.get("amount", 0.0))
        computed_amt = 0.0
        remarks = ""

        if calc_mode == "fixed":
            computed_amt = rate_val
            remarks = "Fixed Amount"
        elif calc_mode == "per_day":
            computed_amt = round(flt(present_days) * rate_val, 2)
            remarks = f"{present_days} Days @ ₹{rate_val}/day"
        elif calc_mode == "per_ot_hour":
            computed_amt = round(flt(total_ot_hours) * rate_val, 2)
            remarks = f"{round(flt(total_ot_hours), 2)} OT Hrs @ ₹{rate_val}/hr"
        elif calc_mode == "percent_gross":
            computed_amt = round(flt(grand_gross_pay) * (rate_val / 100.0), 2)
            remarks = f"{rate_val}% of Gross Pay"
        elif calc_mode == "percent_component":
            target_comps = [str(c).strip().lower() for c in (r.get("selected_components") or []) if str(c).strip()]
            base_amt = 0.0
            if prorated_earnings:
                for e in prorated_earnings:
                    c_name = ((e.get("component_name") or e.get("salary_component") or "").lower() if isinstance(e, dict)
                              else (getattr(e, "component_name", None) or getattr(e, "salary_component", None) or "").lower())
                    if any(tc == c_name or tc in c_name for tc in target_comps):
                        base_amt += flt(e.get("amount", 0.0) if isinstance(e, dict) else getattr(e, "amount", 0.0))
            computed_amt = round(base_amt * (rate_val / 100.0), 2)
            c_label = ", ".join(r.get("selected_components") or ["Selected Components"])
            remarks = f"{rate_val}% of ({c_label})"

        if computed_amt > 0:
            c_name = r.get("name") or f"Custom {comp_type}"
            results.append({
                "component_name": c_name,
                "salary_component": c_name,
                "type": comp_type,
                "standard_amount": 0.0,
                "amount": computed_amt,
                "remarks": remarks
            })

    return results


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
    non_working_dates = []
    working_dates = []
    holiday_desc_map = {}
    holidays_details = []
    non_working_days_details = []
    if holiday_list:
        holiday_doc = frappe.get_doc("Holiday List", holiday_list[0].name)
        for row in holiday_doc.holidays:
            h_date = getdate(row.holiday_date)
            is_declared_holiday = bool(getattr(row, "is_holiday", 0))
            is_work_day = bool(getattr(row, "is_working_day", 1))

            if is_declared_holiday:
                if start_date <= h_date <= end_date:
                    holiday_dates.append(h_date)
                    holiday_desc_map[h_date] = row.description or "Holiday"
                    holidays_details.append({
                        "date": h_date.strftime("%Y-%m-%d"),
                        "description": row.description or "Holiday",
                        "status": "Holiday"
                    })
            elif not is_work_day:
                if start_date <= h_date <= end_date:
                    non_working_dates.append(h_date)
                    non_working_days_details.append({
                        "date": h_date.strftime("%Y-%m-%d"),
                        "description": row.description or h_date.strftime("%A"),
                        "status": "Non Working Day"
                    })
            else:
                if start_date <= h_date <= end_date:
                    working_dates.append(h_date)

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
        month_holiday_dates = [getdate(row.holiday_date) for row in mh_doc.holidays if (bool(getattr(row, "is_holiday", 0)) or not bool(getattr(row, "is_working_day", 1))) and m_start <= getdate(row.holiday_date) <= m_end]

    emp_type = (emp.get("employee_type") or "").lower()
    cat_basis = get_category_setting(settings, "salary_working_days_basis", emp_type)
    cat_fixed_days = flt(get_category_setting(settings, "fixed_working_days", emp_type))
    if "driver" in emp_type:
        month_working_days = cat_fixed_days or 26.0
    elif working_days_basis == "Fixed Number of Days" or (cat_basis and "Fixed" in cat_basis):
        month_working_days = cat_fixed_days or fixed_working_days
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
        is_non_working_day = single_day_date in non_working_dates
        is_scheduled_work_day = single_day_date in working_dates or (not is_holiday and not is_non_working_day)

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
        elif is_non_working_day and physical_val == 0 and comp_off_val == 0 and leave_val == 0:
            components.append("Non Working Day")
            
        absent_val = 0.0
        if is_scheduled_work_day:
            absent_val = round(max(0.0, 1.0 - (physical_val + comp_off_val + leave_val + holiday_val)), 2)
            if absent_val > 0:
                if leave_calc_source != "Via Direct Allocation":
                    components.append(f"Unpaid Leave ({absent_val})" if absent_val < 1.0 else "Unpaid Leave")
                    unpaid_leave_days += absent_val
                    total_leave_days += absent_val
                else:
                    components.append(f"Absent ({absent_val})" if absent_val < 1.0 else "Absent")
                total_absent_days += absent_val
            
        day_status = " + ".join(components) if components else ("Non Working Day" if is_non_working_day else "Absent")
        
        days_breakdown.append({
            "date": single_day_date.strftime("%Y-%m-%d"),
            "status": day_status,
            "is_holiday": is_holiday,
            "is_non_working_day": is_non_working_day,
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
    emp_type = (emp.get("employee_type") or "").lower()
    is_staff = "staff" in emp_type

    bonus_rate = (flt(get_category_setting(settings, "bonus_provision_rate", emp_type, default=8.33)) / 100.0)
    el_days = flt(get_category_setting(settings, "el_provision_days_per_year", emp_type, default=14.0 if is_staff else 15.6))

    # Identify standard basic + DA in employee earnings
    std_basic_da = sum(
        flt(e.amount) for e in emp.earnings
        if any(k in (e.component_name or e.salary_component or "").lower() for k in ["basic", "da", "dearness"])
    )
    if std_basic_da <= 0:
        std_basic_da = flt(emp.total_earnings)

    # Calculate individual components based on period factor (prorated for payable/present days)
    prorated_earnings = []
    base_gross_total = 0.0
    for e in emp.earnings:
        c_name = e.component_name or e.salary_component or ""
        # Skip legacy auto-calculated dynamic components from employee structure
        if c_name in ["Overtime Pay (OT)", "Overtime Allowance", "Attendance Bonus"]:
            continue
        std_val = flt(e.amount)
        if std_val <= 0:
            continue
        item = e.as_dict()
        item["standard_amount"] = std_val
        item["amount"] = excel_round(std_val * period_factor)
        base_gross_total += std_val
        prorated_earnings.append(item)

    if base_gross_total > 0:
        gross_pay = base_gross_total

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

    # 5.2.1. Drivers Fuel Incentive and Referral Bonus
    fuel_incentive = 0.0
    referral_bonus = 0.0
    for e in emp.earnings:
        c_low = (e.component_name or e.salary_component or "").lower().strip()
        if "fuel" in c_low:
            fuel_incentive = flt(e.amount)
        elif "referral" in c_low:
            referral_bonus = flt(e.amount)

    if fuel_incentive > 0 and not any("fuel" in (e.get("component_name") or e.get("salary_component") or "").lower() for e in prorated_earnings):
        prorated_earnings.append({
            "component_name": "Fuel Incentive",
            "salary_component": "Fuel Incentive",
            "type": "Earning",
            "standard_amount": fuel_incentive,
            "amount": fuel_incentive
        })

    if referral_bonus > 0 and not any("referral" in (e.get("component_name") or e.get("salary_component") or "").lower() for e in prorated_earnings):
        prorated_earnings.append({
            "component_name": "Referral Bonus",
            "salary_component": "Referral Bonus",
            "type": "Earning",
            "standard_amount": referral_bonus,
            "amount": referral_bonus
        })

    # 5.3. Calculate Earned Gross Pay (AF6: Earned Gross before dynamic OT/Bonus) & Grand Gross Pay (AK6)
    earned_gross_salary = excel_round(sum(
        flt(e["amount"]) for e in prorated_earnings
        if (e.get("component_name") or e.get("salary_component") or "") not in ["Overtime Pay (OT)", "Overtime Allowance", "Attendance Bonus"]
    ))
    grand_gross_pay = excel_round(sum(flt(e["amount"]) for e in prorated_earnings))

    earned_basic_da = sum(
        flt(e.get("amount", 0)) for e in prorated_earnings 
        if any(k in (e.get("component_name") or e.get("salary_component") or "").lower() for k in ["basic", "da", "dearness"])
    )
    if earned_basic_da <= 0:
        earned_basic_da = earned_gross_salary

    # 5.3.1. Dynamic Annual / Festival Bonus Schemes
    annual_bonus_amt = 0.0
    bonus_schemes_list = []
    bonus_schemes_raw = getattr(settings, "bonus_schemes", None)
    if bonus_schemes_raw:
        if isinstance(bonus_schemes_raw, list):
            bonus_schemes_list = bonus_schemes_raw
        elif isinstance(bonus_schemes_raw, str):
            try:
                bonus_schemes_list = json.loads(bonus_schemes_raw)
            except Exception:
                bonus_schemes_list = []

    current_month_name = start_date.strftime("%B").lower()
    emp_type_lower = (emp_type or "").lower().strip()

    for scheme in bonus_schemes_list:
        is_active = scheme.get("is_active", 1)
        if not (is_active == 1 or is_active is True or is_active == "1"):
            continue
        payout_months = [m.strip().lower() for m in str(scheme.get("payout_month", "")).split(",") if m.strip()]
        if not payout_months and scheme.get("payout_months"):
            raw_pm = scheme.get("payout_months")
            if isinstance(raw_pm, list):
                payout_months = [str(m).strip().lower() for m in raw_pm if m]
        if current_month_name not in payout_months:
            continue

        # Check category match
        scheme_cats = [c.strip().lower().replace("_", " ") for c in scheme.get("categories", [])]
        cat_matches = False
        if not scheme_cats or "all" in scheme_cats or "all categories" in scheme_cats:
            cat_matches = True
        elif "driver" in emp_type_lower and any("driver" in c for c in scheme_cats):
            cat_matches = True
        elif "north indian" in emp_type_lower and any("north indian" in c for c in scheme_cats):
            cat_matches = True
        elif "worker" in emp_type_lower and any("worker" in c and "north" not in c for c in scheme_cats):
            cat_matches = True
        elif "staff" in emp_type_lower:
            if "ctc" in emp_type_lower and "non" not in emp_type_lower and any("ctc" in c and "non" not in c for c in scheme_cats):
                cat_matches = True
            elif ("non-ctc" in emp_type_lower or "non ctc" in emp_type_lower) and any("non" in c for c in scheme_cats):
                cat_matches = True
            elif any("staff" in c for c in scheme_cats):
                cat_matches = True

        if not cat_matches:
            continue

        # Optional Department filter
        scheme_depts = [d.strip().lower() for d in (scheme.get("departments") or []) if d]
        if scheme_depts and "all" not in scheme_depts:
            emp_dept = (getattr(emp, "department", "") or "").strip().lower()
            if not any(d == emp_dept or d in emp_dept for d in scheme_depts):
                continue

        # Optional Designation filter
        scheme_desigs = [d.strip().lower() for d in (scheme.get("designations") or []) if d]
        if scheme_desigs and "all" not in scheme_desigs:
            emp_desig = (getattr(emp, "designation", "") or "").strip().lower()
            if not any(d == emp_desig or d in emp_desig for d in scheme_desigs):
                continue

        calc_method = scheme.get("calc_method", "Percentage of Selected Components")
        pct = flt(scheme.get("percentage") or 8.33)
        ceiling = flt(scheme.get("wage_ceiling") or 0.0)

        if calc_method == "Flat Fixed Amount":
            b_amount = flt(scheme.get("flat_amount", 0.0))
        elif calc_method == "Percentage of Gross":
            base = earned_gross_salary
            if ceiling > 0:
                base = min(base, ceiling)
            b_amount = excel_round(base * (pct / 100.0))
        else:  # Percentage of Selected Components / Percentage of Basic + DA
            custom_components = scheme.get("calculation_components") or scheme.get("components")
            if custom_components and isinstance(custom_components, list) and len(custom_components) > 0:
                norm_custom = [str(c).strip().lower() for c in custom_components if c]
                base = sum(
                    flt(e.get("amount", 0)) for e in prorated_earnings
                    if (e.get("component_name") or e.get("salary_component") or "").strip().lower() in norm_custom
                )
                if base <= 0:
                    base = sum(
                        flt(e.get("amount", 0)) for e in prorated_earnings
                        if any(k in (e.get("component_name") or e.get("salary_component") or "").lower() for k in norm_custom)
                    )
            else:
                base = earned_basic_da

            if base <= 0:
                base = earned_basic_da or earned_gross_salary
            if ceiling > 0:
                base = min(base, ceiling)
            b_amount = excel_round(base * (pct / 100.0))

        if b_amount > 0:
            scheme_title = scheme.get("scheme_name") or "Annual Bonus"
            if not any(scheme_title.lower() in (e.get("component_name") or e.get("salary_component") or "").lower() for e in prorated_earnings):
                prorated_earnings.append({
                    "component_name": scheme_title,
                    "salary_component": scheme_title,
                    "type": "Earning",
                    "standard_amount": b_amount,
                    "amount": b_amount
                })
                annual_bonus_amt += b_amount

    # 5.3.2. Automated Leave Encashment / Payout
    leave_encashment_total = 0.0
    try:
        encashable_leave_types = frappe.get_all(
            "Leave Type",
            filters={"is_encashable": 1, "status": "Active"},
            fields=[
                "name", "leave_type_name", "encashment_cycles", "encashment_payout_months",
                "encashment_rate_basis", "encashment_component_name"
            ]
        )
    except Exception:
        encashable_leave_types = []

    month_name_to_num = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }

    for lt in encashable_leave_types:
        cycles = []
        if lt.get("encashment_cycles"):
            try:
                raw_cycles = json.loads(lt.encashment_cycles)
                if isinstance(raw_cycles, list):
                    cycles = raw_cycles
            except Exception:
                cycles = []

        # Fallback for legacy configurations using encashment_payout_months
        if not cycles:
            p_months = [m.strip() for m in str(lt.encashment_payout_months or "June, December").split(",") if m.strip()]
            if len(p_months) >= 2:
                cycles = [
                    {"from_month": "January", "to_month": "June", "payout_months": [p_months[0]]},
                    {"from_month": "July", "to_month": "December", "payout_months": [p_months[1]]}
                ]
            elif len(p_months) == 1:
                cycles = [
                    {"from_month": "January", "to_month": "December", "payout_months": p_months}
                ]
            else:
                cycles = [
                    {"from_month": "January", "to_month": "June", "payout_months": ["June"]},
                    {"from_month": "July", "to_month": "December", "payout_months": ["December"]}
                ]

        for cycle in cycles:
            c_payout_months = cycle.get("payout_months") or ([cycle.get("payout_month")] if cycle.get("payout_month") else [])
            normalized_p_months = [str(m).strip().lower() for m in c_payout_months if m]
            if current_month_name not in normalized_p_months:
                continue

            from_m_str = str(cycle.get("from_month") or "January").strip().lower()
            to_m_str = str(cycle.get("to_month") or "June").strip().lower()
            start_m = month_name_to_num.get(from_m_str, 1)
            end_m = month_name_to_num.get(to_m_str, 6)

            slip_year = start_date.year
            if start_m <= end_m:
                if start_date.month < start_m:
                    from_year = slip_year - 1
                    to_year = slip_year - 1
                else:
                    from_year = slip_year
                    to_year = slip_year
            else:
                # Financial year cross (e.g. Apr to Mar)
                if start_date.month <= end_m:
                    from_year = slip_year - 1
                    to_year = slip_year
                else:
                    from_year = slip_year
                    to_year = slip_year + 1

            last_day = monthrange(to_year, end_m)[1]
            cycle_start = f"{from_year}-{start_m:02d}-01"
            cycle_end = f"{to_year}-{end_m:02d}-{last_day:02d}"

            # Encashment strictly based on Leave Allocation doctype (No fixed monthly quota)
            alloc_res = frappe.db.sql("""
                SELECT COALESCE(SUM(total_leaves_allocated), 0), COALESCE(SUM(total_leaves_taken), 0)
                FROM `tabLeave Allocation`
                WHERE employee = %s
                  AND (leave_type = %s OR leave_type IN (SELECT name FROM `tabLeave Type` WHERE leave_type_name = %s))
                  AND status = 'Approved'
                  AND (
                      (from_date >= %s AND to_date <= %s)
                      OR (from_date <= %s AND to_date >= %s)
                  )
            """, (emp.name, lt.name, lt.leave_type_name or lt.name, cycle_start, cycle_end, cycle_end, cycle_start))

            total_alloc = flt(alloc_res[0][0]) if alloc_res else 0.0
            alloc_taken = flt(alloc_res[0][1]) if alloc_res else 0.0

            actual_leaves_taken = get_leaves_taken_in_period(emp.name, lt.name, cycle_start, cycle_end)
            leaves_taken = max(alloc_taken, actual_leaves_taken)

            payable_days = max(0.0, total_alloc - leaves_taken)
            if payable_days <= 0:
                continue

            # Rate basis
            r_basis = (lt.encashment_rate_basis or "Gross / 26").lower()
            if "basic" in r_basis and "da" in r_basis:
                daily_rate = flt(earned_basic_da) / 26.0
            elif "basic" in r_basis:
                daily_rate = flt(earned_basic_da) / 26.0
            elif "calendar" in r_basis:
                daily_rate = flt(gross_pay) / max(1.0, flt(calendar_days))
            else:
                daily_rate = flt(gross_pay) / 26.0

            payout_amt = excel_round(payable_days * daily_rate)
            if payout_amt > 0:
                c_label = lt.encashment_component_name or f"{lt.leave_type_name or lt.name} Payout"
                if not any(c_label.lower() in (e.get("component_name") or e.get("salary_component") or "").lower() for e in prorated_earnings):
                    prorated_earnings.append({
                        "component_name": c_label,
                        "salary_component": c_label,
                        "type": "Earning",
                        "standard_amount": payout_amt,
                        "amount": payout_amt
                    })
                    leave_encashment_total += payout_amt

    canteen_entries = []
    canteen_meals_count = 0
    emp_id_val = getattr(emp, "employee_id", None) or (emp.get("employee_id") if isinstance(emp, dict) else "") or emp.name
    enable_lunch = cint(get_category_setting(settings, "enable_lunch_allowance", emp_type, default=1))
    enable_emp_canteen = cint(get_category_setting(settings, "enable_employee_canteen_deduction", emp_type, default=0))
    if (enable_emp_canteen or enable_lunch or getattr(settings, "custom_salary_component_rules", None)) and (frappe.db.table_exists("Canteen Entry") or frappe.db.exists("DocType", "Canteen Entry")):
        canteen_entries = frappe.db.sql(
            """
            SELECT name, canteen_date, meal_type, meal_count, status, source, remarks
            FROM `tabCanteen Entry`
            WHERE (employee = %s OR employee = %s)
              AND canteen_date BETWEEN %s AND %s
            ORDER BY canteen_date ASC
            """,
            (emp.name, emp_id_val, start_date, end_date),
            as_dict=True
        )
        canteen_meals_count = sum(flt(e.get("meal_count") or 1) for e in canteen_entries)

    # Custom Earning Rules (e.g. Festival Bonus, Production Incentive, Daily Allowance)
    custom_earnings = evaluate_custom_salary_rules(
        getattr(settings, "custom_salary_component_rules", None),
        "Earning", emp, emp_type, start_date, end_date,
        present_days, total_ot_hours, gross_pay, earned_basic_da, canteen_meals_count,
        prorated_earnings=prorated_earnings
    )
    for ce in custom_earnings:
        prorated_earnings.append(ce)

    # Recalculate Grand Gross Pay including Bonus, Leave Encashment & Custom Earnings
    grand_gross_pay = excel_round(sum(flt(e["amount"]) for e in prorated_earnings))


    # 5.5. Deductions & Professional Tax, PF, ESI, LWF
    pt_amount = calculate_professional_tax(grand_gross_pay, start_date, settings, employee=emp.name, emp_doc=emp)
    emp_pf = calculate_employee_pf(emp, earned_gross_salary, earned_basic_da, settings, prorated_earnings=prorated_earnings)
    emp_esi = calculate_employee_esi(emp, grand_gross_pay, earned_gross_salary, settings)
    tentative_net = max(0.0, grand_gross_pay - (flt(pt_amount) + flt(emp_pf or 0) + flt(emp_esi or 0) + sum(flt(d.amount) for d in emp.deductions if not any(k in (d.component_name or d.salary_component or "").lower() for k in ["prof", "pt", "pf", "esi", "lwf"]))))
    emp_lwf, empr_lwf, is_lwf_eligible = calculate_lwf(emp, grand_gross_pay, start_date, settings, employee_id=emp.name, prorated_earnings=prorated_earnings, net_pay=tentative_net)

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
        elif any(k in c_lower for k in ["lwf", "labour welfare fund", "welfare fund"]):
            item["amount"] = emp_lwf
        else:
            item["amount"] = flt(d.amount)

        if flt(item.get("amount", 0)) <= 0 and flt(item.get("standard_amount", 0)) <= 0:
            continue

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

    # If LWF wasn't in employee structure but emp_lwf > 0, add it
    has_lwf = any(any(k in (d.get("component_name") or d.get("salary_component") or "").lower() for k in ["lwf", "labour welfare fund", "welfare fund"]) for d in prorated_deductions)
    if not has_lwf and emp_lwf > 0:
        prorated_deductions.append({
            "component_name": "Labour Welfare Fund",
            "salary_component": "Labour Welfare Fund",
            "type": "Deduction",
            "standard_amount": 0.0,
            "amount": emp_lwf,
            "is_statutory": 1
        })

    # Employee Tea & Canteen Deductions
    enable_emp_tea = cint(get_category_setting(settings, "enable_employee_tea_deduction", emp_type, default=0))
    emp_tea_rate = flt(get_category_setting(settings, "employee_tea_deduction_per_day", emp_type, default=0.0))
    emp_tea_deduction = float(round(flt(present_days) * emp_tea_rate, 2)) if enable_emp_tea else 0.0

    enable_emp_canteen = cint(get_category_setting(settings, "enable_employee_canteen_deduction", emp_type, default=0))
    emp_canteen_rate = flt(get_category_setting(settings, "employee_canteen_deduction_per_meal", emp_type, default=0.0))

    # Fetch Canteen entries if canteen deduction or lunch allowance is enabled
    enable_lunch = cint(get_category_setting(settings, "enable_lunch_allowance", emp_type, default=1))
    if not canteen_entries and (enable_emp_canteen or enable_lunch) and (frappe.db.table_exists("Canteen Entry") or frappe.db.exists("DocType", "Canteen Entry")):
        canteen_entries = frappe.db.sql(
            """
            SELECT name, canteen_date, meal_type, meal_count, status, source, remarks
            FROM `tabCanteen Entry`
            WHERE (employee = %s OR employee = %s)
              AND canteen_date BETWEEN %s AND %s
            ORDER BY canteen_date ASC
            """,
            (emp.name, emp_id_val, start_date, end_date),
            as_dict=True
        )
        canteen_meals_count = sum(flt(e.get("meal_count") or 1) for e in canteen_entries)

    emp_canteen_deduction = float(round(flt(canteen_meals_count) * emp_canteen_rate, 2)) if enable_emp_canteen else 0.0

    # Add Tea Deduction to deductions child table
    has_tea_ded = False
    for d in prorated_deductions:
        c_name = (d.get("component_name") or d.get("salary_component") or "").lower()
        if "tea" in c_name and ("deduction" in c_name or "expense" in c_name):
            has_tea_ded = True
            if enable_emp_tea:
                d["amount"] = emp_tea_deduction
            break
    if not has_tea_ded and emp_tea_deduction > 0:
        prorated_deductions.append({
            "component_name": "Tea Deduction",
            "salary_component": "Tea Deduction",
            "type": "Deduction",
            "standard_amount": 0.0,
            "amount": emp_tea_deduction
        })

    # Add Canteen Deduction to deductions child table
    has_canteen_ded = False
    for d in prorated_deductions:
        c_name = (d.get("component_name") or d.get("salary_component") or "").lower()
        if ("canteen" in c_name or "lunch" in c_name or "mess" in c_name) and ("deduction" in c_name or "expense" in c_name):
            has_canteen_ded = True
            if enable_emp_canteen:
                d["amount"] = emp_canteen_deduction
            break
    if not has_canteen_ded and emp_canteen_deduction > 0:
        prorated_deductions.append({
            "component_name": "Canteen Deduction",
            "salary_component": "Canteen Deduction",
            "type": "Deduction",
            "standard_amount": 0.0,
            "amount": emp_canteen_deduction
        })

    # Custom Deduction Rules (e.g. Uniform Deduction, Safety Shoes, Tool Recovery)
    custom_deductions = evaluate_custom_salary_rules(
        getattr(settings, "custom_salary_component_rules", None),
        "Deduction", emp, emp_type, start_date, end_date,
        present_days, total_ot_hours, grand_gross_pay, earned_basic_da, canteen_meals_count,
        prorated_earnings=prorated_earnings
    )
    for cd in custom_deductions:
        prorated_deductions.append(cd)

    # LOP amount for informational and display breakdown purposes
    lop_amount = excel_round(gross_pay * (lop_days / month_working_days)) if month_working_days else 0.0
    
    total_deductions = excel_round(sum(flt(d["amount"]) for d in prorated_deductions))
    grand_net_pay = excel_round(grand_gross_pay - total_deductions)

    # 5.6. Employer Statutory Contributions & Total Monthly Cost to Company (CTC)
    pf_rate = flt(get_category_setting(settings, "employer_pf_rate", emp_type, default=12.0)) / 100.0
    pf_admin_rate = flt(get_category_setting(settings, "pf_admin_rate", emp_type, default=0.5)) / 100.0
    edli_rate = flt(get_category_setting(settings, "edli_rate", emp_type, default=0.5)) / 100.0
    esi_rate = flt(get_category_setting(settings, "employer_esi_rate", emp_type, default=3.25)) / 100.0
    employer_pf_ceiling = flt(get_category_setting(settings, "employer_pf_wage_ceiling", emp_type, default=(get_category_setting(settings, "pf_wage_ceiling", emp_type, default=15000.0))))
    employer_max_pf = flt(get_category_setting(settings, "employer_pf_max_amount", emp_type, default=(employer_pf_ceiling * pf_rate if employer_pf_ceiling > 0 else 1800.0)))
    esi_ceiling = flt(get_category_setting(settings, "esi_wage_ceiling", emp_type, default=21000.0))
    
    # Dynamic PF base for Employer
    pf_basis_raw = get_category_setting(settings, "pf_wage_basis", emp_type)
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

    enable_bonus = cint(get_category_setting(settings, "enable_bonus_provision", emp_type, default=1))
    bonus_rate = (flt(get_category_setting(settings, "bonus_provision_rate", emp_type, default=8.33)) / 100.0) if enable_bonus else 0.0
    enable_el = cint(get_category_setting(settings, "enable_el_provision", emp_type, default=1))
    el_days = flt(get_category_setting(settings, "el_provision_days_per_year", emp_type, default=15.6)) if enable_el else 0.0

    enable_pf = cint(get_category_setting(settings, "enable_auto_pf", emp_type, default=1))
    pf_no = emp.get("pf_number") if hasattr(emp, "get") else getattr(emp, "pf_number", None)
    has_pf_component = False
    if hasattr(emp, "deductions") and emp.deductions:
        for d in emp.deductions:
            c_name = (d.component_name or d.salary_component or "").lower() if hasattr(d, "component_name") else (d.get("component_name") or d.get("salary_component") or "").lower()
            if any(k in c_name for k in ["pf", "provident fund", "epf"]) and "employer" not in c_name and "admin" not in c_name:
                has_pf_component = True
                break

    if not enable_pf or (not pf_no and not has_pf_component):
        employer_pf = 0.0
        pf_admin_charges = 0.0
        edli_charges = 0.0
    else:
        if employer_pf_ceiling > 0 and pf_base_for_employer >= employer_pf_ceiling:
            employer_pf = float(round(employer_max_pf))
        else:
            employer_pf = float(round(pf_base_for_employer * pf_rate))
        
        # Determine PF Admin & EDLI wage basis dynamically from settings
        is_ctc_staff = "ctc" in (emp_type or "").lower() and "non" not in (emp_type or "").lower()
        admin_edli_basis = get_category_setting(settings, "pf_admin_edli_basis", emp_type, default=None)
        if is_ctc_staff or not admin_edli_basis:
            if not is_ctc_staff and ("non ctc" in (emp_type or "").lower() or "non-ctc" in (emp_type or "").lower()):
                admin_edli_basis = "Percentage of Gross Salary"
            else:
                admin_edli_basis = "Statutory PF Wage (Capped at Ceiling)"

        if admin_edli_basis == "Percentage of Gross Salary":
            gross_pct = flt(get_category_setting(settings, "pf_admin_edli_gross_percent", emp_type))
            pf_statutory_base = round(flt(grand_gross_pay) * (gross_pct / 100.0), 2)
        elif admin_edli_basis == "Actual PF Wage (Uncapped)":
            pf_statutory_base = pf_base_for_employer
        else:
            # Statutory EPFO cap on EDLI and Admin Charges (₹15,000 ceiling -> max ₹75.00 each)
            admin_cap = employer_pf_ceiling if employer_pf_ceiling > 0 else 15000.0
            pf_statutory_base = min(pf_base_for_employer, admin_cap)

        pf_admin_charges = excel_round(pf_statutory_base * pf_admin_rate)
        edli_charges = excel_round(pf_statutory_base * edli_rate)

    enable_esi = cint(get_category_setting(settings, "enable_auto_esi", emp_type, default=1))
    esi_no = emp.get("esi_no") if hasattr(emp, "get") else getattr(emp, "esi_no", None)
    has_esi_component = False
    if hasattr(emp, "deductions") and emp.deductions:
        for d in emp.deductions:
            c_name = (d.component_name or d.salary_component or "").lower() if hasattr(d, "component_name") else (d.get("component_name") or d.get("salary_component") or "").lower()
            if any(k in c_name for k in ["esi", "esic"]) and "employer" not in c_name:
                has_esi_component = True
                break

    if not enable_esi or (not esi_no and not has_esi_component) or (esi_ceiling > 0 and earned_gross_salary > esi_ceiling and grand_gross_pay > esi_ceiling):
        employer_esi = 0.0
    else:
        esi_rounding = get_category_setting(settings, "esi_rounding_method", emp_type, default="Round Up to Next Rupee (ROUNDUP / CEIL)")
        raw_employer_esi = flt(grand_gross_pay) * esi_rate
        if "Round Up" in esi_rounding or "ROUNDUP" in esi_rounding or "CEIL" in esi_rounding:
            employer_esi = float(math.ceil(raw_employer_esi))
        else:
            employer_esi = excel_round(raw_employer_esi)

    is_staff = "staff" in (emp_type or "").lower()
    enable_tea = cint(get_category_setting(settings, "enable_tea_allowance", emp_type, default=1))
    tea_rate_default = 14.0 if is_staff else 5.0
    tea_rate_val = get_category_setting(settings, "tea_allowance_per_day", emp_type, default=None)
    if tea_rate_val is None or tea_rate_val == "":
        tea_rate = tea_rate_default
    else:
        tea_rate = flt(tea_rate_val)
    tea_expenses = float(round(flt(present_days) * tea_rate)) if enable_tea else 0.0

    enable_lunch = cint(get_category_setting(settings, "enable_lunch_allowance", emp_type, default=1))
    lunch_rate_val = get_category_setting(settings, "lunch_allowance_per_meal", emp_type, default=None)
    if lunch_rate_val is None or lunch_rate_val == "":
        lunch_rate_val = get_category_setting(settings, "lunch_allowance_per_day", emp_type, default=None)
    lunch_rate = flt(lunch_rate_val) if (lunch_rate_val is not None and lunch_rate_val != "") else 50.0

    if not canteen_entries and enable_lunch and (frappe.db.table_exists("Canteen Entry") or frappe.db.exists("DocType", "Canteen Entry")):
        canteen_entries = frappe.db.sql(
            """
            SELECT name, canteen_date, meal_type, meal_count, status, source, remarks
            FROM `tabCanteen Entry`
            WHERE (employee = %s OR employee = %s)
              AND canteen_date BETWEEN %s AND %s
            ORDER BY canteen_date ASC
            """,
            (emp.name, emp_id_val, start_date, end_date),
            as_dict=True
        )
        canteen_meals_count = sum(flt(e.get("meal_count") or 1) for e in canteen_entries)

    lunch_expenses = float(round(canteen_meals_count * lunch_rate)) if enable_lunch else 0.0

    # Earned CTC = Gross Earnings + Employer PF + EDLI + Admin + Employer ESI + Employer LWF
    earned_ctc = round(grand_gross_pay + employer_pf + pf_admin_charges + edli_charges + employer_esi + empr_lwf, 2)
    total_employer_contrib = round(employer_pf + pf_admin_charges + edli_charges + employer_esi + empr_lwf, 2)

    has_bonus_in_earnings = any(
        "bonus" in ((e.get("component_name") or e.get("salary_component") or "").lower())
        for e in prorated_earnings
        if "attendance" not in ((e.get("component_name") or e.get("salary_component") or "").lower())
    )
    has_el_in_earnings = any(
        any(k in ((e.get("component_name") or e.get("salary_component") or "").lower()) for k in ["earned leave", "el"])
        for e in prorated_earnings
    )

    if has_bonus_in_earnings or "staff" in emp_type:
        bonus_provision = 0.0
    else:
        bonus_provision = float(round(earned_gross_salary * bonus_rate)) if enable_bonus else 0.0

    if has_el_in_earnings or "staff" in emp_type:
        el_provision = 0.0
    else:
        el_provision = float(round((earned_gross_salary / 26.0) * (el_days / 12.0))) if (enable_el and month_working_days) else 0.0
    total_monthly_ctc = round(earned_ctc + tea_expenses + lunch_expenses + bonus_provision + el_provision, 2)

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
        "pf_number": getattr(emp, "pf_number", None) or "",
        "pf_no": getattr(emp, "pf_number", None) or "",
        "uan_number": getattr(emp, "uan_number", None) or "",
        "pf_uan": getattr(emp, "uan_number", None) or getattr(emp, "pf_number", None) or "",
        "esi_no": getattr(emp, "esi_no", None) or "",
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
        "fuel_incentive": fuel_incentive,
        "referral_bonus": referral_bonus,
        "annual_bonus": annual_bonus_amt,
        "leave_encashment_amount": leave_encashment_total,
        "tea_allowance": 0.0,
        "pt_amount": pt_amount,
        "tea_deduction": emp_tea_deduction,
        "canteen_deduction": emp_canteen_deduction,
        "employee_tea_rate": emp_tea_rate,
        "employee_canteen_rate": emp_canteen_rate,
        "enable_employee_tea_deduction": enable_emp_tea,
        "enable_employee_canteen_deduction": enable_emp_canteen,
        "earnings": prorated_earnings,
        "deductions": prorated_deductions,
        # Employer Contributions & CTC
        "employer_pf": employer_pf,
        "pf_admin_charges": pf_admin_charges,
        "edli_charges": edli_charges,
        "employer_esi": employer_esi,
        "employer_lwf": empr_lwf,
        "employee_lwf": emp_lwf,
        "lwf_eligible": 1 if is_lwf_eligible else 0,
        "earned_ctc": earned_ctc,
        "tea_expenses": tea_expenses,
        "lunch_expenses": lunch_expenses,
        "total_employer_contribution": total_employer_contrib,
        "bonus_provision": bonus_provision,
        "el_provision": el_provision,
        "total_monthly_ctc": total_monthly_ctc,
        "total_ctc": total_monthly_ctc,
        "employer_pf_rate": round(pf_rate * 100.0, 2),
        "pf_admin_rate": round(pf_admin_rate * 100.0, 2),
        "edli_rate": round(edli_rate * 100.0, 2),
        "employer_esi_rate": round(esi_rate * 100.0, 2),
        "esi_wage_ceiling": esi_ceiling,
        "employer_pf_wage_ceiling": employer_pf_ceiling,
        "enable_bonus_provision": enable_bonus,
        "bonus_provision_rate": round(bonus_rate * 100.0, 2) if enable_bonus else 0.0,
        "enable_el_provision": enable_el,
        "el_provision_days_per_year": el_days if enable_el else 0.0,
        "has_bonus_in_earnings": has_bonus_in_earnings,
        "has_el_in_earnings": has_el_in_earnings,
        "enable_workers_tea_allowance": enable_tea,
        "workers_tea_allowance_per_day": round(tea_rate, 2),
        "enable_lunch_allowance": enable_lunch,
        "lunch_allowance_per_meal": round(lunch_rate, 2),
        "lunch_rate": lunch_rate,
        "lunch_count": canteen_meals_count,
        "canteen_meals_count": canteen_meals_count,
        "canteen_entries_details": canteen_entries,
        # Detailed Breakdown Fields
        "total_days_in_period": total_days,
        "holiday_count": len(holiday_dates),
        "non_working_count": len(non_working_dates),
        "holiday_working_days": len(working_dates) if holiday_list else (total_days - len(holiday_dates)),
        "holidays_details": holidays_details,
        "non_working_days_details": non_working_days_details,
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
        "bank_account": emp.bank_account or "",
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
                "bank_account": emp.bank_account,
                "bank_account_name": ba.bank_account_name or "",
                "account_number": ba.account_number or "",
                "bank_name": ba.bank_name or "",
                "branch": ba.branch or "",
                "ifsc_code": ba.ifsc_code or "",
            })
        except frappe.DoesNotExistError:
            pass

    # Attach dynamic cycle-based leave balances
    leave_info = get_employee_leave_balances(employee, start_date, end_date)
    res["leave_balances"] = leave_info["balances"]
    res["cl_cycle_period"] = leave_info.get("cl_cycle_period", "")
    res["cl_allocated"] = leave_info["cl_allocated"]
    res["cl_taken"] = leave_info["cl_taken"]
    res["cl_balance"] = leave_info["cl_balance"]
    res["leave_details"] = json.dumps(leave_info["balances"])

    return res


@frappe.whitelist()
def get_salary_slip_with_details(name):
    """
    Fetch Salary Slip document and enrich it with dynamic Employee details (like bank info)
    and a per-day days_breakdown identical to the one produced by preview_salary_slip.
    """
    doc = frappe.get_doc("Salary Slip", name)
    res = doc.as_dict()
    settings = frappe.get_single("HRMS Settings")
    emp_type = (doc.employee_type or res.get("employee_type") or "").lower()

    # Strictly read from Salary Slip document snapshot (no live override from Employee)
    res.update({
        "father_husband_name": getattr(doc, "father_husband_name", None) or "",
        "employee_type": getattr(doc, "employee_type", None) or "",
        "personal_email": getattr(doc, "personal_email", None) or "",
        "department": getattr(doc, "department", None) or "",
        "designation": getattr(doc, "designation", None) or "",
        "date_of_joining": getattr(doc, "date_of_joining", None) or "",
        "pf_number": getattr(doc, "pf_no", None) or "",
        "pf_no": getattr(doc, "pf_no", None) or "",
        "uan_number": getattr(doc, "uan_number", None) or "",
        "esi_no": getattr(doc, "esi_no", None) or "",
        "bank_account_name": "",
        "account_number": "",
        "bank_name": "",
        "branch": "",
        "ifsc_code": "",
    })

    bank_ref = getattr(doc, "bank_account", None)
    if bank_ref:
        try:
            ba = frappe.get_doc("Bank Account", bank_ref)
            res.update({
                "bank_account_name": ba.bank_account_name or "",
                "account_number": ba.account_number or "",
                "bank_name": ba.bank_name or "",
                "branch": ba.branch or "",
                "ifsc_code": ba.ifsc_code or "",
            })
        except frappe.DoesNotExistError:
            pass

    emp_earnings_map = {}
    emp_deductions_map = {}
    base_gross_total = 0.0
    base_deductions_total = 0.0
    std_basic_da = 0.0

    emp = None
    if doc.employee:
        try:
            emp = frappe.get_doc("Employee", doc.employee)
            emp_earnings_map = { (e.component_name or e.salary_component or ""): flt(e.amount) for e in emp.earnings }
            emp_deductions_map = { (d.component_name or d.salary_component or ""): flt(d.amount) for d in emp.deductions }
            std_basic_da = sum(
                flt(e.amount) for e in emp.earnings
                if any(k in (e.component_name or e.salary_component or "").lower() for k in ["basic", "da", "dearness"])
            )
            base_gross_total = round(sum(flt(e.amount) for e in emp.earnings), 2)
            base_deductions_total = round(sum(flt(d.amount) for d in emp.deductions), 2)
        except Exception:
            pass

    bonus_rate = (flt(get_category_setting(settings, "bonus_provision_rate", emp_type, default=8.33)) / 100.0)
    el_days = flt(get_category_setting(settings, "el_provision_days_per_year", emp_type, default=14.0 if ("staff" in emp_type) else 15.6))

    enriched_earnings = []
    for e in doc.earnings:
        item = e.as_dict()
        c_name = e.component_name or e.salary_component or ""
        std_val = emp_earnings_map.get(c_name, 0.0)

        if flt(e.amount) <= 0 and std_val <= 0:
            continue

        item["standard_amount"] = std_val
        enriched_earnings.append(item)
    res["earnings"] = enriched_earnings

    enriched_deductions = []
    for d in doc.deductions:
        item = d.as_dict()
        c_name = d.component_name or d.salary_component or ""
        std_val = emp_deductions_map.get(c_name, 0.0)

        if flt(d.amount) <= 0 and std_val <= 0:
            continue

        item["standard_amount"] = std_val
        enriched_deductions.append(item)
    res["deductions"] = enriched_deductions

    computed_base_gross = sum(
        flt(e["standard_amount"]) for e in enriched_earnings
        if (e.get("component_name") or e.get("salary_component") or "") not in ["Overtime Pay (OT)", "Overtime Allowance", "Attendance Bonus"]
    )
    res["base_gross_pay"] = computed_base_gross or base_gross_total or sum(
        flt(e.amount) for e in doc.earnings
        if (e.component_name or e.salary_component or "") not in ["Overtime Pay (OT)", "Overtime Allowance", "Attendance Bonus"]
    )
    res["base_total_deduction"] = base_deductions_total
    res["base_net_pay"] = res["base_gross_pay"] - res["base_total_deduction"]

    # ── Employer Contributions & CTC ──────────────────────────────────────────
    emp_type = (res.get("employee_type") or "").lower()
    gross_val = flt(getattr(doc, "grand_gross_pay", None) or getattr(doc, "gross_pay", None) or 0.0)
    grand_gross_val = gross_val
    start_date = getdate(getattr(doc, "start_date", None) or getattr(doc, "pay_period_start", None) or getattr(doc, "posting_date", None) or frappe.utils.nowdate())
    is_lwf_eligible = False
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
    pf_rate = flt(get_category_setting(settings, "employer_pf_rate", emp_type, default=12.0)) / 100.0
    pf_admin_rate = flt(get_category_setting(settings, "pf_admin_rate", emp_type, default=0.5)) / 100.0
    edli_rate = flt(get_category_setting(settings, "edli_rate", emp_type, default=0.5)) / 100.0
    esi_rate = flt(get_category_setting(settings, "employer_esi_rate", emp_type, default=3.25)) / 100.0
    employer_pf_ceiling = flt(get_category_setting(settings, "employer_pf_wage_ceiling", emp_type, default=(get_category_setting(settings, "pf_wage_ceiling", emp_type, default=15000.0))))
    employer_max_pf = flt(get_category_setting(settings, "employer_pf_max_amount", emp_type, default=(employer_pf_ceiling * pf_rate if employer_pf_ceiling > 0 else 1800.0)))
    esi_ceiling = flt(get_category_setting(settings, "esi_wage_ceiling", emp_type, default=21000.0))
    pf_basis_raw = get_category_setting(settings, "pf_wage_basis", emp_type)
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

    enable_bonus = cint(get_category_setting(settings, "enable_bonus_provision", emp_type, default=1))
    bonus_rate = (flt(get_category_setting(settings, "bonus_provision_rate", emp_type, default=8.33)) / 100.0) if enable_bonus else 0.0
    enable_el = cint(get_category_setting(settings, "enable_el_provision", emp_type, default=1))
    el_days = flt(get_category_setting(settings, "el_provision_days_per_year", emp_type, default=15.6)) if enable_el else 0.0

    is_staff = "staff" in (emp_type or "").lower()
    tea_rate_default = 14.0 if is_staff else 5.0
    tea_rate_val = get_category_setting(settings, "tea_allowance_per_day", emp_type, default=None)
    if tea_rate_val is None or tea_rate_val == "":
        tea_rate = tea_rate_default
    else:
        tea_rate = flt(tea_rate_val)

    earnings_list = doc.earnings if hasattr(doc, "earnings") else []
    has_bonus_in_earnings = any(
        "bonus" in ((getattr(e, "component_name", None) or getattr(e, "salary_component", None) or (e.get("component_name") if isinstance(e, dict) else "") or "").lower())
        for e in earnings_list
        if "attendance" not in ((getattr(e, "component_name", None) or getattr(e, "salary_component", None) or (e.get("component_name") if isinstance(e, dict) else "") or "").lower())
    )
    has_el_in_earnings = any(
        any(k in ((getattr(e, "component_name", None) or getattr(e, "salary_component", None) or (e.get("component_name") if isinstance(e, dict) else "") or "").lower()) for k in ["earned leave", "el"])
        for e in earnings_list
    )

    # Check if this document already has preserved CTC / employer contributions / expenses
    has_saved_ctc = (
        flt(getattr(doc, "earned_ctc", 0)) > 0
        or flt(getattr(doc, "total_monthly_ctc", 0)) > 0
        or flt(getattr(doc, "total_employer_contribution", 0)) > 0
        or flt(getattr(doc, "employer_pf", 0)) > 0
        or flt(getattr(doc, "employer_esi", 0)) > 0
        or flt(getattr(doc, "tea_expenses", 0)) > 0
        or flt(getattr(doc, "lunch_expenses", 0)) > 0
        or doc.docstatus >= 1
    )

    if has_saved_ctc:
        # Strictly preserve the saved document snapshot values
        employer_pf = flt(getattr(doc, "employer_pf", 0.0))
        pf_admin_charges = flt(getattr(doc, "pf_admin_charges", 0.0))
        edli_charges = flt(getattr(doc, "edli_charges", 0.0))
        employer_esi = flt(getattr(doc, "employer_esi", 0.0))
        employer_lwf = flt(getattr(doc, "employer_lwf", 0.0))
        employee_lwf = flt(getattr(doc, "employee_lwf", 0.0))
        total_employer_contrib = flt(getattr(doc, "total_employer_contribution", 0.0)) or round(employer_pf + pf_admin_charges + edli_charges + employer_esi + employer_lwf, 2)
        tea_expenses = flt(getattr(doc, "tea_expenses", 0.0))
        lunch_expenses = flt(getattr(doc, "lunch_expenses", 0.0))
        canteen_meals_count = flt(getattr(doc, "canteen_meals_count", 0.0))

        if getattr(doc, "lunch_rate", None) is not None and flt(doc.lunch_rate) > 0:
            lunch_rate = flt(doc.lunch_rate)
        else:
            lunch_rate_val = get_category_setting(settings, "lunch_allowance_per_meal", emp_type, default=None)
            if lunch_rate_val is None or lunch_rate_val == "":
                lunch_rate_val = get_category_setting(settings, "lunch_allowance_per_day", emp_type, default=None)
            lunch_rate = flt(lunch_rate_val) if (lunch_rate_val is not None and lunch_rate_val != "") else 50.0

        bonus_provision = flt(getattr(doc, "bonus_provision", 0.0))
        el_provision = flt(getattr(doc, "el_provision", 0.0))
        earned_ctc = flt(getattr(doc, "earned_ctc", 0.0)) or round(gross_val + total_employer_contrib, 2)
        total_monthly_ctc = flt(getattr(doc, "total_monthly_ctc", 0.0)) or round(earned_ctc + tea_expenses + lunch_expenses + bonus_provision + el_provision, 2)

        enable_tea = 1 if tea_expenses > 0 else cint(get_category_setting(settings, "enable_tea_allowance", emp_type, default=1))
        enable_lunch = 1 if (lunch_expenses > 0 or canteen_meals_count > 0) else cint(get_category_setting(settings, "enable_lunch_allowance", emp_type, default=1))

        # Query canteen entries history for display purposes only
        canteen_entries = []
        emp_name = getattr(doc, "employee", None) or (emp.get("name") if emp else None)
        emp_id = getattr(doc, "employee_id", None) or (getattr(emp, "employee_id", None) if emp else None) or emp_name
        p_start = getattr(doc, "pay_period_start", None)
        p_end = getattr(doc, "pay_period_end", None)

        if (enable_lunch or lunch_expenses > 0 or canteen_meals_count > 0) and emp_name and p_start and p_end and (frappe.db.table_exists("Canteen Entry") or frappe.db.exists("DocType", "Canteen Entry")):
            canteen_entries = frappe.db.sql(
                """
                SELECT name, canteen_date, meal_type, meal_count, status, source, remarks
                FROM `tabCanteen Entry`
                WHERE (employee = %s OR employee = %s)
                  AND canteen_date BETWEEN %s AND %s
                ORDER BY canteen_date ASC
                """,
                (emp_name, emp_id, p_start, p_end),
                as_dict=True
            )
            if canteen_meals_count == 0 and canteen_entries and lunch_expenses > 0:
                canteen_meals_count = sum(flt(e.get("meal_count") or 1) for e in canteen_entries)
    else:
        # Fallback dynamic calculation for legacy drafts that were saved before CTC implementation
        enable_pf = cint(get_category_setting(settings, "enable_auto_pf", emp_type, default=1))
        pf_no = getattr(doc, "pf_number", None) or (emp.get("pf_number") if emp else None)
        has_pf_component = False
        if hasattr(doc, "deductions") and doc.deductions:
            for d in doc.deductions:
                c_name = (d.component_name or d.salary_component or "").lower() if hasattr(d, "component_name") else (d.get("component_name") or d.get("salary_component") or "").lower()
                if any(k in c_name for k in ["pf", "provident fund", "epf"]) and "employer" not in c_name and "admin" not in c_name:
                    has_pf_component = True
                    break

        if not enable_pf or (not pf_no and not has_pf_component):
            employer_pf = 0.0
            pf_admin_charges = 0.0
            edli_charges = 0.0
        else:
            if employer_pf_ceiling > 0 and pf_base_for_employer >= employer_pf_ceiling:
                employer_pf = float(round(employer_max_pf))
            else:
                employer_pf = float(round(pf_base_for_employer * pf_rate))
            
            # Determine PF Admin & EDLI wage basis dynamically from settings
            is_ctc_staff = "ctc" in (emp_type or "").lower() and "non" not in (emp_type or "").lower()
            admin_edli_basis = get_category_setting(settings, "pf_admin_edli_basis", emp_type, default=None)
            if is_ctc_staff or not admin_edli_basis:
                if not is_ctc_staff and ("non ctc" in (emp_type or "").lower() or "non-ctc" in (emp_type or "").lower()):
                    admin_edli_basis = "Percentage of Gross Salary"
                else:
                    admin_edli_basis = "Statutory PF Wage (Capped at Ceiling)"

            if admin_edli_basis == "Percentage of Gross Salary":
                gross_pct = flt(get_category_setting(settings, "pf_admin_edli_gross_percent", emp_type))
                pf_statutory_base = round(flt(gross_val) * (gross_pct / 100.0), 2)
            elif admin_edli_basis == "Actual PF Wage (Uncapped)":
                pf_statutory_base = pf_base_for_employer
            else:
                # Statutory EPFO cap on EDLI and Admin Charges (₹15,000 ceiling -> max ₹75.00 each)
                admin_cap = employer_pf_ceiling if employer_pf_ceiling > 0 else 15000.0
                pf_statutory_base = min(pf_base_for_employer, admin_cap)

            pf_admin_charges = excel_round(pf_statutory_base * pf_admin_rate)
            edli_charges = excel_round(pf_statutory_base * edli_rate)

        enable_esi = cint(get_category_setting(settings, "enable_auto_esi", emp_type, default=1))
        esi_no = getattr(doc, "esi_no", None) or (emp.get("esi_no") if emp else None)
        has_esi_component = False
        if hasattr(doc, "deductions") and doc.deductions:
            for d in doc.deductions:
                c_name = (d.component_name or d.salary_component or "").lower() if hasattr(d, "component_name") else (d.get("component_name") or d.get("salary_component") or "").lower()
                if any(k in c_name for k in ["esi", "esic"]) and "employer" not in c_name:
                    has_esi_component = True
                    break

        if not enable_esi or (not esi_no and not has_esi_component) or (esi_ceiling > 0 and earned_gross_salary > esi_ceiling and gross_val > esi_ceiling):
            employer_esi = 0.0
        else:
            esi_rounding = get_category_setting(settings, "esi_rounding_method", emp_type, default="Round Up to Next Rupee (ROUNDUP / CEIL)")
            raw_employer_esi = flt(gross_val) * esi_rate
            if "Round Up" in esi_rounding or "ROUNDUP" in esi_rounding or "CEIL" in esi_rounding:
                employer_esi = float(math.ceil(raw_employer_esi))
            else:
                employer_esi = excel_round(raw_employer_esi)

        enable_tea = cint(get_category_setting(settings, "enable_tea_allowance", emp_type, default=1))
        tea_expenses = float(round(present_days_val * tea_rate)) if enable_tea else 0.0

        enable_lunch = cint(get_category_setting(settings, "enable_lunch_allowance", emp_type, default=1))
        lunch_rate_val = get_category_setting(settings, "lunch_allowance_per_meal", emp_type, default=None)
        if lunch_rate_val is None or lunch_rate_val == "":
            lunch_rate_val = get_category_setting(settings, "lunch_allowance_per_day", emp_type, default=None)
        lunch_rate = flt(lunch_rate_val) if (lunch_rate_val is not None and lunch_rate_val != "") else 50.0

        canteen_entries = []
        canteen_meals_count = 0
        emp_name = getattr(doc, "employee", None) or (emp.get("name") if emp else None)
        emp_id = getattr(doc, "employee_id", None) or (getattr(emp, "employee_id", None) if emp else None) or emp_name
        p_start = getattr(doc, "pay_period_start", None)
        p_end = getattr(doc, "pay_period_end", None)

        if enable_lunch and emp_name and p_start and p_end and (frappe.db.table_exists("Canteen Entry") or frappe.db.exists("DocType", "Canteen Entry")):
            canteen_entries = frappe.db.sql(
                """
                SELECT name, canteen_date, meal_type, meal_count, status, source, remarks
                FROM `tabCanteen Entry`
                WHERE (employee = %s OR employee = %s)
                  AND canteen_date BETWEEN %s AND %s
                ORDER BY canteen_date ASC
                """,
                (emp_name, emp_id, p_start, p_end),
                as_dict=True
            )
            canteen_meals_count = sum(flt(e.get("meal_count") or 1) for e in canteen_entries)

        lunch_expenses = float(round(canteen_meals_count * lunch_rate)) if enable_lunch else 0.0

        if has_bonus_in_earnings or "staff" in emp_type:
            bonus_provision = 0.0
        else:
            bonus_provision = float(round(earned_gross_salary * bonus_rate)) if enable_bonus else 0.0

        if has_el_in_earnings or "staff" in emp_type:
            el_provision = 0.0
        else:
            el_provision = float(round((earned_gross_salary / 26.0) * (el_days / 12.0))) if enable_el else 0.0

        emp_lwf, empr_lwf, is_lwf_eligible = calculate_lwf(emp, grand_gross_val, start_date, settings, employee_id=getattr(doc, "employee", None), current_slip_name=doc.name, prorated_earnings=getattr(doc, "earnings", []), net_pay=getattr(doc, "net_pay", None))
        employer_lwf = empr_lwf
        employee_lwf = emp_lwf

        earned_ctc = round(gross_val + employer_pf + pf_admin_charges + edli_charges + employer_esi + employer_lwf, 2)
        total_employer_contrib = round(employer_pf + pf_admin_charges + edli_charges + employer_esi + employer_lwf, 2)
        total_monthly_ctc = round(earned_ctc + tea_expenses + lunch_expenses + bonus_provision + el_provision, 2)

    res.update({
        "earned_gross_salary": earned_gross_salary,
        "employer_pf": employer_pf,
        "pf_admin_charges": pf_admin_charges,
        "edli_charges": edli_charges,
        "employer_esi": employer_esi,
        "employer_lwf": employer_lwf,
        "employee_lwf": employee_lwf,
        "lwf_eligible": 1 if is_lwf_eligible else 0,
        "is_lwf_eligible": is_lwf_eligible,
        "earned_ctc": earned_ctc,
        "tea_expenses": tea_expenses,
        "lunch_expenses": lunch_expenses,
        "lunch_count": canteen_meals_count,
        "canteen_meals_count": canteen_meals_count,
        "lunch_rate": lunch_rate,
        "enable_lunch_allowance": enable_lunch,
        "canteen_entries_details": canteen_entries,
        "total_employer_contribution": total_employer_contrib,
        "bonus_provision": bonus_provision,
        "el_provision": el_provision,
        "total_monthly_ctc": total_monthly_ctc,
        "total_ctc": total_monthly_ctc,
        "employer_pf_rate": round(pf_rate * 100.0, 2),
        "pf_admin_rate": round(pf_admin_rate * 100.0, 2),
        "edli_rate": round(edli_rate * 100.0, 2),
        "employer_esi_rate": round(esi_rate * 100.0, 2),
        "esi_wage_ceiling": esi_ceiling,
        "employer_pf_wage_ceiling": employer_pf_ceiling,
        "enable_bonus_provision": enable_bonus,
        "bonus_provision_rate": round(bonus_rate * 100.0, 2) if enable_bonus else 0.0,
        "enable_el_provision": enable_el,
        "el_provision_days_per_year": el_days if enable_el else 0.0,
        "has_bonus_in_earnings": has_bonus_in_earnings,
        "has_el_in_earnings": has_el_in_earnings,
        "enable_workers_tea_allowance": enable_tea,
        "workers_tea_allowance_per_day": round(tea_rate, 2),
        "enable_employee_tea_deduction": cint(get_category_setting(settings, "enable_employee_tea_deduction", emp_type, default=0)),
        "employee_tea_deduction_per_day": flt(get_category_setting(settings, "employee_tea_deduction_per_day", emp_type, default=0.0)),
        "enable_employee_canteen_deduction": cint(get_category_setting(settings, "enable_employee_canteen_deduction", emp_type, default=0)),
        "employee_canteen_deduction_per_meal": flt(get_category_setting(settings, "employee_canteen_deduction_per_meal", emp_type, default=0.0)),
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
    non_working_dates = []
    working_dates = []
    holiday_desc_map = {}
    holidays_details = []
    non_working_days_details = []
    if holiday_list:
        h_doc = frappe.get_doc("Holiday List", holiday_list[0].name)
        for row in h_doc.holidays:
            h_date = getdate(row.holiday_date)
            is_declared_holiday = bool(getattr(row, "is_holiday", 0))
            is_work_day = bool(getattr(row, "is_working_day", 1))

            if is_declared_holiday:
                if start_date <= h_date <= end_date:
                    holiday_dates.append(h_date)
                    holiday_desc_map[h_date] = row.description or "Holiday"
                    holidays_details.append({
                        "date": h_date.strftime("%Y-%m-%d"),
                        "description": row.description or "Holiday",
                        "status": "Holiday"
                    })
            elif not is_work_day:
                if start_date <= h_date <= end_date:
                    non_working_dates.append(h_date)
                    non_working_days_details.append({
                        "date": h_date.strftime("%Y-%m-%d"),
                        "description": row.description or h_date.strftime("%A"),
                        "status": "Non Working Day"
                    })
            else:
                if start_date <= h_date <= end_date:
                    working_dates.append(h_date)

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
    total_leave_days = 0.0
    unpaid_leave_days = 0.0
    present_days = 0.0
    physical_attendance_days = 0.0
    for i in range(total_days):
        single_day_date = start_date + timedelta(days=i)

        is_holiday = single_day_date in holiday_dates
        is_non_working_day = single_day_date in non_working_dates
        is_scheduled_work_day = single_day_date in working_dates or (not is_holiday and not is_non_working_day)

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
            total_leave_days += leave_val

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
        elif is_non_working_day and physical_val == 0 and comp_off_val == 0 and leave_val == 0:
            components.append("Non Working Day")
            
        absent_val = 0.0
        if is_scheduled_work_day:
            absent_val = round(max(0.0, 1.0 - (physical_val + comp_off_val + leave_val + holiday_val)), 2)
            if absent_val > 0:
                if leave_calc_source != "Via Direct Allocation":
                    components.append(f"Unpaid Leave ({absent_val})" if absent_val < 1.0 else "Unpaid Leave")
                    unpaid_leave_days += absent_val
                    total_leave_days += absent_val
                else:
                    components.append(f"Absent ({absent_val})" if absent_val < 1.0 else "Absent")
                total_absent_days += absent_val
            
        day_status = " + ".join(components) if components else ("Non Working Day" if is_non_working_day else "Absent")

        days_breakdown.append({
            "date":   single_day_date.strftime("%Y-%m-%d"),
            "status": day_status,
            "is_holiday": is_holiday,
            "is_non_working_day": is_non_working_day,
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

    # Preserve saved doc snapshot if present
    saved_lop_days = getattr(doc, "lop_days", None)
    if saved_lop_days is not None and saved_lop_days != "" and flt(saved_lop_days) > 0:
        lop_days = flt(saved_lop_days)
    elif lop_days == 0 and flt(getattr(doc, "unpaid_leave_days", 0)) > 0:
        lop_days = flt(doc.unpaid_leave_days)
    elif lop_days == 0 and flt(getattr(doc, "no_of_leave", 0)) > 0:
        lop_days = flt(doc.no_of_leave)

    res["days_breakdown"] = days_breakdown
    res["leave_calc_source"] = leave_calc_source
    res["absent_days"] = total_absent_days
    res["no_of_paid_leave"] = paid_leave_days
    res["no_of_comp_off"] = comp_off_days
    res["no_of_leave"] = getattr(doc, "no_of_leave", None) if (getattr(doc, "no_of_leave", None) is not None and flt(getattr(doc, "no_of_leave", 0)) > 0) else unpaid_leave_days
    res["unpaid_leave_days"] = getattr(doc, "unpaid_leave_days", None) if (getattr(doc, "unpaid_leave_days", None) is not None and flt(getattr(doc, "unpaid_leave_days", 0)) > 0) else unpaid_leave_days
    res["lop_days"] = lop_days
    res["holiday_count"] = len(holiday_dates)
    res["non_working_count"] = len(non_working_dates)
    res["holidays_details"] = holidays_details
    res["non_working_days_details"] = non_working_days_details
    res["holiday_working_days"] = len(working_dates) if holiday_list else (total_days - len(holiday_dates))
    res["actual_present_days"] = present_days
    res["physical_attendance_days"] = physical_attendance_days

    # Attach dynamic or stored leave balances
    leave_details_raw = getattr(doc, "leave_details", None)
    leave_balances = []
    if leave_details_raw:
        try:
            leave_balances = json.loads(leave_details_raw)
        except Exception:
            leave_balances = []

    if doc.employee and doc.pay_period_start and doc.pay_period_end:
        leave_info = get_employee_leave_balances(doc.employee, doc.pay_period_start, doc.pay_period_end)
        leave_balances = leave_info["balances"]
        res["cl_cycle_period"] = leave_info.get("cl_cycle_period") or getattr(doc, "cl_cycle_period", "")
        res["cl_allocated"] = leave_info["cl_allocated"]
        res["cl_taken"] = leave_info["cl_taken"]
        res["cl_balance"] = leave_info["cl_balance"]
    else:
        res["cl_cycle_period"] = getattr(doc, "cl_cycle_period", "")
        res["cl_allocated"] = flt(getattr(doc, "cl_allocated", 0))
        res["cl_taken"] = flt(getattr(doc, "cl_taken", 0))
        res["cl_balance"] = flt(getattr(doc, "cl_balance", 0))

    res["leave_balances"] = leave_balances
    res["leave_details"] = json.dumps(leave_balances)

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

            existing_slip = frappe.db.get_value("Salary Slip", {
                "employee": emp_id,
                "pay_period_start": start_date,
                "pay_period_end": end_date
            }, ["name", "docstatus"], as_dict=True)

            if existing_slip:
                if existing_slip.docstatus == 0:
                    frappe.delete_doc("Salary Slip", existing_slip.name, force=1)
                else:
                    skipped_count += 1
                    continue

            slip = frappe.get_doc({
                "doctype": "Salary Slip",
                "employee": data["employee"],
                "employee_name": data["employee_name"],
                "father_husband_name": data.get("father_husband_name"),
                "employee_type": data.get("employee_type"),
                "department": data.get("department"),
                "designation": data.get("designation"),
                "date_of_joining": data.get("date_of_joining"),
                "email": data.get("email"),
                "personal_email": data.get("personal_email"),
                "bank_account": data.get("bank_account"),
                "pf_no": data.get("pf_no") or data.get("pf_number"),
                "uan_number": data.get("uan_number"),
                "esi_no": data.get("esi_no"),
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
                "fuel_incentive": data.get("fuel_incentive", 0.0),
                "referral_bonus": data.get("referral_bonus", 0.0),
                "annual_bonus": data.get("annual_bonus", 0.0),
                "leave_encashment_amount": data.get("leave_encashment_amount", 0.0),
                "pt_amount": data.get("pt_amount", 0.0),
                "canteen_deduction": data.get("canteen_deduction", 0.0),
                "employer_pf": data.get("employer_pf", 0.0),
                "pf_admin_charges": data.get("pf_admin_charges", 0.0),
                "edli_charges": data.get("edli_charges", 0.0),
                "employer_esi": data.get("employer_esi", 0.0),
                "employer_lwf": data.get("employer_lwf", 0.0),
                "employee_lwf": data.get("employee_lwf", 0.0),
                "lwf_eligible": data.get("lwf_eligible", 0),
                "total_employer_contribution": data.get("total_employer_contrib", 0.0) or data.get("total_employer_contribution", 0.0),
                "tea_expenses": data.get("tea_expenses", 0.0),
                "lunch_expenses": data.get("lunch_expenses", 0.0),
                "canteen_meals_count": data.get("canteen_meals_count", 0.0),
                "lunch_rate": data.get("lunch_rate", 50.0),
                "bonus_provision": data.get("bonus_provision", 0.0),
                "el_provision": data.get("el_provision", 0.0),
                "earned_ctc": data.get("earned_ctc", 0.0),
                "total_monthly_ctc": data.get("total_monthly_ctc", 0.0),
                "gross_pay": data["gross_pay"],
                "grand_gross_pay": data["grand_gross_pay"],
                "net_pay": data["net_pay"],
                "grand_net_pay": data["grand_net_pay"],
                "total_deduction": data["total_deduction"],
                "total_working_days": data["total_working_days"],
                "lop": data["lop"],
                "lop_days": data["lop_days"],
                "leave_details": data.get("leave_details") or json.dumps(data.get("leave_balances") or []),
                "cl_cycle_period": data.get("cl_cycle_period", ""),
                "cl_allocated": data.get("cl_allocated", 0.0),
                "cl_taken": data.get("cl_taken", 0.0),
                "cl_balance": data.get("cl_balance", 0.0),
                "status": "Draft"
            })

            for e in data.get("earnings", []):
                if flt(e.get("amount", 0)) > 0 or flt(e.get("standard_amount", 0)) > 0:
                    slip.append("earnings", e)

            for d in data.get("deductions", []):
                if flt(d.get("amount", 0)) > 0:
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


@frappe.whitelist()
def bulk_download_pdf_2in1(names=None, format=None):
    """
    Combines salary slips 2-per-page onto standard A4 Portrait sheets (210mm x 297mm).
    Slip 1: Top half of A4 (A5 Landscape)
    Slip 2: Bottom half of A4 (A5 Landscape)
    """
    import json
    import io
    from pypdf import PdfReader, PdfWriter, PageObject, Transformation

    if isinstance(names, str):
        try:
            names = json.loads(names)
        except Exception:
            names = [s.strip() for s in names.split(",") if s.strip()]

    if not names:
        frappe.throw(_("Please select at least one Salary Slip to print."))

    slip_pages = []
    for slip_name in names:
        doc = frappe.get_doc("Salary Slip", slip_name)
        
        print_fmt = format
        if not print_fmt:
            emp_type = (doc.employee_type or "").lower()
            if "north indian" in emp_type:
                print_fmt = "North Indian Form 25B Pay Slip"
            elif "driver" in emp_type:
                print_fmt = "Driver Form 25B Pay Slip"
            elif "worker" in emp_type:
                print_fmt = "Worker Form 25B Pay Slip"
            else:
                print_fmt = frappe.get_meta("Salary Slip").default_print_format or "Salary Slip"

        pdf_bytes = frappe.get_print("Salary Slip", doc.name, print_format=print_fmt, as_pdf=True)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for p in reader.pages:
            slip_pages.append(p)

    # Standard A4 portrait dimensions in points (72 points/inch)
    # 210mm = 595.28 pt, 297mm = 841.89 pt
    A4_WIDTH = 595.28
    A4_HEIGHT = 841.89
    HALF_HEIGHT = A4_HEIGHT / 2.0  # 420.945 pt

    writer = PdfWriter()

    from pypdf.generic import DecodedStreamObject, NameObject

    for i in range(0, len(slip_pages), 2):
        a4_page = PageObject.create_blank_page(width=A4_WIDTH, height=A4_HEIGHT)
        
        # Slip 1 (Top half)
        page_top = slip_pages[i]
        w_top = float(page_top.mediabox.width)
        h_top = float(page_top.mediabox.height)
        scale_x_top = A4_WIDTH / w_top if w_top else 1.0
        scale_y_top = HALF_HEIGHT / h_top if h_top else 1.0
        scale_top = min(scale_x_top, scale_y_top)

        tx_top = (A4_WIDTH - (w_top * scale_top)) / 2.0
        ty_top = HALF_HEIGHT + (HALF_HEIGHT - (h_top * scale_top)) / 2.0
        
        trans_top = (
            Transformation()
            .scale(scale_top, scale_top)
            .translate(tx=tx_top, ty=ty_top)
        )
        a4_page.merge_transformed_page(page_top, trans_top)

        # Slip 2 (Bottom half, if exists)
        if i + 1 < len(slip_pages):
            page_bottom = slip_pages[i + 1]
            w_bot = float(page_bottom.mediabox.width)
            h_bot = float(page_bottom.mediabox.height)
            scale_x_bot = A4_WIDTH / w_bot if w_bot else 1.0
            scale_y_bot = HALF_HEIGHT / h_bot if h_bot else 1.0
            scale_bot = min(scale_x_bot, scale_y_bot)

            tx_bot = (A4_WIDTH - (w_bot * scale_bot)) / 2.0
            ty_bot = (HALF_HEIGHT - (h_bot * scale_bot)) / 2.0
            
            trans_bot = (
                Transformation()
                .scale(scale_bot, scale_bot)
                .translate(tx=tx_bot, ty=ty_bot)
            )
            a4_page.merge_transformed_page(page_bottom, trans_bot)

            # Dashed cutting guide between top and bottom slips
            try:
                cut_page = PageObject.create_blank_page(width=A4_WIDTH, height=A4_HEIGHT)
                cut_stream = DecodedStreamObject()
                cut_stream.set_data(b"q 0.75 G 0.5 w [4 4] 0 d 15 420.95 m 580.28 420.95 l S Q")
                cut_page[NameObject("/Contents")] = cut_stream
                a4_page.merge_page(cut_page)
            except Exception:
                pass

        writer.add_page(a4_page)

    output_stream = io.BytesIO()
    writer.write(output_stream)
    pdf_data = output_stream.getvalue()

    frappe.local.response.filename = "Salary_Slips_2in1_A4.pdf"
    frappe.local.response.filecontent = pdf_data
    frappe.local.response.type = "pdf"