# -*- coding: utf-8 -*-
# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document
from company.company.crm_meta_page_api import subscribe_page_to_meta_webhooks


@frappe.whitelist()
def preview_graph_api_pages(account_name=None):
    """
    Step 1 Preview: Fetches accessible Facebook Pages from Meta Graph API
    without saving them to Frappe DB. Returns pages with existing DB status flags.
    """
    if not account_name:
        account_name = frappe.db.get_value("CRM Meta Account", {"connection_status": "Connected", "is_active": 1}, "name")
        if not account_name:
            account_name = frappe.db.get_value("CRM Meta Account", {"is_default": 1, "is_active": 1}, "name")
        if not account_name:
            account_name = frappe.db.get_value("CRM Meta Account", {"connection_status": "Connected"}, "name")
        if not account_name:
            account_name = frappe.db.get_value("CRM Meta Account", {}, "name")

    if not account_name or not frappe.db.exists("CRM Meta Account", account_name):
        return {"account": None, "total_pages": 0, "pages": []}

    account_doc = frappe.get_doc("CRM Meta Account", account_name)
    user_access_token = None
    try:
        user_access_token = account_doc.get_token()
    except Exception:
        user_access_token = None

    if not user_access_token:
        return {
            "account": account_doc.name,
            "total_pages": 0,
            "pages": [],
            "message": f"User Access Token is missing or expired for CRM Meta Account '{account_doc.name}'. Please reconnect Facebook."
        }

    app_doc = frappe.get_doc("CRM Meta App", account_doc.meta_app)
    graph_version = app_doc.graph_api_version or "v23.0"

    # GET /me/accounts
    current_url = f"https://graph.facebook.com/{graph_version}/me/accounts"
    params = {
        "access_token": user_access_token,
        "fields": "id,name,access_token,category,tasks",
        "limit": 100
    }

    preview_pages = []
    
    # Query existing DB pages for reference
    db_pages = frappe.get_all(
        "CRM Meta Page",
        filters={"meta_app": account_doc.meta_app},
        fields=["name", "page_id", "page_name", "category", "subscription_status", "is_connected", "is_active", "webhook_enabled"]
    )
    existing_page_map = {p["page_id"]: p for p in db_pages}

    try:
        while current_url:
            if params:
                res = requests.get(current_url, params=params, timeout=15)
            else:
                res = requests.get(current_url, timeout=15)
                
            if res.status_code != 200:
                err_msg = res.json().get("error", {}).get("message", res.text)
                frappe.throw(f"Meta Graph API Error fetching pages: {err_msg}")
                
            res_json = res.json()
            data = res_json.get("data", [])
            for page_item in data:
                page_id = str(page_item.get("id"))
                page_name = page_item.get("name")
                page_token = page_item.get("access_token")
                category = page_item.get("category") or "Business"

                existing = existing_page_map.get(page_id)
                
                preview_pages.append({
                    "page_id": page_id,
                    "page_name": page_name,
                    "page_access_token": page_token,
                    "category": category,
                    "is_existing": bool(existing),
                    "db_name": existing["name"] if existing else None,
                    "is_active": existing["is_active"] if existing else 0,
                    "is_connected": existing["is_connected"] if existing else 0,
                    "webhook_enabled": existing["webhook_enabled"] if existing else 0,
                    "subscription_status": existing["subscription_status"] if existing else "Unsubscribed"
                })
                
            paging = res_json.get("paging", {})
            current_url = paging.get("next")
            params = None # URL contains parameters now
    except Exception as err:
        frappe.throw(f"Error fetching pages from Facebook: {str(err)}")

    return {
        "account": account_doc.name,
        "total_pages": len(preview_pages),
        "pages": preview_pages
    }


