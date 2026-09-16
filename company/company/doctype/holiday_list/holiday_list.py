# Copyright (c) 2025, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class HolidayList(Document):
    def validate(self):
        self.calculate_working_days()
        
    def calculate_working_days(self):
        # Calculate working days by counting the rows in the child table
        # where 'is_working_day' is checked.
        if self.holidays:
            working_days_count = sum(1 for row in self.holidays if getattr(row, "is_working_day", 0))
            self.working_days = working_days_count
        else:
            self.working_days = 0

