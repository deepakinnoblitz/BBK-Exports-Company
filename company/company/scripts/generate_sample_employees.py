import random
import time
from datetime import date, timedelta
import frappe
from frappe.utils import getdate

# ----------------------------------------------------------------------
# Name Pools
# ----------------------------------------------------------------------

MALE_FIRST_NAMES = [
    "Aarav", "Aditya", "Ajay", "Amit", "Anand", "Anbu", "Arjun", "Arun", 
    "Ashok", "Balaji", "Balamurugan", "Bharath", "Chandran", "Deepak", 
    "Dhanush", "Dinesh", "Elango", "Ganesh", "Gopinath", "Hari", "Harish", 
    "Ilango", "Jagadish", "Jayakumar", "Kailash", "Kannan", "Karthik", 
    "Kishore", "Krishnan", "Kumar", "Madhavan", "Mahesh", "Manikandan", 
    "Manoj", "Mithun", "Mohan", "Mugilan", "Mukesh", "Murugan", "Muthu", 
    "Nagaraj", "Naveen", "Nirmal", "Parthiban", "Prakash", "Prasanna", 
    "Prasanth", "Praveen", "Raghavan", "Rahul", "Raja", "Rajesh", "Ramesh", 
    "Ranjith", "Ravi", "Ravichandran", "Rohit", "Sachin", "Sakthivel", 
    "Sanjay", "Santhosh", "Saravanan", "Sasikumar", "Sathish", "Selvam", 
    "Senthil", "Shankar", "Shiva", "Siddharth", "Siva", "Subramanian", 
    "Sundar", "Sunil", "Suresh", "Surya", "Thangavel", "Udhaya", "Vasanth", 
    "Velu", "Venkatesh", "Vignesh", "Vijay", "Vijayakumar", "Vikram", 
    "Vinoth", "Vishal", "Vivek", "Yogesh"
]

FEMALE_FIRST_NAMES = [
    "Abirami", "Aishwarya", "Akshaya", "Ananya", "Anitha", "Anu", "Anushka", 
    "Archana", "Bhavani", "Bhuvaneswari", "Deepa", "Deepika", "Devi", 
    "Dhanalakshmi", "Divya", "Durga", "Gayathri", "Geetha", "Gomathi", 
    "Hemalatha", "Indira", "Ishwarya", "Janani", "Jaya", "Jayanthi", 
    "Kalaivani", "Kamali", "Kanimozhi", "Karthika", "Kavitha", "Keerthana", 
    "Kokila", "Kowsalya", "Krithika", "Lakshmi", "Lavanya", "Madhumitha", 
    "Malathi", "Manju", "Meena", "Meenakshi", "Monisha", "Mythili", 
    "Nandhini", "Navaneetha", "Nithya", "Pavithra", "Pooja", "Prabhavathi", 
    "Preethi", "Priya", "Priyanka", "Radha", "Rajalakshmi", "Rajeswari", 
    "Ramya", "Revathi", "Rithika", "Rohini", "Sandhiya", "Sangeetha", 
    "Saranya", "Saraswathi", "Sasikala", "Sathya", "Shalini", "Shanthi", 
    "Sharmila", "Sindhu", "Sneha", "Soundarya", "Sowmya", "Subhashini", 
    "Suganya", "Sujatha", "Sumathi", "Sundari", "Sunita", "Swathi", 
    "Swetha", "Uma", "Usha", "Vaishnavi", "Vasanthi", "Vedhavalli", 
    "Vidya", "Vijaya", "Vinitha", "Yamuna"
]

