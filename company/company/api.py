import frappe
import json
import os
from frappe import _
from frappe.utils import (
    getdate,
    get_first_day,
    get_last_day,
    add_days,
    add_months,
    flt,
    today,
    formatdate, 
    get_date_str
)
from datetime import datetime, timedelta
from calendar import monthrange

@frappe.whitelist()
def bootstrap_salary_components():
    """Bootstrap default salary components"""
    defaults = [
        {"component_name": "Basic Pay", "type": "Earning", "percentage": 50},
        {"component_name": "HRA", "type": "Earning", "percentage": 20},
        {"component_name": "Conveyance Allowances", "type": "Earning", "percentage": 10},
        {"component_name": "Medical Allowances", "type": "Earning", "percentage": 10},
        {"component_name": "Other Allowances", "type": "Earning", "percentage": 10},
        {"component_name": "PF", "type": "Deduction", "static_amount": 1800},
        {"component_name": "ESI/Health Insurance", "type": "Deduction", "percentage": 0.75},
        {"component_name": "Professional Tax", "type": "Deduction", "static_amount": 200},
        {"component_name": "Loan Recovery", "type": "Deduction", "static_amount": 0},
    ]

    for d in defaults:
        if not frappe.db.exists("Salary Structure Component", d["component_name"]):
            doc = frappe.get_doc({
                "doctype": "Salary Structure Component",
                "component_name": d["component_name"],
                "type": d["type"],
                "percentage": d.get("percentage", 0),
                "static_amount": d.get("static_amount", 0)
            })
            doc.insert(ignore_permissions=True)
    
    return "Bootstrap completed"

from frappe.utils import get_bench_path
from frappe.utils.file_manager import save_file

@frappe.whitelist()
def is_hrms_notification_enabled(fieldname):
    """
    Check if a specific HRMS notification is enabled.
    """
    try:
        enabled = frappe.db.get_single_value("HRMS Settings", fieldname)
        # Checkboxes in Frappe are 1 (True) or 0 (False)
        return bool(enabled)
    except Exception:
        return True  # Default to True to avoid missing important emails

@frappe.whitelist()
def get_hrms_settings():
    """Retrieve HRMS Settings singleton values with global fallbacks"""
    try:
        settings = frappe.get_single("HRMS Settings")
        data = settings.as_dict()
        
        # Fallback to system defaults if not set in HRMS Settings
        if not data.get("default_currency"):
            data["default_currency"] = frappe.defaults.get_global_default("currency") or "INR"
        
        # Pull the currency symbol from the Frappe Currency DocType
        if data.get("default_currency"):
            data["currency_symbol"] = frappe.db.get_value("Currency", data["default_currency"], "symbol") or "₹"
        
        if not data.get("default_locale"):
            data["default_locale"] = "en-IN"

        return data
    except Exception as e:
        frappe.log_error(f"Error fetching HRMS Settings: {str(e)}")
        # Ultimate fail-safe defaults
        return {
            "default_currency": "INR",
            "currency_symbol": "₹",
            "default_locale": "en-IN"
        }

# =================== ESTIMATION REFERENCE ===================
@frappe.whitelist()
def get_next_estimation_preview():
    """Get next Estimation number for preview or assignment"""
    today = getdate()
    year = today.year

    if today.month < 4:
        start_year = year - 1
        end_year = year
    else:
        start_year = year
        end_year = year + 1

    fy = f"{str(start_year)[-2:]}-{str(end_year)[-2:]}"  # e.g., 25-26

    # Get last saved Estimation for this FY
    last = frappe.db.sql("""
        SELECT ref_no FROM `tabEstimation`
        WHERE ref_no LIKE %s
        ORDER BY creation DESC LIMIT 1
    """, (f"IB-E/{fy}/%",), as_dict=True)

    if last:
        last_num = int(last[0].ref_no.split("/")[-1])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"IB-E/{fy}/{str(next_num).zfill(3)}"


def before_insert_estimation(doc, method):
    """Assign Estimation ref_no automatically if not set"""
    if not doc.ref_no:
        doc.ref_no = get_next_estimation_preview()


# =================== INVOICE REFERENCE ===================
@frappe.whitelist()
def get_next_invoice_preview():
    """Get next Invoice number for preview or assignment"""
    today = getdate()
    year = today.year

    if today.month < 4:
        start_year = year - 1
        end_year = year
    else:
        start_year = year
        end_year = year + 1

    fy = f"{str(start_year)[-2:]}-{str(end_year)[-2:]}"  # e.g., 25-26

    # Get last saved Invoice for this FY
    last = frappe.db.sql("""
        SELECT ref_no FROM `tabInvoice`
        WHERE ref_no LIKE %s
        ORDER BY creation DESC LIMIT 1
    """, (f"IB-I/{fy}/%",), as_dict=True)

    if last:
        last_num = int(last[0].ref_no.split("/")[-1])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"IB-I/{fy}/{str(next_num).zfill(3)}"


def before_insert_invoice(doc, method):
    """Assign Invoice ref_no automatically if not set"""
    if not doc.ref_no:
        doc.ref_no = get_next_invoice_preview()


@frappe.whitelist()
def get_total_collected(invoice_name):
    total = frappe.db.sql("""
        SELECT SUM(amount_collected)
        FROM `tabInvoice Collection`
        WHERE invoice=%s
    """, invoice_name)[0][0] or 0

    return total

def update_invoice_received_balance(doc, method):
    """
    Update received_amount and balance_amount in Invoice
    whenever an Invoice Collection is inserted/updated/deleted.
    """
    invoice_name = doc.invoice
    if not invoice_name:
        return

    # Call the existing function
    total_collected = flt(get_total_collected(invoice_name))

    grand_total = flt(frappe.db.get_value("Invoice", invoice_name, "grand_total") or 0)
    balance = grand_total - total_collected
    if balance < 0:
        balance = 0

    frappe.db.set_value("Invoice", invoice_name, {
        "received_amount": total_collected,
        "balance_amount": balance
    })

def validate_invoice_collection(doc, method):
    """
    Prevent Invoice Collection from exceeding Invoice grand_total
    """
    if not doc.invoice:
        return

    # Get grand total & already collected
    invoice = frappe.db.get_value("Invoice", doc.invoice, ["grand_total"], as_dict=True)
    if not invoice:
        return

    already_collected = frappe.db.sql("""
        SELECT SUM(amount_collected)
        FROM `tabInvoice Collection`
        WHERE invoice=%s AND name != %s
    """, (doc.invoice, doc.name))[0][0] or 0

    new_total = flt(already_collected) + flt(doc.amount_collected)

    if new_total > flt(invoice.grand_total):
        frappe.throw(
            f"Collection exceeds Invoice Amount.<br><br>"
            f"Grand Total: {invoice.grand_total}<br>"
            f"Already Collected: {already_collected}<br>"
            f"Trying to Add: {doc.amount_collected}<br><br>"
            f"Remaining Balance: {invoice.grand_total - already_collected}"
        )

# =================== PURCHASE COLLECTION ===================
@frappe.whitelist()
def get_total_purchase_collected(purchase_name):
    total = frappe.db.sql("""
        SELECT SUM(amount_collected)
        FROM `tabPurchase Collection`
        WHERE purchase=%s
    """, purchase_name)[0][0] or 0

    return total

def update_purchase_paid_balance(doc, method):
    """
    Update paid_amount and balance_amount in Purchase
    whenever a Purchase Collection is inserted/updated/deleted.
    """
    purchase_name = doc.purchase
    if not purchase_name:
        return

    total_collected = flt(get_total_purchase_collected(purchase_name))

    grand_total = flt(frappe.db.get_value("Purchase", purchase_name, "grand_total") or 0)
    balance = grand_total - total_collected
    if balance < 0:
        balance = 0

    frappe.db.set_value("Purchase", purchase_name, {
        "paid_amount": total_collected,
        "balance_amount": balance
    })

def validate_purchase_collection(doc, method):
    """
    Prevent Purchase Collection from exceeding Purchase grand_total
    """
    if not doc.purchase:
        return

    purchase = frappe.db.get_value("Purchase", doc.purchase, ["grand_total"], as_dict=True)
    if not purchase:
        return

    already_collected = frappe.db.sql("""
        SELECT SUM(amount_collected)
        FROM `tabPurchase Collection`
        WHERE purchase=%s AND name != %s
    """, (doc.purchase, doc.name))[0][0] or 0

    new_total = flt(already_collected) + flt(doc.amount_collected)

    if new_total > flt(purchase.grand_total):
        frappe.throw(
            f"Collection exceeds Purchase Amount.<br><br>"
            f"Grand Total: {purchase.grand_total}<br>"
            f"Already Collected: {already_collected}<br>"
            f"Trying to Add: {doc.amount_collected}<br><br>"
            f"Remaining Balance: {purchase.grand_total - already_collected}"
        )

def validate_purchase_with_collections(doc, method):
    """
    Prevent editing of Purchase if it has associated collections
    """
    if not doc.is_new():
        if frappe.db.exists("Purchase Collection", {"purchase": doc.name}):
            frappe.throw("This purchase already has collections. Editing is not allowed.")


@frappe.whitelist()
def get_todays_followups():
    today = frappe.utils.today()  # '2025-09-23'
    return frappe.db.sql("""
        SELECT f.parent, f.followup_date, f.remarks
        FROM `tabFollowup` f
        WHERE DATE(f.followup_date) = %s
        ORDER BY f.followup_date ASC
    """, today, as_dict=True)


# =================== EXPENSES REFERENCE ===================
@frappe.whitelist()
def get_next_expense_preview():
    """Get next Expense number for preview or assignment"""
    today = getdate()
    year = today.year

    # Financial Year (April → March)
    if today.month < 4:
        start_year = year - 1
        end_year = year
    else:
        start_year = year
        end_year = year + 1

    fy = f"{str(start_year)[-2:]}-{str(end_year)[-2:]}"  # e.g., 25-26

    # Get last saved Expense for this FY
    last = frappe.db.sql("""
        SELECT expense_no FROM `tabExpenses`
        WHERE expense_no LIKE %s
        ORDER BY creation DESC LIMIT 1
    """, (f"EXP/{fy}/%",), as_dict=True)

    if last:
        last_num = int(last[0].expense_no.split("/")[-1])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"EXP/{fy}/{str(next_num).zfill(3)}"


def before_insert_expense(doc, method):
    """Assign Expense number automatically if not set"""
    if not doc.expense_no:
        doc.expense_no = get_next_expense_preview()
        doc.name = doc.expense_no  

@frappe.whitelist()
def get_leave_allocation_preview(year: int, month: int):
    """
    Returns a preview list of employees and their proposed leave allocations 
    for the given month/year.
    """
    year, month = int(year), int(month)
    month_start = get_first_day(datetime(year, month, 1))
    
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_id", "employee_name", "date_of_joining", "skip_probation"]
    )

    leave_types = {
        "Paid Leave": 1,
        "Unpaid Leave": 30,
        "Permission": 120
    }

    preview_data = []

    for emp in employees:
        # Check Probation (Joining Date + 3 months > month_start)
        in_probation = False
        if emp.date_of_joining and not emp.skip_probation:
            joining_date = getdate(emp.date_of_joining)
            probation_end = add_months(joining_date, 3)
            if probation_end > month_start:
                in_probation = True

        proposed_allocs = []
        for leave_type, base_count in leave_types.items():
            # If in probation, skip Paid Leave
            if in_probation and leave_type == "Paid Leave":
                continue
            
            # Check if already exists
            exists = frappe.db.exists("Leave Allocation", {
                "employee": emp.name,
                "leave_type": leave_type,
                "from_date": month_start,
                "status": "Approved"
            })

            proposed_allocs.append({
                "leave_type": leave_type,
                "count": base_count,
                "exists": bool(exists)
            })

        preview_data.append({
            "employee": emp.name,
            "employee_id": emp.employee_id,
            "employee_name": emp.employee_name,
            "date_of_joining": emp.date_of_joining,
            "in_probation": in_probation,
            "allocations": proposed_allocs
        })

    return preview_data


@frappe.whitelist()
def get_employee_probation_info(employee, date=None):
    """
    Returns probation status for a given employee.
    Probation is active if tenure < 3 months.
    """
    if not employee:
        return {"in_probation": False}

    emp_data = frappe.db.get_value("Employee", employee, ["date_of_joining", "skip_probation"], as_dict=True)
    if not emp_data or not emp_data.date_of_joining or emp_data.skip_probation:
        return {"in_probation": False}

    # Probation end = Joining Date + 3 Months
    probation_end = add_months(getdate(emp_data.date_of_joining), 3)
    
    # Check against provided date or today
    check_date = getdate(date) if date else getdate(today())
    
    # Inclusive: If check_date is the end date, it's still probation.
    in_probation = probation_end >= check_date

    return {
        "in_probation": in_probation,
        "probation_end_date": probation_end
    }


