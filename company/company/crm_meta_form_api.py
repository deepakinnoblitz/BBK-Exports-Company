# -*- coding: utf-8 -*-
# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import frappe
import json
import requests
from frappe.model.document import Document

class CRMMetaForm(Document):
    pass


@frappe.whitelist()
def get_connected_meta_forms(page_name=None):
    """
    Returns CRM Meta Form records from the database for connected Meta Pages.
    Does NOT call Graph API. Used for fast initial load on the dashboard.
    """
    filters = {}
    
    if page_name:
        filters["meta_page"] = page_name
    else:
        connected_pages = frappe.get_all(
            "CRM Meta Page",
            filters={"is_connected": 1, "is_active": 1},
            pluck="name"
        )
        if connected_pages:
            filters["meta_page"] = ["in", connected_pages]
            filters["is_active"] = 1
        else:
            return {"page": None, "total_forms": 0, "forms": []}

    if "is_active" not in filters:
        filters["is_active"] = 1

    forms = frappe.get_all(
        "CRM Meta Form",
        filters=filters,
        fields=["name", "form_id", "form_name", "form_status", "is_active", "meta_page"]
    )

    for f in forms:
        f["questions_count"] = f.get("questions_count") or 4
        f["form_status"] = f.get("form_status") or "ACTIVE"

    return {
        "page": page_name,
        "total_forms": len(forms),
        "forms": forms
    }


def sync_single_meta_page_forms(page_name):
    """
    Internal helper to fetch and sync Meta Lead Forms for a single CRM Meta Page from Graph API.
    """
    page_doc = frappe.get_doc("CRM Meta Page", page_name)
    
    if not page_doc.is_connected or not page_doc.is_active:
        return {"page": page_doc.name, "total_forms": 0, "forms": []}

    page_token = page_doc.get_token()

    if not page_token and page_doc.meta_account:
        try:
            acc_doc = frappe.get_doc("CRM Meta Account", page_doc.meta_account)
            page_token = acc_doc.get_token()
        except Exception:
            pass

    if not page_token:
        db_forms = frappe.get_all(
            "CRM Meta Form",
            filters={"meta_page": page_doc.name},
            fields=["name", "form_id", "form_name", "form_status", "is_active"]
        )
        for f in db_forms:
            f["questions_count"] = 4
            f["form_status"] = f.get("form_status") or "ACTIVE"
        return {"page": page_doc.name, "total_forms": len(db_forms), "forms": db_forms}

    app_doc = frappe.get_doc("CRM Meta App", page_doc.meta_app)
    graph_version = app_doc.graph_api_version or "v23.0"

    url = f"https://graph.facebook.com/{graph_version}/{page_doc.page_id}/leadgen_forms"
    params = {
        "fields": "id,name,status,questions,locale,created_time",
        "access_token": page_token,
        "limit": 100
    }

    res = requests.get(url, params=params, timeout=15)

    if res.status_code != 200:
        err_json = res.json().get("error", {})
        err_code = err_json.get("code")
        if err_code == 190 or "Page Access Token" in err_json.get("message", ""):
            db_forms = frappe.get_all(
                "CRM Meta Form",
                filters={"meta_page": page_doc.name},
                fields=["name", "form_id", "form_name", "form_status", "is_active"]
            )
            for f in db_forms:
                f["questions_count"] = 4
                f["form_status"] = f.get("form_status") or "ACTIVE"
            return {"page": page_doc.name, "total_forms": len(db_forms), "forms": db_forms}

        frappe.log_error(f"Failed to fetch Meta Lead Forms for page {page_doc.name}: {res.text}", "Meta Form Fetch Error")
        db_forms = frappe.get_all(
            "CRM Meta Form",
            filters={"meta_page": page_doc.name},
            fields=["name", "form_id", "form_name", "form_status", "is_active"]
        )
        return {"page": page_doc.name, "total_forms": len(db_forms), "forms": db_forms}

    forms_data = res.json().get("data", [])
    synced_forms = []

    if not forms_data:
        db_forms = frappe.get_all(
            "CRM Meta Form",
            filters={"meta_page": page_doc.name},
            fields=["name", "form_id", "form_name", "form_status", "is_active"]
        )
        return {
            "page": page_doc.name,
            "total_forms": len(db_forms),
            "forms": db_forms
        }

    fetched_form_ids = set()

    for form_item in forms_data:
        form_id = str(form_item.get("id"))
        form_name = form_item.get("name")
        status = form_item.get("status", "ACTIVE")
        locale = form_item.get("locale")
        questions = form_item.get("questions", [])
        fetched_form_ids.add(form_id)

        existing_name = frappe.db.get_value("CRM Meta Form", {"form_id": form_id}, "name")

        if existing_name:
            form_doc = frappe.get_doc("CRM Meta Form", existing_name)
        else:
            form_doc = frappe.new_doc("CRM Meta Form")
            form_doc.form_id = form_id

        form_doc.form_name = form_name
        form_doc.meta_page = page_doc.name
        form_doc.form_status = status
        form_doc.locale = locale
        form_doc.questions_json = json.dumps(questions, indent=2)
        form_doc.is_active = 1

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

                if crm_fld:
                    is_reqd = 1 if crm_fld in ("lead_name", "phone_number") else 0
                    form_doc.append("field_mappings", {
                        "meta_field": key,
                        "crm_field": crm_fld,
                        "required": is_reqd,
                        "transform_function": transform
                    })

        form_doc.save(ignore_permissions=True)
        synced_forms.append({
            "name": form_doc.name,
            "form_id": form_doc.form_id,
            "form_name": form_doc.form_name,
            "form_status": form_doc.form_status,
            "is_active": form_doc.is_active,
            "questions_count": len(questions)
        })

    page_forms = frappe.get_all("CRM Meta Form", filters={"meta_page": page_doc.name}, fields=["name", "form_id"])
    for existing_f in page_forms:
        if existing_f["form_id"] not in fetched_form_ids:
            frappe.db.set_value("CRM Meta Form", existing_f["name"], "is_active", 0)

    frappe.db.commit()

    return {
        "page": page_doc.name,
        "total_forms": len(synced_forms),
        "forms": synced_forms
    }


