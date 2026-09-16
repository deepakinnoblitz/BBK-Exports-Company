import frappe
import requests
from frappe.utils import now_datetime
from datetime import timedelta
import secrets

# --------------------------------------------------------------------
# TEST CONNECTION
# --------------------------------------------------------------------

@frappe.whitelist(allow_guest=False)
def get_monthly_message_count():
    from frappe.utils import get_first_day, today
    start_of_month = get_first_day(today())
    count = frappe.db.count(
        "CRM WhatsApp Message",
        filters={
            "creation": [">=", start_of_month],
            "message_direction": "Outgoing",
            "status": "Sent"
        }
    )
    return count


@frappe.whitelist()
def test_connection():

    settings = frappe.get_single(
        "CRM WhatsApp Settings"
    )

    try:

        url = (
            f"https://graph.facebook.com/v23.0/"
            f"{settings.phone_number_id}"
        )

        headers = {
            "Authorization":
                f"Bearer {settings.get_password('access_token')}"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:

            settings.connection_status = "Connected"
            settings.last_connected_on = frappe.utils.now()

            settings.save(ignore_permissions=True)

            frappe.logger().info(settings.last_connected_on)
            frappe.db.commit()

            return {
                "success": True,
                "message": "Connected Successfully"
            }

        return {
            "success": False,
            "error": response.text
        }

    except Exception:

        frappe.log_error(
            frappe.get_traceback(),
            "WhatsApp Test Connection Error"
        )

        return {
            "success": False,
            "error": str(frappe.get_traceback())
        }


def get_temporary_file_url(file_doc):

    token = secrets.token_urlsafe(32)

    frappe.cache().set_value(
        f"wa_file:{token}",
        file_doc.name,
        expires_in_sec=300  # 5 minutes
    )

    return (
        frappe.utils.get_url()
        + f"/api/method/company.company.crm_whatsapp_api.download_file"
        + f"?token={token}"
    )

@frappe.whitelist(allow_guest=True)
def download_file(token):

    file_name = frappe.cache().get_value(
        f"wa_file:{token}"
    )

    if not file_name:
        frappe.throw(
            "Link expired",
            frappe.PermissionError
        )

    file_doc = frappe.get_doc(
        "File",
        file_name
    )

    frappe.local.response.filename = (
        file_doc.file_name
    )

    frappe.local.response.filecontent = (
        file_doc.get_content()
    )

    frappe.local.response.type = "download"


# --------------------------------------------------------------------
# SEND WHATSAPP MESSAGE
# --------------------------------------------------------------------

@frappe.whitelist()
def send_whatsapp(phone, message=None, attachment=None):

    settings = frappe.get_single(
        "CRM WhatsApp Settings"
    )

    try:
        clean_phone = "".join(filter(str.isdigit, str(phone)))
        if not clean_phone:
            return {
                "success": False,
                "error": "Invalid phone number"
            }

        # Check max success send message limit
        limit = settings.max_success_send_message_limit or 0
        if limit > 0:
            count = get_monthly_message_count()
            if count >= limit:
                return {
                    "success": False,
                    "error": f"Max success send message limit of {limit} reached."
                }

        url = (
            f"https://graph.facebook.com/v23.0/"
            f"{settings.phone_number_id}/messages"
        )

        headers = {
            "Authorization":
                f"Bearer {settings.get_password('access_token')}",
            "Content-Type":
                "application/json"
        }

        payload = None
        message_type = "Text"

        # ----------------------------------------------------
        # ATTACHMENT MESSAGE
        # ----------------------------------------------------

        if attachment:

            file_doc = frappe.get_doc(
                "File",
                {
                    "file_url": attachment
                }
            )

            if file_doc.is_private:
                file_url = get_temporary_file_url(
                    file_doc
                )
            else:
                import urllib.parse
                file_url = frappe.utils.get_url(
                    urllib.parse.quote(file_doc.file_url, safe='/')
                )

            extension = (
                file_doc.file_name.split(".")[-1]
                .lower()
            )

            image_extensions = [
                "jpg",
                "jpeg",
                "png",
                "gif",
                "webp"
            ]

            if extension in image_extensions:

                payload = {
                    "messaging_product": "whatsapp",
                    "to": clean_phone,
                    "type": "image",
                    "image": {
                        "link": file_url,
                        "caption": message or ""
                    }
                }

                message_type = "Image"

            else:

                payload = {
                    "messaging_product": "whatsapp",
                    "to": clean_phone,
                    "type": "document",
                    "document": {
                        "link": file_url,
                        "filename": file_doc.file_name
                    }
                }

                message_type = "Document"

        # ----------------------------------------------------
        # TEXT MESSAGE
        # ----------------------------------------------------

        else:

            payload = {
                "messaging_product": "whatsapp",
                "to": clean_phone,
                "type": "text",
                "text": {
                    "body": message or ""
                }
            }

        # ----------------------------------------------------
        # SEND TEXT FIRST + DOCUMENT SECOND
        # ----------------------------------------------------

        meta_message_id = ""
        result = {}

        if (
            attachment
            and message
            and message_type == "Document"
        ):

            # Send text first

            text_payload = {
                "messaging_product": "whatsapp",
                "to": clean_phone,
                "type": "text",
                "text": {
                    "body": message
                }
            }

            text_response = requests.post(
                url,
                headers=headers,
                json=text_payload,
                timeout=30
            )

            text_result = text_response.json()

            frappe.logger().info(
                f"WhatsApp Text Response: {text_result}"
            )

            if text_response.status_code != 200:

                return {
                    "success": False,
                    "error": text_result
                }

            # Send document second

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            )

            result = response.json()

            frappe.logger().info(
                f"WhatsApp Document Response: {result}"
            )

            if response.status_code != 200:

                return {
                    "success": False,
                    "error": result
                }

        else:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            )

            result = response.json()

            frappe.logger().info(
                f"WhatsApp Response: {result}"
            )

            if response.status_code != 200:

                return {
                    "success": False,
                    "error": result
                }

        # ----------------------------------------------------
        # GET META MESSAGE ID
        # ----------------------------------------------------

        if result.get("messages"):

            meta_message_id = (
                result["messages"][0]
                .get("id", "")
            )

        # ----------------------------------------------------
        # GET OR CREATE CONVERSATION
        # ----------------------------------------------------

        conversation_name = frappe.db.exists(
            "CRM WhatsApp Conversation",
            {
                "mobile_number": clean_phone
            }
        )

        if conversation_name:

            conversation = frappe.get_doc(
                "CRM WhatsApp Conversation",
                conversation_name
            )

        else:

            conversation = frappe.get_doc({

                "doctype":
                    "CRM WhatsApp Conversation",

                "mobile_number":
                    clean_phone,

                "contact_name":
                    clean_phone,

                "status":
                    "Open",

                "unread_count":
                    0

            })

            conversation.insert(
                ignore_permissions=True
            )

        # ----------------------------------------------------
        # STORE MESSAGE
        # ----------------------------------------------------

        # Try to find a matching lead to link
        lead_name = frappe.db.get_value("Lead", {"phone_number": ["like", f"%{clean_phone[-10:]}"]})

        msg_doc = frappe.get_doc({

            "doctype":
                "CRM WhatsApp Message",

            "conversation":
                conversation.name,

            "mobile_number":
                clean_phone,

            "message_direction":
                "Outgoing",

            "message_type":
                message_type,

            "message_content":
                message or "",

            "attachment":
                attachment or "",

            "meta_message_id":
                meta_message_id,

            "status":
                "Sent",

            "lead":
                lead_name,

            "raw_payload":
                frappe.as_json(
                    result,
                    indent=2
                )

        })

        msg_doc.insert(
            ignore_permissions=True
        )

        # ----------------------------------------------------
        # UPDATE CONVERSATION
        # ----------------------------------------------------

        update_vals = {
            "last_message_on": frappe.utils.now()
        }

        if message:
            update_vals["last_message"] = message
        elif attachment:
            update_vals["last_message"] = f"{message_type} Sent"

        frappe.db.set_value(
            "CRM WhatsApp Conversation",
            conversation.name,
            update_vals
        )

        frappe.db.commit()

        return {

            "success": True,

            "message":
                "WhatsApp Message Sent Successfully",

            "conversation":
                conversation.name,

            "message_doc":
                msg_doc.name,

            "meta_message_id":
                meta_message_id,

            "data":
                result

        }

    except Exception:

        frappe.log_error(
            frappe.get_traceback(),
            "WhatsApp Send Message Error"
        )

        return {

            "success": False,

            "error":
                frappe.get_traceback()

        }


# --------------------------------------------------------------------
# GET WHATSAPP MESSAGES
# --------------------------------------------------------------------

@frappe.whitelist()
def get_whatsapp_messages(phone, start=0, limit=10):
    if not phone:
        return []

    clean_phone = "".join(filter(str.isdigit, str(phone)))

    conversation_name = frappe.db.get_value(
        "CRM WhatsApp Conversation",
        {"mobile_number": clean_phone}
    )

    if not conversation_name and clean_phone != phone:
        conversation_name = frappe.db.get_value(
            "CRM WhatsApp Conversation",
            {"mobile_number": phone}
        )

    if not conversation_name:
        return []

    # Reset unread count
    frappe.db.set_value(
        "CRM WhatsApp Conversation",
        conversation_name,
        "unread_count",
        0
    )
    frappe.db.commit()

    messages = frappe.get_all(
        "CRM WhatsApp Message",
        filters={"conversation": conversation_name},
        fields=["name", "message_direction", "message_type", "message_content", "attachment", "status", "creation"],
        order_by="creation desc",
        limit_start=int(start),
        limit_page_length=int(limit)
    )

    messages.reverse()

    return messages