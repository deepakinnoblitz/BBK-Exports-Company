# -*- coding: utf-8 -*-
# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document

class CRMMetaPage(Document):
    def get_token(self):
        """
        Helper method to safely retrieve Page Access Token from encrypted Password storage.
        """
        return self.get_password("page_access_token") or self.get_password("long_lived_token") or self.page_access_token


@frappe.whitelist()
def get_connected_meta_pages(account_name=None):
    """
    Returns CRM Meta Page records from the database for the connected account.
    Does NOT call Graph API. Used for initial page load on the dashboard.
    """
    if not account_name:
        account_name = frappe.db.get_value("CRM Meta Account", {"is_default": 1, "is_active": 1}, "name")
        if not account_name:
            account_name = frappe.db.get_value("CRM Meta Account", {"connection_status": "Connected"}, "name")
        if not account_name:
            account_name = frappe.db.get_value("CRM Meta Account", {}, "name")

    if not account_name:
        return {"account": None, "total_pages": 0, "pages": []}

    # Only return connected and active pages in database
    pages = frappe.get_all(
        "CRM Meta Page",
        filters={"meta_account": account_name, "is_connected": 1, "is_active": 1},
        fields=["name", "page_id", "page_name", "category", "subscription_status", "is_connected", "is_active"]
    )

    return {
        "account": account_name,
        "total_pages": len(pages),
        "pages": pages
    }


