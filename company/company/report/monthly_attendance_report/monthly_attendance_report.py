import frappe
from frappe.utils import getdate
from frappe import _
from datetime import date, timedelta

def execute(filters=None):
    if not filters:
        filters = {}

    today = getdate()

    # Map month names to numbers
    MONTHS = {
        "January": 1, "February": 2, "March": 3, "April": 4,
        "May": 5, "June": 6, "July": 7, "August": 8,
        "September": 9, "October": 10, "November": 11, "December": 12
    }

    # Get month and year from filters
    month_name = filters.get("month") or today.strftime("%B")
    month = MONTHS.get(month_name, 1)
    year = int(filters.get("year") or today.year)
    employee_filter = filters.get("employee")

    # --- Get Attendance records ---
    conditions = "MONTH(attendance_date) = %s AND YEAR(attendance_date) = %s"
    values = [month, year]

    if employee_filter:
        conditions += " AND employee = %s"
        values.append(employee_filter)

    attendance_records = frappe.db.sql(
        f"""
        SELECT
            a.employee,
            e.employee_name,
            a.status,
            a.half_day_status,
            a.in_time,
            a.out_time
        FROM `tabAttendance` a
        LEFT JOIN `tabEmployee` e ON e.name = a.employee
        WHERE {conditions}
        """,
        values,
        as_dict=True
    )

    # --- Helper functions ---
    def td_to_minutes(td):
        """Convert timedelta/time to minutes"""
        if not td:
            return 0
        if isinstance(td, str):
            # if frappe returns time as string, convert manually
            h, m, s = map(int, td.split(":"))
            return h * 60 + m
        return td.total_seconds() / 60

    def minutes_to_hhmm(minutes):
        """Convert minutes to HH:MM string"""
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours}:{mins:02d}"

    # --- Get Holiday List and calculate working days ---
    start_date = date(year, month, 1)
    end_date = date(year, month + 1, 1) - timedelta(days=1) if month != 12 else date(year, 12, 31)

    holiday_list = frappe.db.get_value("Holiday List", {"year": year, "month_year": str(month)}, "name")

    holidays = set()
    if holiday_list:
        holiday_dates = frappe.db.sql(
            """
            SELECT holiday_date
            FROM `tabHolidays`
            WHERE parent = %s AND holiday_date BETWEEN %s AND %s AND is_working_day = 0
            """,
            (holiday_list, start_date, end_date),
            as_dict=True
        )
        holidays = {h.holiday_date for h in holiday_dates}

    total_days_in_month = (end_date - start_date).days + 1
    total_holidays = len(holidays)
    company_working_days = total_days_in_month - total_holidays
    expected_working_minutes = company_working_days * 9 * 60  # 9 hours/day

    # --- Aggregate attendance data ---
    employee_data = {}

    for a in attendance_records:
        minutes = 0
        if a.status in ["Absent", "On Leave"]:
            minutes = 0
        elif a.in_time and a.out_time:
            start_minutes = td_to_minutes(a.in_time)
            end_minutes = td_to_minutes(a.out_time)
            if end_minutes < start_minutes:
                end_minutes += 24 * 60
            total_minutes = int(end_minutes - start_minutes)
            if a.status == "Half Day" and a.half_day_status == "Present":
                total_minutes /= 2
            minutes = total_minutes

        if a.employee not in employee_data:
            employee_data[a.employee] = {
                "employee_name": a.employee_name,
                "total_minutes": 0,
                "total_days": 0
            }

        employee_data[a.employee]["total_minutes"] += minutes
        if minutes > 0:
            employee_data[a.employee]["total_days"] += 1

    # --- Prepare columns ---
    columns = [
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 350},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 350},
        {"label": _("Total Working Hours"), "fieldname": "total_hours", "fieldtype": "Data", "width": 200},
        {"label": _("Total Days Present"), "fieldname": "total_days", "fieldtype": "Int", "width": 200},
    ]

    # --- Prepare data ---
    data = []
    company_total_minutes = 0
    company_total_days = 0

    for emp, val in sorted(employee_data.items(), key=lambda x: x[1]["employee_name"] or ""):
        data.append({
            "employee": emp,
            "employee_name": val["employee_name"],
            "total_hours": minutes_to_hhmm(val["total_minutes"]),
            "total_days": val["total_days"]
        })
        company_total_minutes += val["total_minutes"]
        company_total_days += val["total_days"]

    # --- Calculate Efficiency ---
    attendance_efficiency = (company_total_minutes / expected_working_minutes * 100) if expected_working_minutes else 0

    # --- Add Company Summary Rows ---
    data.append({
        "employee": "Company Total (Actual)",
        "employee_name": f"Efficiency: {attendance_efficiency:.1f}%",
        "total_hours": minutes_to_hhmm(company_total_minutes),
        "total_days": company_total_days
    })

    data.append({
        "employee": f"Expected (Based on Holiday List: {holiday_list or 'N/A'})",
        "employee_name": f"Working Days: {company_working_days} | Holidays: {total_holidays}",
        "total_hours": minutes_to_hhmm(expected_working_minutes),
        "total_days": company_working_days
    })

    return columns, data