# =================== Auto Allocate Leave ==================
@frappe.whitelist()
def auto_allocate_monthly_leaves(year: int, month: int):
    """
    Automatically allocate leaves (Paid + Unpaid) to all active employees
    for a given month/year.
    """
    year, month = int(year), int(month)
    try:
        month_start = get_first_day(datetime(year, month, 1))
        month_end = get_last_day(datetime(year, month, 1))

        prev_month_start = get_first_day(add_months(month_start, -1))
        prev_month_end = get_last_day(add_months(month_start, -1))

        employees = frappe.get_all(
            "Employee",
            filters={"status": "Active"},
            fields=["name", "employee_id", "date_of_joining", "skip_probation"]
        )

        leave_types = {
            "Paid Leave": 1,
            "Unpaid Leave": 30,
            "Permission" : 120
        }

        created_count, skipped_count = 0, 0
        errors = []
        created_details = []

        for emp in employees:
            # Check Probation
            in_probation = False
            if emp.date_of_joining and not emp.skip_probation:
                probation_end = add_months(getdate(emp.date_of_joining), 3)
                if probation_end > month_start:
                    in_probation = True

            for leave_type, base_leave_count in leave_types.items():
                try:
                    # Skip Paid Leave if in probation
                    if in_probation and leave_type == "Paid Leave":
                        continue

                    # === Step 1: Skip if already exists for this month ===
                    if frappe.db.exists("Leave Allocation", {
                        "employee": emp.name,
                        "leave_type": leave_type,
                        "from_date": month_start,
                        "to_date": month_end,
                        "status": "Approved"
                    }):
                        skipped_count += 1
                        continue

                    # === Step 2: Get previous month's allocation ===
                    prev_alloc = frappe.get_value(
                        "Leave Allocation",
                        {
                            "employee": emp.name,
                            "leave_type": leave_type,
                            "from_date": prev_month_start,
                            "to_date": prev_month_end,
                            "status": "Approved"
                        },
                        ["total_leaves_allocated", "total_leaves_taken"],
                        as_dict=True
                    )

                    # === Step 3: Count how many allocations exist ===
                    allocation_count = frappe.db.count(
                        "Leave Allocation",
                        {
                            "employee": emp.name,
                            "leave_type": leave_type,
                            "status": "Approved"
                        }
                    )

                    carry_forward_balance = 0
                    leave_count = base_leave_count

                    # === ✅ Step 4: Logic for Paid Leave ===
                    if leave_type == "Paid Leave":
                        # Fetch reset frequency from Leave Type
                        paid_leave_frequency = frappe.db.get_value("Leave Type", "Paid Leave", "reset_frequency") or "Every 3 months"
                        
                        freq_map = {
                            "Every 3 months": 3,
                            "Every 4 months": 4,
                            "Every 6 months": 6,
                            "Whole year": 12
                        }
                        reset_interval = freq_map.get(paid_leave_frequency, 3)

                        # Check if current month is a reset month (Start of a period)
                        is_reset_month = (month - 1) % reset_interval == 0

                        if is_reset_month:
                            # Restart at the start of each period
                            carry_forward_balance = 0
                            leave_count = base_leave_count
                        elif prev_alloc:
                            # Carry forward within the period
                            balance = flt(prev_alloc.total_leaves_allocated) - flt(prev_alloc.total_leaves_taken)
                            if balance > 0:
                                carry_forward_balance = balance

                    # === ✅ Step 5: Logic for Unpaid Leave / Permission ===
                    else:
                        carry_forward_balance = 0
                        leave_count = base_leave_count

                    # === Step 6: Create new allocation ===
                    new_alloc_doc = frappe.get_doc({
                        "doctype": "Leave Allocation",
                        "employee": emp.name,
                        "leave_type": leave_type,
                        "from_date": month_start,
                        "to_date": month_end,
                        "total_leaves_allocated": leave_count + carry_forward_balance,
                        "total_leaves_taken": 0,
                        "status": "Approved"
                    })
                    new_alloc_doc.insert(ignore_permissions=True, ignore_mandatory=True)

                    created_count += 1
                    created_details.append({
                        "employee_name": frappe.db.get_value("Employee", emp.name, "employee_name"),
                        "employee_id": emp.employee_id,
                        "leave_type": leave_type,
                        "total_leaves": leave_count + carry_forward_balance
                    })

                except Exception as e:
                    errors.append(f"{emp.employee_id} - {leave_type} - {str(e)}")

        frappe.db.commit()

        return {
            "created_count": created_count,
            "skipped_count": skipped_count,
            "created_details": created_details,
            "errors": errors
        }

    except Exception as e:
        frappe.throw(f"Error in auto leave allocation: {e}")


# =================== SALARY SLIP GENERATION ===================

@frappe.whitelist()
def generate_salary_slips_from_employee(year=None, month=None, employees=None):
    import json

    if not year or not month:
        frappe.throw(_("Please provide year and month"))

    year = int(year)
    month = int(month)
    start_date = getdate(f"{year}-{month}-01")
    end_date = getdate(f"{year}-{month}-{monthrange(year, month)[1]}")

    # 🔹 Convert employees argument (JSON string) to Python list
    if isinstance(employees, str):
        try:
            employees = json.loads(employees)
        except Exception:
            frappe.throw(_("Invalid employees data"))

    # Fetch holidays
    holiday_dates = get_holiday_dates_for_month(year, month)
    number_of_holidays = len(holiday_dates)  # total holidays in month

    # 🔹 If employees are selected → filter only them, else include all
    if employees:
        employee_filters = {"name": ["in", employees]}
    else:
        employee_filters = {}

    # Get employees
    employees = frappe.get_all(
        "Employee",
        filters=employee_filters,
        fields=[
            "name", "employee_name", "basic_pay", "hra", "conveyance_allowances",
            "medical_allowances", "other_allowances", "pf", "health_insurance",
            "professional_tax", "loan_recovery", "email", "personal_email", "user"
        ]
    )

    created_count = 0
    skipped_count = 0
    errors = []

    for emp in employees:
        # Skip already submitted slips
        if frappe.db.exists("Salary Slip", {
            "employee": emp.name,
            "pay_period_start": start_date,
            "pay_period_end": end_date,
        }):
            skipped_count += 1
            continue

        # Fetch attendance
        attendance_records = frappe.get_all(
            "Attendance",
            filters={
                "employee": emp.name,
                "attendance_date": ["between", [start_date, end_date]],
                "docstatus": ["in", [0, 1]]
            },
            fields=["status", "leave_type", "attendance_date"]
        )

        # Initialize counters
        total_days = (end_date - start_date).days + 1
        present_days = 0
        absent_days = 0
        paid_leave_days = 0
        total_leave_days = 0

        for single_day in [start_date + timedelta(days=i) for i in range(total_days)]:
            is_holiday = single_day in holiday_dates
            record = next((r for r in attendance_records if r["attendance_date"] == single_day), None)

            if is_holiday:
                present_days += 1  # count holiday as present
                continue  # skip further attendance check

            if record:
                status = record.get("status")
                if status == "Present":
                    present_days += 1
                elif status == "Half Day":
                    total_leave_days += 0.5
                    leave_type = record.get("leave_type")

                    if leave_type == "Unpaid Leave":
                        absent_days += 0.5  # unpaid leave
                    else:
                        present_days += 0.5
                        paid_leave_days += 0.5
                elif status == "Absent":
                    absent_days += 1
                    total_leave_days += 1
                elif status in ["On Leave", "Leave"]:
                    leave_type = record.get("leave_type")
                    if leave_type:
                        # Check Leave Allocation for this day
                        allocations = frappe.get_all(
                            "Leave Allocation",
                            filters={
                                "employee": emp.name,
                                "leave_type": leave_type,
                                "status": "Approved",
                                "from_date": ["<=", single_day],
                                "to_date": [">=", single_day]
                            },
                            fields=["name", "total_leaves_allocated", "total_leaves_taken"]
                        )
                        allocation_found = None
                        for a in allocations:
                            if flt(a.total_leaves_taken) < flt(a.total_leaves_allocated):
                                allocation_found = a
                                break

                        if allocation_found:
                            paid_leave_days += 1
                            present_days += 1
                            total_leave_days += 1
                        else:
                            # Check if there’s an approved Leave Application for this date
                            approved_leave = frappe.db.exists("Leave Application", {
                                "employee": emp.name,
                                "leave_type": leave_type,
                                "workflow_state": "Approved",
                                "from_date": ["<=", single_day],
                                "to_date": [">=", single_day]
                            })
                            if approved_leave:
                                paid_leave_days += 1
                                present_days += 1
                                total_leave_days += 1
                            else:
                                absent_days += 1
                                total_leave_days += 1

            else:
                # No attendance record → absent
                absent_days += 1
                total_leave_days += 1

        # Calculate salary
        working_days = total_days
        unpaid_leave_days = total_leave_days - paid_leave_days

        # Earnings
        gross_pay = (
            flt(emp.basic_pay)
            + flt(emp.hra)
            + flt(emp.conveyance_allowances)
            + flt(emp.medical_allowances)
            + flt(emp.other_allowances)
        )

        # Deductions
        base_deductions = (
            flt(emp.pf)
            + flt(emp.health_insurance)
            + flt(emp.professional_tax)
            + flt(emp.loan_recovery)
        )

        # Prorate based on attendance
        grand_gross_pay = gross_pay * ((working_days - unpaid_leave_days) / working_days) if working_days else gross_pay
        grand_net_pay = grand_gross_pay - base_deductions

        lop_amount = gross_pay * (unpaid_leave_days / working_days) if working_days else 0

        total_deductions = base_deductions + lop_amount

        try:
            slip = frappe.get_doc({
                "doctype": "Salary Slip",
                "employee": emp.name,
                "employee_name": emp.employee_name,
                "email": emp.email,
                "personal_email": emp.personal_email,
                "user": emp.user,
                "pay_period_start": start_date,
                "pay_period_end": end_date,
                "no_of_leave": total_leave_days,
                "no_of_paid_leave": paid_leave_days,
                "gross_pay": gross_pay,
                "grand_gross_pay": grand_gross_pay,
                "net_pay": grand_gross_pay - base_deductions,
                "grand_net_pay": grand_net_pay,
                "total_deduction": total_deductions,
                "total_working_days": working_days,
                "lop": lop_amount,
                "lop_days": unpaid_leave_days,
                "status": "Draft",
                "basic_pay": emp.basic_pay,
                "hra": emp.hra,
                "conveyance_allowances": emp.conveyance_allowances,
                "medical_allowances": emp.medical_allowances,
                "other_allowances": emp.other_allowances,
                "pf": emp.pf,
                "health_insurance": emp.health_insurance,
                "professional_tax": emp.professional_tax,
                "loan_recovery": emp.loan_recovery
            })
            slip.insert(ignore_permissions=True)
            created_count += 1

        except Exception as e:
            errors.append(f"Error for {emp.name}: {str(e)}")

    result_msg = f"Salary Slips Created: {created_count}, Skipped: {skipped_count}"
    if errors:
        result_msg += "\nErrors:\n" + "\n".join(errors)

    return result_msg


def get_holiday_dates_for_month(year, month):
    """
    Fetch all holiday dates for given month/year from Holiday List (auto + manual holidays)
    """
    holiday_list = frappe.get_all("Holiday List",
        filters={"year": year, "month_year": month},
        fields=["name"]
    )

    if not holiday_list:
        return []

    holiday_doc = frappe.get_doc("Holiday List", holiday_list[0].name)
    holiday_dates = []

    for row in holiday_doc.holidays:
        if row.is_working_day == 0:
            holiday_dates.append(row.holiday_date)

    
    return holiday_dates


@frappe.whitelist()
def populate_holidays_for_ui(month, year):
    

    month = int(month)
    year = int(year)
    num_days = monthrange(year, month)[1]

    holidays = []
    saturday_count = 0
    working_days_count = 0

    for day in range(1, num_days + 1):
        d = getdate(f"{year}-{month:02d}-{day:02d}")
        weekday = d.weekday()  # Monday=0, Sunday=6
        is_holiday = False
        description = ""

        if weekday == 6:  # Sunday
            is_holiday = True
            description = "Sunday"
        elif weekday == 5:  # Saturday
            saturday_count += 1
            if saturday_count in [2,4]:
                is_holiday = True
                description = "2nd/4th Saturday"

        is_working_day = 0 if is_holiday else 1
        if is_working_day:
            working_days_count += 1

        holidays.append({
            "holiday_date": d,
            "description": description if is_holiday else "",
            "is_working_day": is_working_day
        })

    # Return both holidays and working_days
    return {
        "holidays": holidays,
        "working_days": working_days_count
    }


