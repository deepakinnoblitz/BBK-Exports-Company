import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import frappe
from frappe import _
from frappe.utils import cint, flt, get_last_day, getdate

DEFAULT_TDS_NEW_SLABS = [
    {"from_amount": 0, "to_amount": 400000, "rate_percent": 0},
    {"from_amount": 400001, "to_amount": 800000, "rate_percent": 5},
    {"from_amount": 800001, "to_amount": 1200000, "rate_percent": 10},
    {"from_amount": 1200001, "to_amount": 1600000, "rate_percent": 15},
    {"from_amount": 1600001, "to_amount": 2000000, "rate_percent": 20},
    {"from_amount": 2000001, "to_amount": 2400000, "rate_percent": 25},
    {"from_amount": 2400001, "to_amount": None, "rate_percent": 30},
]

DEFAULT_TDS_OLD_SLABS = [
    {"from_amount": 0, "to_amount": 250000, "rate_percent": 0},
    {"from_amount": 250001, "to_amount": 500000, "rate_percent": 5},
    {"from_amount": 500001, "to_amount": 1000000, "rate_percent": 20},
    {"from_amount": 1000001, "to_amount": None, "rate_percent": 30},
]

DEFAULT_TDS_NEW_SLABS_JSON = json.dumps(DEFAULT_TDS_NEW_SLABS)
DEFAULT_TDS_OLD_SLABS_JSON = json.dumps(DEFAULT_TDS_OLD_SLABS)

DEFAULT_STD_DEDUCTION_NEW = 75000.0
DEFAULT_STD_DEDUCTION_OLD = 50000.0
DEFAULT_REBATE_LIMIT_87A_NEW = 1200000.0
DEFAULT_REBATE_LIMIT_87A_OLD = 500000.0
DEFAULT_CESS_RATE = 4.0
DEFAULT_TDS_COMPONENT = "TDS"
NEW_REGIME_NAME = "New Tax Regime u/s 115BAC"
OLD_REGIME_NAME = "Old Tax Regime"
MAX_SLAB_RATE_PERCENT = 50.0
MAX_CESS_RATE_PERCENT = 20.0


