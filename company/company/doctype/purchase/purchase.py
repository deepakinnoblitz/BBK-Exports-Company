# Copyright (c) 2025, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class Purchase(Document):
	def validate(self):
		"""Validate prices, calculate balance_amount"""
		self.validate_prices()
		self.validate_grand_total()
		if not self.paid_amount:
			self.paid_amount = 0
		
		# Calculate balance_amount as grand_total - paid_amount
		self.balance_amount = (self.grand_total or 0) - (self.paid_amount or 0)
	
	def validate_prices(self):
		"""Ensure all items have price > 0"""
		for idx, item in enumerate(self.table_qecz, 1):
			if not item.price or float(item.price) <= 0:
				frappe.throw(f"Row {idx}: Price cannot be zero or negative")
	
	def validate_grand_total(self):
		"""Ensure grand_total > 0"""
		if not self.grand_total or float(self.grand_total) <= 0:
			frappe.throw("Grand Total cannot be zero or negative")

	def after_insert(self):
		"""Update paid_amount and balance_amount after saving the purchase"""
		total_paid = frappe.db.sql("""
			SELECT SUM(amount_collected) FROM `tabPurchase Collection`
			WHERE purchase=%s
		""", self.name)[0][0] or 0

		balance_amount = flt(self.grand_total) - flt(total_paid)
		if balance_amount < 0:
			balance_amount = 0

		# Use set_value to persist to DB
		frappe.db.set_value(self.doctype, self.name, {
			"paid_amount": flt(total_paid),
			"balance_amount": flt(balance_amount)
		})
		frappe.db.commit()


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_purchase_contacts(doctype, txt, searchfield, start, page_len, filters):
	"""Return only contacts where customer_type = 'Purchase'"""
	return frappe.db.sql("""
		SELECT name, first_name, company_name
		FROM `tabContacts`
		WHERE customer_type = 'Purchase'
			AND (name LIKE %(txt)s 
				OR first_name LIKE %(txt)s 
				OR company_name LIKE %(txt)s)
		ORDER BY
			CASE WHEN name LIKE %(txt)s THEN 0 ELSE 1 END,
			CASE WHEN first_name LIKE %(txt)s THEN 0 ELSE 1 END,
			name
		LIMIT %(page_len)s OFFSET %(start)s
	""", {
		'txt': f"%{txt}%",
		'start': start,
		'page_len': page_len
	})
