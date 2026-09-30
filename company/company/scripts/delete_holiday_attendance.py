import frappe

def run():
    print("Deleting child punches for Holiday attendance...")
    frappe.db.sql("""
        DELETE FROM `tabAttendance Punch`
        WHERE parent IN (
            SELECT name FROM `tabAttendance` WHERE status = 'Holiday'
        )
    """)

    print("Deleting Attendance records with status = 'Holiday'...")
    holiday_count = frappe.db.count("Attendance", filters={"status": "Holiday"})
    print(f"Found {holiday_count:,} Holiday Attendance records to delete.")

    frappe.db.sql("DELETE FROM `tabAttendance` WHERE status = 'Holiday'")
    frappe.db.commit()

    remaining = frappe.db.count("Attendance", filters={"status": "Holiday"})
    print(f"Deletion complete. Remaining Holiday Attendance records: {remaining}")
