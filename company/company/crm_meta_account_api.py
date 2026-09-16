# -*- coding: utf-8 -*-
# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import frappe
from datetime import datetime, timedelta
from frappe.utils import now_datetime, get_datetime

@frappe.whitelist()
def create_or_update_meta_account(
    meta_app,
    facebook_user_id,
    user_access_token,
    facebook_user_name=None,
    facebook_email=None,
    token_type="bearer",
    expires_in_seconds=None,
    is_default=0
):
    """
    Reusable helper to create or update a CRM Meta Account record.
    Used by OAuth callback in Phase 3.
    """
    if not meta_app or not facebook_user_id or not user_access_token:
        frappe.throw("meta_app, facebook_user_id, and user_access_token are required.")

    # Search for existing account under this (meta_app, facebook_user_id)
    existing_name = frappe.db.get_value(
        "CRM Meta Account",
        {"meta_app": meta_app, "facebook_user_id": str(facebook_user_id)},
        "name"
    )

    now = now_datetime()
    token_expires_on = None
    if expires_in_seconds:
        try:
            token_expires_on = now + timedelta(seconds=int(expires_in_seconds))
        except (ValueError, TypeError):
            pass

    if existing_name:
        doc = frappe.get_doc("CRM Meta Account", existing_name)
    else:
        doc = frappe.new_doc("CRM Meta Account")
        doc.meta_app = meta_app
        doc.facebook_user_id = str(facebook_user_id)
        doc.connected_on = now
        doc.connected_by = frappe.session.user

    # Update fields
    doc.facebook_user_name = facebook_user_name or doc.facebook_user_name
    doc.facebook_email = facebook_email or doc.facebook_email
    doc.token_type = token_type
    doc.token_expires_on = token_expires_on
    doc.token_last_refreshed_on = now
    doc.connection_status = "Connected"
    doc.is_active = 1
    doc.last_error = ""
    doc.last_error_on = None
    doc.save(ignore_permissions=True)
    if user_access_token:
        frappe.utils.password.set_encrypted_password("CRM Meta Account", doc.name, user_access_token, "user_access_token")

    frappe.db.commit()

    return doc.name

@frappe.whitelist()
def get_meta_account_status(account_name=None):
    """
    Frontend-safe method to return Meta Account status without exposing access tokens.
    If account_name is not provided, defaults to active default CRM Meta Account.
    """
    if not account_name:
        account_name = frappe.db.get_value("CRM Meta Account", {"is_default": 1, "is_active": 1}, "name")
        if not account_name:
            account_name = frappe.db.get_value("CRM Meta Account", {"is_active": 1}, "name")

    if not account_name or not frappe.db.exists("CRM Meta Account", account_name):
        return None

    doc = frappe.get_doc("CRM Meta Account", account_name)
    
    # Run expiry check
    expiry_info = doc.check_token_status()

    return {
        "name": doc.name,
        "meta_app": doc.meta_app,
        "facebook_user_id": doc.facebook_user_id,
        "facebook_user_name": doc.facebook_user_name,
        "facebook_email": doc.facebook_email,
        "connection_status": doc.connection_status,
        "is_active": doc.is_active,
        "is_default": doc.is_default,
        "connected_on": doc.connected_on,
        "token_expires_on": doc.token_expires_on,
        "is_expired": expiry_info.get("is_expired", False),
        "last_synced_on": doc.last_synced_on,
        "last_successful_sync": doc.last_successful_sync,
        "last_error": doc.last_error,
        "last_error_on": doc.last_error_on
    }


@frappe.whitelist()
def disconnect_meta_account(account_name):
    """
    Disconnects a CRM Meta Account safely.
    1. Sets connection_status = "Disconnected" and is_active = 0
    2. Unsubscribes all linked Facebook Pages from Meta Webhooks
    3. Soft-deactivates linked Pages
    4. Preserves all historical audit leads and queue records.
    """
    if not frappe.db.exists("CRM Meta Account", account_name):
        frappe.throw(f"Meta Account '{account_name}' not found.")

    account_doc = frappe.get_doc("CRM Meta Account", account_name)
    account_doc.connection_status = "Disconnected"
    account_doc.is_active = 0
    account_doc.save(ignore_permissions=True)

    # Unsubscribe linked pages from webhooks and soft-deactivate pages & forms
    pages = frappe.get_all("CRM Meta Page", filters={"meta_account": account_name}, fields=["name"])
    if not pages:
        pages = frappe.get_all("CRM Meta Page", filters={"meta_app": account_doc.meta_app}, fields=["name"])

    from company.company.crm_meta_page_api import unsubscribe_page_from_meta_webhooks

    for p in pages:
        try:
            unsubscribe_page_from_meta_webhooks(p.name)
        except Exception:
            pass

        frappe.db.set_value("CRM Meta Page", p.name, {"is_connected": 0, "is_active": 0, "webhook_enabled": 0, "subscription_status": "Unsubscribed"})

        # Cascade deactivation to forms under this page
        forms = frappe.get_all("CRM Meta Form", filters={"meta_page": p.name}, fields=["name"])
        for f in forms:
            frappe.db.set_value("CRM Meta Form", f.name, {
                "is_active": 0,
                "form_status": "INACTIVE"
            })

    frappe.db.commit()
    return {"status": "Disconnected", "account": account_name}


@frappe.whitelist()
def check_meta_account_tokens_and_permissions():
    """
    Daily scheduled audit job to verify Meta Account tokens and check expiration/permissions.
    """
    accounts = frappe.get_all("CRM Meta Account", filters={"is_active": 1}, fields=["name"])
    for acc in accounts:
        try:
            doc = frappe.get_doc("CRM Meta Account", acc.name)
            doc.check_token_status()
        except Exception as e:
            frappe.log_error(f"Error checking token status for {acc.name}: {str(e)}", "Meta Token Audit Cron Error")

    return True
