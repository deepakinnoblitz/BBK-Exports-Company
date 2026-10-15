import frappe
from frappe.model.document import Document

class AttendanceTransfer(Document):
    def validate(self):
        if self.items:
            self.total_employees = len(self.items)
