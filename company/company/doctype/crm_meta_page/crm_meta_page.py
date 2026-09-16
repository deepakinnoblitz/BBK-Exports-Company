# -*- coding: utf-8 -*-
# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class CRMMetaPage(Document):
    def get_token(self):
        """
        Safely fetch page access token without raising error if missing.
        """
        try:
            return self.get_password("page_access_token")
        except Exception:
            return None