@frappe.whitelist()
def fetch_salary_slips(start_date, end_date):
    """
    Fetch all employees with Salary Slips in the given period
    """
    start_date = getdate(start_date)
    end_date = getdate(end_date)

    salary_slips = frappe.get_all(
        "Salary Slip",
        filters={
            "pay_period_start": ["<=", end_date],
            "pay_period_end": [">=", start_date],
        },
        fields=["name", "employee", "employee_name", "grand_gross_pay", "grand_net_pay"]
    )

    # Prepare data for child table
    employee_rows = []
    for slip in salary_slips:
        employee_rows.append({
            "employee": slip.employee,
            "salary_slip": slip.name,
            "gross_pay": slip.grand_gross_pay,
            "net_pay": slip.grand_net_pay
        })

    return employee_rows

# @frappe.whitelist()
# def get_today_leave_employees():
#     """
#     Returns a list of employees who are on leave today
#     """
#     today_date = getdate(today())

#     leave_apps = frappe.get_all(
#         "Leave Application",
#         filters={
#             "workflow_state": "Approved",
#             "from_date": ["<=", today_date],
#             "to_date": [">=", today_date],
#         },
#         fields=["employee", "employee_name", "leave_type", "from_date", "to_date"]
#     )

#      # Convert dates to string so JS can handle
#     for app in leave_apps:
#         app["from_date"] = str(app["from_date"])
#         app["to_date"] = str(app["to_date"])

#     return leave_apps

@frappe.whitelist()
def get_today_leave_employees():
    """
    Returns a list of employees who are on approved leave today,
    only for Paid Leave and Unpaid Leave
    """

    today_date = getdate(today())

    leave_apps = frappe.get_all(
        "Leave Application",
        filters={
            "workflow_state": "Approved",
            "from_date": ["<=", today_date],
            "to_date": [">=", today_date],
        },
        fields=["employee", "employee_name", "leave_type", "from_date", "to_date"]
    )

    # Convert dates to string for JS
    for app in leave_apps:
        app["from_date"] = str(app["from_date"])
        app["to_date"] = str(app["to_date"])

    return leave_apps



# @frappe.whitelist()
# def update_leave_allocation_on_approval(doc):
#     frappe.log_error(f"Workflow Approved: {doc.name}, state: {doc.workflow_state}", "Leave Allocation Debug")

#     if not doc.leave_type or not doc.employee:
#         frappe.log_error("Skipping allocation: missing leave_type or employee", "Leave Allocation Debug")
#         return

#     from_date = getdate(doc.from_date)
#     to_date = getdate(doc.to_date)
#     leave_days = (to_date - from_date).days + 1
#     if getattr(doc, "half_day", 0):
#         leave_days -= 0.5

#     allocations = frappe.get_all(
#         "Leave Allocation",
#         filters={
#             "employee": doc.employee,
#             "leave_type": doc.leave_type,
#             "status": "Approved",
#             "from_date": ["<=", to_date],
#             "to_date": [">=", from_date]
#         },
#         fields=["name", "total_leaves_allocated", "total_leaves_taken"]
#     )

#     if not allocations:
#         frappe.throw(f"No approved leave allocation found for {doc.employee} and {doc.leave_type}")

#     remaining_days = leave_days
#     for allocation in allocations:
#         available = flt(allocation.total_leaves_allocated) - flt(allocation.total_leaves_taken)
#         if available <= 0:
#             continue

#         to_add = min(available, remaining_days)
#         new_total_taken = flt(allocation.total_leaves_taken) + to_add

#         frappe.db.set_value(
#             "Leave Allocation",
#             allocation.name,
#             "total_leaves_taken",
#             new_total_taken
#         )

#         remaining_days -= to_add
#         if remaining_days <= 0:
#             break

#     if remaining_days > 0:
#         frappe.throw(f"Not enough leave balance for {doc.employee} and {doc.leave_type}")

#     frappe.db.commit()



def update_leave_allocation_from_attendance(doc, method=None):
    if not doc.employee or not doc.attendance_date:
        return

    previous = getattr(doc, "_previous_status", None)

    allocation = frappe.get_all(
        "Leave Allocation",
        filters={
            "employee": doc.employee,
            "leave_type": doc.leave_type,
            "status": "Approved",
            "from_date": ["<=", doc.attendance_date],
            "to_date": [">=", doc.attendance_date]
        },
        fields=["name", "total_leaves_allocated", "total_leaves_taken"],
        limit_page_length=1
    )

    if not allocation:
        return

    allocation = allocation[0]
    total_taken = allocation.total_leaves_taken or 0
    total_alloc = allocation.total_leaves_allocated or 0

    # Only act if status changed
    if doc.status in ["On Leave", "Leave"] and previous not in ["On Leave", "Leave"]:
        if total_taken < total_alloc:
            frappe.db.set_value("Leave Allocation", allocation.name, "total_leaves_taken", total_taken + 1)

    elif previous in ["On Leave", "Leave"] and doc.status == "Present":
        if total_taken > 0:
            frappe.db.set_value("Leave Allocation", allocation.name, "total_leaves_taken", total_taken - 1)


def is_permission_leave_type(leave_type):
    """
    Checks if a leave type is configured as Permission (is_permission=1)
    or named 'Permission' as a fallback.
    """
    if not leave_type:
        return False
    is_perm = frappe.db.get_value("Leave Type", leave_type, "is_permission")
    if is_perm:
        return True
    return str(leave_type).strip().lower() == "permission"


@frappe.whitelist()
def check_leave_balance(employee, leave_type, from_date, to_date, permission_hours=None, half_day=False):
    """
    Returns dict:
    {
        "allowed": True/False,
        "remaining": float,
        "requested": float,
        "unit": "Minutes" | "Days"
    }
    """
    from_date = getdate(from_date)
    to_date = getdate(to_date)

    # Fetch active allocations overlapping the range
    allocations = frappe.get_all(
        "Leave Allocation",
        filters={
            "employee": employee,
            "leave_type": leave_type,
            "status": "Approved",
            "from_date": ["<=", to_date],
            "to_date": [">=", from_date]
        },
        fields=["total_leaves_allocated", "total_leaves_taken"]
    )

    remaining = 0
    if allocations:
        total_allocated = sum(flt(a.total_leaves_allocated) for a in allocations)
        total_taken = sum(flt(a.total_leaves_taken) for a in allocations)
        remaining = total_allocated - total_taken

    # --- Permission logic ---
    if is_permission_leave_type(leave_type):
        requested = flt(permission_hours or 0)
        if not requested:
            frappe.throw("Please enter Permission Hours in minutes")

        allowed = remaining >= requested
        return {
            "allowed": allowed,
            "remaining": remaining,
            "requested": requested,
            "unit": "Minutes"
        }

    # --- Normal Leave Day Calculation ---
    leave_days = (to_date - from_date).days + 1

    # 🔥 APPLY HALF-DAY LOGIC
    is_half_day = str(half_day) in ("1", "true", "True")
    if is_half_day:
        leave_days = 0.5

    allowed = remaining >= leave_days

    return {
        "allowed": allowed,
        "remaining": remaining,
        "requested": leave_days,
        "unit": "Days"
    }


def validate_leave_balance(doc, method=None):
    """
    Hook for Leave Application — blocks submission if insufficient balance or duplicate permission.
    """
    if not doc.employee or not doc.leave_type:
        frappe.throw("Employee and Leave Type are required.")

    # --- 1️⃣ Check balance ---
    res = check_leave_balance(
        employee=doc.employee,
        leave_type=doc.leave_type,
        from_date=doc.from_date,
        to_date=doc.to_date,
        permission_hours=doc.permission_hours,
        half_day=doc.half_day
    )

    if not res.get("allowed"):
        frappe.throw(
            f"Not enough {res['unit'].lower()} balance for {doc.employee_name or doc.employee}.<br>"
            f"Available: {res['remaining']} {res['unit']}, Requested: {res['requested']} {res['unit']}."
        )

    # --- 2️⃣ Prevent overlapping (normal leave only) ---
    if not is_permission_leave_type(doc.leave_type):
        if has_approved_leave(doc.employee, doc.from_date, doc.to_date, exclude_doc=doc.name):
            frappe.throw(
                f"Employee {doc.employee} already has an approved leave in the selected date range."
            )

    # --- 3️⃣ Prevent duplicate permission ---
    if is_permission_leave_type(doc.leave_type):
        perm_types = frappe.get_all("Leave Type", filters={"is_permission": 1}, pluck="name")
        if "Permission" not in perm_types:
            perm_types.append("Permission")
        if doc.leave_type not in perm_types:
            perm_types.append(doc.leave_type)

        existing = frappe.db.exists(
            "Leave Application",
            {
                "employee": doc.employee,
                "leave_type": ["in", perm_types],
                "from_date": doc.from_date,
                "workflow_state": ["in", ["Approved", "Pending Approval"]],
                "name": ["!=", doc.name]
            }
        )
        if existing:
            frappe.throw(
                f"Employee {doc.employee} already has a Permission applied on {doc.from_date}."
            )



def has_approved_leave(employee, from_date, to_date, exclude_doc=None):
    """
    Checks if employee already has approved leave overlapping the given range.
    """
    filters = {
        "employee": employee,
        "status": "Approved",
        "from_date": ["<=", to_date],
        "to_date": [">=", from_date]
    }
    if exclude_doc:
        filters["name"] = ["!=", exclude_doc]

    return frappe.db.exists("Leave Application", filters)


# def update_permission_allocation(doc, method=None):
#     # ✅ Run only when leave type is Permission and workflow state is Approved
#     if doc.leave_type.lower() != "permission" or doc.workflow_state != "Approved":
#         return

#     # 🚫 Prevent double deduction if it was already approved
#     before_save = doc.get_doc_before_save()
#     if before_save and before_save.workflow_state == "Approved":
#         return

#     if not doc.permission_hours:
#         frappe.throw("Permission Hours are required for Permission leave type.")

#     # 🔍 Fetch the active Approved Leave Allocation for the specific date
#     allocation = frappe.db.get_value(
#         "Leave Allocation",
#         {
#             "employee": doc.employee,
#             "leave_type": doc.leave_type,
#             "status": "Approved",
#             "from_date": ["<=", doc.from_date],
#             "to_date": [">=", doc.from_date]
#         },
#         ["name", "total_leaves_taken"],
#         as_dict=True
#     )

#     if not allocation:
#         frappe.msgprint(f"No Leave Allocation found for {doc.employee} - {doc.leave_type}")
#         return

#     # ➕ Add new taken minutes
#     new_taken = flt(allocation.total_leaves_taken) + flt(doc.permission_hours)

#     frappe.db.set_value("Leave Allocation", allocation.name, "total_leaves_taken", new_taken)
#     frappe.db.commit()

#     frappe.msgprint(
#         f"✅ Permission hours updated for {doc.employee}.<br>"
#         f"Added: {doc.permission_hours} minutes.<br>"
#         f"Total taken now: {new_taken} minutes."
#     )

def sync_future_leave_allocations(employee, leave_type, from_date, previous_balance):
    """
    Recalculate future carry-forward allocations until the next reset period.
    """

    leave = frappe.get_doc("Leave Type", leave_type)

    if not leave.carry_forward:
        return

    freq_map = {
        "Every 3 months": 3,
        "Every 4 months": 4,
        "Every 6 months": 6,
        "Whole year": 12,
    }

    reset_interval = freq_map.get(
        leave.reset_frequency,
        3
    )

    allocations = frappe.get_all(
        "Leave Allocation",
        filters={
            "employee": employee,
            "leave_type": leave_type,
            "status": "Approved",
            "from_date": [">=", from_date]
        },
        fields=[
            "name",
            "from_date",
            "total_leaves_allocated",
            "total_leaves_taken",
        ],
        order_by="from_date asc",
    )

    if len(allocations) <= 1:
        return

    # Update future months
    base = flt(leave.max_leaves)

    for index, alloc in enumerate(allocations[1:], start=1):

        # Stop at the configured reset interval
        if index >= reset_interval:
            break

        carry = max(previous_balance, 0)

        new_total = base + carry

        if flt(alloc.total_leaves_allocated) != new_total:
            frappe.db.set_value(
                "Leave Allocation",
                alloc.name,
                "total_leaves_allocated",
                new_total
            )

        previous_balance = max(
            0,
            new_total - flt(alloc.total_leaves_taken)
        )

