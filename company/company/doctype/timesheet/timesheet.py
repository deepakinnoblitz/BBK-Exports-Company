import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import format_date


class Timesheet(Document):
    def validate(self):
        self.calculate_total_hours()
        self.validate_duplicate()

    def calculate_total_hours(self):
        self.total_hours = sum([d.hours for d in self.timesheet_entries or []])

    def validate_duplicate(self):
        if not self.employee or not self.timesheet_date:
            return

        duplicate = frappe.db.exists(
            "Timesheet",
            {
                "employee": self.employee,
                "timesheet_date": self.timesheet_date,
                "name": ["!=", self.name],
            }
        )

        if duplicate:
            frappe.throw(_("Timesheet already exists on {0}")
                         .format(format_date(self.timesheet_date, "dd-mm-yyyy")))