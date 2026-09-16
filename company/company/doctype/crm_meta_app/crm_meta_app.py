# -*- coding: utf-8 -*-
# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class CRMMetaApp(Document):
    def onload(self):
        self.webhook_url = frappe.utils.get_url("/api/method/company.company.crm_meta_api.webhook")
        
    def validate(self):
        self.webhook_url = frappe.utils.get_url("/api/method/company.company.crm_meta_api.webhook")
        
        # Enforce single default app rule
        if self.is_default:
            # Unset is_default on other active apps
            frappe.db.sql("""
                UPDATE `tabCRM Meta App`
                SET is_default = 0
                WHERE name != %s AND is_default = 1
            """, (self.name,))