def update_leave_allocation(doc, method=None):
    """
    Update Leave Allocation when Leave Application is Approved.
    Deducts only from the current month's allocation and
    recalculates future carry-forward allocations.
    """

    if getattr(doc.flags, "in_delete", False):
        return

    if doc.workflow_state != "Approved":
        return

    before_save = doc.get_doc_before_save()
    if before_save and before_save.workflow_state == "Approved":
        return

    if not doc.employee or not doc.leave_type:
        return

    leave_type_lower = doc.leave_type.lower()

    # -----------------------------
    # Calculate Leave Amount
    # -----------------------------
    if is_permission_leave_type(doc.leave_type):
        if not doc.permission_hours:
            frappe.throw("Permission Hours are required.")

        to_add = flt(doc.permission_hours)
        unit = "minutes"

        allocation = frappe.get_value(
            "Leave Allocation",
            {
                "employee": doc.employee,
                "leave_type": doc.leave_type,
                "status": "Approved",
                "from_date": ["<=", doc.from_date],
                "to_date": [">=", doc.from_date],
            },
            [
                "name",
                "from_date",
                "total_leaves_allocated",
                "total_leaves_taken",
            ],
            as_dict=True,
        )

        if not allocation:
            frappe.throw(
                f"No Leave Allocation found for {doc.employee} on {doc.from_date}"
            )

        allocated = flt(allocation.total_leaves_allocated)
        taken = flt(allocation.total_leaves_taken)
        available = allocated - taken

        if available < to_add:
            frappe.throw(
                f"Only {available} {unit} available."
            )

        new_taken = taken + to_add
        frappe.db.set_value(
            "Leave Allocation",
            allocation.name,
            "total_leaves_taken",
            new_taken
        )

        previous_balance = max(0, allocated - new_taken)
        sync_future_leave_allocations(
            doc.employee,
            doc.leave_type,
            allocation.from_date,
            previous_balance
        )
        frappe.db.commit()

        frappe.msgprint(
            f"""
            <b>{doc.leave_type}</b> updated successfully.<br><br>

            Allocated : <b>{allocated}</b><br>
            Taken : <b>{new_taken}</b><br>
            Remaining : <b>{previous_balance}</b>
            """
        )

    else:
        # Loop through each day in the date range (handles multi-day & cross-month leaves)
        current_date = getdate(doc.from_date)
        end_date = getdate(doc.to_date)
        total_days = (end_date - current_date).days + 1
        day_cost = 0.5 if (doc.half_day and total_days == 1) else 1.0

        updated_allocations = set()

        while current_date <= end_date:
            allocation = frappe.get_value(
                "Leave Allocation",
                {
                    "employee": doc.employee,
                    "leave_type": doc.leave_type,
                    "status": "Approved",
                    "from_date": ["<=", current_date],
                    "to_date": [">=", current_date],
                },
                [
                    "name",
                    "from_date",
                    "total_leaves_allocated",
                    "total_leaves_taken",
                ],
                as_dict=True,
            )

            if not allocation:
                frappe.throw(
                    f"No Leave Allocation found for {doc.employee} ({doc.leave_type}) on {current_date}"
                )

            allocated = flt(allocation.total_leaves_allocated)
            taken = flt(allocation.total_leaves_taken)
            available = allocated - taken

            if available < day_cost:
                frappe.throw(
                    f"Insufficient leave balance on {current_date}. Available: {available} days, Required: {day_cost} day."
                )

            new_taken = taken + day_cost
            frappe.db.set_value(
                "Leave Allocation",
                allocation.name,
                "total_leaves_taken",
                new_taken
            )

            updated_allocations.add((allocation.name, allocation.from_date, allocated))
            current_date += timedelta(days=1)

        # Sync future leave allocations for all modified monthly allocations
        for alloc_name, alloc_from_date, allocated in updated_allocations:
            curr_taken = flt(frappe.db.get_value("Leave Allocation", alloc_name, "total_leaves_taken"))
            prev_balance = max(0, allocated - curr_taken)
            sync_future_leave_allocations(
                doc.employee,
                doc.leave_type,
                alloc_from_date,
                prev_balance
            )

        frappe.db.commit()

        frappe.msgprint(
            f"""
            <b>{doc.leave_type}</b> updated successfully for period {doc.from_date} to {doc.to_date}.
            """
        )



@frappe.whitelist()
def auto_submit_leave_application(doc, method=None):
    """
    Automatically submit Leave Application after save if all validations pass.
    """
    try:
        # Skip if already submitted
        if doc.docstatus == 1:
            return

        # Double-check validation again (safety)
        validate_leave_balance(doc)

        # Submit the document programmatically
        doc.submit()

        frappe.msgprint(
            f"✅ Leave Application {doc.name} has been submitted successfully."
        )

    except frappe.ValidationError as e:
        # Do not submit — validation failed
        frappe.msgprint(f"❌ Leave not submitted: {str(e)}")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Auto Submit Leave Application Error")


def auto_submit_employee_evaluation(doc, method=None):
    """
    Automatically submit Employee Evaluation after save if auto_submit is enabled.
    """
    try:
        if doc.get("auto_submit") and doc.docstatus == 0:
            doc.submit()
            frappe.log_error(f"Auto-submitted Employee Evaluation {doc.name}", "Evaluation Automation - Success")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Auto Submit Employee Evaluation Error")


@frappe.whitelist()
def handle_leave_status_change(doc, method=None):
    """
    Trigger when workflow state changes (Approved/Rejected).
    Sends mail to Employee + HR with a modern styled HTML template.
    """
    if getattr(doc, "docstatus", 0) not in [1, 2]:
        return

    employee = frappe.get_value(
        "Employee",
        doc.employee,
        ["email", "personal_email"],
        as_dict=True
    )

    employee_email = employee.email or employee.personal_email
    recipients = [employee_email] if employee_email else []

    if not recipients:
        return

    # Determine color and header text based on status
    if doc.workflow_state == "Approved":
        color = "#28a745"
        header_text = "✅ Leave Approved"
        intro_text = f"Good news, <b>{doc.employee_name}</b>! Your leave request has been approved."
    elif doc.workflow_state == "Rejected":
        color = "#dc3545"
        header_text = "❌ Leave Rejected"
        intro_text = f"Dear <b>{doc.employee_name}</b>, unfortunately your leave request has been rejected."
    else:
        return

    # ============================================
    # 🔹 Add Permission Hours if Leave Type = Permission
    # ============================================
    permission_row = ""
    if is_permission_leave_type(doc.leave_type):
        permission_hours = getattr(doc, "permission_hours", None)
        if permission_hours is not None:
            hrs = int(permission_hours) // 60
            mins = int(permission_hours) % 60

            # 👇 Format properly depending on duration
            if hrs >= 1 and mins > 0:
                formatted_time = f"{hrs} hr(s) {mins} min(s)"
            elif hrs >= 1:
                formatted_time = f"{hrs} hr(s)"
            elif mins > 0:
                formatted_time = f"{mins} min(s)"
            else:
                formatted_time = "0 min"

            permission_row = f"""
                <tr>
                    <td style="padding:6px; font-weight:bold;">Permission Duration</td>
                    <td>{formatted_time}</td>
                </tr>
            """


    # Leave details section
    leave_details = f"""
        <table style="width:100%; border-collapse:collapse; margin-top:10px;">
            <tr><td style="padding:6px; font-weight:bold; width:150px;">Employee</td><td>{doc.employee_name} ({doc.employee})</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Leave Type</td><td>{doc.leave_type}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">From</td><td>{formatdate(doc.from_date)}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">To</td><td>{formatdate(doc.to_date)}</td></tr>
            <tr><td style="padding:6px; font-weight:bold;">Total Days</td><td>{doc.total_days}</td></tr>
            {permission_row}
            <tr><td style="padding:6px; font-weight:bold;">Reason</td><td>{getattr(doc, 'reson', '') or ''}</td></tr>
        </table>
    """

    # Main styled email layout
    message = f"""
        <div style="font-family: 'Montserrat', 'Segoe UI', Arial, sans-serif; font-size:15px; color:#333; background:#f8f9fa; padding:25px;">
            <div style="max-width:600px; margin:auto; background:white; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.1); overflow:hidden;">
                <div style="background:{color}; color:white; padding:16px 20px; font-size:18px; font-weight:bold;">
                    {header_text}
                </div>
                <div style="padding:20px;">
                    <p style="margin:0 0 15px;">{intro_text}</p>

                    <div style="border:1px solid #e0e0e0; border-radius:8px; background-color:#fafafa; padding:12px;">
                        {leave_details}
                    </div>

                    <p style="margin-top:20px;">Best Regards,<br>
                    <b style="color:{color};">HR Team</b></p>
                </div>
            </div>
        </div>
    """

    subject = f"{header_text} - {doc.employee_name}"

    try:
        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            message=message,
            reference_doctype="Leave Application",
            reference_name=doc.name
        )
    except Exception as e:
        frappe.log_error(f"Leave Status Change Mail Error: {str(e)}", "Leave Email Debug")


def has_approved_leave(employee, from_date, to_date, exclude_doc=None):
    """
    Returns True if there is already an approved leave for the employee
    that overlaps with the given date range.
    exclude_doc: optional Leave Application name to exclude from check (useful during updates)
    """
    filters = {
        "employee": employee,
        "workflow_state": "Approved",
        "docstatus": 1,
        "from_date": ["<=", to_date],
        "to_date": [">=", from_date],
    }

    if exclude_doc:
        filters["name"] = ["!=", exclude_doc]

    existing = frappe.get_all("Leave Application", filters=filters, fields=["name"])
    return bool(existing)


@frappe.whitelist()
def get_today_birthdays():
    """
    Returns a list of employees who have birthday today
    """
    employees = frappe.get_all(
        "Employee",
        filters={
            "status": "Active"
        },
        fields=["employee_name", "employee_id", "dob"]
    )
    

    today_mmdd = getdate(today()).strftime("%m-%d")  # e.g., "10-02"
    result = []
    
    for emp in employees:
        if not emp.dob:
            continue

        dob_date = getdate(emp.dob)  # convert to date object
        emp_mmdd = dob_date.strftime("%m-%d")

        

        if emp_mmdd == today_mmdd:
            res = result.append({
                "employee_name": emp.employee_name,
                "employee": emp.employee_id,
                "dob": str(emp.dob)
            })

    return result


@frappe.whitelist()
def get_current_month_holidays():

    today = datetime.today()
    current_month = today.month
    current_year = today.year

    # fetch only parent holiday lists for the current year
    holiday_lists = frappe.get_all("Holiday List", filters={"year": current_year}, fields=["name"])

    result = []

    for hl in holiday_lists:
        doc = frappe.get_doc("Holiday List", hl.name)
        for h in doc.holidays:
            # Only consider current month and non-working days
            if h.holiday_date.month == current_month and h.is_working_day == 0:
                result.append({
                    "holiday_date": h.holiday_date.strftime("%Y-%m-%d"),
                    "description": h.description
                })

    return result


@frappe.whitelist()
def get_recent_announcements(limit=5):
    """Return the most recent active announcements"""
    announcements = frappe.get_all(
        "Announcement",
        fields=["announcement_name", "announcement", "creation"],
        filters={"is_active": 1},
        order_by="creation desc",
        limit=limit
    )
    return announcements
    

@frappe.whitelist()
def get_upcoming_and_expired_renewals(days=7):
    days = int(days)
    today_date = today()
    end_date = add_days(today(), days)
    
    # Get upcoming renewals
    upcoming_items = frappe.get_all(
        "Renewal Tracker",
        fields=["item_name", "category", "renewal_date", "amount", "status"],
        filters={"renewal_date": ["between", [today_date, end_date]]},
        order_by="renewal_date asc"
    )

    # Get expired items
    expired_items = frappe.get_all(
        "Renewal Tracker",
        fields=["item_name", "category", "renewal_date", "amount", "status"],
        filters={"renewal_date": ["<", today_date]},
        order_by="renewal_date asc"
    )

    # Add a flag to indicate type
    for item in upcoming_items:
        item["type"] = "upcoming"

    for item in expired_items:
        item["type"] = "expired"

    return upcoming_items + expired_items

def update_expired_renewals():
    today_date = today()
    # Find items whose renewal date has passed and status is not Expired
    expired_items = frappe.get_all(
        "Renewal Tracker",
        filters={
            "renewal_date": ["<", today_date],
            "status": ["!=", "Expired"]
        },
        fields=["name"]
    )

    for item in expired_items:
        frappe.db.set_value("Renewal Tracker", item.name, "status", "Expired")
        frappe.db.commit()



def format_timedelta(td):
    """Convert timedelta to HH:MM:SS format. Shows 00:00:00 if zero, '—' if None."""
    if td is None:
        return "—"
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"