@frappe.whitelist()
def fetch_meta_pages_from_graph_api(account_name=None):

    """
    Fetches accessible Facebook Pages from Meta Graph API v23.0 /me/accounts using the
    connected User Access Token stored in CRM Meta Account.
    Automatically upserts CRM Meta Page records linked to meta_account and parent meta_app.
    """
    if not account_name:
        account_name = frappe.db.get_value("CRM Meta Account", {"is_default": 1, "is_active": 1}, "name")
        if not account_name:
            account_name = frappe.db.get_value("CRM Meta Account", {"connection_status": "Connected"}, "name")
        if not account_name:
            account_name = frappe.db.get_value("CRM Meta Account", {}, "name")

    if not account_name:
        frappe.throw("No connected CRM Meta Account found. Please connect Facebook first.")

    account_doc = frappe.get_doc("CRM Meta Account", account_name)
    if account_doc.connection_status != "Connected" or not account_doc.is_active:
        return {
            "account": account_name,
            "total_pages": 0,
            "pages": []
        }

    user_token = account_doc.get_token()

    if not user_token:
        return {
            "account": account_name,
            "total_pages": 0,
            "pages": []
        }

    app_doc = frappe.get_doc("CRM Meta App", account_doc.meta_app)
    graph_version = app_doc.graph_api_version or "v23.0"

    # Query Graph API /v23.0/me/accounts
    url = f"https://graph.facebook.com/{graph_version}/me/accounts"
    params = {
        "fields": "id,name,access_token,category,is_published",
        "limit": 100
    }
    headers = {"Authorization": f"Bearer {user_token}"}

    res = requests.get(url, headers=headers, params=params, timeout=15)
    if res.status_code != 200:
        error_msg = f"Graph API returned status {res.status_code}: {res.text}"
        account_doc.record_error(error_msg)
        frappe.throw(f"Failed to fetch Facebook Pages: {res.json().get('error', {}).get('message', res.text)}")

    data = res.json().get("data", [])
    synced_pages = []

    # If Graph API returned empty or no pages found, fallback to existing CRM Meta Page records for this account/app
    if not data:
        db_pages = frappe.get_all(
            "CRM Meta Page",
            filters={"meta_account": account_doc.name},
            fields=["name", "page_id", "page_name", "category", "subscription_status", "is_connected", "is_active"]
        )
        if not db_pages:
            db_pages = frappe.get_all(
                "CRM Meta Page",
                filters={"meta_app": account_doc.meta_app},
                fields=["name", "page_id", "page_name", "category", "subscription_status", "is_connected", "is_active"]
            )
            # Link them to current account
            for p in db_pages:
                frappe.db.set_value("CRM Meta Page", p["name"], {"meta_account": account_doc.name, "is_connected": 1, "is_active": 1})
            frappe.db.commit()

        # Ensure default connection state is active
        for p in db_pages:
            frappe.db.set_value("CRM Meta Page", p["name"], {"is_connected": 1, "is_active": 1})
            p["is_connected"] = 1
            p["is_active"] = 1
        frappe.db.commit()

        return {
            "account": account_doc.name,
            "total_pages": len(db_pages),
            "pages": db_pages
        }

    fetched_page_ids = set()

    for page_item in data:
        page_id = str(page_item.get("id"))
        page_name = page_item.get("name")
        page_token = page_item.get("access_token")
        category = page_item.get("category")
        fetched_page_ids.add(page_id)

        # Check existing Page record by page_id (stable unique identifier)
        existing_name = frappe.db.get_value("CRM Meta Page", {"page_id": page_id}, "name")

        if existing_name:
            page_doc = frappe.get_doc("CRM Meta Page", existing_name)
        else:
            page_doc = frappe.new_doc("CRM Meta Page")
            page_doc.page_id = page_id
            page_doc.meta_app = account_doc.meta_app

        # Update relationships & details
        page_doc.page_name = page_name
        page_doc.category = category or page_doc.category
        page_doc.meta_account = account_doc.name
        page_doc.meta_app = account_doc.meta_app
        page_doc.is_connected = 1
        page_doc.is_active = 1
        
        if page_token:
            page_doc.page_access_token = page_token
        page_doc.save(ignore_permissions=True)
        frappe.db.commit()

        synced_pages.append({
            "name": page_doc.name,
            "page_id": page_doc.page_id,
            "page_name": page_doc.page_name,
            "category": page_doc.category,
            "subscription_status": page_doc.subscription_status or "Subscribed",
            "is_connected": 1,
            "is_active": 1
        })

    # Merge any existing DB pages for this account/app into synced_pages and ensure they are active
    db_pages = frappe.get_all(
        "CRM Meta Page",
        filters={"meta_app": account_doc.meta_app},
        fields=["name", "page_id", "page_name", "category", "subscription_status", "is_connected", "is_active"]
    )
    existing_ids = {p["page_id"] for p in synced_pages}

    for db_p in db_pages:
        if db_p["page_id"] not in existing_ids:
            frappe.db.set_value("CRM Meta Page", db_p["name"], {
                "meta_account": account_doc.name,
                "is_connected": 1,
                "is_active": 1,
                "webhook_enabled": 1,
                "subscription_status": "Subscribed"
            })
            db_p["is_connected"] = 1
            db_p["is_active"] = 1
            db_p["subscription_status"] = "Subscribed"
            synced_pages.append(db_p)

    frappe.db.commit()

    # Auto-subscribe active pages to webhooks & trigger form discovery for active pages
    from company.company.crm_meta_form_api import fetch_meta_forms_from_graph_api
    for p in synced_pages:
        p_name = p.get("name")
        if p_name:
            sub_res = None
            try:
                sub_res = subscribe_page_to_meta_webhooks(p_name)
            except Exception as sub_err:
                frappe.log_error(f"Error subscribing page {p_name} to webhooks: {str(sub_err)}", "Meta Page Webhook Subscription Exception")
            
            p_doc = frappe.get_doc("CRM Meta Page", p_name)
            p["subscription_status"] = p_doc.subscription_status or "Subscribed"
            p["webhook_enabled"] = p_doc.webhook_enabled
            
            # Fetch Lead Forms belonging to this active Page
            try:
                fetch_meta_forms_from_graph_api(p_doc.name)
            except Exception as e:
                frappe.log_error(f"Error auto-syncing forms for page {p_name}: {str(e)}", "Meta Form Auto Sync Error")

    frappe.db.commit()

    return {
        "account": account_doc.name,
        "total_pages": len(synced_pages),
        "pages": synced_pages
    }


