# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CRMWhatsAppSettings(Document):
	def validate(self):
		self.webhook_url = (
			frappe.utils.get_url()
			+ "/api/method/company.company.crm_whatsapp_webhook.webhook"
		)