def _excel_round(val: float) -> float:
    """Round half-up to nearest rupee matching Excel ROUND(val, 0)."""
    if val is None:
        return 0.0
    try:
        return float(Decimal(str(round(flt(val), 8))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return float(round(flt(val)))


def _get_setting(settings, fieldname: str, default=None):
    """Read a field safely from either a Document object or a plain dict."""
    if settings is None:
        return default
    if isinstance(settings, dict):
        val = settings.get(fieldname)
    else:
        val = getattr(settings, fieldname, None)
    return default if val is None else val


def _get_numeric_setting(settings, fieldname: str, default: float) -> float:
    """Read a numeric setting while preserving explicit zero values."""
    raw = _get_setting(settings, fieldname, None)
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return flt(default)
    return flt(raw)


def _parse_to_amount(val):
    if val is None:
        return None
    if isinstance(val, str):
        cleaned = val.strip().lower()
        if cleaned in ("", "null", "none", "above"):
            return None
    return flt(val)


def parse_tds_slabs(raw_slabs, default_slabs: list[dict] | None = None) -> list[dict]:
    """Parse configured TDS slab JSON/list and fall back cleanly to default slabs."""
    fallback = [dict(s) for s in (default_slabs or DEFAULT_TDS_NEW_SLABS)]
    if not raw_slabs:
        return fallback

    parsed = raw_slabs
    if isinstance(raw_slabs, str):
        try:
            parsed = json.loads(raw_slabs)
        except Exception:
            return fallback

    if not isinstance(parsed, list) or not parsed:
        return fallback

    slabs = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        slabs.append(
            {
                "from_amount": flt(item.get("from_amount", 0)),
                "to_amount": _parse_to_amount(item.get("to_amount")),
                "rate_percent": flt(item.get("rate_percent", 0)),
            }
        )
    if not slabs:
        return fallback

    slabs.sort(key=lambda s: s["from_amount"])
    return slabs


def validate_tds_slabs(raw_slabs, label: str) -> list[dict]:
    """Validate configured TDS slab table structure, ranges, and rates."""
    if raw_slabs is None or (isinstance(raw_slabs, str) and not raw_slabs.strip()):
        return []

    parsed = raw_slabs
    if isinstance(raw_slabs, str):
        try:
            parsed = json.loads(raw_slabs)
        except Exception:
            frappe.throw(_("{0} must be a valid JSON list of income tax slabs.").format(label))

    if not isinstance(parsed, list) or not parsed:
        frappe.throw(_("{0} must contain at least one income tax slab.").format(label))

    normalized = []
    for idx, row in enumerate(parsed, start=1):
        if not isinstance(row, dict):
            frappe.throw(_("{0} row {1} must be an object.").format(label, idx))

        from_amt = flt(row.get("from_amount", 0))
        to_amt = _parse_to_amount(row.get("to_amount"))
        rate = flt(row.get("rate_percent", 0))

        if from_amt < 0:
            frappe.throw(_("{0} row {1}: From amount cannot be negative.").format(label, idx))
        if to_amt is not None and to_amt < from_amt:
            frappe.throw(_("{0} row {1}: To amount must be greater than or equal to From amount.").format(label, idx))
        if rate < 0 or rate > MAX_SLAB_RATE_PERCENT:
            frappe.throw(
                _("{0} row {1}: Tax rate must be between 0% and {2}%.").format(label, idx, MAX_SLAB_RATE_PERCENT)
            )

        normalized.append({"from_amount": from_amt, "to_amount": to_amt, "rate_percent": rate})

    normalized.sort(key=lambda s: s["from_amount"])
    prev_to = None
    for idx, slab in enumerate(normalized, start=1):
        if idx > 1 and prev_to is None:
            frappe.throw(_("{0}: Open-ended 'Above' slab can only be the final tier.").format(label))
        if prev_to is not None and slab["from_amount"] < prev_to:
            frappe.throw(_("{0} row {1}: Slab range overlaps with previous slab.").format(label, idx))
        prev_to = slab["to_amount"]

    return normalized


def parse_applicable_categories(raw_categories) -> list[str] | None:
    """Parse TDS applicable employee categories; returns None when all types apply by default."""
    if raw_categories is None or (isinstance(raw_categories, str) and not raw_categories.strip()):
        return None

    if isinstance(raw_categories, list):
        return [str(c).strip() for c in raw_categories if str(c).strip()]

    if isinstance(raw_categories, str):
        try:
            parsed = json.loads(raw_categories)
            if isinstance(parsed, list):
                return [str(c).strip() for c in parsed if str(c).strip()]
        except Exception:
            return [c.strip() for c in raw_categories.split(",") if c.strip()]

    return None


def is_tds_applicable_for_employee(settings, emp_type: str = "") -> bool:
    """Return True if global TDS is enabled and employee_type is covered."""
    if not cint(_get_setting(settings, "enable_tds", 1)):
        return False

    categories = parse_applicable_categories(_get_setting(settings, "tds_applicable_categories", None))
    if categories is None:
        return True
    if not categories:
        return False

    emp_type_lower = (emp_type or "").strip().lower()
    if not emp_type_lower:
        return True
    return any(cat.lower() == emp_type_lower for cat in categories)


def get_fiscal_year_bounds(ref_date) -> tuple[date, date, str]:
    """Return (fy_start, fy_end, fy_label) for the Indian Apr-Mar fiscal year containing ref_date."""
    dt = getdate(ref_date)
    start_year = dt.year if dt.month >= 4 else dt.year - 1
    end_year = start_year + 1
    return date(start_year, 4, 1), date(end_year, 3, 31), f"{start_year}-{end_year}"


def resolve_tds_policy(settings) -> dict:
    """Resolve effective tax regime, deductions, 87A limit, marginal relief, cess, and slabs."""
    configured_regime = _get_setting(settings, "tds_default_regime", NEW_REGIME_NAME) or NEW_REGIME_NAME
    regime = str(configured_regime).strip()
    is_new_regime = "old" not in regime.lower()

    if is_new_regime:
        slabs = parse_tds_slabs(_get_setting(settings, "tds_new_regime_slabs", None), DEFAULT_TDS_NEW_SLABS)
        std_deduction = _get_numeric_setting(settings, "tds_standard_deduction_new", DEFAULT_STD_DEDUCTION_NEW)
        rebate_limit = _get_numeric_setting(settings, "tds_rebate_limit_87a_new", DEFAULT_REBATE_LIMIT_87A_NEW)
    else:
        slabs = parse_tds_slabs(_get_setting(settings, "tds_old_regime_slabs", None), DEFAULT_TDS_OLD_SLABS)
        std_deduction = _get_numeric_setting(settings, "tds_standard_deduction_old", DEFAULT_STD_DEDUCTION_OLD)
        rebate_limit = _get_numeric_setting(settings, "tds_rebate_limit_87a_old", DEFAULT_REBATE_LIMIT_87A_OLD)

    cess_rate = max(0.0, _get_numeric_setting(settings, "tds_cess_rate", DEFAULT_CESS_RATE))
    marginal_relief_enabled = bool(cint(_get_setting(settings, "tds_enable_marginal_relief", 1))) and is_new_regime
    component_name = str(_get_setting(settings, "tds_deduction_component", DEFAULT_TDS_COMPONENT) or DEFAULT_TDS_COMPONENT).strip()

    return {
        "regime": NEW_REGIME_NAME if is_new_regime else OLD_REGIME_NAME,
        "is_new_regime": is_new_regime,
        "slabs": slabs,
        "standard_deduction": max(0.0, flt(std_deduction)),
        "rebate_limit_87a": max(0.0, flt(rebate_limit)),
        "enable_marginal_relief": marginal_relief_enabled,
        "cess_rate": cess_rate,
        "component_name": component_name or DEFAULT_TDS_COMPONENT,
    }


def compute_slab_tax(taxable_income: float, slabs: list[dict]) -> float:
    """Compute progressive income tax across ordered slab tiers without off-by-1 rupee drift."""
    income = max(0.0, flt(taxable_income))
    if income <= 0 or not slabs:
        return 0.0

    total_tax = 0.0
    prev_to = None
    for slab in slabs:
        from_amt = flt(slab.get("from_amount", 0))
        to_amt = _parse_to_amount(slab.get("to_amount"))
        rate = flt(slab.get("rate_percent", 0))

        # Preserve full bracket width for 1-rupee-step slab definitions like 400001..800000
        effective_from = (from_amt - 1.0) if (prev_to is not None and abs(from_amt - (prev_to + 1.0)) < 1e-6) else from_amt
        prev_to = to_amt

        if income <= effective_from:
            break

        upper = min(income, to_amt) if to_amt is not None else income
        taxable_in_slab = max(0.0, upper - effective_from)
        total_tax += taxable_in_slab * (rate / 100.0)

    return round(total_tax, 2)


def compute_annual_income_tax(projected_annual_gross: float, policy: dict) -> dict:
    """Compute annual tax breakdown (standard deduction, slabs, 87A rebate, marginal relief, cess)."""
    gross = max(0.0, flt(projected_annual_gross))
    std_deduction = min(gross, flt(policy.get("standard_deduction", 0)))
    taxable_income = max(0.0, round(gross - std_deduction, 2))
    raw_slab_tax = compute_slab_tax(taxable_income, policy.get("slabs") or [])

    rebate_limit = flt(policy.get("rebate_limit_87a", 0))
    rebate_87a = 0.0
    marginal_relief = 0.0
    tax_after_relief = raw_slab_tax

    if rebate_limit > 0 and taxable_income <= rebate_limit:
        rebate_87a = raw_slab_tax
        tax_after_relief = 0.0
    elif policy.get("enable_marginal_relief") and rebate_limit > 0 and taxable_income > rebate_limit:
        # Section 87A proviso (New Regime): income tax before cess cannot exceed income above 12L
        excess_income = taxable_income - rebate_limit
        if raw_slab_tax > excess_income:
            marginal_relief = round(raw_slab_tax - excess_income, 2)
            tax_after_relief = round(excess_income, 2)

    cess_rate = flt(policy.get("cess_rate", 0))
    cess_amount = round(tax_after_relief * (cess_rate / 100.0), 2) if tax_after_relief > 0 else 0.0
    total_annual_tax = _excel_round(tax_after_relief + cess_amount)

    return {
        "projected_annual_gross": round(gross, 2),
        "standard_deduction": round(std_deduction, 2),
        "taxable_income": taxable_income,
        "raw_slab_tax": round(raw_slab_tax, 2),
        "rebate_87a": round(rebate_87a, 2),
        "marginal_relief": round(marginal_relief, 2),
        "tax_after_relief": round(tax_after_relief, 2),
        "cess_amount": cess_amount,
        "total_annual_tax": total_annual_tax,
    }


def _month_start(dt: date) -> date:
    return date(dt.year, dt.month, 1)


def _next_month(dt: date) -> date:
    if dt.month == 12:
        return date(dt.year + 1, 1, 1)
    return date(dt.year, dt.month + 1, 1)


def _count_months_inclusive(start_dt: date, end_dt: date) -> int:
    start_m = _month_start(start_dt)
    end_m = _month_start(end_dt)
    if end_m < start_m:
        return 0
    return (end_m.year - start_m.year) * 12 + (end_m.month - start_m.month) + 1


def _extract_tds_from_slip(slip_name: str, tds_amount_col: float | None, tds_component_name: str) -> float:
    """Read already-deducted TDS from a prior Salary Slip, checking column and deduction rows."""
    if flt(tds_amount_col) > 0:
        return flt(tds_amount_col)

    rows = frappe.get_all(
        "Salary Structure",
        filters={"parent": slip_name, "parenttype": "Salary Slip", "parentfield": "deductions"},
        fields=["component_name", "amount"],
    )
    target_lower = tds_component_name.strip().lower()
    total = 0.0
    for r in rows:
        cname = (r.get("component_name") or "").strip().lower()
        if cname == target_lower or cname in ("tds", "income tax", "tds deduction"):
            total += flt(r.get("amount"))
    return total


def calculate_monthly_tds(
    grand_gross_pay: float,
    pay_period_start,
    settings,
    employee: str | None = None,
    emp_doc=None,
    current_slip_name: str | None = None,
    base_monthly_gross: float | None = None,
) -> dict:
    """Calculate Section 192 monthly TDS for a pay period using FY annual projection and YTD history."""
    emp_id = employee or (emp_doc.get("name") if hasattr(emp_doc, "get") else getattr(emp_doc, "name", None))
    emp_type = ""
    doj = None
    dol = None
    std_monthly_gross = flt(base_monthly_gross) if base_monthly_gross is not None else 0.0

    if emp_doc:
        emp_type = _get_setting(emp_doc, "employee_type", "") or ""
        doj = getdate(emp_doc.get("date_of_joining")) if emp_doc.get("date_of_joining") else None
        dol_raw = emp_doc.get("relieving_date") or emp_doc.get("date_of_leaving")
        dol = getdate(dol_raw) if dol_raw else None
        if std_monthly_gross <= 0:
            std_monthly_gross = flt(emp_doc.get("total_earnings") or 0)
            if std_monthly_gross <= 0 and getattr(emp_doc, "earnings", None):
                std_monthly_gross = sum(flt(e.amount) for e in emp_doc.earnings)
    elif emp_id:
        emp_row = frappe.db.get_value(
            "Employee",
            emp_id,
            ["employee_type", "date_of_joining", "relieving_date", "date_of_leaving", "total_earnings"],
            as_dict=True,
        )
        if emp_row:
            emp_type = emp_row.get("employee_type") or ""
            doj = getdate(emp_row.get("date_of_joining")) if emp_row.get("date_of_joining") else None
            dol_raw = emp_row.get("relieving_date") or emp_row.get("date_of_leaving")
            dol = getdate(dol_raw) if dol_raw else None
            if std_monthly_gross <= 0:
                std_monthly_gross = flt(emp_row.get("total_earnings") or 0)

    policy = resolve_tds_policy(settings)
    zero_result = {
        "tds_amount": 0.0,
        "tds_component": policy["component_name"],
        "applicable": False,
        "regime": policy["regime"],
        "breakdown": None,
    }

    if not is_tds_applicable_for_employee(settings, emp_type):
        return zero_result

    period_start = getdate(pay_period_start)
    if doj and doj > get_last_day(period_start):
        return zero_result
    if dol and dol < period_start:
        return zero_result

    fy_start, fy_end, fy_label = get_fiscal_year_bounds(period_start)
    effective_start = max(fy_start, _month_start(doj)) if doj else fy_start
    effective_end = min(fy_end, _month_start(dol)) if dol else fy_end
    current_month_start = _month_start(period_start)

    fallback_monthly_gross = std_monthly_gross if std_monthly_gross > 0 else flt(grand_gross_pay)
    past_gross = 0.0
    ytd_tds = 0.0
    recorded_past_months = set()

    if emp_id:
        has_tds_col = frappe.db.has_column("Salary Slip", "tds_amount")
        fields = ["name", "gross_pay", "grand_gross_pay", "pay_period_start"]
        if has_tds_col:
            fields.append("tds_amount")

        past_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": emp_id,
                "docstatus": ["<", 2],
                "pay_period_start": ["between", [effective_start, fy_end]],
            },
            fields=fields,
        )
        for ps in past_slips:
            if current_slip_name and ps.name == current_slip_name:
                continue
            ps_month = _month_start(getdate(ps.pay_period_start))
            if ps_month >= current_month_start:
                continue
            recorded_past_months.add((ps_month.year, ps_month.month))
            past_gross += flt(ps.grand_gross_pay or ps.gross_pay)
            ytd_tds += _extract_tds_from_slip(
                ps.name,
                ps.get("tds_amount") if has_tds_col else None,
                policy["component_name"],
            )

        iter_dt = _month_start(effective_start)
        while iter_dt < current_month_start:
            if (iter_dt.year, iter_dt.month) not in recorded_past_months:
                past_gross += fallback_monthly_gross
            iter_dt = _next_month(iter_dt)

    # Remaining FY months strictly after the current month
    future_start = _next_month(current_month_start)
    future_months = _count_months_inclusive(future_start, effective_end) if future_start <= effective_end else 0
    projected_future_gross = future_months * fallback_monthly_gross
    projected_annual_gross = round(past_gross + flt(grand_gross_pay) + projected_future_gross, 2)

    tax_info = compute_annual_income_tax(projected_annual_gross, policy)
    remaining_months = max(1, 1 + future_months)
    remaining_tax = max(0.0, tax_info["total_annual_tax"] - ytd_tds)
    monthly_tds = _excel_round(remaining_tax / remaining_months) if remaining_tax > 0 else 0.0

    return {
        "tds_amount": float(monthly_tds),
        "tds_component": policy["component_name"],
        "applicable": True,
        "regime": policy["regime"],
        "breakdown": {
            **tax_info,
            "fy": fy_label,
            "ytd_gross": round(past_gross, 2),
            "current_month_gross": round(flt(grand_gross_pay), 2),
            "projected_future_gross": round(projected_future_gross, 2),
            "ytd_tds_deducted": round(ytd_tds, 2),
            "remaining_tax_payable": round(remaining_tax, 2),
            "remaining_months": remaining_months,
            "monthly_tds": float(monthly_tds),
        },
    }