@frappe.whitelist()
def subscribe_page_to_meta_webhooks(page_name):
    """
    Subscribes a Facebook Page to leadgen webhook events via Meta Graph API v23.0 POST /{page_id}/subscribed_apps.
    """
    if not frappe.db.exists("CRM Meta Page", page_name):
        frappe.throw(f"Meta Page '{page_name}' not found.")

    page_doc = frappe.get_doc("CRM Meta Page", page_name)
    page_token = page_doc.get_token()

    account_doc = frappe.get_doc("CRM Meta Account", page_doc.meta_account) if page_doc.meta_account else None
    user_token = account_doc.get_token() if account_doc else None

    token_to_use = page_token or user_token
    if not token_to_use:
        frappe.throw(f"No access token available to subscribe Facebook Page '{page_doc.page_name}'.")

    app_doc = frappe.get_doc("CRM Meta App", page_doc.meta_app)
    graph_version = app_doc.graph_api_version or "v23.0"

    # POST /{page_id}/subscribed_apps
    url = f"https://graph.facebook.com/{graph_version}/{page_doc.page_id}/subscribed_apps"
    params = {"subscribed_fields": "leadgen"}
    headers = {"Authorization": f"Bearer {token_to_use}"}

    res = requests.post(url, headers=headers, data=params, timeout=15)
    
    # If page token failed and user token is available, try with user token
    if res.status_code != 200 and page_token and user_token and page_token != user_token:
        headers = {"Authorization": f"Bearer {user_token}"}
        res = requests.post(url, headers=headers, data=params, timeout=15)
    
    if res.status_code == 200 and res.json().get("success"):
        page_doc.webhook_enabled = 1
        page_doc.subscription_status = "Subscribed"
        page_doc.last_subscription_check = frappe.utils.now_datetime()
        page_doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "page_name": page_doc.page_name, "status": "Subscribed"}
    else:
        err_text = res.text
        page_doc.subscription_status = "Failed"
        page_doc.last_subscription_check = frappe.utils.now_datetime()
        page_doc.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.log_error(f"Failed page webhook subscription for {page_doc.page_name}: {err_text}", "Meta Page Webhook Subscription Error")
        return {"success": False, "page_name": page_doc.page_name, "status": "Failed", "error": err_text}


@frappe.whitelist()
def unsubscribe_page_from_meta_webhooks(page_name):
    """
    Unsubscribes a Facebook Page from leadgen webhook events via Meta Graph API v23.0 DELETE /{page_id}/subscribed_apps.
    """
    if not frappe.db.exists("CRM Meta Page", page_name):
        frappe.throw(f"Meta Page '{page_name}' not found.")

    page_doc = frappe.get_doc("CRM Meta Page", page_name)
    page_token = page_doc.get_token()

    if not page_token:
        page_doc.webhook_enabled = 0
        page_doc.subscription_status = "Not Subscribed"
        page_doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "status": "Not Subscribed"}

    app_doc = frappe.get_doc("CRM Meta App", page_doc.meta_app)
    graph_version = app_doc.graph_api_version or "v23.0"

    url = f"https://graph.facebook.com/{graph_version}/{page_doc.page_id}/subscribed_apps"
    headers = {"Authorization": f"Bearer {page_token}"}

    res = requests.delete(url, headers=headers, timeout=15)
    page_doc.webhook_enabled = 0
    page_doc.subscription_status = "Not Subscribed"
    page_doc.last_subscription_check = frappe.utils.now_datetime()
    page_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "page_name": page_doc.page_name, "status": "Not Subscribed"}


@frappe.whitelist()
def toggle_meta_page_connection(page_name, is_connected):
    """
    Enable or disable lead sync connection for a specific CRM Meta Page.
    Automatically subscribes or unsubscribes the Page from Meta Webhooks.
    """
    if not frappe.db.exists("CRM Meta Page", page_name):
        frappe.throw(f"Meta Page '{page_name}' not found.")

    doc = frappe.get_doc("CRM Meta Page", page_name)
    should_connect = bool(int(is_connected))

    doc.is_connected = 1 if should_connect else 0
    doc.is_active = 1 if should_connect else 0
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # Trigger webhook subscription update and cascade forms update
    if should_connect:
        subscribe_page_to_meta_webhooks(page_name)
    else:
        unsubscribe_page_from_meta_webhooks(page_name)
        # Cascade deactivation to all linked Lead Ad Forms
        forms = frappe.get_all("CRM Meta Form", filters={"meta_page": page_name}, fields=["name"])
        for f in forms:
            frappe.db.set_value("CRM Meta Form", f.name, {
                "is_active": 0,
                "form_status": "INACTIVE"
            })
        frappe.db.commit()

    doc.reload()
    return {
        "name": doc.name,
        "page_name": doc.page_name,
        "is_connected": doc.is_connected,
        "subscription_status": doc.subscription_status
    }
