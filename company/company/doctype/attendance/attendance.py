from datetime import datetime, timedelta
import frappe
from frappe.model.document import Document

class Attendance(Document):
    def validate(self):
        self.check_duplicate_attendance()
        self.populate_shift()
        self.sync_punches_data()
        self.calculate_working_hours()

    def check_duplicate_attendance(self):
        existing_attendance = frappe.db.exists("Attendance", {
            "employee": self.employee,
            "attendance_date": self.attendance_date,
            "name": ["!=", self.name]
        })
        if existing_attendance:
            frappe.throw(f"Attendance record already exists for Employee {self.employee} on {self.attendance_date}")

    def populate_shift(self):
        if not self.shift and self.employee:
            self.shift = frappe.db.get_value("Employee", self.employee, "shift")

    def sync_punches_data(self):
        if not self.get("attendance_punches"):
            return

        valid_punches = [p for p in self.attendance_punches if p.punch_time]
        if not valid_punches:
            return

        # Sort chronologically by punch_time
        valid_punches.sort(key=lambda p: str(p.punch_time))

        def _extract_time_str(dt_val):
            if not dt_val:
                return None
            if isinstance(dt_val, str):
                parts = dt_val.strip().split(" ")
                t = parts[-1]
                if len(t) == 5:
                    return f"{t}:00"
                return t
            if hasattr(dt_val, "strftime"):
                return dt_val.strftime("%H:%M:%S")
            return str(dt_val)

        in_punches = [p for p in valid_punches if p.punch_type == "IN"]
        out_punches = [p for p in valid_punches if p.punch_type == "OUT"]

        first_in = in_punches[0] if in_punches else valid_punches[0]
        last_out = out_punches[-1] if out_punches else (valid_punches[-1] if len(valid_punches) > 1 else None)

        def _is_empty_or_zero(val):
            if not val or val in ["00:00", "00:00:00"]:
                return True
            if isinstance(val, timedelta) and val.total_seconds() == 0:
                return True
            return False

        # If not manually overridden or times are blank/00:00:00, sync from punches
        if not self.manual or _is_empty_or_zero(self.in_time):
            if first_in:
                self.in_time = _extract_time_str(first_in.punch_time)

        if not self.manual or _is_empty_or_zero(self.out_time):
            if last_out:
                self.out_time = _extract_time_str(last_out.punch_time)

        if not self.attendance_source:
            sources = [p.source for p in valid_punches if p.source]
            if sources and all(s == "Biometric" for s in sources):
                self.attendance_source = "Biometric"
            else:
                self.attendance_source = "Manual"

    def calculate_working_hours(self):

        # ------------------------------
        # 1️⃣ LEAVE TYPE LOGIC
        # ------------------------------
        # If leave type exists AND no in/out time => full leave
        if self.leave_type and (not self.in_time and not self.out_time):
            self.status = "On Leave"
            self.working_hours_display = "0:00"
            self.working_hours_decimal = 0
            self.official_overtime = "0:00"
            self.unofficial_overtime = "0:00"
            return

        # DO NOT force "On Leave" when Half Day + Leave Type
        # allow working hours to be calculated normally

        # ------------------------------
        # 2️⃣ TIME NORMALIZATION
        #-------------------------------
        def _to_time_str(val):
            if not val or val in ["00:00", "00:00:00"]:
                return None
            if isinstance(val, timedelta):
                total_sec = int(val.total_seconds())
                return f"{total_sec // 3600:02d}:{(total_sec % 3600) // 60:02d}:{total_sec % 60:02d}"
            if hasattr(val, "strftime"):
                return val.strftime("%H:%M:%S")
            return str(val)

        in_time = _to_time_str(self.in_time)
        out_time = _to_time_str(self.out_time)

        # No time → Absent
        if not in_time and not out_time:
            if self.leave_type:
                self.status = "On Leave"
            else:
                self.status = "Absent"

            self.working_hours_display = "0:00"
            self.working_hours_decimal = 0
            self.official_overtime = "0:00"
            self.unofficial_overtime = "0:00"
            return


        # Only one time → Missing
        if (in_time and not out_time) or (not in_time and out_time):
            if self.leave_type:
                self.status = "On Leave"
            else:
                self.status = "Missing"
            self.working_hours_display = "0:00"
            self.working_hours_decimal = 0
            self.official_overtime = "0:00"
            self.unofficial_overtime = "0:00"
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
            self.official_overtime = "0:00"
            self.unofficial_overtime = "0:00"
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
        # 5️⃣ OVERTIME CALCULATION (OFFICIAL & UNOFFICIAL)
        #------------------------------
        # Fetch Shift details
        if not self.shift and self.employee:
            self.shift = frappe.db.get_value("Employee", self.employee, "shift")

        shift_doc = None
        if self.shift:
            shift_doc = frappe.db.get_value(
                "Shift",
                self.shift,
                ["start_time", "end_time", "allow_overtime", "overtime_hours", "min_overtime_minutes"],
                as_dict=True
            )

        if shift_doc and shift_doc.get("end_time"):
            s_end_str = _to_time_str(shift_doc.end_time)
            s_end = datetime.strptime(s_end_str, fmt)

            # Adjust shift end for overnight if start_time > end_time
            if shift_doc.get("start_time"):
                s_start_str = _to_time_str(shift_doc.start_time)
                s_start = datetime.strptime(s_start_str, fmt)
                if s_end < s_start:
                    s_end += timedelta(days=1)

            # Extra time worked after shift end
            extra_seconds = (end - s_end).total_seconds()
            extra_minutes = max(0, int(extra_seconds / 60))

            min_threshold = int(shift_doc.get("min_overtime_minutes") or 0)
            if extra_minutes < min_threshold:
                extra_minutes = 0

            # Unofficial Overtime: All overtime in log past shift end
            unoff_h = extra_minutes // 60
            unoff_m = extra_minutes % 60
            self.unofficial_overtime = f"{unoff_h}:{unoff_m:02d}"

            # Official Overtime: Capped by shift overtime_hours if allowed
            if shift_doc.get("allow_overtime"):
                max_official_hours = float(shift_doc.get("overtime_hours") or 0)
                max_official_minutes = int(max_official_hours * 60)
                official_minutes = min(extra_minutes, max_official_minutes)
            else:
                official_minutes = 0

            off_h = official_minutes // 60
            off_m = official_minutes % 60
            self.official_overtime = f"{off_h}:{off_m:02d}"

        else:
            # Fallback when no shift is assigned: standard 9 hours threshold
            overtime_minutes = max(0, total_minutes - 9 * 60)
            ot_hours = overtime_minutes // 60
            ot_minutes = overtime_minutes % 60

            self.official_overtime = f"{ot_hours}:{ot_minutes:02d}"
            self.unofficial_overtime = f"{ot_hours}:{ot_minutes:02d}"
