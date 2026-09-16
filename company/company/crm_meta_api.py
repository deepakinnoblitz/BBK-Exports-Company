# -*- coding: utf-8 -*-
# Copyright (c) 2026, Deepak and contributors
# For license information, please see license.txt

import frappe
import json
import hashlib
import hmac
import requests
from datetime import datetime
from frappe import _

# Set logger
def get_logger():
    return frappe.logger("crm_meta_api")

def _plain_response(body, status=200):
    frappe.response["type"] = "download"
    frappe.response["content_type"] = "text/plain"
    frappe.response["display_content_as"] = "inline"
    frappe.response["filename"] = "response.txt"
    frappe.response["filecontent"] = str(body)
    frappe.response["http_status_code"] = status
    return

def format_phone_standard(p_val):
    """
    Format Phone Number into standard Frappe format (+<CountryCode>-<SubscriberNumber>)
    """
    if not p_val:
        return p_val
    raw = str(p_val).strip()

    # 1. Try parsing with Google `phonenumbers` library (works for all 240+ countries/territories)
    try:
        import phonenumbers
        # Test parsing with explicit '+' prefix first
        parse_target = raw if raw.startswith("+") else "+" + raw
        parsed = phonenumbers.parse(parse_target, None)
        if phonenumbers.is_possible_number(parsed) or phonenumbers.is_valid_number(parsed):
            return f"+{parsed.country_code}-{parsed.national_number}"
    except Exception:
        pass

    # 2. Fallback parsing for raw digits
    raw_digits = "".join(filter(str.isdigit, raw))
    if not raw_digits:
        return p_val

    # If user provided number starting with +, strip + and extract country code using phonenumbers if available
    try:
        import phonenumbers
        for test_str in [f"+{raw_digits}", raw_digits]:
            try:
                p = phonenumbers.parse(test_str, None)
                if p.country_code and p.national_number:
                    return f"+{p.country_code}-{p.national_number}"
            except Exception:
                continue
    except Exception:
        pass

    # 3. Fallback Heuristics when phonenumbers is unavailable
    if len(raw_digits) == 10:
        # 10 digits without country code default to +91
        return f"+91-{raw_digits}"
    elif len(raw_digits) > 10:
        # Check for 1-digit country code (+1 North America)
        if raw_digits.startswith("1") and len(raw_digits) == 11:
            return f"+1-{raw_digits[1:]}"
        # Check for 2-digit country code (e.g. 44 UK, 33 France, 49 Germany, 91 India, 81 Japan, 61 Australia)
        cc_len = 2 if len(raw_digits) == 12 else (len(raw_digits) - 10)
        return f"+{raw_digits[:cc_len]}-{raw_digits[cc_len:]}"

    return f"+{raw_digits}"

