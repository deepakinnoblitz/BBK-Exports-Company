# Copyright (c) 2026, Deepak and contributors
# For license information, please see license.txt

import re
import frappe
from frappe.model.document import Document


class CRMWhatsAppAutomation(Document):
    pass


@frappe.whitelist()
def get_matching_automation(
    document_type,
    trigger_event,
    current_state=None,
    previous_state=None,
):
    """
    Return the first enabled automation matching the trigger.
    """

    # Normalize document_type to match DB options (Lead, Contacts, Accounts, Deal, Proposal)
    db_document_type = document_type
    if document_type == "Deals" or document_type == "Deal":
        db_document_type = "Deal"
    elif document_type == "Proposals" or document_type == "Proposal":
        db_document_type = "Proposal"
    elif document_type == "Contact" or document_type == "Contacts":
        db_document_type = "Contacts"
    elif document_type == "Account" or document_type == "Accounts":
        db_document_type = "Accounts"

    filters = {
        "is_active": 1,
        "document_type": db_document_type,
        "trigger_event": trigger_event,
    }

    # Lead
    if trigger_event == "Lead Workflow State Change":
        if current_state:
            filters["workflow_state"] = current_state
        if previous_state:
            filters["previous_workflow_state"] = previous_state

    # Deal
    elif trigger_event == "Deal Stage Change":
        if current_state:
            filters["deal_stage"] = current_state
        if previous_state:
            filters["previous_deal_stage"] = previous_state

    automation = frappe.get_all(
        "CRM WhatsApp Automation",
        filters=filters,
        fields=["name"],
        limit=1,
    )

    if not automation:
        return None

    return frappe.get_doc("CRM WhatsApp Automation", automation[0].name)


def replace_template_variables(message, doc, proposal_name=None):
    """
    Render template message using Frappe's Jinja environment.
    Provides {{ doc.fieldname }} and standard Frappe utilities.
    """
    if not message:
        return ""

    try:
        import re
        # Provide both direct fields {{ lead_name }} and {{ doc.name }}
        context = doc.as_dict().copy()
        context["doc"] = doc
        
        # Supply proposal context if applicable
        if doc.doctype == "Lead":
            if not proposal_name:
                # For preview, try to grab the latest proposal
                latest = frappe.db.get_value("Proposal", {"lead": doc.name}, "name", order_by="creation desc")
                if latest:
                    proposal_name = latest
            
            if proposal_name:
                context["proposal"] = frappe.get_doc("Proposal", proposal_name).as_dict()
            else:
                # Provide an empty dict so jinja doesn't fail with UndefinedError
                context["proposal"] = frappe._dict()

        rendered = frappe.render_template(message, context)
        
        # Convert paragraph and break tags to newlines to preserve spacing
        rendered = re.sub(r'(?i)<br\s*/?>', '\n', rendered)
        rendered = re.sub(r'(?i)</p>', '\n', rendered)
        rendered = re.sub(r'(?i)</div>', '\n', rendered)
        
        # Strip remaining HTML tags
        rendered = frappe.utils.strip_html(rendered)
        
        # Collapse 3+ consecutive newlines down to max 2 (one blank line)
        rendered = re.sub(r'\n{3,}', '\n\n', rendered)
        
        return rendered.strip()
        
    except Exception as e:
        frappe.log_error(f"Template Render Error: {str(e)}", "WhatsApp Automation Error")
        return message


def build_whatsapp_message(automation, doc, proposal_name=None):
    """
    Load template and return rendered message.
    """

    template = frappe.get_doc(
        "CRM WhatsApp Template",
        automation.whatsapp_template
    )

    header = replace_template_variables(
        template.header_text or "",
        doc, proposal_name
    )

    body = replace_template_variables(
        template.message_body or "",
        doc, proposal_name
    )

    footer = replace_template_variables(
        template.footer_text or "",
        doc, proposal_name
    )

    return "\n\n".join(
        part for part in [header, body, footer] if part
    )


def evaluate_automations(doc, method=None):
    """
    Evaluates global document updates to trigger WhatsApp Automations.
    Called via hooks.py on_update doc_event.
    """
    if doc.is_new():
        return

    # Check if workflow_state changed
    doc_before_save = doc.get_doc_before_save()
    if not doc_before_save:
        return

    if doc.doctype == "Lead":
        trigger_event = "Lead Workflow State Change"
        current_state = doc.workflow_state
        previous_state = doc_before_save.workflow_state

    elif doc.doctype == "Deal":
        trigger_event = "Deal Stage Change"
        current_state = doc.stage
        previous_state = doc_before_save.stage

    else:
        return

    if current_state == previous_state:
        return

    automation = get_matching_automation(
        document_type=doc.doctype,
        trigger_event=trigger_event,
        current_state=current_state,
        previous_state=previous_state,
    )

    if not automation:
        return
        
    if automation.auto_send:
        _execute_automation(automation, doc)


