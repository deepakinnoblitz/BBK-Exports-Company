import frappe

def run():
    # Remove any unwanted / typo entries
    for name in ["North Indian Staff - CTC", "North Indian Staff - Non CTC", "Contator"]:
        if frappe.db.exists("Employee Type", name):
            frappe.delete_doc("Employee Type", name, force=1)
            print(f"Deleted: {name}")

    employee_types_to_create = [
        {"employee_type": "Staff", "category_type": "CTC"},
        {"employee_type": "Staff", "category_type": "Non CTC"},
        {"employee_type": "North Indian", "category_type": "CTC"},
        {"employee_type": "North Indian", "category_type": "Non CTC"},
        {"employee_type": "Workers", "category_type": "Skilled"},
        {"employee_type": "Workers", "category_type": "Semi Skilled"},
        {"employee_type": "Workers", "category_type": "Unskilled"},
        {"employee_type": "Drivers", "category_type": "General"},
        {"employee_type": "Contractor", "category_type": "General"},
        {"employee_type": "House Keeping", "category_type": "General"},
        {"employee_type": "Security", "category_type": "General"},
        {"employee_type": "STP Employees", "category_type": "General"},
    ]

    results = []
    for item in employee_types_to_create:
        emp_type = item["employee_type"]
        cat_type = item["category_type"]
        expected_name = f"{emp_type} - {cat_type}" if cat_type != "General" else emp_type
        
        if not frappe.db.exists("Employee Type", expected_name):
            doc = frappe.new_doc("Employee Type")
            doc.employee_type = emp_type
            doc.category_type = cat_type
            doc.description = f"{emp_type} with {cat_type} categorization"
            doc.insert(ignore_permissions=True)
            results.append(f"Created: {doc.name}")
        else:
            results.append(f"Verified exists: {expected_name}")

    frappe.db.commit()
    print("\n".join(results))