@frappe.whitelist()
def preview_graph_api_forms(selected_pages=None):
    """
    Step 2 Preview: Accepts a JSON array or list of selected pages (with page_id, page_name, page_access_token),
    fetches Lead Forms from Graph API for each page, and returns forms with existing DB status flags.
    """
    if isinstance(selected_pages, str):
        import json
        selected_pages = json.loads(selected_pages)

    if not selected_pages:
        try:
            page_res = preview_graph_api_pages()
            selected_pages = page_res.get("pages", [])
        except Exception:
            selected_pages = []

    if not selected_pages:
        # Fallback: load all CRM Meta Pages from DB
        db_p_records = frappe.get_all(
            "CRM Meta Page",
            fields=["name", "page_id", "page_name", "category"]
        )
        selected_pages = [
            {
                "page_id": p["page_id"],
                "page_name": p["page_name"],
                "db_name": p["name"]
            }
            for p in db_p_records
        ]

    if not selected_pages:
        return {"total_forms": 0, "forms": []}

    # Query existing DB forms
    existing_db_forms = frappe.get_all(
        "CRM Meta Form",
        fields=["name", "form_id", "form_name", "form_status", "is_active", "meta_page"]
    )
    existing_form_map = {f["form_id"]: f for f in existing_db_forms}

    preview_forms = []

    for page_item in selected_pages:
        page_id = str(page_item.get("page_id"))
        page_name = page_item.get("page_name")
        page_token = page_item.get("page_access_token")
        db_name = page_item.get("db_name")

        if not page_token and db_name and frappe.db.exists("CRM Meta Page", db_name):
            p_doc = frappe.get_doc("CRM Meta Page", db_name)
            page_token = p_doc.get_token()

        if not page_token:
            # Fallback to CRM Meta Account user token
            acc_name = frappe.db.get_value("CRM Meta Account", {"is_default": 1, "is_active": 1}, "name")
            if not acc_name:
                acc_name = frappe.db.get_value("CRM Meta Account", {"connection_status": "Connected"}, "name")
            if not acc_name:
                acc_name = frappe.db.get_value("CRM Meta Account", {}, "name")
            if acc_name:
                acc_doc = frappe.get_doc("CRM Meta Account", acc_name)
                page_token = acc_doc.get_token()

        if not page_token:
            continue

        # GET /{page_id}/leadgen_forms
        current_url = f"https://graph.facebook.com/v23.0/{page_id}/leadgen_forms"
        params = {
            "access_token": page_token,
            "fields": "id,name,status,leads_count,questions,created_time",
            "limit": 100
        }

        try:
            while current_url:
                if params:
                    res = requests.get(current_url, params=params, timeout=15)
                else:
                    res = requests.get(current_url, timeout=15)
                
                if res.status_code == 200:
                    res_json = res.json()
                    forms_data = res_json.get("data", [])
                    for f_item in forms_data:
                        form_id = str(f_item.get("id"))
                        form_name = f_item.get("name")
                        status = f_item.get("status") or "ACTIVE"
                        leads_count = f_item.get("leads_count") or 0

                        existing = existing_form_map.get(form_id)

                        preview_forms.append({
                            "form_id": form_id,
                            "form_name": form_name,
                            "page_id": page_id,
                            "page_name": page_name,
                            "form_status": status,
                            "leads_count": leads_count,
                            "locale": f_item.get("locale"),
                            "questions": f_item.get("questions") or [],
                            "is_existing": bool(existing),
                            "db_name": existing["name"] if existing else None,
                            "is_active": existing["is_active"] if existing else 0
                        })
                    
                    # Follow pagination links to fetch all remaining forms
                    paging = res_json.get("paging", {})
                    current_url = paging.get("next")
                    params = None # Parameters are encoded in the next URL link
                else:
                    break
        except Exception as err:
            frappe.log_error(f"Error fetching preview forms for page {page_name}: {str(err)}", "Meta Sync Wizard Form Error")

    return {
        "total_forms": len(preview_forms),
        "forms": preview_forms
    }