LAST_NAMES = [
    "Adhithya", "Balakrishnan", "Baskaran", "Chandrasekar", "Chelliah", 
    "Chidambaram", "Dakshinamoorthy", "Damodaran", "Dayalan", "Devarajan", 
    "Dhandapani", "Duraisamy", "Elangovan", "Ganesan", "Gopalakrishnan", 
    "Govindasamy", "Gunasekaran", "Hariharan", "Ilavarasu", "Iniyan", 
    "Iyyappan", "Jayaraman", "Kadhirvel", "Kaliappan", "Kandasamy", 
    "Karthikeyan", "Karuppasamy", "Kasiviswanathan", "Krishnamoorthy", 
    "Kulasekaran", "Kumaravel", "Lakshmanan", "Madhusudhanan", "Manickam", 
    "Marimuthu", "Meenakshisundaram", "Moorthy", "Munusamy", "Murugesan", 
    "Muthukumar", "Muthusamy", "Nadarajan", "Nagarajan", "Nallathambi", 
    "Nallasamy", "Narayanasamy", "Natarajan", "Palani", "Palanisamy", 
    "Paneerselvam", "Parthasarathy", "Periasamy", "Perumal", "Ponnusamy", 
    "Pugazhenthi", "Radhakrishnan", "Raghavendran", "Rajagopal", "Rajan", 
    "Rajendran", "Ramachandran", "Ramalingam", "Ramasamy", "Ranganathan", 
    "Sadhasivam", "Sambasivam", "Sampath", "Sankaran", "Santhanam", 
    "Saravanakumar", "Sathiyamoorthy", "Selvaraj", "Shanmugam", "Singaravelu", 
    "Sivakumar", "Sivalingam", "Sivasamy", "Soundararajan", "Subbarayan", 
    "Sundararajan", "Sundaresan", "Thangamuthu", "Thangaraj", "Thirunavukkarasu", 
    "Thirupathi", "Vadivel", "Vairavan", "Varadharajan", "Vedhachalam", 
    "Veerappan", "Velayutham", "Velmurugan", "Venkataraman", "Venugopal", 
    "Viswanathan"
]

CITIES_TAMIL_NADU = [
    ("Chennai", "Tamil Nadu"),
    ("Tiruppur", "Tamil Nadu"),
    ("Coimbatore", "Tamil Nadu"),
    ("Madurai", "Tamil Nadu"),
    ("Salem", "Tamil Nadu"),
    ("Erode", "Tamil Nadu"),
    ("Tiruchirappalli", "Tamil Nadu"),
    ("Vellore", "Tamil Nadu"),
    ("Thoothukudi", "Tamil Nadu"),
    ("Dindigul", "Tamil Nadu")
]

QUALIFICATIONS = [
    "10th Standard", "12th Standard", "ITI", "Diploma", 
    "B.A", "B.Com", "B.Sc", "B.E / B.Tech", "BCA / BBA", 
    "MBA", "Post Graduate / Master"
]

BLOOD_GROUPS = ["A+", "B+", "O+", "AB+", "A-", "B-", "O-"]

BUS_POINTS = ["Ambattur OT", "Thirumullaivoyal"]

# ----------------------------------------------------------------------
# Salary Tier Configurations
# ----------------------------------------------------------------------