@frappe.whitelist(allow_guest=True)
def webhook():
    """
    Unified Meta (Facebook Lead Ads) Webhook Endpoint.
    GET: Handles Webhook Verification.
    POST: Processes Lead Gen Webhook payloads asynchronously.
    """
    logger = get_logger()
    req = frappe.request
    
    # 1. GET Request: Verify Token challenge handshake
    if req.method == "GET":
        mode = frappe.request.args.get("hub.mode")
        token = frappe.request.args.get("hub.verify_token")
        challenge = frappe.request.args.get("hub.challenge")
        
        if mode == "subscribe" and token:
            # Check verify token across active configured Meta Developer Apps
            apps = frappe.get_all("CRM Meta App", filters={"is_active": 1}, fields=["name", "verify_token"])
            for app in apps:
                # Decrypt/retrieve password verify token
                app_doc = frappe.get_doc("CRM Meta App", app.name)
                saved_token = app_doc.get_password("verify_token")
                if saved_token == token:
                    logger.info(f"Webhook verified successfully for App: {app.name}")
                    return _plain_response(challenge, 200)
            
            logger.warning(f"Verification failed: invalid verify token '{token}'")
            return _plain_response("Verification Failed", 403)
            
        return _plain_response("Invalid Parameters", 400)

    # 2. POST Request: Receive Lead Ad Payload
    elif req.method == "POST":
        start_time = datetime.now()
        payload_bytes = req.get_data()
        payload_str = payload_bytes.decode("utf-8") if payload_bytes else ""
        
        # Extract X-Hub-Signature-256 signature from headers
        signature = req.headers.get("X-Hub-Signature-256")
        
        # Save raw Webhook Log immediately
        headers_dict = dict(req.headers)
        headers_str = json.dumps(headers_dict, indent=2)
        
        log_doc = frappe.get_doc({
            "doctype": "CRM Meta Webhook Log",
            "headers": headers_str,
            "payload": payload_str,
            "http_status": 200,
            "status": "Unverified"
        })
        log_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        try:
            if not payload_str:
                raise ValueError("Empty request payload received")
            
            data = json.loads(payload_str)
            
            # Loop through entries to find form_id and app_id
            form_id = None
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    val = change.get("value", {})
                    if val.get("form_id"):
                        form_id = val.get("form_id")
                        break
            
            # Check signature if app signature validation is enabled
            app_name = None
            if form_id:
                app_name = frappe.db.get_value(
                    "CRM Meta Page",
                    {"name": frappe.db.get_value("CRM Meta Form", {"form_id": form_id}, "meta_page")},
                    "meta_app"
                )
                
            if not app_name:
                # Fallback to default app
                app_name = frappe.db.get_value("CRM Meta App", {"is_default": 1, "is_active": 1}, "name")
                
            if app_name:
                app_doc = frappe.get_doc("CRM Meta App", app_name)
                if app_doc.signature_validation:
                    secret = app_doc.get_password("app_secret")
                    if signature and secret:
                        # Validate signature
                        expected = hmac.new(
                            secret.encode("utf-8"),
                            payload_bytes,
                            hashlib.sha256
                        ).hexdigest()
                        
                        sig_hash = signature[7:] if signature.startswith("sha256=") else signature
                        if not hmac.compare_digest(expected, sig_hash):
                            log_doc.status = "Failed"
                            log_doc.response = "Invalid payload signature"
                            log_doc.http_status = 401
                            log_doc.save(ignore_permissions=True)
                            frappe.db.commit()
                            return _plain_response("Invalid signature", 401)
                    else:
                        log_doc.status = "Failed"
                        log_doc.response = "Signature validation enabled but App Secret or Signature header is missing"
                        log_doc.http_status = 401
                        log_doc.save(ignore_permissions=True)
                        frappe.db.commit()
                        return _plain_response("Invalid signature", 401)
            
            log_doc.status = "Verified"
            log_doc.save(ignore_permissions=True)
            frappe.db.commit()
            
            # Enqueue parsing payload in background worker queue to avoid HTTP timeouts
            frappe.enqueue(
                "company.company.crm_meta_api.enqueue_webhook_lead_processing",
                queue="default",
                payload_data=data,
                webhook_log_name=log_doc.name
            )
            
            # Return HTTP 200 immediately
            log_doc.response = "Webhook payload enqueued successfully"
            log_doc.execution_time = (datetime.now() - start_time).total_seconds()
            log_doc.save(ignore_permissions=True)
            frappe.db.commit()
            return _plain_response("Success", 200)
            
        except Exception as e:
            logger.error(f"Error handling webhook: {str(e)}")
            log_doc.status = "Failed"
            log_doc.response = str(e)
            log_doc.http_status = 400
            log_doc.execution_time = (datetime.now() - start_time).total_seconds()
            log_doc.save(ignore_permissions=True)
            frappe.db.commit()
            return _plain_response(str(e), 400)

    return _plain_response("Method Not Allowed", status=405)


