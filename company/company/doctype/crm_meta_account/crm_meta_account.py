# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime

class CRMMetaAccount(Document):
    def get_token(self):
        """
        Safely fetch user access token without raising error if missing.
        """
        try:
            return self.get_password("user_access_token")
        except Exception:
            return None

    def validate(self):
        # 1. Enforce unique composite key (meta_app + facebook_user_id)
        if self.meta_app and self.facebook_user_id:
            existing = frappe.db.get_value(
                "CRM Meta Account",
                {"meta_app": self.meta_app, "facebook_user_id": self.facebook_user_id, "name": ["!=", self.name or ""]},
                "name"
            )
            if existing:
                frappe.throw(
                    f"Facebook User ID '{self.facebook_user_id}' is already registered under Meta App '{self.meta_app}'."
                )

        # 2. Enforce single default account per Meta App
        if self.is_default and self.meta_app:
            frappe.db.sql(
                """
                UPDATE `tabCRM Meta Account`
                SET is_default = 0
                WHERE meta_app = %s AND name != %s AND is_default = 1
                """,
                (self.meta_app, self.name or ""),
            )

        # 3. Token Expiry Check
        if self.token_expires_on:
            expires_at = get_datetime(self.token_expires_on)
            if expires_at <= now_datetime():
                self.connection_status = "Token Expired"

    def check_token_status(self):
        """
        Check if current token is expired or valid.
        """
        if not self.token_expires_on:
            return {"is_expired": False, "status": self.connection_status}

        expires_at = get_datetime(self.token_expires_on)
        is_expired = expires_at <= now_datetime()
        if is_expired and self.connection_status == "Connected":
            self.connection_status = "Token Expired"
            self.db_set("connection_status", "Token Expired")

        return {"is_expired": is_expired, "status": self.connection_status}

    def record_error(self, error_message):
        """
        Record a safe diagnostic error without exposing tokens.
        """
        safe_msg = str(error_message).replace("<", "").replace(">", "").strip()
        self.last_error = safe_msg
        self.last_error_on = now_datetime()
        self.connection_status = "Error"
        self.save(ignore_permissions=True)
