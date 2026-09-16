from datetime import datetime, timedelta
import frappe
from frappe.model.document import Document

class Attendance(Document):
    def validate(self):
        self.check_duplicate_attendance()
        self.calculate_working_hours()

    def check_duplicate_attendance(self):
        existing_attendance = frappe.db.exists("Attendance", {
            "employee": self.employee,
            "attendance_date": self.attendance_date,
            "name": ["!=", self.name]
        })
        if existing_attendance:
            frappe.throw(f"Attendance record already exists for Employee {self.employee} on {self.attendance_date}")

    def calculate_working_hours(self):

        # ------------------------------
        # 1️⃣ LEAVE TYPE LOGIC
        # ------------------------------
        # If leave type exists AND no in/out time => full leave
        if self.leave_type and (not self.in_time and not self.out_time):
            self.status = "On Leave"
            self.working_hours_display = "0:00"
            self.working_hours_decimal = 0
            self.overtime_display = "0:00"
            self.overtime_decimal = 0
            return

        # DO NOT force "On Leave" when Half Day + Leave Type
        # allow working hours to be calculated normally

        # ------------------------------
        # 2️⃣ TIME NORMALIZATION
        #-------------------------------
        in_time = self.in_time if self.in_time not in ["00:00", "00:00:00", None] else None
        out_time = self.out_time if self.out_time not in ["00:00", "00:00:00", None] else None

        # No time → Absent
        if not in_time and not out_time:
            if self.leave_type:
                self.status = "On Leave"
            else:
                self.status = "Absent"

            self.working_hours_display = "0:00"
            self.working_hours_decimal = 0
            self.overtime_display = "0:00"
            self.overtime_decimal = 0
            return


        # Only one time → Missing
        if (in_time and not out_time) or (not in_time and out_time):
            if self.leave_type:
                self.status = "On Leave"
            else:
                self.status = "Missing"
            self.working_hours_display = "0:00"
            self.working_hours_decimal = 0
            self.overtime_display = "0:00"
            self.overtime_decimal = 0
            return

        # ------------------------------
        # 3️⃣ CALCULATE WORKING HOURS
        #------------------------------
        fmt = "%H:%M:%S"
        start = datetime.strptime(in_time, fmt)
        end = datetime.strptime(out_time, fmt)

        # Overnight shift support
        if end < start:
            end += timedelta(days=1)

        total_minutes = int((end - start).total_seconds() / 60)

        if total_minutes <= 0:
            self.status = "Missing"
            self.working_hours_display = "0:00"
            self.working_hours_decimal = 0
            self.overtime_display = "0:00"
            self.overtime_decimal = 0
            return

        reg_hours = total_minutes // 60
        reg_minutes = total_minutes % 60
        self.working_hours_display = f"{reg_hours}:{reg_minutes:02d}"
        self.working_hours_decimal = round(total_minutes / 60, 2)

        # ------------------------------
        # 4️⃣ AUTO STATUS BASED ON HOURS
        #------------------------------
        # Only auto-set if user did NOT pick a leave type
        if not self.leave_type:
            if total_minutes < 5 * 60:
                self.status = "Half Day"
            else:
                self.status = "Present"
        # If leave type is selected AND user set status to Half Day → allow it

        # ------------------------------
        # 5️⃣ OVERTIME CALCULATION
        #------------------------------
        overtime_minutes = max(0, total_minutes - 9 * 60)
        ot_hours = overtime_minutes // 60
        ot_minutes = overtime_minutes % 60

        self.overtime_display = f"{ot_hours}:{ot_minutes:02d}"
        self.overtime_decimal = round(overtime_minutes / 60, 2)