def enqueue_webhook_lead_processing(payload_data, webhook_log_name):
    """
    Extracts individual leads from incoming payload data, creates CRM Meta Lead
    and enqueues background worker job to retrieve Meta Lead details and save to Lead.
    """
    # Always run as Administrator - webhook is unauthenticated so session user is Guest
    frappe.set_user("Administrator")
    logger = get_logger()
    try:
        entries = payload_data.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                val = change.get("value", {})
                lead_id = val.get("leadgen_id")
                form_id = val.get("form_id")
                
                if not lead_id or not form_id:
                    continue
                
                # Check if CRM Meta Lead record already exists
                if frappe.db.exists("CRM Meta Lead", lead_id):
                    logger.info(f"Meta Lead ID {lead_id} already exists. Skipping import.")
                    continue
                
                # Find associated Page and App using Form ID (filter by form_id field, not document name)
                form_info = frappe.db.get_value("CRM Meta Form", {"form_id": form_id}, ["name", "meta_page", "is_active"], as_dict=True)
                if not form_info:
                    msg = f"Skipping lead {lead_id}: No matching CRM Meta Form configured for form_id {form_id}."
                    logger.info(msg)
                    if webhook_log_name:
                        frappe.db.set_value("CRM Meta Webhook Log", webhook_log_name, {"status": "Failed", "response": msg})
                        frappe.db.commit()
                    continue
                if not form_info.is_active:
                    msg = f"The linked Meta Form '{form_info.name}' is inactive. Please activate it first."
                    logger.info(msg)
                    if webhook_log_name:
                        frappe.db.set_value("CRM Meta Webhook Log", webhook_log_name, {"status": "Failed", "response": msg})
                        frappe.db.commit()
                    continue

                page_info = frappe.db.get_value("CRM Meta Page", form_info.meta_page, ["name", "meta_app", "is_active"], as_dict=True)
                if not page_info:
                    msg = f"Skipping lead {lead_id}: No matching CRM Meta Page configured."
                    logger.info(msg)
                    if webhook_log_name:
                        frappe.db.set_value("CRM Meta Webhook Log", webhook_log_name, {"status": "Failed", "response": msg})
                        frappe.db.commit()
                    continue
                if not page_info.is_active:
                    msg = f"The linked Meta Page '{page_info.name}' is inactive. Please activate it first."
                    logger.info(msg)
                    if webhook_log_name:
                        frappe.db.set_value("CRM Meta Webhook Log", webhook_log_name, {"status": "Failed", "response": msg})
                        frappe.db.commit()
                    continue

                app_info = frappe.db.get_value("CRM Meta App", page_info.meta_app, ["name", "is_active"], as_dict=True)
                if not app_info:
                    msg = f"Skipping lead {lead_id}: No matching CRM Meta App configured."
                    logger.info(msg)
                    if webhook_log_name:
                        frappe.db.set_value("CRM Meta Webhook Log", webhook_log_name, {"status": "Failed", "response": msg})
                        frappe.db.commit()
                    continue
                if not app_info.is_active:
                    msg = f"The linked Meta App '{app_info.name}' is inactive. Please activate it first."
                    logger.info(msg)
                    if webhook_log_name:
                        frappe.db.set_value("CRM Meta Webhook Log", webhook_log_name, {"status": "Failed", "response": msg})
                        frappe.db.commit()
                    continue
                
                # Initialize Raw Lead audit record
                lead_audit = frappe.get_doc({
                    "doctype": "CRM Meta Lead",
                    "meta_lead_id": lead_id,
                    "meta_app": app_info.name,
                    "meta_page": page_info.name,
                    "meta_form": form_info.name,  # Link field needs document name, not numeric form_id
                    "webhook_payload": json.dumps(payload_data, indent=2),
                    "received_time": datetime.now(),
                    "processing_status": "Pending"
                })
                lead_audit.insert(ignore_permissions=True)
                
                # Create queue job tracker record
                queue_doc = frappe.get_doc({
                    "doctype": "CRM Meta Queue",
                    "meta_lead": lead_audit.name,
                    "status": "Queued",
                    "attempts": 0
                })
                queue_doc.insert(ignore_permissions=True)
                frappe.db.commit()
                
                # Enqueue processing pipeline
                job = frappe.enqueue(
                    "company.company.crm_meta_api.process_meta_lead_job",
                    queue="default",
                    meta_lead_name=lead_audit.name,
                    queue_job_name=queue_doc.name
                )
                
                # Save Job ID
                queue_doc.job_id = job.id
                queue_doc.save(ignore_permissions=True)
                frappe.db.commit()
                
    except Exception as e:
        logger.error(f"Error enqueuing webhook entries: {str(e)}")


