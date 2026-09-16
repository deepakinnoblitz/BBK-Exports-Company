import frappe
import pandas as pd
from frappe.model.document import Document
from datetime import datetime, time
import os
import re
import numpy as np


class UploadAttendance(Document):
    def validate(self):
        self.convert_xls_to_xlsx()

    def convert_xls_to_xlsx(self):
        if self.attendance_file and self.attendance_file.lower().endswith(".xls"):
            try:
                # Get file doc
                file_doc = frappe.get_doc("File", {"file_url": self.attendance_file})
                file_url = file_doc.file_url

                # Determine file path
                if file_url.startswith("/private/"):
                    file_path = frappe.get_site_path(file_url.lstrip("/"))
                elif file_url.startswith("/files/"):
                    file_path = frappe.get_site_path("public", file_url.lstrip("/files/"))
                else:
                    return

                if not os.path.exists(file_path):
                    return

                # Read XLS and write XLSX
                df = pd.read_excel(file_path, engine="xlrd")

                # Create a temporary XLSX file
                new_file_name = os.path.splitext(file_doc.file_name)[0] + ".xlsx"
                temp_path = os.path.join("/tmp", new_file_name)
                df.to_excel(temp_path, index=False)

                # Create new File doc in Frappe
                with open(temp_path, "rb") as f:
                    new_file_doc = frappe.get_doc({
                        "doctype": "File",
                        "file_name": new_file_name,
                        "content": f.read(),
                        "is_private": file_doc.is_private,
                        "folder": file_doc.folder
                    })
                    new_file_doc.insert(ignore_permissions=True)

                # Update attendance_file to point to the new XLSX file
                self.attendance_file = new_file_doc.file_url

                # Cleanup temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)

                frappe.msgprint(f"File converted from XLS to XLSX: {new_file_name}")

            except Exception as e:
                frappe.log_error(frappe.get_traceback(), "XLS to XLSX Conversion Error")
                frappe.msgprint(f"Failed to convert XLS to XLSX: {str(e)}")


