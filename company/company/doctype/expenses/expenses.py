import frappe
from frappe.model.document import Document
from frappe.utils import getdate, flt

class Expenses(Document):

    def autoname(self):
        """Set document name = expense_no"""
        if self.expense_no:
            self.name = self.expense_no

    def before_insert(self):
        """Generate expense_no before inserting"""
        if not self.expense_no:
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

            # Get last Expense in this FY
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

            # Assign expense_no
            self.expense_no = f"EXP/{fy}/{str(next_num).zfill(3)}"

            # Also set document name
            self.name = self.expense_no
