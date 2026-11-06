# Copyright (c) 2026, Innoblitz and contributors
# For license information, please see license.txt

import json
from datetime import datetime, timedelta
import frappe
from frappe.utils import getdate

DEFAULT_API_KEY = "541812323206"
DEFAULT_SERIAL = "E03C1CB464F01801"

DEFAULT_EMPLOYEE_CONFIG = [
    {
        "code": "BEPL01976",
        "punches": ["08:24:07", "16:14:07"],
    },
    {
        "code": "BEPL01974",
        "punches": ["08:24:09"],
    },
]


@frappe.whitelist(allow_guest=True)
def get_device_logs(APIKey=None, FromDate=None, ToDate=None, include_out=0, serial_number=None, employees=None):
    """
    Mock SmartOffice WebAPI GetDeviceLogs endpoint within Frappe.
    Accessible via:
    /api/method/company.company.biometric.mock_api.get_device_logs?APIKey=541812323206&FromDate=2026-11-06&ToDate=2026-11-06
    """
    # Fallback to query params if not passed as kwarg
    api_key = APIKey or frappe.form_dict.get("APIKey") or frappe.form_dict.get("apikey")
    from_date_str = FromDate or frappe.form_dict.get("FromDate") or frappe.form_dict.get("fromdate")
    to_date_str = ToDate or frappe.form_dict.get("ToDate") or frappe.form_dict.get("todate")

    if not api_key or str(api_key).strip() != DEFAULT_API_KEY:
        frappe.response["http_status_code"] = 401
        return {
            "status": False,
            "message": "Invalid API Key."
        }

    serial = serial_number or DEFAULT_SERIAL
    inc_out = frappe.parse_json(include_out) if include_out is not None else False

    # Date parsing
    today_dt = datetime.now().date()
    try:
        from_d = getdate(from_date_str) if from_date_str else today_dt
    except Exception:
        from_d = today_dt

    try:
        to_d = getdate(to_date_str) if to_date_str else from_d
    except Exception:
        to_d = from_d

    if from_d > to_d:
        from_d, to_d = to_d, from_d

    # Employee list
    emp_list = DEFAULT_EMPLOYEE_CONFIG
    if employees:
        if isinstance(employees, str):
            codes = [c.strip() for c in employees.split(",") if c.strip()]
        elif isinstance(employees, list):
            codes = [str(c).strip() for c in employees if str(c).strip()]
        else:
            codes = []
        if codes:
            emp_list = []
            for i, c in enumerate(codes):
                sec = (i * 2) % 60
                emp_list.append({
                    "code": c,
                    "in_time": f"08:24:{sec:02d}",
                    "out_time": f"17:30:{sec:02d}",
                })

    logs = []
    curr = from_d
    while curr <= to_d:
        d_str = curr.strftime("%Y-%m-%d")
        for emp in emp_list:
            code = emp["code"]
            punches = emp.get("punches")
            if not punches:
                punches = [emp.get("in_time", "08:24:00")]
                if inc_out and emp.get("out_time"):
                    punches.append(emp["out_time"])

            for p_time in punches:
                logs.append({
                    "EmployeeCode": code,
                    "LogDate": f"{d_str} {p_time}",
                    "SerialNumber": serial,
                    "PunchDirection": " ",
                    "Temperature": 0,
                    "TemperatureState": "Not Measured"
                })
        curr += timedelta(days=1)

    return logs