@frappe.whitelist()
def import_attendance(docname):
    """
    Import attendance from uploaded CSV/XLSX file into ERPNext.
    - Match Excel 'Person ID' exactly with Employee.employee_id (no leading zero correction)
    - Create new Attendance even if in_time or out_time is '-' or missing
    - Skip existing or manual attendance records
    - Provide detailed reason if employee not found
    """
    try:
        # --- Get uploaded file ---
        doc = frappe.get_doc("Upload Attendance", docname)
        file_doc = frappe.get_doc("File", {"file_url": doc.attendance_file})
        file_url = file_doc.file_url

        # --- Determine file path ---
        if file_url.startswith("/private/"):
            file_path = frappe.get_site_path(file_url.lstrip("/"))
        elif file_url.startswith("/files/"):
            file_path = frappe.get_site_path("public", file_url.lstrip("/files/"))
        else:
            frappe.throw(f"Unsupported file path: {file_url}")

        if not os.path.exists(file_path):
            frappe.throw(f"File not found: {file_url}")

        # --- Read Excel or CSV ---
        file_name = file_doc.file_name.lower()
        if file_name.endswith(".csv"):
            df = pd.read_csv(file_path, header=4, dtype=str, keep_default_na=False)
        elif file_name.endswith(".xlsx"):
            df = pd.read_excel(file_path, engine="openpyxl", header=4, dtype=str, keep_default_na=False)
        else:
            frappe.throw("Unsupported file format! Please upload CSV or XLSX.")

        if df.empty:
            frappe.throw("No data found in the uploaded file.")

        # --- Normalize headers ---
        df.columns = [c.strip().lower() for c in df.columns]
        column_map = {
            "person id": "person_id",
            "name": "employee_name",
            "date": "attendance_date",
            "check-in": "in_time",
            "check-out": "out_time"
        }
        df.rename(columns=lambda x: column_map.get(x, x), inplace=True)

        if "person_id" not in df.columns:
            frappe.throw("CSV must contain 'Person ID' column!")

        # --- Clean Person IDs ---
        df["person_id"] = (
            df["person_id"]
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
            .replace({"None": "", "nan": ""})
        )

        # --- Cache employee table for faster lookup ---
        employees = frappe.db.get_all("Employee", ["name", "employee_id", "employee_name"])
        emp_dict = {str(e["employee_id"]).strip(): e for e in employees if e["employee_id"]}

        created, skipped, errors = [], [], []

        for idx, row in df.iterrows():
            try:
                person_id = str(row.get("person_id", "")).strip()

                if not person_id:
                    skipped.append(f"Row {idx+1}: ❌ Missing Person ID")
                    continue

                # --- Exact match only ---
                emp = emp_dict.get(person_id)

                if not emp:
                    pid_no_zero = person_id.lstrip("0")
                    similar = next((e for e in emp_dict.keys() if e == pid_no_zero), None)
                    reason = "No matching Employee.employee_id found"

                    if similar:
                        reason += f" (Found '{similar}' without leading zeros)"
                    elif any(e.lower() == person_id.lower() for e in emp_dict.keys()):
                        reason += " (Case mismatch)"
                    else:
                        reason += " (Completely missing in Employee table)"

                    skipped.append(f"Row {idx+1}: ❌ {reason} → Person ID '{person_id}'")
                    continue

                emp_name = emp["name"]
                emp_employee_id = emp["employee_id"]
                emp_employee_name = emp["employee_name"]

                # --- Attendance Date ---
                attendance_date = row.get("attendance_date")
                if not attendance_date:
                    skipped.append(f"Row {idx+1}: ⚠️ Missing Attendance Date for {emp_name}")
                    continue

                # --- Normalize Times (accept '-' or empty) ---
                in_time_raw = str(row.get("in_time", "")).strip()
                out_time_raw = str(row.get("out_time", "")).strip()
                in_time = None if in_time_raw in ["-", "", "None", "nan"] else normalize_time(in_time_raw)
                out_time = None if out_time_raw in ["-", "", "None", "nan"] else normalize_time(out_time_raw)

                # --- Skip if attendance already exists ---
                exists = frappe.db.exists({
                    "doctype": "Attendance",
                    "employee": emp_name,
                    "attendance_date": attendance_date
                })
                if exists:
                    skipped.append(f"Row {idx+1}: ⚪ Attendance already exists for {emp_name} on {attendance_date}")
                    continue

                # --- Create new Attendance (even with missing times) ---
                new_doc = frappe.get_doc({
                    "doctype": "Attendance",
                    "employee": emp_name,
                    "employee_id": emp_employee_id,
                    "employee_name": emp_employee_name,
                    "attendance_date": attendance_date,
                    "in_time": in_time,
                    "out_time": out_time
                })
                new_doc.insert(ignore_permissions=True)
                created.append(
                    f"✅ {emp_name} | {attendance_date} inserted (In: {in_time or '-'}, Out: {out_time or '-'})"
                )

            except Exception as e:
                errors.append(f"Row {idx+1}: ❌ {str(e)}")

        frappe.db.commit()

        # --- Update imported status ---
        if created or (not errors and df.shape[0] > 0):
            frappe.db.set_value("Upload Attendance", docname, "imported", 1)
            frappe.db.commit()

        # --- Summary ---
        summary = (
            f"<b>Attendance Import Summary</b><br>"
            f"✅ Created: {len(created)}<br>"
            f"⚪ Skipped: {len(skipped)}<br>"
            f"🔴 Errors: {len(errors)}<br><br>"
        )
        if created:
            summary += "<b>✅ Created:</b><br>" + "<br>".join(created[:20]) + "<br><br>"
        if skipped:
            summary += "<b>⚪ Skipped (with reasons):</b><br>" + "<br>".join(skipped[:30]) + "<br><br>"
        if errors:
            summary += "<b>🔴 Errors:</b><br>" + "<br>".join(errors[:20]) + "<br>"

        return summary

    except Exception as e:
        frappe.throw(f"Error importing attendance: {e}")


# === Robust Time Normalizer ===
def normalize_time(value):
    """Convert Excel/float/string time to HH:MM:SS"""
    if value in [None, "", "-", "–", "nan", "NaT"] or pd.isna(value):
        return None

    if isinstance(value, time):
        return value.strftime("%H:%M:%S")

    if isinstance(value, (pd.Timestamp, datetime)):
        try:
            return value.time().strftime("%H:%M:%S")
        except Exception:
            return value.strftime("%H:%M:%S")

    try:
        if isinstance(value, (int, float, np.number)) or re.match(r"^\d+(\.\d+)?$", str(value)):
            t = pd.to_datetime(float(value), unit="d", origin="1899-12-30").time()
            return t.strftime("%H:%M:%S")
    except Exception:
        pass

    value = str(value).strip().replace("\xa0", "").replace(" ", "")

    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p", "%H.%M"):
        try:
            return datetime.strptime(value, fmt).strftime("%H:%M:%S")
        except Exception:
            continue

    match = re.search(r"(\d{1,2})[:.](\d{2})(?::(\d{2}))?", value)
    if match:
        hh, mm, ss = int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
        return f"{hh:02d}:{mm:02d}:{ss:02d}"

    frappe.log_error(f"Unrecognized time format: {repr(value)}", "Attendance Import")
    return None