@frappe.whitelist()
def get_today_checkin_time():
    """Return today's check-in/out details for the logged-in employee with formatted debug logging."""
    try:
        user = frappe.session.user

        # Try both possible link fields: 'user' or 'user_id'
        employee = frappe.db.get_value("Employee", {"user": user}, "name")
        if not employee:
            employee = frappe.db.get_value("Employee", {"user_id": user}, "name")

        if not employee:
            all_emps = frappe.get_all("Employee", ["name", "user", "user_id"])
            return {"status": "Not Linked", "checkin_time": None, "checkout_time": None}


        today = getdate()
        attendance = frappe.db.get_value(
            "Attendance",
            {"employee": employee, "attendance_date": today},
            ["in_time", "out_time", "status"],
            as_dict=True
        )

        # Format in/out times for logging
        if attendance:
            formatted_checkin = format_timedelta(attendance.in_time)
            formatted_checkout = format_timedelta(attendance.out_time)
            frappe.log_error(
                f"Today's attendance (formatted): "
                f"in_time={formatted_checkin}, "
                f"out_time={formatted_checkout}, "
                f"status={attendance.status}",
                "Checkin Debug"
            )
        else:
            frappe.log_error("Today's attendance: None", "Checkin Debug")

        if not attendance:
            return {"status": "Not Checked In", "checkin_time": None, "checkout_time": None}

        checkin_time = format_timedelta(attendance.in_time)
        checkout_time = format_timedelta(attendance.out_time)
        status = attendance.status or "—"

        return {
            "status": status,
            "checkin_time": checkin_time,
            "checkout_time": checkout_time
        }

    except Exception as e:
        return {"status": "Error", "checkin_time": None, "checkout_time": None}


@frappe.whitelist()
def get_employee_last_seven_days_attendance():
    """
    Returns the logged-in employee's in/out times for the last 7 days,
    including holidays and working day info — in reverse order (latest first).
    """
    try:
        from datetime import datetime, timedelta

        user = frappe.session.user

        # Get employee linked to logged-in user
        employee = frappe.db.get_value("Employee", {"user": user}, "name") or \
                   frappe.db.get_value("Employee", {"user": user}, "name")

        if not employee:
            return {"status": "Not Linked", "timeline": []}

        today_date = datetime.today().date()
        start_date = today_date - timedelta(days=6)  # last 7 days including today
        end_date = today_date

        # Fetch attendance records
        attendance_records = frappe.get_all(
            "Attendance",
            filters={
                "employee": employee,
                "attendance_date": ["between", [start_date, end_date]]
            },
            fields=["attendance_date", "in_time", "out_time", "status"],
            order_by="attendance_date asc"
        )
        attendance_dict = {str(rec.attendance_date): rec for rec in attendance_records}

        # Fetch holidays
        holidays = frappe.get_all(
            "Holidays",
            filters={"holiday_date": ["between", [start_date, end_date]]},
            fields=["holiday_date", "description", "is_working_day"]
        )
        holiday_dict = {str(h["holiday_date"]): h for h in holidays}

        timeline_data = []

        # Build timeline (oldest to newest)
        for i in range(7):
            date = start_date + timedelta(days=i)
            date_str = str(date)

            att_rec = attendance_dict.get(date_str)
            hol_rec = holiday_dict.get(date_str)

            checkin_time = str(att_rec.in_time) if att_rec and att_rec.in_time else None
            checkout_time = str(att_rec.out_time) if att_rec and att_rec.out_time else None
            status = att_rec.status if att_rec else "Absent"

            # Holiday info
            if hol_rec:
                if hol_rec.get("is_working_day"):
                    holiday_info = f"Working Day: {hol_rec.get('description') or ''}"
                else:
                    holiday_info = f"Holiday: {hol_rec.get('description') or ''}"
            else:
                holiday_info = "—"

            timeline_data.append({
                "date": date_str,
                "checkin_time": checkin_time,
                "checkout_time": checkout_time,
                "status": status,
                "holiday_info": holiday_info
            })

        # ✅ Reverse the order (latest first)
        timeline_data.reverse()

        frappe.log_error(f"Last 7 Days Timeline Data (Reversed) for {employee}: {timeline_data}", "Timeline Debug")
        return timeline_data

    except Exception as e:
        frappe.log_error(f"Error fetching last 7 days timeline: {str(e)}", "Timeline Error")
        return {"status": "Error", "timeline": []}



#=========Firebase Notification==========

import frappe
import requests
from google.oauth2 import service_account
import google.auth.transport.requests
from typing import Optional

def _get_credentials():
    """
    Load service account credentials from site_config fcm_key_path.
    Returns google Credentials object.
    """
    key_relative = frappe.get_site_config().get("fcm_key_path")
    if not key_relative:
        frappe.throw("FCM key path not configured in site_config.json (fcm_key_path)")
    key_path = frappe.get_site_path(key_relative)
    creds = service_account.Credentials.from_service_account_file(
        key_path,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"]
    )
    return creds

@frappe.whitelist(allow_guest=False)
def save_fcm_token(token: str):
    """Save the browser/device FCM token on the logged-in User record."""
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Login required")
    
    # Save to User doctype (existing)
    frappe.db.set_value("User", user, "fcm_token", token)
    
    # Sync with ClefinCode Chat Profile (required for chat app)
    # The chat app stores tokens in 'ClefinCode Chat Profile'
    # We find the profile linked to this user's email/ID
    profile_parent = frappe.db.get_value(
        "ClefinCode Chat Profile Contact Details",
        {"contact_info": user, "parenttype": "ClefinCode Chat Profile"},
        "parent"
    )
    if profile_parent:
        frappe.db.set_value("ClefinCode Chat Profile", profile_parent, "registration_token", token)

    frappe.db.commit()
    return {"status": "ok", "message": "Token saved", "token": token}

@frappe.whitelist(allow_guest=False)
def remove_fcm_token():
    """Remove the browser/device FCM token on the logged-in User record."""
    user = frappe.session.user
    if not user or user == "Guest":
        return {"status": "failed", "message": "Login required"}
    
    # Remove from User doctype
    frappe.db.set_value("User", user, "fcm_token", "")
    
    # Remove from ClefinCode Chat Profile
    profile_parent = frappe.db.get_value(
        "ClefinCode Chat Profile Contact Details",
        {"contact_info": user, "parenttype": "ClefinCode Chat Profile"},
        "parent"
    )
    if profile_parent:
        frappe.db.set_value("ClefinCode Chat Profile", profile_parent, "registration_token", "")

    frappe.db.commit()
    return {"status": "ok", "message": "Token removed"}

def _send_v1_message_to_token(token: str, title: str, body: str, data: dict = None) -> dict:
    """
    Send a message to a device token using FCM HTTP v1.
    Returns FCM response JSON.
    """
    creds = _get_credentials()
    request = google.auth.transport.requests.Request()
    creds.refresh(request)
    access_token = creds.token
    project_id = creds.project_id

    message = {
        "message": {
            "token": token,
            "data": {
                "title": title,
                "body": body,
                **(data or {})
            }
        }
    }

    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; UTF-8"
    }
    resp = requests.post(url, headers=headers, json=message, timeout=10)
    try:
        return resp.json()
    except ValueError:
        return {"error": "non-json-response", "status_code": resp.status_code, "text": resp.text}

def send_push_notification_to_user(user: str, title: str, body: str, data: dict = None):
    """
    Public helper to send a push notification to a Frappe User (by email/ID).
    """
    token = frappe.db.get_value("User", user, "fcm_token")
    if not token:
        frappe.log_error(message=f"No FCM token for user {user}", title="FCM No Token")
        return {"error": "no_token", "message": f"No token for user {user}"}
    return _send_v1_message_to_token(token, title, body, data)

def send_chat_notification_to_user(user: str, title: str, body: str):
    """
    Send a browser push notification for chat messages.
    Strips HTML from body content before sending.
    """
    try:
        from bs4 import BeautifulSoup
        
        # Strip HTML tags from body while preserving newlines for alignment
        if body:
            soup = BeautifulSoup(body, 'html.parser')
            
            # Replace <br> tags with actual newlines
            for br in soup.find_all("br"):
                br.replace_with("\n")
            
            # Extract text with space separator (explicit <br> handled above will be newlines)
            body = soup.get_text(separator=" ").strip()
            
            # Clean up: collapse multiple spaces but keep single newlines
            import re
            body = re.sub(r'[ \t]+', ' ', body) # Collapse horizontal whitespace
            body = re.sub(r'\n\s*\n', '\n\n', body) # Collapse multiple empty lines to max 2
            body = body.replace("\n\n\n", "\n\n") # Double safety
        
        # Send the notification with a link to the chat SPA
        return send_push_notification_to_user(user, title, body, data={"url": "/chat"})
    except Exception as e:
        frappe.log_error(
            message=f"Error sending chat notification to {user}: {str(e)}",
            title="Chat Notification Error"
        )
        return {"error": str(e)}


def extend_bootinfo(bootinfo):
    """Expose firebase config from site_config to frontend"""
    site_config = frappe.get_site_config()
    firebase_config = site_config.get("firebase")

    if firebase_config:
        # Ensure the site_config dict exists
        bootinfo["site_config"] = bootinfo.get("site_config", {})
        bootinfo["site_config"]["firebase"] = firebase_config


def _get_unread_data(user: str):
    """Internal helper to get counts and IDs of unread HR items."""
    unread_items = frappe.db.get_all("HR Read Tracker",
        filters={"is_read": 0, "read_by": user},
        fields=["reference_doctype", "reference_name"]
    )
    
    counts = {}
    unread_ids = {}
    
    for item in unread_items:
        dt = item.reference_doctype
        counts[dt] = counts.get(dt, 0) + 1
        if dt not in unread_ids:
            unread_ids[dt] = []
        unread_ids[dt].append(item.reference_name)
        
    return {
        "counts": counts,
        "unread_ids": unread_ids
    }


def _push_unread_count_update(user: str):
    """Re-query unread data for a user and push via Frappe realtime socket."""
    payload = _get_unread_data(user)
    frappe.publish_realtime(
        event="unread_count_updated",
        message=payload,
        user=user
    )


@frappe.whitelist()
def create_unread_entry_for_hr(doc, method=None):
    # skip if HR created it
    hr_roles = ["HR", "HR Manager", "System Manager", "Administrator"]
    owner_roles = frappe.get_roles(doc.owner)
    if any(role in owner_roles for role in hr_roles):
        return

    # avoid duplicates
    if frappe.db.exists("HR Read Tracker", {
        "reference_doctype": doc.doctype,
        "reference_name": doc.name
    }):
        return

    hr_users = list(set(frappe.get_all("Has Role",
        filters={"role": ["in", hr_roles], "parenttype": "User"},
        pluck="parent"
    )))

    for user in hr_users:
        if not frappe.db.exists("HR Read Tracker", {
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "read_by": user
        }):
            frappe.get_doc({
                "doctype": "HR Read Tracker",
                "reference_doctype": doc.doctype,
                "reference_name": doc.name,
                "read_by": user,
                "is_read": 0
            }).insert(ignore_permissions=True)

    # Push realtime update to each affected HR user
    frappe.db.commit()
    for user in hr_users:
        _push_unread_count_update(user)

@frappe.whitelist()
def create_unread_entry_for_employee(doc, method=None):
    # This is for notifying the employee when HR acts on their request.
    # We skip if the current user is the employee themselves (e.g., they just edited it).
    owner = doc.owner
    if frappe.session.user == owner:
        return

    # Avoid duplicates
    if frappe.db.exists("HR Read Tracker", {
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "read_by": owner
    }):
        return

    frappe.get_doc({
        "doctype": "HR Read Tracker",
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "read_by": owner,
        "is_read": 0
    }).insert(ignore_permissions=True)

    frappe.db.commit()
    _push_unread_count_update(owner)

@frappe.whitelist()
def mark_hr_item_as_read(doctype, name):
    """Mark document as read for logged-in HR."""
    user = frappe.session.user
    tracker = frappe.db.exists("HR Read Tracker", {
        "reference_doctype": doctype,
        "reference_name": name,
        "read_by": user
    })
    if tracker:
        frappe.db.set_value("HR Read Tracker", tracker, {
            "is_read": 1,
            "read_time": frappe.utils.now()
        })
    frappe.db.commit()
    # Push updated counts to this HR user immediately
    _push_unread_count_update(user)


@frappe.whitelist()
def get_unread_count():
    """Return unread counts and unread IDs per doctype for the logged-in HR."""
    return _get_unread_data(frappe.session.user)

@frappe.whitelist()
def get_attendance_stats(range=None, from_date=None, to_date=None):
    import datetime

    # -----------------------------
    # LOGGED-IN USER
    # -----------------------------
    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user": user}, "name")

    today = frappe.utils.getdate()

    # -----------------------------
    # RANGE HANDLING
    # -----------------------------
    if range == "today":
        from_date = to_date = today

    elif range == "week":
        from_date = today - datetime.timedelta(days=today.weekday())
        to_date = today

    elif range == "month":
        from_date = today.replace(day=1)
        to_date = today

    from_date = frappe.utils.getdate(from_date)
    to_date = frappe.utils.getdate(to_date)

    # ============================================================
    # 1️⃣ IF EMPLOYEE NOT LINKED → RETURN GLOBAL COMPANY DATA
    # ============================================================
    if not employee:
        return get_global_attendance_stats(from_date, to_date)

    # ============================================================
    # 2️⃣ EMPLOYEE-WISE ATTENDANCE
    # ============================================================
    return get_employee_attendance_stats(employee, from_date, to_date)

