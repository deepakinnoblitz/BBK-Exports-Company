# Copyright (c) 2025, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

class InvoiceCollection(Document):
	
	def validate(self):
		"""Only allow editing if it is the latest collection for the invoice"""
		if not self.is_new():
			self.ensure_latest_collection()

	def on_trash(self):
		"""Only allow deleting if it is the latest collection for the invoice"""
		self.ensure_latest_collection()

	def ensure_latest_collection(self):
		"""Check if there are any newer collections for the same invoice"""
		if self.is_new() or not self.invoice:
			return

		# Find the latest collection's name
		latest_collection = frappe.db.get_value("Invoice Collection", 
			filters={"invoice": self.invoice},
			fieldname="name",
			order_by="creation desc"
		)

		if latest_collection and latest_collection != self.name:
			frappe.throw(_("Only the last collection ({0}) for Invoice {1} can be modified or deleted.").format(latest_collection, self.invoice))

	def after_insert(self):
		"""Update Invoice amounts after creating a new collection"""
		self.update_invoice_amounts()
	
	def on_update(self):
		"""Update Invoice amounts after modifying a collection"""
		self.update_invoice_amounts()
	
	def after_delete(self):
		"""Update Invoice amounts after deleting a collection"""
		self.update_invoice_amounts()
	
	def update_invoice_amounts(self):
		"""Recalculate and update received_amount and balance_amount in the Invoice"""
		if not self.invoice:
			return
		
		# Get the Invoice document
		invoice = frappe.get_doc("Invoice", self.invoice)
		
		# Calculate total collected amount from all Invoice Collection records
		total_collected = frappe.db.sql("""
			SELECT SUM(amount_collected) as total
			FROM `tabInvoice Collection`
			WHERE invoice = %s
		""", (self.invoice,))[0][0] or 0
		
		# Update Invoice fields
		invoice.db_set("received_amount", total_collected, update_modified=False)
		invoice.db_set("balance_amount", invoice.grand_total - total_collected, update_modified=False)
		
		frappe.db.commit()