@frappe.whitelist()
def get_automation_preview(
    doctype,
    docname,
    current_state=None,
    previous_state=None,
    proposal_name=None,
):
    """
    Return WhatsApp automation preview.
    """

    doc = frappe.get_doc(doctype, docname)

    # Use current workflow state if not passed
    if doctype == "Lead":
        trigger_event = "Lead Workflow State Change"
        current_state = current_state or doc.workflow_state

    elif doctype == "Deal":
        trigger_event = "Deal Stage Change"
        current_state = current_state or doc.stage

    else:
        return None

    automation = get_matching_automation(
        document_type=doctype,
        trigger_event=trigger_event,
        current_state=current_state,
        previous_state=previous_state,
    )

    if not automation:
        return None

    return {
        "automation_name": automation.name,
        "title": automation.dialog_title,
        "message": automation.dialog_message,
        "preview": build_whatsapp_message(automation, doc, proposal_name),
        "show_confirmation": automation.show_confirmation_dialog,
    }

@frappe.whitelist()
def send_automation_message(automation_name, doctype, docname, proposal_name=None, attachments=None):
    """
    Triggered manually via Frappe msgprint dialog confirmation.
    """
    automation = frappe.get_doc("CRM WhatsApp Automation", automation_name)
    doc = frappe.get_doc(doctype, docname)
    _execute_automation(automation, doc, proposal_name, attachments)


def _execute_automation(automation, doc, proposal_name=None, attachments=None):
    """
    Core logic to build message and call API.
    """
    # Evaluate Conditions (if any)
    if automation.get("conditions"):
        for condition in automation.conditions:
            doc_value = doc.get(condition.field_name)
            expected_value = condition.value
            
            if condition.operator == "Equals" and str(doc_value) != str(expected_value):
                return
            elif condition.operator == "Not Equals" and str(doc_value) == str(expected_value):
                return

    # Build Message
    message_body = build_whatsapp_message(automation, doc, proposal_name)
    
    # Get Phone Number
    phone_number = None
    phone_number = get_phone_number(doc)

    if not phone_number:
        frappe.log_error(
            f"WhatsApp Automation failed for {doc.name}: No phone number found.",
            "WhatsApp Automation Error"
        )
        return
            
    if not phone_number:
        frappe.log_error(f"WhatsApp Automation failed for {doc.name}: No phone number found.", "WhatsApp Automation Error")
        return

    # Call API
    from company.company.crm_whatsapp_api import send_whatsapp
    
    template = frappe.get_doc("CRM WhatsApp Template", automation.whatsapp_template)
    
    selected_attachments = []
    if template.allow_attachment:
        if attachments:
            if isinstance(attachments, str):
                import json
                try:
                    parsed_attachments = json.loads(attachments)
                except Exception:
                    parsed_attachments = None
            else:
                parsed_attachments = attachments

            if parsed_attachments:
                selected_attachments = [att.get("file_url") for att in parsed_attachments if att.get("file_url")]
        else:
            if template.default_attachment:
                selected_attachments = [att.file for att in template.default_attachment if att.file]
        
    attachment = selected_attachments[0] if selected_attachments else None
    
    try:
        response = send_whatsapp(phone=phone_number, message=message_body, attachment=attachment)
        
        if response.get("success") and len(selected_attachments) > 1:
            for extra_attachment in selected_attachments[1:]:
                send_whatsapp(phone=phone_number, message=None, attachment=extra_attachment)
        
        msg_doc = frappe.new_doc("CRM WhatsApp Message")
        msg_doc.mobile_number = phone_number
        msg_doc.message_direction = "Outgoing"
        msg_doc.message_type = "Template"
        msg_doc.message_content = message_body
        
        if doc.doctype == "Lead":
            msg_doc.lead = doc.name
        elif doc.doctype == "Contacts":
            msg_doc.client = doc.name
        elif doc.doctype == "Deal":
            msg_doc.prospect = doc.name
        elif doc.doctype == "Proposal":
            msg_doc.proposal = doc.name
            
        if response.get("success"):
            frappe.logger().info(f"WhatsApp Automation sent for {doc.name}")
            msg_doc.status = "Sent"
            msg_doc.raw_payload = frappe.as_json(response)
        else:
            frappe.log_error(f"WhatsApp Automation API Error for {doc.name}: {response.get('error')}", "WhatsApp Automation Error")
            msg_doc.status = "Failed"
            msg_doc.raw_payload = frappe.as_json(response)
            
        msg_doc.insert(ignore_permissions=True)
            
    except Exception as e:
        frappe.log_error(f"WhatsApp Automation Exception for {doc.name}: {str(e)}", "WhatsApp Automation Error")

def get_phone_number(doc):

    # Direct fields
    for field in ("phone_number", "phone"):
        if doc.get(field):
            return doc.get(field)

    # Deal -> Contact
    if doc.doctype == "Deal" and doc.contact:
        contact = frappe.get_doc("Contacts", doc.contact)

        for field in ("phone_number", "phone"):
            if contact.get(field):
                return contact.get(field)

    return None