# ==================================================================
# 🔹 GLOBAL ATTENDANCE (ALL EMPLOYEES)
# ==================================================================
def get_global_attendance_stats(from_date, to_date):
    import datetime

    # Get all possible holiday lists
    holiday_list_names = frappe.db.get_list("Holiday List", pluck="name")
    holidays = set()

    if holiday_list_names:
        holiday_rows = frappe.db.get_all(
            "Holidays",
            filters={
                "parent": ["in", holiday_list_names],
                "holiday_date": ["between", [from_date, to_date]],
                "is_working_day": 0
            },
            fields=["holiday_date"]
        )
        holidays = { frappe.utils.getdate(h["holiday_date"]) for h in holiday_rows }

    holiday_count = len(holidays)

    # Count attendance for all employees
    def count(status):
        return frappe.db.count("Attendance", {
            "status": status,
            "attendance_date": ["between", [from_date, to_date]]
        })

    present = count("Present")
    absent = count("Absent")
    half_day = count("Half Day")
    on_leave = count("On Leave")

    # Add holidays into Present count
    present_final = present + holiday_count

    # Missing calculation
    total_days = (to_date - from_date).days + 1
    missing = total_days - (present + absent + half_day + on_leave + holiday_count)
    missing = max(missing, 0)

    return {
        "present": present_final,
        "absent": absent,
        "half_day": half_day,
        "on_leave": on_leave,
        "missing": missing,
        "last_sync": frappe.utils.now()
    }



# ==================================================================
# 🔹 EMPLOYEE-WISE ATTENDANCE
# ==================================================================
def get_employee_attendance_stats(employee, from_date, to_date):
    import datetime

    # Joining date
    doj = frappe.utils.getdate(
        frappe.db.get_value("Employee", employee, "date_of_joining")
    )

    # Holiday list from "Holiday List" (your custom)
    holiday_list_doc = frappe.db.get_value(
        "Holiday List",
        {"year": from_date.year, "month_year": from_date.month},
        "name"
    )

    holidays = set()

    if holiday_list_doc:
        holiday_rows = frappe.db.get_all(
            "Holidays",
            filters={
                "parent": holiday_list_doc,
                "holiday_date": ["between", [from_date, to_date]],
                "is_working_day": 0
            },
            fields=["holiday_date"]
        )
        holidays = { frappe.utils.getdate(h["holiday_date"]) for h in holiday_rows }

    holiday_count = len(holidays)

    # Attendance counts for employee
    def count(status):
        return frappe.db.count("Attendance", {
            "employee": employee,
            "status": status,
            "attendance_date": ["between", [from_date, to_date]]
        })

    present = count("Present")
    absent = count("Absent")
    half_day = count("Half Day")
    on_leave = count("On Leave")

    # Add holidays to present
    present_final = present + holiday_count

    # Missing days
    missing = 0
    cur = from_date

    while cur <= to_date:

        if cur < doj:
            cur += datetime.timedelta(days=1)
            continue

        if cur in holidays:
            cur += datetime.timedelta(days=1)
            continue

        exists = frappe.db.exists(
            "Attendance",
            {"employee": employee, "attendance_date": cur}
        )

        if not exists:
            missing += 1

        cur += datetime.timedelta(days=1)

    return {
        "present": present_final,
        "absent": absent,
        "half_day": half_day,
        "on_leave": on_leave,
        "missing": missing,
        "last_sync": frappe.utils.now()
    }


# ==================================================================
# 🔹 MISSING ATTENDANCE CHART DATA (Last 7 Days)
# ==================================================================
@frappe.whitelist()
def get_missing_attendance_chart_data():
    """
    Returns daily missing attendance counts for the last 7 days.
    Used for Missing Attendance Chart in HR Dashboard.
    """
    import datetime
    
    today = frappe.utils.getdate()
    result = []
    
    # Get total active employees count
    total_employees = frappe.db.count("Employee", {"status": "Active"})
    
    # Get all holiday lists
    holiday_list_names = frappe.db.get_list("Holiday List", pluck="name")
    
    for i in range(6, -1, -1):  # Last 7 days (6 days ago to today)
        date = today - datetime.timedelta(days=i)
        
        # Get holidays for this date
        holidays = set()
        if holiday_list_names:
            holiday_rows = frappe.db.get_all(
                "Holidays",
                filters={
                    "parent": ["in", holiday_list_names],
                    "holiday_date": date,
                    "is_working_day": 0
                },
                fields=["holiday_date"]
            )
            holidays = {frappe.utils.getdate(h["holiday_date"]) for h in holiday_rows}
        
        # If it's a holiday, missing count is 0
        if date in holidays:
            missing_count = 0
        else:
            # Count attendance records for this date
            marked_attendance = frappe.db.count("Attendance", {"attendance_date": date})
            missing_count = max(0, total_employees - marked_attendance)
        
        result.append({
            "date": str(date),
            "count": missing_count
        })
    
    return result


# ==================================================================
# 🔹 WEEKLY PRESENT COUNT CHART DATA (Current Week Mon-Sun)
# ==================================================================
@frappe.whitelist()
def get_weekly_present_chart_data():
    """
    Returns daily present counts for the current week (Monday to Sunday).
    Used for Weekly Present Count Chart in HR Dashboard.
    """
    import datetime
    
    today = frappe.utils.getdate()
    
    # Find Monday of current week (weekday() returns 0 for Monday)
    days_since_monday = today.weekday()
    monday = today - datetime.timedelta(days=days_since_monday)
    
    result = []
    
    # Get all holiday lists
    holiday_list_names = frappe.db.get_list("Holiday List", pluck="name")
    
    for i in range(7):  # Monday to Sunday
        date = monday + datetime.timedelta(days=i)
        
        # For future dates, show 0 count
        if date > today:
            day_name = date.strftime('%a')
            result.append({
                "date": str(date),
                "day": day_name,
                "count": 0
            })
            continue
        
        # Get holidays for this date
        holidays = set()
        if holiday_list_names:
            holiday_rows = frappe.db.get_all(
                "Holidays",
                filters={
                    "parent": ["in", holiday_list_names],
                    "holiday_date": date,
                    "is_working_day": 0
                },
                fields=["holiday_date"]
            )
            holidays = {frappe.utils.getdate(h["holiday_date"]) for h in holiday_rows}
        
        # Count present attendance
        present_count = frappe.db.count("Attendance", {
            "attendance_date": date,
            "status": "Present"
        })
        
        # Add holiday count to present
        if date in holidays:
            # Count total employees as present on holidays
            total_employees = frappe.db.count("Employee", {"status": "Active"})
            present_count = total_employees
        
        day_name = date.strftime('%a')  # Mon, Tue, Wed, etc.
        
        result.append({
            "date": str(date),
            "day": day_name,
            "count": present_count
        })
    
    return result


@frappe.whitelist()
def get_month_holidays(month=None, year=None):
    """
    Fetch holidays for any given month/year.
    """

    today = datetime.today()
    month = int(month) if month else today.month
    year = int(year) if year else today.year

    holiday_lists = frappe.get_all(
        "Holiday List",
        filters={"year": year},
        fields=["name"]
    )

    result = []

    for hl in holiday_lists:
        doc = frappe.get_doc("Holiday List", hl.name)
        for h in doc.holidays:
            if h.holiday_date.month == month and h.holiday_date.year == year and h.is_working_day == 0:
                result.append({
                    "holiday_date": h.holiday_date.strftime("%Y-%m-%d"),
                    "description": h.description
                })

    return result


# Keep the file loaded in memory for performance
LOCATION_CACHE = None

def load_location_data():
    global LOCATION_CACHE
    if LOCATION_CACHE:
        return LOCATION_CACHE

    path = os.path.join(
        get_bench_path(),
        "apps", "company", "company", "utils", "location_data.json"
    )

    with open(path, "r", encoding="utf-8") as f:
        LOCATION_CACHE = json.load(f)

    return LOCATION_CACHE


@frappe.whitelist()
def get_states(country):
    data = load_location_data()

    for c in data:
        if c["country"] == country:
            # return array of state names EXACTLY like old API
            return [state["name"] for state in c["states"]]

    return []


@frappe.whitelist()
def get_cities(country, state):
    data = load_location_data()

    for c in data:
        if c["country"] == country:
            for st in c["states"]:
                if st["name"].lower().strip() == state.lower().strip():
                    # return list of city names EXACTLY like old API
                    return st["cities"]

    return []
    
    
#=================== Convert Estimation to Invoice ==========================

import frappe

@frappe.whitelist()
def convert_estimation_to_invoice(estimation):
    if not estimation:
        frappe.throw("Estimation ID required")

    # Load estimation document
    est = frappe.get_doc("Estimation", estimation)

    # Prevent duplicate conversion
    existing_invoice = frappe.db.get_value(
        "Invoice",
        {"converted_estimation_id": est.name},
        "name"
    )
    if existing_invoice:
        frappe.msgprint(f"Invoice <b>{existing_invoice}</b> already created for this estimation.")
        return existing_invoice

    # Create new invoice
    inv = frappe.new_doc("Invoice")
    inv.flags.ignore_mandatory = True

    # Copy main fields
    fields_to_copy = [
        "client_name",
        "billing_name",
        "total_qty",
        "total_amount",
        "overall_discount_type",
        "overall_discount",
        "grand_total",
        "description"
    ]

    for f in fields_to_copy:
        inv.set(f, est.get(f))

    # Invoice date
    inv.invoice_date = frappe.utils.nowdate()

    # Conversion flags
    inv.converted_from_estimation = 1
    inv.converted_estimation_id = est.name

    # Copy items
    for item in est.get("table_qecz"):
        inv.append("table_qecz", {
            "service": item.service,
            "hsn_code": item.hsn_code,
            "description": item.description,
            "quantity": item.quantity,
            "price": item.price,
            "discount_type": item.discount_type,
            "discount": item.discount,
            "tax_type": item.tax_type,
            "tax_category": item.tax_category,
            "tax_percent": item.tax_percent,
            "tax_amount": item.tax_amount,
            "cgst": item.cgst,
            "sgst": item.sgst,
            "igst": item.igst,
            "sub_total": item.sub_total
        })

    # Save invoice
    inv.insert(ignore_permissions=True, ignore_mandatory=True)

    # SUCCESS MESSAGE
    frappe.msgprint(
        msg=f"Estimation <b>{est.name}</b> successfully converted to Invoice <b>{inv.name}</b>!",
        title="Conversion Complete",
        indicator="green"
    )

    return inv.name


@frappe.whitelist()
def get_current_month_missing_timesheets():
    import calendar
    from datetime import date, timedelta

    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user": user}, "name")

    if not employee:
        return {"error": "No employee linked"}

    today = date.today()
    year = today.year
    month = today.month

    # Month start & end
    first_day = date(year, month, 1)
    last_day = today - timedelta(days=1)

    # ---------------------------
    # 1️⃣ FETCH HOLIDAYS (Your Custom DocType)
    # ---------------------------
    holiday_list_doc = frappe.get_all(
        "Holiday List",
        fields=["name"],
        filters={"year": year, "month_year": month},
        limit=1
    )

    holidays = []
    if holiday_list_doc:
        holiday_list_name = holiday_list_doc[0].name

        holiday_rows = frappe.get_all(
            "Holidays",
            fields=["holiday_date", "is_working_day"],
            filters={"parent": holiday_list_name}
        )

        holidays = [
            h.holiday_date
            for h in holiday_rows
            if not h.is_working_day   # exclude working days
        ]

    # ---------------------------
    # 2️⃣ FETCH EXISTING TIMESHEETS
    # ---------------------------
    existing_ts = [
        d.timesheet_date
        for d in frappe.get_all(
            "Timesheet",
            fields=["timesheet_date"],
            filters={
                "employee": employee,
                "timesheet_date": ["between", [first_day, last_day]]
            }
        )
    ]

    # ---------------------------
    # 3️⃣ CALCULATE MISSING DATES
    # ---------------------------
    missing = []
    current = first_day

    while current <= last_day:

        # Skip Sundays
        if current.weekday() == 6:
            current += timedelta(days=1)
            continue

        # Skip holidays (non-working)
        if current in holidays:
            current += timedelta(days=1)
            continue

        # Skip days already having timesheet
        if current not in existing_ts:
            missing.append(str(current))

        current += timedelta(days=1)

    return missing