def calculate_salary_structure(designation):
    """
    Computes balanced earnings, deductions, and CTC based on designation.
    Returns: (ctc, earnings_rows, deductions_rows, total_earnings, total_deductions, net_salary)
    """
    if designation == "Workers":
        # Workers: CTC 16,000 - 21,000
        ctc = float(random.choice([16000, 17000, 17500, 18000, 18500, 19000, 20000, 21000]))
        basic_da = round(ctc * 0.50, 2)
        hra = round(basic_da * 0.40, 2)
        other_allowance = round(ctc - basic_da - hra, 2)
        
        # Deductions
        pf = round(min(basic_da * 0.12, 1800.0), 2)
        esi = round(ctc * 0.0075, 2) if ctc <= 21000 else 0.0
        pt = 200.0
        
        earnings = [
            {"component_name": "Basic Pay + DA", "type": "Earning", "amount": basic_da},
            {"component_name": "HRA", "type": "Earning", "amount": hra},
            {"component_name": "Other Allowance", "type": "Earning", "amount": other_allowance},
        ]
        deductions = [
            {"component_name": "PF", "type": "Deduction", "amount": pf},
            {"component_name": "Prof.Tax", "type": "Deduction", "amount": pt},
        ]
        if esi > 0:
            deductions.append({"component_name": "ESI", "type": "Deduction", "amount": esi})
            
    elif designation == "North Indian Staff":
        # North Indian Staff: CTC 22,000 - 32,000
        ctc = float(random.choice([22000, 24000, 25000, 26000, 28000, 30000, 32000]))
        basic_da = round(ctc * 0.45, 2)
        hra = round(basic_da * 0.40, 2)
        other_allowance = round(ctc - basic_da - hra, 2)
        
        pf = round(min(basic_da * 0.12, 1800.0), 2)
        esi = round(ctc * 0.0075, 2) if ctc <= 21000 else 0.0
        pt = 450.0
        
        earnings = [
            {"component_name": "Basic Pay + DA", "type": "Earning", "amount": basic_da},
            {"component_name": "HRA", "type": "Earning", "amount": hra},
            {"component_name": "Other Allowance", "type": "Earning", "amount": other_allowance},
        ]
        deductions = [
            {"component_name": "PF", "type": "Deduction", "amount": pf},
            {"component_name": "Prof.Tax", "type": "Deduction", "amount": pt},
        ]
        if esi > 0:
            deductions.append({"component_name": "ESI", "type": "Deduction", "amount": esi})
            
    else:  # Staff Member / Senior
        # Staff Member: CTC 26,000 - 55,000
        ctc = float(random.choice([26000, 28000, 30000, 32000, 35000, 38000, 42000, 45000, 50000, 55000]))
        basic_da = round(ctc * 0.40, 2)
        hra = round(basic_da * 0.50, 2)
        other_allowance = round(ctc - basic_da - hra, 2)
        
        pf = 1800.0  # capped statutory PF
        pt = 740.0
        
        earnings = [
            {"component_name": "Basic Pay + DA", "type": "Earning", "amount": basic_da},
            {"component_name": "HRA", "type": "Earning", "amount": hra},
            {"component_name": "Other Allowance", "type": "Earning", "amount": other_allowance},
        ]
        deductions = [
            {"component_name": "PF", "type": "Deduction", "amount": pf},
            {"component_name": "Prof.Tax", "type": "Deduction", "amount": pt},
        ]

    total_earnings = round(sum(e["amount"] for e in earnings), 2)
    total_deductions = round(sum(d["amount"] for d in deductions), 2)
    net_salary = round(total_earnings - total_deductions, 2)

    return ctc, earnings, deductions, total_earnings, total_deductions, net_salary


# ----------------------------------------------------------------------
# Generator Function
# ----------------------------------------------------------------------