def process_meta_lead_job(meta_lead_name, queue_job_name):
    """
    Background worker task to fetch lead details using Page Access Token,
    runs duplicate checking, maps fields, and creates a CRM Lead.
    """
    # Always run as Administrator - webhook is unauthenticated so session user is Guest
    frappe.set_user("Administrator")
    logger = get_logger()
    
    lead_audit = frappe.get_doc("CRM Meta Lead", meta_lead_name)
    queue_job = frappe.get_doc("CRM Meta Queue", queue_job_name)
    
    queue_job.started = datetime.now()
    queue_job.status = "Processing"
    queue_job.attempts += 1
    queue_job.save(ignore_permissions=True)
    frappe.db.commit()
    
    try:
        if not lead_audit.meta_form:
            raise ValueError(f"No Meta Form linked to Lead ID {lead_audit.meta_lead_id}")
            
        form_doc = frappe.get_doc("CRM Meta Form", lead_audit.meta_form)
        page_doc = frappe.get_doc("CRM Meta Page", form_doc.meta_page)
        
        access_token = page_doc.get_token()
        if not access_token:
            if hasattr(page_doc, 'meta_account') and page_doc.meta_account:
                account_doc = frappe.get_doc("CRM Meta Account", page_doc.meta_account)
                account_doc.record_error(f"Page Access Token missing for Page '{page_doc.page_name}'. Please reconnect Facebook.")
            raise ValueError(f"Page Access Token is not configured for Page ID: {page_doc.page_id}")
            
        # Fetch lead fields from Meta Graph API
        url = f"https://graph.facebook.com/v23.0/{lead_audit.meta_lead_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        logger.info(f"Fetching Lead ID {lead_audit.meta_lead_id} from Meta Graph API...")
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            err_msg = f"Facebook Graph API responded with status {response.status_code}: {response.text}"
            if response.status_code in (400, 401, 403) and hasattr(page_doc, 'meta_account') and page_doc.meta_account:
                try:
                    account_doc = frappe.get_doc("CRM Meta Account", page_doc.meta_account)
                    account_doc.record_error(f"Meta API error ({response.status_code}): {response.json().get('error', {}).get('message', response.text)}")
                except Exception:
                    pass
            raise Exception(err_msg)
            
        lead_data = response.json()
        lead_audit.lead_json = json.dumps(lead_data, indent=2)
        
        # Save Campaign/Ad metadata
        lead_audit.campaign_name = lead_data.get("campaign_name")
        lead_audit.ad_set_name = lead_data.get("ad_set_name")
        lead_audit.ad_name = lead_data.get("ad_name")
        
        # Parse fields from API response
        field_data = {}
        for entry in lead_data.get("field_data", []):
            name = entry.get("name")
            values = entry.get("values", [])
            if name and values:
                field_data[name] = values[0]
                
        # Load form field mappings
        default_dict = {}
        mapping_dict = {}
        for mapping in form_doc.field_mappings:
            if mapping.meta_field:
                mapping_dict[mapping.meta_field] = {
                    "crm_field": mapping.crm_field,
                    "transform": mapping.transform_function
                }
            if mapping.default_value:
                default_dict[mapping.crm_field] = mapping.default_value
                
        # Load questions configuration to retrieve labels
        questions_list = []
        if form_doc.questions_json:
            try:
                questions_list = json.loads(form_doc.questions_json)
            except Exception:
                pass
        question_label_map = {q.get("key"): q.get("label") for q in questions_list if q.get("key")}

        # Transform and populate values
        extracted_data = {}
        custom_records_dict = {}
        
        # We will build notes questions following the order of field_mappings
        custom_questions_map = {}
        unmapped_questions = []

        for name, val in field_data.items():
            val = "" if val is None else str(val).strip()

            # Remove HTML XSS tags from value
            val = val.replace("<", "").replace(">", "").strip()

            if name in mapping_dict:
                mapping_info = mapping_dict[name]
                crm_field = mapping_info["crm_field"]
                transform = mapping_info["transform"]

                # Apply transforms
                if transform == "Title Case":
                    val = val.title()
                elif transform == "Upper Case":
                    val = val.upper()
                elif transform == "Lower Case":
                    val = val.lower()
                elif transform == "Clean Phone":
                    val = format_phone_standard(val)

                if crm_field == "notes":
                    lbl = question_label_map.get(name, name)
                    custom_questions_map[name] = f"{lbl}\n{val}"
                else:
                    extracted_data[crm_field] = val
            else:
                # Default matching heuristics for common fields
                if name in ("full_name", "first_name", "last_name", "name") and "lead_name" not in extracted_data:
                    extracted_data["lead_name"] = val
                elif name in ("email", "e-mail") and "email" not in extracted_data:
                    extracted_data["email"] = val
                elif name in ("phone", "phone_number") and "phone_number" not in extracted_data:
                    extracted_data["phone_number"] = val
                elif name in ("company_name", "company") and "company_name" not in extracted_data:
                    extracted_data["company_name"] = val
                else:
                    lbl = question_label_map.get(name, name)
                    unmapped_questions.append(f"{lbl}\n{val}")

        # Construct ordered custom questions list using mapping table rows order
        custom_questions = []
        for mapping in form_doc.field_mappings:
            if mapping.crm_field == "notes":
                if mapping.meta_field and mapping.meta_field in custom_questions_map:
                    val = custom_questions_map[mapping.meta_field]
                    if val and val.strip():
                        custom_questions.append(val.strip())
                elif mapping.default_value and mapping.default_value.strip():
                    custom_questions.append(mapping.default_value.strip())

        # Append any unmapped questions at the end
        custom_questions.extend(unmapped_questions)

        # Set the notes field to contain the formatted plain text lines
        if custom_questions:
            extracted_data["notes"] = "\n\n".join(custom_questions)

        # Apply defaults
        for crm_fld, def_val in default_dict.items():
            if crm_fld != "notes" and not extracted_data.get(crm_fld):
                extracted_data[crm_fld] = def_val

        # Format name fallback
        lead_name = extracted_data.get("lead_name")
        if not lead_name:
            lead_name = f"Meta Lead {lead_audit.meta_lead_id}"
        extracted_data["lead_name"] = lead_name

        email = extracted_data.get("email")
        phone = extracted_data.get("phone_number")
        remarks_str = "\n".join(custom_questions) if custom_questions else ""
        
        # DUPLICATE RULES ENGINE CHECK
        duplicate_lead = None
        allow_duplicates = form_doc.allow_duplicates if hasattr(form_doc, 'allow_duplicates') else 0
        limit_by = form_doc.duplicate_limit_by if hasattr(form_doc, 'duplicate_limit_by') else "Email or Phone"
        
        # Rule 1: Check by meta_lead_id audit logs (Always checks to prevent double processing of identical lead ID)
        existing_imported = frappe.db.get_value("CRM Meta Lead", {"meta_lead_id": lead_audit.meta_lead_id, "processing_status": "Success"}, "created_lead")
        if existing_imported:
            duplicate_lead = existing_imported
            
        if not allow_duplicates:
            # Rule 2: Check by case-insensitive Email
            if not duplicate_lead and email and limit_by in ("Email or Phone", "Email Only"):
                clean_email = email.lower().strip()
                duplicate_lead = frappe.db.get_value("Lead", {"email": clean_email}, "name")
                
            # Rule 3: Check by Phone Number (matching last 10 digits)
            if not duplicate_lead and phone and limit_by in ("Email or Phone", "Phone Only"):
                clean_phone = "".join(filter(str.isdigit, phone))
                if len(clean_phone) >= 10:
                    last_10_digits = clean_phone[-10:]
                    
                    # Check parent field
                    duplicate_lead = frappe.db.sql("""
                        SELECT name FROM `tabLead`
                        WHERE RIGHT(REPLACE(REPLACE(REPLACE(phone_number, ' ', ''), '-', ''), '+', ''), 10) = %s
                        LIMIT 1
                    """, (last_10_digits,), as_dict=False)
                    
                    if duplicate_lead:
                        duplicate_lead = duplicate_lead[0][0]
                    else:
                        # Check child table
                        duplicate_lead = frappe.db.sql("""
                            SELECT lp.parent FROM `tabLead Phone` lp
                            WHERE RIGHT(REPLACE(REPLACE(REPLACE(lp.phone, ' ', ''), '-', ''), '+', ''), 10) = %s
                            LIMIT 1
                        """, (last_10_digits,), as_dict=False)
                        if duplicate_lead:
                            duplicate_lead = duplicate_lead[0][0]
                            
        if duplicate_lead:
            # Raise exception to fail processing and log duplicate
            lead_audit.processing_status = "Duplicate"
            raise Exception(f"Duplicate Lead found: Lead already exists with same email or phone: {duplicate_lead}")
            
        if phone:
            phone = format_phone_standard(phone)
            extracted_data["phone_number"] = phone

        # Validate phone formatting fallback
        is_phone_valid = False
        if phone:
            try:
                frappe.utils.validate_phone_number_with_country_code(phone, "phone_number")
                is_phone_valid = True
            except Exception:
                is_phone_valid = False
                
        if not phone or not is_phone_valid:
            phone = "+91-9999999999"
            extracted_data["phone_number"] = phone
            
        # Validate Country link
        country = extracted_data.get("country")
        if country and not frappe.db.exists("Country", country):
            extracted_data["country"] = None
            
        # Create Lead DocType
        lead_fields = {
            "doctype": "Lead",
            "leads_from": extracted_data.get("leads_from") or "Meta Lead Ads",
            "leads_type": extracted_data.get("leads_type") or "Incoming",
            "status": "Not Converted",
            "phone_number": phone,
        }
        
        for fld, val in extracted_data.items():
            if fld not in ("phone_numbers", "emails", "phone_number") and val:
                lead_fields[fld] = val
                
        lead_doc = frappe.get_doc(lead_fields)
        
        if phone:
            lead_doc.append("phone_numbers", {"phone": phone})
        if email:
            lead_doc.append("emails", {"email": email})
            
        lead_doc.insert(ignore_permissions=True)
        
        lead_audit.created_lead = lead_doc.name
        lead_audit.processing_status = "Success"
        lead_audit.error_message = ""
        lead_audit.processed_time = datetime.now()
        
        queue_job.status = "Completed"
        queue_job.completed = datetime.now()
        queue_job.last_error = ""
        
        logger.info(f"Successfully processed Meta Lead {lead_audit.meta_lead_id} -> Lead: {lead_doc.name}")
        
    except Exception as e:
        logger.error(f"Error processing Meta Lead: {str(e)}")
        
        if lead_audit.processing_status != "Duplicate":
            lead_audit.processing_status = "Failed"
            
        lead_audit.error_message = str(e)
        lead_audit.processed_time = datetime.now()
        
        queue_job.status = "Failed"
        queue_job.completed = datetime.now()
        queue_job.last_error = str(e)
        
    finally:
        lead_audit.save(ignore_permissions=True)
        queue_job.save(ignore_permissions=True)
        frappe.db.commit()