@frappe.whitelist()
def get_leave_allocation_by_type(leave_type):
    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user": user}, "name")

    if not employee:
        return {
            "allocated": 0,
            "taken": 0,
            "balance": 0
        }

    today = getdate()
    month_start = today.replace(day=1)
    month_end = today

    # Fetch allocations that match leave type AND overlap this month
    allocations = frappe.db.get_all(
        "Leave Allocation",
        filters={
            "employee": employee,
            "leave_type": leave_type,
            "status": "Approved",
            "from_date": ["<=", month_end],
            "to_date": [">=", month_start]
        },
        fields=["total_leaves_allocated", "total_leaves_taken"]
    )

    if not allocations:
        return {
            "allocated": 0,
            "taken": 0,
            "balance": 0
        }

    allocated = sum(a.total_leaves_allocated for a in allocations)
    taken = sum(a.total_leaves_taken for a in allocations)
    balance = allocated - taken

    return {
        "allocated": allocated,
        "taken": taken,
        "balance": balance
    }


from dateutil.relativedelta import relativedelta

@frappe.whitelist()
def is_employee_in_probation():
    user = frappe.session.user

    employee = frappe.db.get_value(
        "Employee",
        {"user": user},
        ["date_of_joining"],
        as_dict=True
    )

    if not employee or not employee.date_of_joining:
        return {"in_probation": False}

    doj = employee.date_of_joining
    today = frappe.utils.getdate()

    # Probation ends exactly 3 months after DOJ
    probation_end = doj + relativedelta(months=+3)

    return {
        "in_probation": today < probation_end
    }


@frappe.whitelist()
def get_today_event():
    user = frappe.session.user

    event = frappe.db.get_value(
        "Flash Message",
        {"enabled": 1, "event_date": frappe.utils.today()},
        ["name", "event_name", "title", "message", "music"],
        as_dict=True
    )

    if not event:
        return

    # Fetch child table entries
    allowed_users = frappe.get_all(
        "Event Popup Allowed User",
        filters={"parent": event.name, "parenttype": "Flash Message"},
        fields=["user"]
    )

    if allowed_users:
        allowed_list = [u.user for u in allowed_users]
        if user not in allowed_list:
            return  # Block popup for this user

    return event

import frappe
import qrcode
import base64
from io import BytesIO

@frappe.whitelist()
def get_upi_qr(upi_string):
    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=2
    )
    qr.add_data(upi_string)
    qr.make(fit=True)

    img = qr.make_image(fill='black', back_color='white')

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return encoded

@frappe.whitelist()
def has_invoice_collections(invoice_name):
    count = frappe.db.count("Invoice Collection", {"invoice": invoice_name})
    return count > 0


@frappe.whitelist()
def get_dashboard_stats():

    # ----------------------------------
    # ESTIMATION COUNTS
    # ----------------------------------

    # Converted estimations = Those that appear in Invoice.converted_estimation_id
    converted_list = frappe.db.get_all(
        "Invoice",
        filters={"converted_from_estimation": 1},
        fields=["converted_estimation_id"]
    )

    converted_ids = [d.converted_estimation_id for d in converted_list if d.converted_estimation_id]

    # Total converted estimation count
    converted_estimations = len(converted_ids)

    # Pending estimations = Estimations NOT in converted list
    if converted_ids:
        pending_estimations = frappe.db.count(
            "Estimation",
            filters=[["ref_no", "not in", converted_ids]]
        )
    else:
        # if nothing converted, all are pending
        pending_estimations = frappe.db.count("Estimation")

    # ----------------------------------
    # INVOICE COUNTS
    # ----------------------------------

    invoices = frappe.db.get_all(
        "Invoice",
        filters={"docstatus": 0},
        fields=["name", "balance_amount"]
    )

    total_pending = 0

    for inv in invoices:

        # Fetch latest Invoice Collection entry
        latest = frappe.db.sql("""
            SELECT amount_pending
            FROM `tabInvoice Collection`
            WHERE invoice = %s
            ORDER BY creation DESC
            LIMIT 1
        """, (inv.name,), as_dict=True)

        if latest and latest[0].amount_pending is not None:
            # If collection exists → use latest pending
            pending = latest[0].amount_pending
        else:
            # If no collection → full balance is pending
            pending = inv.balance_amount

        total_pending += pending or 0


    # Count open invoices
    open_invoices = frappe.db.count("Invoice", {"docstatus": 0})


    return {
        "pending_estimations": pending_estimations,
        "converted_estimations": converted_estimations,
        "open_invoices": open_invoices,
        "invoice_pending_amount": total_pending
    }
    
@frappe.whitelist()
def get_job_openings():
    jobs = frappe.get_all(
        "Job Opening",
        filters={"status": "Open"},
        fields="*",
        order_by="posted_on desc"
    )
    return jobs


@frappe.whitelist(allow_guest=True)
def submit_job_application():
    data = frappe.form_dict

    # 1) Validate file
    if "resume_attachment" not in frappe.request.files:
        frappe.throw("Please upload your Resume / CV")

    uploaded_file = frappe.request.files["resume_attachment"]

    # 2) Save file temporarily (without linking)
    temp_file = save_file(
        uploaded_file.filename,
        uploaded_file.read(),
        None,
        None,
        folder=None,
        is_private=1
    )

    # 3) Create Job Applicant with mandatory resume field filled
    doc = frappe.get_doc({
        "doctype": "Job Applicant",
        "applicant_name": data.get("applicant_name"),
        "email_id": data.get("email_id"),
        "phone_number": data.get("phone_number"),
        "state": data.get("state"),
        "city": data.get("city"),
        "job_title": data.get("job_title"),
        "source": data.get("source"),
        "cover_letter": data.get("cover_letter"),
        "resume_attachment": temp_file.file_url,
        "lower_range": data.get("lower_range"),
        "upper_range": data.get("upper_range")
    })

    doc.insert(ignore_permissions=True)

    # 4) Attach file to Job Applicant safely (no timestamp mismatch)
    temp_file.update({
        "attached_to_doctype": "Job Applicant",
        "attached_to_name": doc.name
    })

    frappe.db.commit()

    return {
        "status": "success",
        "message": "Application submitted",
        "applicant_id": doc.name
    }


@frappe.whitelist()
def get_expense_income_summary(filter_type=None, from_date=None, to_date=None):

    conditions_income = ""
    conditions_expense = ""

    # ---------------------- FILTER HANDLING ----------------------
    if filter_type == "today":
        conditions_income = "WHERE date = CURDATE()"
        conditions_expense = "WHERE date = CURDATE()"

    elif filter_type == "this_week":
        conditions_income = "WHERE YEARWEEK(date) = YEARWEEK(CURDATE())"
        conditions_expense = "WHERE YEARWEEK(date) = YEARWEEK(CURDATE())"

    elif filter_type == "this_month":
        conditions_income = "WHERE MONTH(date) = MONTH(CURDATE()) AND YEAR(date) = YEAR(CURDATE())"
        conditions_expense = "WHERE MONTH(date) = MONTH(CURDATE()) AND YEAR(date) = YEAR(CURDATE())"

    elif filter_type == "this_year":
        conditions_income = "WHERE YEAR(date) = YEAR(CURDATE())"
        conditions_expense = "WHERE YEAR(date) = YEAR(CURDATE())"

    elif filter_type == "custom" and from_date and to_date:
        conditions_income = f"WHERE date BETWEEN '{from_date}' AND '{to_date}'"
        conditions_expense = f"WHERE date BETWEEN '{from_date}' AND '{to_date}'"


    # ---------------------- QUERY ----------------------
    total_income = frappe.db.sql(f"""
        SELECT IFNULL(SUM(amount), 0)
        FROM `tabIncome`
        {conditions_income}
    """)[0][0]

    total_expense = frappe.db.sql(f"""
        SELECT IFNULL(SUM(total), 0)
        FROM `tabExpense`
        {conditions_expense}
    """)[0][0]

    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": total_income - total_expense
    }

@frappe.whitelist()
def get_expense_tracker_summary(filter_type="", from_date="", to_date="", expense_type=""):
    filters = []

    if expense_type and expense_type != "All":
        filters.append(["type", "=", expense_type])
    
    # Fallback to creation if date_time is not set
    # Note: Using get_list with filters is easier for standard fields
    
    if filter_type == "today":
        filters.append(["date_time", "between", [today() + " 00:00:00", today() + " 23:59:59"]])
    
    elif filter_type == "this_week":
        start = add_days(today(), -7)
        filters.append(["date_time", "between", [get_date_str(start) + " 00:00:00", today() + " 23:59:59"]])
        
    elif filter_type == "this_month":
        start = get_first_day(today())
        end = get_last_day(today())
        filters.append(["date_time", "between", [get_date_str(start) + " 00:00:00", get_date_str(end) + " 23:59:59"]])

        
    elif filter_type == "this_year":
        year = getdate(today()).year
        filters.append(["date_time", "between", [f"{year}-01-01 00:00:00", f"{year}-12-31 23:59:59"]])
        
    elif filter_type == "custom" and from_date and to_date:
        filters.append(["date_time", "between", [from_date + " 00:00:00", to_date + " 23:59:59"]])


    # We fetch type and amount for all matching records and sum in Python
    # This is very fast for reasonable amounts of data and much easier to debug
    records = frappe.get_all("Expense Tracker", 
        fields=["type", "amount"], 
        filters=filters
    )

    income = 0
    expense = 0
    
    for d in records:
        val = float(d.amount or 0)
        if d.type == "Income":
            income += val
        elif d.type == "Expense":
            expense += val

    return {
        "total_income": income,
        "total_expense": expense,
        "balance": income - expense,
        "debug": {
            "filters": filters,
            "filter_type": filter_type,
            "count": len(records),
            "total_count": frappe.db.count("Expense Tracker")
        }
    }




# =================== Automated Chat Messages ==================

def get_chatbot_user():
    """Find a user with the 'Chat Bot' role."""
    return frappe.db.get_value("Has Role", {"role": "Chat Bot", "parenttype": "User"}, "parent")

def send_automated_chat_message(sender_email, receiver_email, content):
    if not sender_email:
        sender_email = get_chatbot_user()
    
    if not sender_email:
        return False
    """
    Sends an automated chat message between two users.
    If no direct chat channel exists, it creates one.
    """
    try:
        from clefincode_chat.api.api_1_2_1.api import check_if_contact_has_chat, create_channel, send
    except ImportError:
        frappe.log_error("clefincode_chat app not found or API path incorrect", "Automated Chat Error")
        return False

    if not sender_email or not receiver_email or not content:
        return False

    # 1. Check if chat exists
    chat_info = check_if_contact_has_chat(sender_email, receiver_email, "Chat")
    room = None
    if chat_info.get("results") and isinstance(chat_info["results"], dict) and chat_info["results"].get("name"):
        room = chat_info["results"]["name"]

    # 2. If no room, create a Direct channel
    if not room:
        users_list = [
            {"email": sender_email, "platform": "Chat"},
            {"email": receiver_email, "platform": "Chat"}
        ]
        sender_full_name = frappe.db.get_value("User", sender_email, "full_name") or sender_email
        
        create_res = create_channel(
            channel_name="",
            users=json.dumps(users_list),
            type="Direct",
            last_message=content,
            creator_email=sender_email,
            creator=sender_full_name
        )
        
        if create_res.get("results") and create_res["results"][0].get("room"):
            room = create_res["results"][0]["room"]

    # 3. Send the message
    if room:
        sender_full_name = frappe.db.get_value("User", sender_email, "full_name") or sender_email
        send(content, sender_full_name, room, sender_email, skip_notification=1)
        return True

    return False


@frappe.whitelist()
def test_automated_message(receiver_email, content):
    """
    Whitelisted API to test automated message sending.
    Uses the current user as sender.
    """
    return send_automated_chat_message(frappe.session.user, receiver_email, content)


def is_working_day(check_date):
    """
    Checks if a date is a working day (not Sunday and not in Holiday List).
    """
    from frappe.utils import getdate
    check_date = getdate(check_date)
    
    # 1. Skip Sundays
    if check_date.weekday() == 6:
        return False
        
    # 2. Check Holiday List
    year = check_date.year
    month = check_date.month
    
    holiday_list_doc = frappe.get_all(
        "Holiday List",
        filters={"year": year, "month_year": month},
        limit=1
    )
    
    if holiday_list_doc:
        holidays = frappe.get_all(
            "Holidays",
            filters={"parent": holiday_list_doc[0].name, "holiday_date": check_date, "is_working_day": 0}
        )
        if holidays:
            return False
            
    return True


def send_daily_timesheet_reminders():
    """
    Scheduled job to send messages based on Manual Chat Message settings.
    """
    try:
        doc = frappe.get_single("Manual Chat Message")
        doc.process_scheduled_send()
    except Exception as e:
        frappe.log_error(f"Scheduled Chat Error: {str(e)}", "Scheduled Chat Error")


