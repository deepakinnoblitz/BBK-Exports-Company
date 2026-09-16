import os
import json
import frappe

from datetime import datetime
from werkzeug.wrappers import Response


LOG_FILE = (
    "/home/innoblitz/frappe-dev/server/com-bench/"
    "apps/company/company/company/logs/"
    "whatsapp_webhook.log"
)


def write_log(title, data=""):

    try:

        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

        with open(LOG_FILE, "a", encoding="utf-8") as f:

            f.write(f"\n\n{'=' * 100}\n")

            f.write(f"{datetime.now()} | {title}\n")

            f.write(f"{data}\n")

    except Exception as e:

        print(str(e))


@frappe.whitelist(allow_guest=True)
def webhook():

    write_log(
        "WEBHOOK HIT",
        f"""
METHOD:
{frappe.request.method}

ARGS:
{dict(frappe.form_dict)}

RAW:
{frappe.request.get_data(as_text=True)}
""",
    )

    # =====================================================
    # VERIFY WEBHOOK
    # =====================================================

    if frappe.request.method == "GET":

        try:

            settings = frappe.get_single("CRM WhatsApp Settings")

            verify_token = frappe.form_dict.get("hub.verify_token")

            challenge = frappe.form_dict.get("hub.challenge")

            saved_token = settings.get_password("webhook_verify_token")

            write_log(
                "VERIFY REQUEST",
                f"""
Received Token:
{verify_token}

Saved Token:
{saved_token}

Challenge:
{challenge}
""",
            )

            if verify_token == saved_token:

                return Response(challenge, mimetype="text/plain")

            return Response("Invalid Verify Token", status=403)

        except Exception:

            write_log("VERIFY ERROR", frappe.get_traceback())

            frappe.log_error(frappe.get_traceback(), "WhatsApp Verify Error")

            return Response("Verification Failed", status=500)

    # =====================================================
    # RECEIVE EVENTS
    # =====================================================

    if frappe.request.method == "POST":

        try:

            payload = frappe.request.get_json()

            write_log("POST PAYLOAD", json.dumps(payload, indent=2))

            for entry in payload.get("entry", []):

                for change in entry.get("changes", []):

                    value = change.get("value", {})

                    # =================================
                    # MESSAGES
                    # =================================

                    messages = value.get("messages", [])

                    write_log("MESSAGES FOUND", json.dumps(messages, indent=2))

                    for msg in messages:

                        phone = msg.get("from")

                        meta_message_id = msg.get("id")

                        message_type = msg.get("type", "text")

                        message_body = ""

                        if message_type == "text":

                            message_body = msg.get("text", {}).get("body", "")

                        write_log(
                            "PROCESS MESSAGE",
                            f"""
Phone:
{phone}

Message:
{message_body}

Meta Message ID:
{meta_message_id}
""",
                        )

                        conversation = get_or_create_conversation(phone)

                        create_message(
                            conversation=conversation.name,
                            phone=phone,
                            body=message_body,
                            meta_message_id=meta_message_id,
                            direction="Incoming",
                            message_type="Text",
                            raw_payload=msg,
                        )

                        update_conversation(conversation, message_body)

                    # =================================
                    # STATUS EVENTS
                    # =================================

                    statuses = value.get("statuses", [])

                    write_log("STATUSES FOUND", json.dumps(statuses, indent=2))

                    for status_data in statuses:

                        update_message_status(status_data)

            frappe.db.commit()

            return Response("EVENT_RECEIVED", status=200)

        except Exception:

            write_log("POST ERROR", frappe.get_traceback())

            frappe.log_error(frappe.get_traceback(), "WhatsApp POST Error")

            return Response("ERROR", status=500)

    return Response("METHOD NOT ALLOWED", status=405)


# =====================================================
# CONVERSATION
# =====================================================


def get_or_create_conversation(phone):

    try:
        clean_phone = "".join(filter(str.isdigit, str(phone)))

        conversation_name = frappe.db.get_value(
            "CRM WhatsApp Conversation", {"mobile_number": clean_phone}
        )

        if not conversation_name:
            conversation_name = frappe.db.get_value(
                "CRM WhatsApp Conversation", {"mobile_number": phone}
            )

        if conversation_name:

            write_log("CONVERSATION EXISTS", conversation_name)

            return frappe.get_doc("CRM WhatsApp Conversation", conversation_name)

        doc = frappe.get_doc(
            {
                "doctype": "CRM WhatsApp Conversation",
                "mobile_number": clean_phone,
                "status": "Open",
            }
        )

        doc.insert(ignore_permissions=True)

        frappe.db.commit()

        write_log("CONVERSATION CREATED", doc.name)

        return doc

    except Exception:

        write_log("CONVERSATION ERROR", frappe.get_traceback())

        raise


# =====================================================
# MESSAGE
# =====================================================


def create_message(
    conversation, phone, body, meta_message_id, direction, message_type, raw_payload
):

    try:
        clean_phone = "".join(filter(str.isdigit, str(phone)))

        if frappe.db.exists(
            "CRM WhatsApp Message", {"meta_message_id": meta_message_id}
        ):

            write_log("MESSAGE ALREADY EXISTS", meta_message_id)

            return

        # Try to find a matching lead to link
        lead_name = frappe.db.get_value("Lead", {"phone_number": ["like", f"%{clean_phone[-10:]}"]})

        doc = frappe.get_doc(
            {
                "doctype": "CRM WhatsApp Message",
                "conversation": conversation,
                "mobile_number": clean_phone,
                "message_direction": direction,
                "message_type": message_type,
                "message_content": body,
                "meta_message_id": meta_message_id,
                "status": "Delivered",
                "lead": lead_name,
                "raw_payload": json.dumps(raw_payload, indent=2),
            }
        )

        doc.insert(ignore_permissions=True)

        frappe.db.commit()

        write_log("MESSAGE CREATED", doc.name)

        return doc

    except Exception:

        write_log("MESSAGE ERROR", frappe.get_traceback())

        raise


# =====================================================
# UPDATE CONVERSATION
# =====================================================


def update_conversation(conversation, message):

    try:

        unread = conversation.unread_count or 0

        conversation.last_message = message

        conversation.last_message_on = frappe.utils.now()

        conversation.unread_count = unread + 1

        conversation.save(ignore_permissions=True)

        frappe.db.commit()

        write_log("CONVERSATION UPDATED", conversation.name)

    except Exception:

        write_log("CONVERSATION UPDATE ERROR", frappe.get_traceback())


# =====================================================
# STATUS UPDATE
# =====================================================


def update_message_status(status_data):

    try:

        meta_message_id = status_data.get("id")

        status = status_data.get("status")

        write_log(
            "STATUS UPDATE",
            f"""
Meta Message ID:
{meta_message_id}

Status:
{status}
""",
        )

        message_name = frappe.db.get_value(
            "CRM WhatsApp Message", {"meta_message_id": meta_message_id}
        )

        if not message_name:

            write_log("MESSAGE NOT FOUND", meta_message_id)

            return

        doc = frappe.get_doc("CRM WhatsApp Message", message_name)

        if status == "sent":

            doc.status = "Sent"
            doc.sent_on = frappe.utils.now()

        elif status == "delivered":

            doc.status = "Delivered"
            doc.delivered_on = frappe.utils.now()

        elif status == "read":

            doc.status = "Read"
            doc.read_on = frappe.utils.now()

        elif status == "failed":

            doc.status = "Failed"

        doc.save(ignore_permissions=True)

        frappe.db.commit()

        write_log("STATUS UPDATED", message_name)

    except Exception:

        write_log("STATUS UPDATE ERROR", frappe.get_traceback())
