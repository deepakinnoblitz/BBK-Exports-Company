import frappe
from frappe.model.document import Document
from frappe.utils import flt

class PurchaseCollection(Document):
    def on_update(self):
        self.update_purchase_balance()

    def after_insert(self):
        self.update_purchase_balance()

    def after_delete(self):
        self.update_purchase_balance()

    def on_submit(self):
        self.update_purchase_balance()

    def on_cancel(self):
        self.update_purchase_balance()

    def update_purchase_balance(self):
        if not self.purchase:
            return

        # Get the sum of all collections for this purchase
        total_collected = frappe.db.sql("""
            SELECT SUM(amount_collected) FROM `tabPurchase Collection`
            WHERE purchase=%s
        """, self.purchase)[0][0] or 0

        purchase_doc = frappe.get_doc("Purchase", self.purchase)
        grand_total = flt(purchase_doc.grand_total)
        
        balance_amount = grand_total - flt(total_collected)
        if balance_amount < 0:
            balance_amount = 0

        # Update the Purchase document
        frappe.db.set_value("Purchase", self.purchase, {
            "paid_amount": flt(total_collected),
            "balance_amount": flt(balance_amount)
        })

# Global hooks for Purchase Collection
@frappe.whitelist()
def update_purchase_after_collection_delete(doc, method):
    if doc.purchase:
        total_collected = frappe.db.sql("""
            SELECT SUM(amount_collected) FROM `tabPurchase Collection`
            WHERE purchase=%s AND name != %s
        """, (doc.purchase, doc.name))[0][0] or 0

        purchase_doc = frappe.get_doc("Purchase", doc.purchase)
        grand_total = flt(purchase_doc.grand_total)
        
        balance_amount = grand_total - flt(total_collected)
        if balance_amount < 0:
            balance_amount = 0

        frappe.db.set_value("Purchase", doc.purchase, {
            "paid_amount": flt(total_collected),
            "balance_amount": flt(balance_amount)
        })