def process_chat_message_queue():
    """
    Background job to process pending messages in the queue.
    """
    pending_messages = frappe.get_all(
        "Chat Message Queue",
        filters={"status": "Pending"},
        fields=["name", "sender", "receiver", "content"]
    )

    for msg in pending_messages:
        # Update status to Sending to prevent duplicate processing
        frappe.db.set_value("Chat Message Queue", msg.name, "status", "Sending")
        frappe.db.commit()

        try:
            if send_automated_chat_message(msg.sender, msg.receiver, msg.content):
                frappe.db.set_value("Chat Message Queue", msg.name, {
                    "status": "Sent",
                    "sent_on": frappe.utils.now_datetime()
                })
            else:
                frappe.db.set_value("Chat Message Queue", msg.name, {
                    "status": "Failed",
                    "error_message": "send_automated_chat_message returned False"
                })
        except Exception as e:
            frappe.db.set_value("Chat Message Queue", msg.name, {
                "status": "Failed",
                "error_message": str(e)
            })
        
        frappe.db.commit()


def _get_attendance_status(hours, p_threshold, h_threshold):
    """Categorize hours into Present, Half Day, or Absent."""
    hours = float(hours or 0)
    p_threshold = float(p_threshold or 5.0)
    h_threshold = float(h_threshold or 3.0)
    
    if hours >= p_threshold:
        return "Present"
    elif hours >= h_threshold:
        return "Half Day"
    else:
        return "Absent"

@frappe.whitelist()
def get_month_calendar_data(month=None, year=None):
    """
    Fetch both holidays and attendance for a specific employee and month.
    """
    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user": user}, ["name", "date_of_joining"], as_dict=True)
    
    if not employee:
        return {"holidays": [], "attendance": [], "joining_date": None}
    
    employee_id = employee.name
    joining_date = employee.date_of_joining

    today_date = datetime.today().date()
    month = int(month) if month else today_date.month
    year = int(year) if year else today_date.year

    # 1. Fetch Holidays
    holidays = []
    # Try to get a holiday list for the current month/year
    try:
        holiday_list = frappe.db.get_value("Holiday List", 
            {"month_year": str(month), "year": year}, 
            "name")
        
        if not holiday_list:
            # If no specific month/year list, get any holiday list
            holiday_list = frappe.db.get_value("Holiday List", None, "name")
    except Exception:
        holiday_list = None
    
    if holiday_list:
        start_date = f"{year}-{month:02d}-01"
        end_date = get_last_day(getdate(start_date))
        h_records = frappe.db.sql("""
            SELECT holiday_date as date, description, is_working_day
            FROM `tabHolidays`
            WHERE parent = %s
            AND holiday_date BETWEEN %s AND %s
        """, (holiday_list, start_date, end_date), as_dict=True)
        holidays = [{
            "date": str(h.date), 
            "description": h.description,
            "is_working_day": h.is_working_day
        } for h in h_records]

    # 2. Fetch Attendance
    attendance = []
    start_date = f"{year}-{month:02d}-01"
    end_date = get_last_day(getdate(start_date))
    
    settings = frappe.get_doc("HRMS Settings")
    source = settings.get("weekly_chart_source") or "Attendance"
    p_threshold = settings.get("present_threshold") or 5.0
    h_threshold = settings.get("half_day_threshold") or 3.0

    if source == "Daily Log":
        # Fetch Session records
        session_records = frappe.db.sql("""
            SELECT 
                login_date as date,
                login_time,
                logout_time,
                total_work_hours as working_hours
            FROM `tabEmployee Session`
            WHERE employee = %s
            AND login_date BETWEEN %s AND %s
            ORDER BY login_date ASC
        """, (employee_id, start_date, end_date), as_dict=True)

        for record in session_records:
            attendance.append({
                "date": str(record.date),
                "status": _get_attendance_status(record.working_hours, p_threshold, h_threshold),
                "in_time": record.login_time.strftime("%H:%M:%S") if record.login_time else None,
                "out_time": record.logout_time.strftime("%H:%M:%S") if record.logout_time else None,
                "working_hours": record.working_hours or 0
            })
    else:
        # Helper to convert timedelta to time str
        def td_to_str(td):
            if not td: return None
            total_seconds = int(td.total_seconds())
            return f"{total_seconds // 3600:02d}:{(total_seconds % 3600) // 60:02d}:{(total_seconds % 60):02d}"

        att_records = frappe.get_all("Attendance",
            filters={
                "employee": employee_id,
                "attendance_date": ["between", [start_date, end_date]]
            },
            fields=["attendance_date", "status", "in_time", "out_time", "working_hours_decimal as working_hours", "leave_type"],
            order_by="attendance_date asc"
        )

        for att in att_records:
            att_dict = {
                "date": str(att.attendance_date),
                "status": att.status,
                "in_time": td_to_str(att.in_time),
                "out_time": td_to_str(att.out_time),
                "working_hours": att.working_hours or 0
            }
            if att.leave_type:
                att_dict["leave_type"] = att.leave_type
            attendance.append(att_dict)

    # 3. Fetch approved Leave Applications for the month
    leave_app_map = {}
    try:
        approved_leaves = frappe.get_all("Leave Application",
            filters={
                "employee": employee_id,
                "from_date": ["<=", end_date],
                "to_date": [">=", start_date],
                "docstatus": ["<", 2]
            },
            fields=["leave_type", "from_date", "to_date", "half_day", "status", "workflow_state", "docstatus"]
        )
        for l in approved_leaves:
            status_val = str(l.get("status") or "").lower()
            wf_val = str(l.get("workflow_state") or "").lower()
            is_approved = status_val == "approved" or wf_val == "approved" or l.get("docstatus") == 1
            if is_approved:
                l_from = getdate(l.from_date)
                l_to = getdate(l.to_date)
                m_s = getdate(start_date)
                m_e = getdate(end_date)
                d_p = max(l_from, m_s)
                d_e = min(l_to, m_e)
                while d_p <= d_e:
                    l_type = l.leave_type
                    if l.half_day:
                        l_type += " (Half Day)"
                    leave_app_map[str(d_p)] = l_type
                    d_p = add_days(d_p, 1)
                    if isinstance(d_p, str):
                        d_p = getdate(d_p)
    except Exception as e:
        frappe.log_error(f"Error in get_month_calendar_data leave fetch: {e}")

    # 4. Build Full Month Timeline
    calendar_data = []
    first_day = getdate(f"{year}-{month:02d}-01")
    last_day = get_last_day(first_day)
    
    attendance_map = {a['date']: a for a in attendance}
    holiday_map = {h['date']: h for h in holidays}
    
    current = first_day
    while current <= last_day:
        date_str = str(current)
        day_record = {
            "date": date_str,
            "status": "Not Marked",
            "check_in": None,
            "check_out": None,
            "working_hours": 0,
            "holiday_info": None,
            "holiday_is_working_day": 0,
            "leave_type": leave_app_map.get(date_str)
        }
        
        # Add attendance data if exists
        if date_str in attendance_map:
            att = attendance_map[date_str]
            day_record.update({
                "status": att["status"],
                "check_in": att["in_time"],
                "check_out": att["out_time"],
                "working_hours": att["working_hours"]
            })
            if att.get("leave_type"):
                day_record["leave_type"] = att["leave_type"]

        # Add leave application info if exists
        if date_str in leave_app_map:
            day_record["leave_type"] = leave_app_map[date_str]
            if day_record["status"] in ["Not Marked", "On Leave", "Leave"]:
                day_record["status"] = "On Leave"

        # Add holiday info if exists
        if date_str in holiday_map:
            h = holiday_map[date_str]
            day_record["holiday_info"] = h["description"]
            day_record["holiday_is_working_day"] = h["is_working_day"]
            # If not marked and is a non-working holiday
            if day_record["status"] == "Not Marked" and not h["is_working_day"]:
                day_record["status"] = "Holiday"
                
        calendar_data.append(day_record)
        current = add_days(current, 1)

    return {
        "calendar_data": calendar_data,
        "joining_date": str(joining_date) if joining_date else None
    }


@frappe.whitelist()
def get_salary_slips_with_child_tables(start_date=None, end_date=None, employee=None):
    filters = {}
    if start_date:
        filters["pay_period_start"] = [">=", start_date]
    if end_date:
        filters["pay_period_end"] = ["<=", end_date]
    if employee and employee != "all":
        filters["employee"] = employee

    slips = frappe.get_all("Salary Slip", filters=filters, fields=["name"], order_by="pay_period_start desc")
    
    detailed_slips = []
    for s in slips:
        doc = frappe.get_doc("Salary Slip", s.name)
        detailed_slips.append(doc.as_dict())
        
    return detailed_slips

@frappe.whitelist(allow_guest=True)
def track_open(id):
	from company.company.doctype.crm_email_campaign.crm_email_campaign import track_open as _track_open
	return _track_open(id)

@frappe.whitelist(allow_guest=True)
def track_click(id, url):
	from company.company.doctype.crm_email_campaign.crm_email_campaign import track_click as _track_click
	return _track_click(id, url)


@frappe.whitelist()
def get_leave_application_permission_query_conditions(user):
    # Check roles of the user
    hr_roles = ["HR", "HR Manager", "System Manager", "Administrator"]
    user_roles = frappe.get_roles(user)
    is_hr = any(role in user_roles for role in hr_roles)
    
    if not is_hr:
        return ""
        
    unread_only_requested = False
    
    # Check direct form_dict parameter
    if frappe.form_dict.get('unread_only') in ('true', '1') or frappe.form_dict.get('unread_messages') in ('true', '1'):
        unread_only_requested = True
        
    # Check filters in form_dict
    filters_str = frappe.form_dict.get('filters')
    if filters_str:
        try:
            import json
            filters_list = json.loads(filters_str)
            if isinstance(filters_list, list):
                for f in filters_list:
                    if isinstance(f, list) and len(f) >= 3:
                        fieldname = f[1] if len(f) == 4 else f[0]
                        value = f[3] if len(f) == 4 else f[2]
                        if fieldname in ('unread_only', 'unread_messages') and value in (True, 'true', 1, '1'):
                            unread_only_requested = True
                            break
                    elif isinstance(f, dict):
                        if f.get('unread_only') or f.get('unread_messages'):
                            unread_only_requested = True
                            break
        except Exception:
            pass
            
    if unread_only_requested:
        return f"`tabLeave Application`.name in (select reference_name from `tabHR Read Tracker` where reference_doctype = 'Leave Application' and read_by = {frappe.db.escape(user)} and is_read = 0)"
        
    return ""


@frappe.whitelist()
def get_request_permission_query_conditions(user):
    # Only HR roles get the unread filter applied
    hr_roles = ["HR", "HR Manager", "System Manager", "Administrator"]
    user_roles = frappe.get_roles(user)
    is_hr = any(role in user_roles for role in hr_roles)

    if not is_hr:
        return ""

    unread_only_requested = False

    # Check direct form_dict parameter
    if frappe.form_dict.get('unread_messages') in ('true', '1'):
        unread_only_requested = True

    if unread_only_requested:
        return f"`tabRequest`.name in (select reference_name from `tabHR Read Tracker` where reference_doctype = 'Request' and read_by = {frappe.db.escape(user)} and is_read = 0)"

    return ""


@frappe.whitelist()
def get_wfh_attendance_permission_query_conditions(user):
    # Only HR roles get the unread filter applied
    hr_roles = ["HR", "HR Manager", "System Manager", "Administrator"]
    user_roles = frappe.get_roles(user)
    is_hr = any(role in user_roles for role in hr_roles)

    if not is_hr:
        return ""

    unread_only_requested = False

    # Check direct form_dict parameter
    if frappe.form_dict.get('unread_only') in ('true', '1') or frappe.form_dict.get('unread_messages') in ('true', '1'):
        unread_only_requested = True

    if unread_only_requested:
        return f"`tabWFH Attendance`.name in (select reference_name from `tabHR Read Tracker` where reference_doctype = 'WFH Attendance' and read_by = {frappe.db.escape(user)} and is_read = 0)"

    return ""


@frappe.whitelist()
def get_reimbursement_claim_permission_query_conditions(user):
    # Only HR / manager roles get the unread filter applied
    hr_roles = ["HR", "HR Manager", "HR User", "System Manager", "Administrator", "Accounts Manager"]
    user_roles = frappe.get_roles(user)
    is_hr = any(role in user_roles for role in hr_roles)

    if not is_hr:
        return ""

    unread_only_requested = False

    # Check direct form_dict parameter
    if frappe.form_dict.get('unread_only') in ('true', '1') or frappe.form_dict.get('unread_messages') in ('true', '1'):
        unread_only_requested = True

    if unread_only_requested:
        return f"`tabReimbursement Claim`.name in (select reference_name from `tabHR Read Tracker` where reference_doctype = 'Reimbursement Claim' and read_by = {frappe.db.escape(user)} and is_read = 0)"

    return ""



