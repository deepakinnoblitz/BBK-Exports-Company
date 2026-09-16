# Copyright (c) 2025
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class EstimationItems(Document):

    def validate(self):
        self.calculate_tax_split()

    def calculate_tax_split(self):
        """Calculate tax_amount, cgst, sgst, igst, and sub_total"""

        qty = self.quantity or 0
        price = self.price or 0
        discount = self.discount or 0
        discount_type = self.discount_type or "Flat"
        tax_percent = float(self.tax_percent or 0)
        tax_category = (self.tax_category or "").upper().strip()

        # Base amount
        base = qty * price

        # Discount
        if discount_type == "Percentage":
            disc = base * (discount / 100)
        else:  # Flat
            disc = discount

        taxable = base - disc

        # Tax
        tax_amount = taxable * (tax_percent / 100)
        self.tax_amount = tax_amount

        # Reset all
        self.cgst = 0
        self.sgst = 0
        self.igst = 0

        # Apply tax splitting
        if tax_category == "GST":
            # 50% CGST + 50% SGST
            self.cgst = tax_amount / 2
            self.sgst = tax_amount / 2
        elif tax_category == "IGST":
            # Full IGST
            self.igst = tax_amount
        else:
            # No tax
            self.cgst = 0
            self.sgst = 0
            self.igst = 0

        # Subtotal
        self.sub_total = taxable + tax_amount
