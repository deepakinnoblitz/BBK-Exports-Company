import frappe
from frappe.model.document import Document
from frappe.utils import getdate, flt

class Invoice(Document):

    def validate(self):
        self.validate_prices()
        self.calculate_child_rows()
        self.calculate_totals()
        self.validate_grand_total()

        # Only validate collections for existing invoices
        if not self.is_new():
            if frappe.db.exists("Invoice Collection", {"invoice": self.name}):
                frappe.throw("This invoice already has collections. Editing is not allowed.")
    
    def validate_prices(self):
        """Ensure all items have price > 0"""
        for idx, item in enumerate(self.table_qecz, 1):
            if not item.price or float(item.price) <= 0:
                frappe.throw(f"Row {idx}: Price cannot be zero or negative")
    
    def validate_grand_total(self):
        """Ensure grand_total > 0"""
        if not self.grand_total or float(self.grand_total) <= 0:
            frappe.throw("Grand Total cannot be zero or negative")

    
    def autoname(self):
        """Set document name = ref_no"""
        if self.ref_no:
            self.name = self.ref_no

    def before_insert(self):
        """Generate Invoice ref_no before inserting"""
        if not self.ref_no:
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

            # Get last Invoice in this FY
            last = frappe.db.sql("""
                SELECT ref_no FROM `tabInvoice`
                WHERE ref_no LIKE %s
                ORDER BY creation DESC LIMIT 1
            """, (f"IB-I/{fy}/%",), as_dict=True)

            if last:
                last_num = int(last[0].ref_no.split("/")[-1])
                next_num = last_num + 1
            else:
                next_num = 1

            # Assign ref_no
            self.ref_no = f"IB-I/{fy}/{str(next_num).zfill(3)}"

            # Also set document name
            self.name = self.ref_no

    def after_insert(self):
        """Update received_amount and balance_amount after saving the invoice"""
        total_collected = frappe.db.sql("""
            SELECT SUM(amount_collected) FROM `tabInvoice Collection`
            WHERE invoice=%s
        """, self.name)[0][0] or 0

        balance_amount = flt(self.grand_total) - flt(total_collected)
        if balance_amount < 0:
            balance_amount = 0

        # Use set_value to persist to DB
        frappe.db.set_value(self.doctype, self.name, {
            "received_amount": flt(total_collected),
            "balance_amount": flt(balance_amount)
        })

    def calculate_child_rows(self):
        for item in self.table_qecz:
            item.calculate_tax_split()

    def calculate_totals(self):
        total = 0
        total_qty = 0

        for item in self.table_qecz:
            total += item.sub_total or 0
            total_qty += item.quantity or 0

        # Assign raw totals
        self.total_qty = total_qty
        self.total_amount = total

        # Apply Overall Discount
        overall_disc = float(self.overall_discount or 0)
        disc_type = self.overall_discount_type or "Flat"

        if disc_type == "Flat":
            total -= overall_disc
        elif disc_type == "Percentage":
            total -= (total * overall_disc / 100)

        if total < 0:
            total = 0

        self.grand_total = total