def run(count=1000, batch_size=100):
    """
    Generates `count` sample employee documents in Frappe with complete details and salary.
    Usage:
        bench --site <site> execute company.scripts.generate_sample_employees.run --args "(1000,)"
    """
    count = int(count)
    batch_size = int(batch_size)
    print(f"\n=======================================================")
    print(f" Starting Sample Employee Generation: {count} records")
    print(f"=======================================================")
    start_time = time.time()

    # Find starting employee_id sequence
    existing_records = frappe.db.get_all("Employee", fields=["employee_id"])
    existing_nums = [
        int(r.employee_id) for r in existing_records 
        if r.employee_id and r.employee_id.isdigit()
    ]
    next_id_num = (max(existing_nums) + 1) if existing_nums else 5

    # Fetch and ensure available masters dynamically
    departments = [d.name for d in frappe.db.get_all("Department")] or ["Level 1", "Level 2"]
    designations = [d.name for d in frappe.db.get_all("Designation")] or ["Workers", "Staff Member", "North Indian Staff"]
    shifts = [s.name for s in frappe.db.get_all("Shift")] or ["Morning Shift", "Afternoon Shift", "Night Shift"]
    lines = [l.name for l in frappe.db.get_all("Line Order")] or ["Line 1 - Cutting", "Line 2 - Ironing", "Line 3 - Striching"]
    routes = [r.name for r in frappe.db.get_all("Bus Travel Route")] or ["Avadi to Ambattur 2"]
    
    # Ensure all standard Blood Groups exist in the DB
    all_blood_groups = ["O+", "B+", "A+", "AB+", "O-", "A-", "B-", "AB-"]
    existing_bgs = [b.name for b in frappe.db.get_all("Blood Group")]
    for bg in all_blood_groups:
        if bg not in existing_bgs:
            try:
                bg_doc = frappe.get_doc({"doctype": "Blood Group", "blood_group": bg})
                bg_doc.insert(ignore_permissions=True)
                existing_bgs.append(bg)
            except Exception:
                pass
    blood_groups = existing_bgs or ["O+", "B+", "A+"]

    qualifications = [q.name for q in frappe.db.get_all("Qualification")] or ["10th Standard", "12th Standard", "B.A", "B.Com", "B.Sc"]

    # Bus route points
    bus_route_points = ["Ambattur OT", "Thirumullaivoyal", "Avadi Bus Terminus"]
    try:
        if routes:
            route_doc = frappe.get_doc("Bus Travel Route", routes[0])
            if hasattr(route_doc, "points") and route_doc.points:
                bus_route_points = [p.point_name for p in route_doc.points]
    except Exception:
        pass

    print(f"Loaded Master Records:")
    print(f" - Departments ({len(departments)}): {', '.join(departments)}")
    print(f" - Designations ({len(designations)}): {', '.join(designations)}")
    print(f" - Shifts ({len(shifts)}): {', '.join(shifts)}")
    print(f" - Lines ({len(lines)}): {', '.join(lines)}")
    print(f" - Blood Groups ({len(blood_groups)}): {', '.join(blood_groups)}")
    print(f" - Bus Route Points ({len(bus_route_points)}): {', '.join(bus_route_points)}")
    print(f" - Starting ID sequence from: {next_id_num:04d}\n")

    created_count = 0
    errors_count = 0

    base_joining_start = date(2021, 1, 1)
    base_joining_end = date(2026, 8, 1)
    days_range_joining = (base_joining_end - base_joining_start).days

    for i in range(count):
        emp_num = next_id_num + i
        emp_id_str = f"{emp_num:04d}"

        # Gender & Name Selection
        is_female = random.random() < 0.45
        gender = "Female" if is_female else "Male"
        first_name = random.choice(FEMALE_FIRST_NAMES) if is_female else random.choice(MALE_FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        full_name = f"{first_name} {last_name}"

        # Father / Husband Name
        guardian_first = random.choice(MALE_FIRST_NAMES)
        guardian_last = random.choice(LAST_NAMES)
        father_husband_name = f"{guardian_first} {guardian_last}"

        # Designation & Employee Type Mapping
        designation = random.choice(designations)
        if designation == "Workers":
            emp_type = "Workers - Skilled"
        elif designation == "North Indian Staff":
            emp_type = "North Indian Staff - Non CTC"
        else:
            emp_type = "Staff - CTC"

        department = random.choice(departments)
        shift = random.choice(shifts)
        line = random.choice(lines)

        # Dates: DOB (1975 to 2004) and DOJ (2021 to 2026)
        dob_year = random.randint(1975, 2004)
        dob_month = random.randint(1, 12)
        dob_day = random.randint(1, 28)
        dob = date(dob_year, dob_month, dob_day)

        doj_offset = random.randint(0, days_range_joining)
        doj = base_joining_start + timedelta(days=doj_offset)

        # Status: 96% Active, 4% Inactive
        is_active = random.random() < 0.96
        status = "Active" if is_active else "Inactive"
        date_of_leaving = None
        if not is_active:
            # Leaving date after joining
            dol_offset = random.randint(30, 700)
            date_of_leaving = min(doj + timedelta(days=dol_offset), date(2026, 9, 1))

        # Location
        city, state = random.choice(CITIES_TAMIL_NADU)

        # Contact & Email (unique per ID)
        clean_first = first_name.lower().replace(" ", "")
        clean_last = last_name.lower().replace(" ", "")
        email = f"{clean_first}.{clean_last}.{emp_num}@bbkexports.com"
        personal_email = f"{clean_first}.{clean_last}.{emp_num}@gmail.com"
        
        # Phone: Indian mobile +91-9... or +91-8... or +91-7...
        phone_prefix = random.choice(["98", "97", "99", "80", "81", "73", "74", "94"])
        phone = f"+91-{phone_prefix}{random.randint(10000000, 99999999)}"

        # Statutory IDs
        aadhar_number = f"{random.randint(2000, 9999)}{random.randint(1000, 9999)}{emp_num:04d}"
        uan_number = f"10{random.randint(1000, 9999)}{emp_num:06d}"
        pf_number = f"TN/MAS/{random.randint(10000, 99999)}/{emp_num:07d}"
        esi_no = f"51{random.randint(100000000000000, 999999999999999)}"
        
        # Bank Account: Create a linked Bank Account record
        acc_no = f"62{emp_num:010d}"
        bank_name = random.choice(["State Bank of India", "HDFC Bank", "ICICI Bank", "Indian Bank", "Canara Bank", "Axis Bank"])
        if not frappe.db.exists("Bank Account", acc_no):
            try:
                frappe.get_doc({
                    "doctype": "Bank Account",
                    "account_number": acc_no,
                    "bank_account_name": f"{full_name} ({emp_id_str})",
                    "bank_name": bank_name,
                    "branch": city,
                    "ifsc_code": f"SBIN{random.randint(1000000, 9999999)}",
                    "account_type": "Salary Account"
                }).insert(ignore_permissions=True)
            except Exception as e:
                print(f"Error creating Bank Account {acc_no}: {e}")

        # Performance & Qualifications
        score = random.randint(70, 100)
        eval_status = "Excellent" if score >= 90 else "Good" if score >= 80 else "Average"
        qualification = random.choice(qualifications)
        blood_group = random.choice(blood_groups)

        # Bus Route
        bus_route = random.choice(routes) if routes and random.random() < 0.70 else None
        bus_point = random.choice(bus_route_points) if bus_route else None

        # Salary Structure Calculation
        ctc, earnings, deductions, total_earnings, total_deductions, net_salary = calculate_salary_structure(designation)

        # Build Document Payload
        doc_payload = {
            "doctype": "Employee",
            "employee_id": emp_id_str,
            "employee_name": full_name,
            "father_husband_name": father_husband_name,
            "sex": gender,
            "dob": dob.strftime("%Y-%m-%d"),
            "marital_status": random.choice(["Married", "Single"]),
            "blood_group": blood_group,
            "qualification": qualification,
            "country": "India",
            "state": state,
            "city": city,
            "email": email,
            "personal_email": personal_email,
            "phone": phone,
            "department": department,
            "designation": designation,
            "employee_type": emp_type,
            "date_of_joining": doj.strftime("%Y-%m-%d"),
            "status": status,
            "date_of_leaving": date_of_leaving.strftime("%Y-%m-%d") if date_of_leaving else None,
            "shift": shift,
            "line_order": line,
            "bus_travel_route": bus_route,
            "bus_route_point": bus_point,
            "aadhar_number": aadhar_number,
            "uan_number": uan_number,
            "pf_number": pf_number,
            "esi_no": esi_no,
            "bank_account": acc_no,
            "evaluation_score": score,
            "evaluation_status": eval_status,
            "ctc": ctc,
            "total_earnings": total_earnings,
            "total_deductions": total_deductions,
            "net_salary": net_salary,
            "earnings": earnings,
            "deductions": deductions,
        }

        try:
            emp_doc = frappe.get_doc(doc_payload)
            emp_doc.insert(ignore_permissions=True)
            created_count += 1
        except Exception as e:
            errors_count += 1
            print(f"Error inserting {emp_id_str} ({full_name}): {e}")

        # Batch Commit
        if created_count % batch_size == 0 or (i + 1) == count:
            frappe.db.commit()
            elapsed = time.time() - start_time
            rate = created_count / elapsed if elapsed > 0 else 0
            percent = (created_count / count) * 100
            print(f"  [Progress] {created_count}/{count} ({percent:.1f}%) created - {rate:.1f} records/sec")

    frappe.db.commit()
    total_elapsed = time.time() - start_time

    print(f"\n=======================================================")
    print(f" Successfully Completed Employee Generation!")
    print(f" Total Created: {created_count}")
    print(f" Total Errors : {errors_count}")
    print(f" Time Taken   : {total_elapsed:.2f} seconds ({created_count/total_elapsed:.1f} rec/sec)")
    print(f" Total in DB  : {frappe.db.count('Employee')} employees")
    print(f"=======================================================\n")

    return {
        "created": created_count,
        "errors": errors_count,
        "elapsed_seconds": round(total_elapsed, 2)
    }