@frappe.whitelist()
def fetch_meta_forms_from_graph_api(page_name=None):
    """
    Fetches Meta Lead Ads Instant Forms belonging to a CRM Meta Page from Graph API v23.0.
    Matches fetched forms against existing DB records or creates new CRM Meta Form records.
    """
    if not page_name:
        connected_pages = frappe.get_all(
            "CRM Meta Page",
            filters={"is_connected": 1, "is_active": 1},
            pluck="name"
        )
        if not connected_pages:
            connected_pages = frappe.get_all("CRM Meta Page", pluck="name")

        if not connected_pages:
            return {"page": None, "total_forms": 0, "forms": []}

        all_forms = []
        for p_name in connected_pages:
            res = sync_single_meta_page_forms(p_name)
            if res and res.get("forms"):
                all_forms.extend(res.get("forms"))

        return {"page": None, "total_forms": len(all_forms), "forms": all_forms}
    else:
        return sync_single_meta_page_forms(page_name)


@frappe.whitelist()
def toggle_meta_form_connection(form_name, is_active):
    """
    Enable or disable lead sync ingestion for a specific CRM Meta Form.
    """
    if not frappe.db.exists("CRM Meta Form", form_name):
        frappe.throw(f"Meta Form '{form_name}' not found.")

    doc = frappe.get_doc("CRM Meta Form", form_name)
    is_act = 1 if int(is_active) else 0
    doc.is_active = is_act
    if not is_act:
        doc.form_status = "INACTIVE"
    else:
        doc.form_status = "ACTIVE"
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "name": doc.name,
        "form_name": doc.form_name,
        "is_active": doc.is_active
    }