# ----------------------------------------------------------------------
# PHASE 3: META OAUTH AUTHORIZATION & CALLBACK HANDLERS
# ----------------------------------------------------------------------

@frappe.whitelist()
def initiate_meta_oauth(meta_app=None):
    """
    Constructs Meta OAuth authorization URL for Facebook Login with required permissions.
    """
    if not meta_app:
        meta_app = frappe.db.get_value("CRM Meta App", {"is_default": 1, "is_active": 1}, "name")
        if not meta_app:
            meta_app = frappe.db.get_value("CRM Meta App", {"is_active": 1}, "name")

    if not meta_app:
        frappe.throw("No active CRM Meta App configured in system. Please configure Meta Developer App credentials first.")

    app_doc = frappe.get_doc("CRM Meta App", meta_app)
    if not app_doc.app_id:
        frappe.throw(f"App ID is missing in CRM Meta App '{app_doc.name}'.")

    redirect_uri = app_doc.oauth_redirect_uri or frappe.utils.get_url("/api/method/company.company.crm_meta_api.meta_oauth_callback")
    graph_version = app_doc.graph_api_version or "v23.0"

    # Generate secure state token
    import uuid
    nonce = str(uuid.uuid4())
    state_payload = {
        "user": frappe.session.user,
        "app": app_doc.name,
        "nonce": nonce,
        "ts": datetime.now().timestamp()
    }
    state_key = f"meta_oauth_state_{nonce}"
    frappe.cache().set_value(state_key, json.dumps(state_payload), expires_in_sec=900)

    scopes = [
        "pages_show_list",
        "leads_retrieval",
        "pages_read_engagement",
        "pages_manage_metadata"
    ]
    scope_str = ",".join(scopes)

    oauth_url = (
        f"https://www.facebook.com/{graph_version}/dialog/oauth?"
        f"client_id={app_doc.app_id}"
        f"&redirect_uri={requests.utils.quote(redirect_uri, safe='')}"
        f"&state={nonce}"
        f"&scope={scope_str}"
        f"&auth_type=rerequest"
    )

    return {
        "oauth_url": oauth_url,
        "app_name": app_doc.app_name,
        "redirect_uri": redirect_uri
    }