@frappe.whitelist()
def import_selected_meta_pages_and_forms(account_name=None, selected_pages=None, selected_forms=None):
    """
    Atomic Commit Action:
    1. Upserts selected CRM Meta Pages in Frappe DB
    2. Subscribes selected Pages to Facebook Webhooks
    3. Upserts selected CRM Meta Forms under respective Pages
    """
    import json
    if isinstance(selected_pages, str):
        selected_pages = json.loads(selected_pages)
    if isinstance(selected_forms, str):
        selected_forms = json.loads(selected_forms)

    if not account_name:
        account_name = frappe.db.get_value("CRM Meta Account", {"is_default": 1, "is_active": 1}, "name")
        if not account_name:
            account_name = frappe.db.get_value("CRM Meta Account", {"connection_status": "Connected"}, "name")
        if not account_name:
            account_name = frappe.db.get_value("CRM Meta Account", {}, "name")

    if not account_name or not frappe.db.exists("CRM Meta Account", account_name):
        frappe.throw("CRM Meta Account not found.")

    account_doc = frappe.get_doc("CRM Meta Account", account_name)

    saved_page_docs = {}

    # 1. Save selected Pages
    if selected_pages:
        for page_item in selected_pages:
            page_id = str(page_item.get("page_id"))
            page_name = page_item.get("page_name")
            page_token = page_item.get("page_access_token")
            category = page_item.get("category") or "Business"

            existing_name = page_item.get("db_name") or frappe.db.get_value("CRM Meta Page", {"page_id": page_id}, "name")

            if existing_name and frappe.db.exists("CRM Meta Page", existing_name):
                page_doc = frappe.get_doc("CRM Meta Page", existing_name)
            else:
                page_doc = frappe.new_doc("CRM Meta Page")
                page_doc.page_id = page_id
                page_doc.meta_app = account_doc.meta_app

            page_doc.page_name = page_name
            page_doc.category = category
            page_doc.meta_account = account_doc.name
            page_doc.meta_app = account_doc.meta_app
            page_doc.is_connected = 1
            page_doc.is_active = 1
            page_doc.webhook_enabled = 1
            page_doc.subscription_status = "Subscribed"
            if page_token:
                page_doc.page_access_token = page_token

            page_doc.save(ignore_permissions=True)
            frappe.db.commit()

            saved_page_docs[page_id] = page_doc

            # Subscribe page to webhooks
            try:
                subscribe_page_to_meta_webhooks(page_doc.name)
            except Exception as sub_err:
                frappe.log_error(f"Error subscribing page {page_doc.name} to webhooks: {str(sub_err)}", "Meta Sync Wizard Webhook Error")

    # 2. Save selected Forms
    saved_forms_count = 0
    if selected_forms:
        for form_item in selected_forms:
            form_id = str(form_item.get("form_id"))
            form_name = form_item.get("form_name")
            page_id = str(form_item.get("page_id"))
            status = form_item.get("form_status") or "ACTIVE"

            parent_page = saved_page_docs.get(page_id)
            if not parent_page:
                parent_page_name = frappe.db.get_value("CRM Meta Page", {"page_id": page_id}, "name")
                if parent_page_name:
                    parent_page = frappe.get_doc("CRM Meta Page", parent_page_name)

            if not parent_page:
                continue

            existing_form_name = form_item.get("db_name") or frappe.db.get_value("CRM Meta Form", {"form_id": form_id}, "name")

            if existing_form_name and frappe.db.exists("CRM Meta Form", existing_form_name):
                form_doc = frappe.get_doc("CRM Meta Form", existing_form_name)
            else:
                form_doc = frappe.new_doc("CRM Meta Form")
                form_doc.form_id = form_id

            form_doc.form_name = form_name
            form_doc.meta_page = parent_page.name
            form_doc.form_status = status
            form_doc.is_active = 1

            questions = form_item.get("questions") or []
            form_doc.locale = form_item.get("locale")
            form_doc.questions_json = json.dumps(questions, indent=2)

            if not form_doc.field_mappings:
                for q in questions:
                    key = q.get("key", "").strip()
                    q_type = q.get("type", "").upper()

                    if not key:
                        continue

                    crm_fld = None
                    transform = "None"

                    if key in ("full_name", "first_name", "last_name", "name") or "FULL_NAME" in q_type or "FIRST_NAME" in q_type:
                        crm_fld = "lead_name"
                        transform = "Title Case"
                    elif key in ("email", "e-mail") or "EMAIL" in q_type:
                        crm_fld = "email"
                        transform = "Lower Case"
                    elif key in ("phone", "phone_number") or "PHONE" in q_type:
                        crm_fld = "phone_number"
                        transform = "Clean Phone"
                    elif key in ("company_name", "company") or "COMPANY_NAME" in q_type:
                        crm_fld = "company_name"
                    else:
                        crm_fld = "notes"

                    is_reqd = 0
                    if crm_fld in ("lead_name", "phone_number"):
                        is_reqd = 1

                    form_doc.append("field_mappings", {
                        "meta_field": key,
                        "crm_field": crm_fld,
                        "required": is_reqd,
                        "transform_function": transform
                    })

                # Automatically add defaults for mandatory lead fields
                form_doc.append("field_mappings", {
                    "crm_field": "leads_type",
                    "default_value": "Incoming",
                    "required": 0,
                    "transform_function": "None"
                })
                form_doc.append("field_mappings", {
                    "crm_field": "leads_from",
                    "default_value": "Meta Lead Ads",
                    "required": 0,
                    "transform_function": "None"
                })

            form_doc.save(ignore_permissions=True)
            saved_forms_count += 1

    frappe.db.commit()

    # Update account timestamp
    account_doc.last_synced_on = frappe.utils.now_datetime()
    account_doc.last_successful_sync = frappe.utils.now_datetime()
    account_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "imported_pages": len(saved_page_docs),
        "imported_forms": saved_forms_count
    }