@frappe.whitelist(allow_guest=True)
def meta_oauth_callback(code=None, state=None, error=None, error_description=None):
    """
    Handles Meta OAuth Callback.
    1. Validates CSRF State token
    2. Exchanges auth code for short-lived user token
    3. Exchanges short-lived token for long-lived user token (~60 days)
    4. Fetches User Profile details from Meta Graph API
    5. Calls create_or_update_meta_account()
    6. Redirects browser back to CRM frontend
    """
    logger = get_logger()
    req = frappe.request
    
    # Extract query params if passed via GET
    if not code and req.args.get("code"):
        code = req.args.get("code")
    if not state and req.args.get("state"):
        state = req.args.get("state")
    if not error and req.args.get("error"):
        error = req.args.get("error")
    if not error_description and req.args.get("error_description"):
        error_description = req.args.get("error_description")

    frontend_redirect = frappe.utils.get_url("/lead-integration/meta-apps")

    if error:
        logger.error(f"Meta OAuth Error Callback: {error} - {error_description}")
        return frappe.respond_as_web_page(
            "Meta OAuth Failed",
            f"Facebook returned an authorization error: {error_description or error}. You may close this window and try again.",
            indicator_color="red"
        )

    if not code or not state:
        return frappe.respond_as_web_page(
            "Invalid OAuth Callback",
            "Missing authorization code or state token in response.",
            indicator_color="red"
        )

    # Validate state parameter
    state_key = f"meta_oauth_state_{state}"
    cached_state_str = frappe.cache().get_value(state_key)
    if not cached_state_str:
        return frappe.respond_as_web_page(
            "CSRF State Expired",
            "The authorization state token has expired or is invalid. Please restart Facebook connection from CRM.",
            indicator_color="red"
        )

    frappe.cache().delete_value(state_key)
    state_data = json.loads(cached_state_str)
    app_name = state_data.get("app")

    try:
        app_doc = frappe.get_doc("CRM Meta App", app_name)
        app_secret = app_doc.get_password("app_secret")
        redirect_uri = app_doc.oauth_redirect_uri or frappe.utils.get_url("/api/method/company.company.crm_meta_api.meta_oauth_callback")
        graph_version = app_doc.graph_api_version or "v23.0"

        # Step 1: Exchange code for Short-Lived Access Token
        exchange_url = f"https://graph.facebook.com/{graph_version}/oauth/access_token"
        params = {
            "client_id": app_doc.app_id,
            "redirect_uri": redirect_uri,
            "client_secret": app_secret,
            "code": code
        }

        res = requests.get(exchange_url, params=params, timeout=15)
        if res.status_code != 200:
            raise Exception(f"Failed short-lived token exchange: {res.text}")

        token_data = res.json()
        short_token = token_data.get("access_token")
        if not short_token:
            raise Exception("No access_token returned by Meta.")

        # Step 2: Exchange for Long-Lived User Access Token (~60 days)
        long_token_url = f"https://graph.facebook.com/{graph_version}/oauth/access_token"
        long_params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_doc.app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token
        }

        long_res = requests.get(long_token_url, params=long_params, timeout=15)
        long_token = short_token
        expires_in = token_data.get("expires_in")

        if long_res.status_code == 200:
            long_data = long_res.json()
            if long_data.get("access_token"):
                long_token = long_data.get("access_token")
                expires_in = long_data.get("expires_in") or expires_in

        # Step 3: Fetch User Profile from Graph API
        me_url = f"https://graph.facebook.com/{graph_version}/me"
        me_res = requests.get(
            me_url,
            headers={"Authorization": f"Bearer {long_token}"},
            params={"fields": "id,name,email"},
            timeout=15
        )

        if me_res.status_code != 200:
            raise Exception(f"Failed to fetch Facebook User profile: {me_res.text}")

        user_info = me_res.json()
        fb_user_id = user_info.get("id")
        fb_user_name = user_info.get("name")
        fb_email = user_info.get("email")

        # Step 4: Create/Update CRM Meta Account
        from company.company.crm_meta_account_api import create_or_update_meta_account
        acc_name = create_or_update_meta_account(
            meta_app=app_doc.name,
            facebook_user_id=fb_user_id,
            user_access_token=long_token,
            facebook_user_name=fb_user_name,
            facebook_email=fb_email,
            token_type=token_data.get("token_type", "bearer"),
            expires_in_seconds=expires_in,
            is_default=1
        )

        logger.info(f"Meta OAuth connection successful -> CRM Meta Account: {acc_name}")

        # Step 5: OAuth Connection complete. Pages and Forms are synced when user confirms import in Wizard Dialog.

        # Step 6: Render auto-closing HTML page for popup window (closes instantly)
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Connecting...</title>
        </head>
        <body style="background:#ffffff;margin:0;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;">
            <script>
                try {{
                    if (window.opener) {{
                        window.opener.postMessage({{ type: "META_OAUTH_SUCCESS", account: "{acc_name}" }}, "*");
                    }}
                }} catch(e) {{}}
                window.close();
            </script>
        </body>
        </html>
        """
        frappe.response["type"] = "page"
        frappe.response["page_name"] = "meta_oauth_success"
        frappe.response["filecontent"] = html_content
        frappe.respond_as_web_page("Facebook Connected", html_content, http_status_code=200)
        return

    except Exception as e:
        logger.error(f"Meta OAuth Callback processing error: {str(e)}")
        return frappe.respond_as_web_page(
            "Connection Failed",
            f"Failed to connect Meta Account: {str(e)}. You may close this page and try again.",
            indicator_color="red"
        )


@frappe.whitelist()
def retry_meta_lead(meta_lead_name):
    """
    Manually retries processing a failed/pending CRM Meta Lead.
    """
    logger = get_logger()
    
    try:
        # Load the Meta Lead audit record
        lead_audit = frappe.get_doc("CRM Meta Lead", meta_lead_name)
        
        # Reset Status
        lead_audit.processing_status = "Pending"
        lead_audit.error_message = None
        lead_audit.save(ignore_permissions=True)
        
        # Create queue job tracker record
        queue_doc = frappe.get_doc({
            "doctype": "CRM Meta Queue",
            "meta_lead": lead_audit.name,
            "status": "Queued",
            "attempts": 0
        })
        queue_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        # Enqueue processing pipeline
        job = frappe.enqueue(
            "company.company.crm_meta_api.process_meta_lead_job",
            queue="default",
            meta_lead_name=lead_audit.name,
            queue_job_name=queue_doc.name
        )
        
        # Save Job ID
        queue_doc.job_id = job.id
        queue_doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        return {"status": "success", "message": "Meta Lead enqueued for processing successfully"}
    except Exception as e:
        logger.error(f"Error retrying Meta Lead {meta_lead_name}: {str(e)}")
        frappe.throw(f"Failed to retry Meta Lead: {str(e)}")

