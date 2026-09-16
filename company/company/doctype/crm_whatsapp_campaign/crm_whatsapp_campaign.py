# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import re
import time
import frappe
from frappe.model.document import Document


class CRMWhatsAppCampaign(Document):
	pass


# ---------------------------------------------------------------------------
# RECIPIENTS
# ---------------------------------------------------------------------------

def get_recipients(campaign):
    """
    Return recipients matching campaign filters.
    """

    doctype_map = {
        "Lead": "Lead",
        "Contact": "Contacts",
        "Account": "Accounts",
    }

    doctype = doctype_map.get(campaign.target_type)

    if not doctype:
        return []

    # -------------------------
    # Build Filters
    # -------------------------

    filters = []

    for row in campaign.filters:
        field = row.field_name

        if not field:
            continue

        operator = row.operator or "="
        value = row.value

        if operator in ("Like", "Not Like") and value:
            if "%" not in value:
                value = f"%{value}%"

        filters.append([field, operator, value])

    # -------------------------
    # Name field
    # -------------------------

    if doctype == "Lead":
        name_field = "lead_name"
    elif doctype == "Contacts":
        name_field = "first_name"
    else:
        name_field = "account_name"

    # -------------------------
    # Fetch Records
    # -------------------------

    try:
        query_fields = ["name", name_field]

        meta = frappe.get_meta(doctype)

        if meta.has_field("phone"):
            query_fields.append("phone")

        if meta.has_field("phone_number"):
            query_fields.append("phone_number")

        records = frappe.get_all(
            doctype,
            filters=filters,
            fields=query_fields,
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "CRM WhatsApp Campaign Recipient Error",
        )
        return []

    recipients = []

    # -------------------------
    # Build Recipient List
    # -------------------------

    if doctype == "Accounts":

        for rec in records:

            contacts = frappe.db.sql(
                """
                SELECT
                    c.name,
                    c.first_name,
                    c.phone,
                    c.phone_number
                FROM `tabContacts` c
                INNER JOIN `tabContact Company` cc
                    ON cc.parent = c.name
                WHERE cc.company_name=%s
                """,
                (rec.account_name,),
                as_dict=True,
            )

            if contacts:

                for contact in contacts:

                    phone = contact.phone or contact.phone_number

                    if phone:
                        recipients.append({
                            "name": contact.first_name,
                            "phone": phone,
                            "doctype": "Contacts",
                            "docname": contact.name,
                        })

            else:

                phone = rec.get("phone") or rec.get("phone_number")

                if phone:
                    recipients.append({
                        "name": rec.get(name_field),
                        "phone": phone,
                        "doctype": doctype,
                        "docname": rec.name,
                    })

    else:

        for rec in records:

            phone = rec.get("phone_number") or rec.get("phone")

            if not phone:
                continue

            recipients.append({
                "name": rec.get(name_field),
                "phone": phone,
                "doctype": doctype,
                "docname": rec.name,
            })

    return recipients


# ---------------------------------------------------------------------------
# TEMPLATE RENDERING
# ---------------------------------------------------------------------------

def render_template(template_doc, recipient_info):
	"""
	Render the WhatsApp template (header + body + footer) using Frappe Jinja.
	Returns plain-text message string.
	"""
	ref_doc = None
	if recipient_info.get("doctype") and recipient_info.get("docname"):
		try:
			ref_doc = frappe.get_doc(recipient_info["doctype"], recipient_info["docname"])
		except Exception:
			pass

	context = {
		"lead_name": recipient_info.get("name", ""),
		"first_name": "",
		"last_name": "",
		"company_name": "",
		"mobile_no": recipient_info.get("phone", ""),
		"current_date": frappe.utils.formatdate(frappe.utils.nowdate(), "yyyy-MM-dd")
	}

	if context["lead_name"]:
		parts = context["lead_name"].split(" ", 1)
		context["first_name"] = parts[0]
		context["last_name"] = parts[1] if len(parts) > 1 else ""

	if ref_doc:
		if ref_doc.doctype == "Lead":
			context["lead_name"] = ref_doc.get("lead_name") or context["lead_name"]
			if context["lead_name"]:
				parts = context["lead_name"].split(" ", 1)
				context["first_name"] = parts[0]
				context["last_name"] = parts[1] if len(parts) > 1 else ""
			context["company_name"] = ref_doc.get("company_name") or ""
			context["mobile_no"] = ref_doc.get("phone_number") or ref_doc.get("phone") or ""
		elif ref_doc.doctype == "Contacts":
			context["lead_name"] = ref_doc.get("first_name") or context["lead_name"]
			context["first_name"] = ref_doc.get("first_name") or context["first_name"]
			context["last_name"] = ""
			if ref_doc.get("company_name"):
				try:
					context["company_name"] = ref_doc.company_name[0].company_name or ""
				except Exception:
					pass
			context["mobile_no"] = ref_doc.get("phone") or ""
		elif ref_doc.doctype == "Accounts":
			context["lead_name"] = ref_doc.get("account_name") or context["lead_name"]
			context["first_name"] = ref_doc.get("account_name") or context["first_name"]
			context["company_name"] = ref_doc.get("account_name") or ""
			context["mobile_no"] = ref_doc.get("phone_number") or ""

	header = template_doc.header_text or ""
	body = template_doc.message_body or ""
	footer = template_doc.footer_text or ""

	def _render(text):
		if not text:
			return ""
		try:
			rendered = frappe.render_template(text, context)
		except Exception:
			for key, val in context.items():
				rendered = text.replace("{{" + key + "}}", str(val))
		# Strip HTML tags and normalise whitespace
		rendered = re.sub(r'(?i)<br\s*/?>', '\n', rendered)
		rendered = re.sub(r'(?i)</p>', '\n', rendered)
		rendered = re.sub(r'(?i)</div>', '\n', rendered)
		rendered = frappe.utils.strip_html(rendered)
		rendered = re.sub(r'\n{3,}', '\n\n', rendered)
		return rendered.strip()

	parts = [_render(header), _render(body), _render(footer)]
	return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# FILTER HELPERS  (whitelisted — used by frontend / JS)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_filter_fields(target_type):
	"""Return filterable fields for the given target_type."""
	doctype_map = {
		"Lead": "Lead",
		"Contact": "Contacts",
		"Account": "Accounts"
	}
	doctype = doctype_map.get(target_type)
	if not doctype:
		return []

	meta = frappe.get_meta(doctype)
	fields = []

	if meta.has_field("workflow_status"):
		fields.append({"value": "workflow_status", "label": "Workflow State"})

	fields.extend([
		{"value": "owner", "label": "Owner"},
		{"value": "creation", "label": "Created Date"},
		{"value": "modified", "label": "Modified Date"}
	])

	for field in meta.fields:
		if field.fieldtype in [
			"Select", "Link", "Data", "Int", "Float",
			"Currency", "Date", "Check", "Autocomplete"
		]:
			if field.fieldname not in ["workflow_status", "owner", "creation", "modified"]:
				fields.append({
					"value": field.fieldname,
					"label": field.label or field.fieldname
				})

	return fields


@frappe.whitelist()
def get_filter_value_options(target_type, field_name):
	"""Return distinct values for a given field on the target doctype."""
	doctype_map = {
		"Lead": "Lead",
		"Contact": "Contacts",
		"Account": "Accounts"
	}
	doctype = doctype_map.get(target_type)
	if not doctype:
		return []

	actual_field = field_name

	if actual_field == "workflow_status":
		workflow_name = frappe.db.get_value(
			"Workflow", {"document_type": doctype, "is_active": 1}, "name"
		)
		if workflow_name:
			states = frappe.get_all(
				"Workflow Document State",
				filters={"parent": workflow_name},
				fields=["state"]
			)
			options = [s.get("state") for s in states if s.get("state")]
			if options:
				return sorted(list(set(options)))

	meta = frappe.get_meta(doctype)
	if not meta.has_field(actual_field):
		return []

	df = meta.get_field(actual_field)
	if df and df.fieldtype == "Select" and df.options:
		options = [opt.strip() for opt in df.options.split("\n") if opt.strip()]
		return sorted(list(set(options)))

	try:
		values = frappe.get_all(
			doctype,
			fields=[actual_field],
			distinct=True,
			filters=[[actual_field, "is", "set"]]
		)
	except Exception:
		try:
			values = frappe.get_all(
				doctype,
				fields=[actual_field],
				distinct=True,
				filters=[[actual_field, "!=", ""]]
			)
		except Exception:
			return []

	options = []
	for val in values:
		v = val.get(actual_field)
		if v is not None and v != "":
			options.append(str(v))

	return sorted(list(set(options)))


# ---------------------------------------------------------------------------
# CALCULATE / PREVIEW
# ---------------------------------------------------------------------------

@frappe.whitelist()
def calculate_recipients(campaign_name):
	"""Count matching recipients and save total_recipients on the campaign."""
	campaign = frappe.get_doc("CRM WhatsApp Campaign", campaign_name)
	recipients = get_recipients(campaign)
	campaign.total_recipients = len(recipients)
	campaign.save(ignore_permissions=True)
	return campaign.total_recipients


@frappe.whitelist()
def preview_recipients(target_type, filters=None):
	"""Return count + first 100 recipients for live filter preview."""
	import json

	filters = json.loads(filters or "[]")
	filters = [frappe._dict(f) for f in filters]

	campaign = frappe._dict({
		"target_type": target_type,
		"filters": filters
	})

	recipients = get_recipients(campaign)

	return {
		"count": len(recipients),
		"recipients": recipients[:100]
	}


@frappe.whitelist()
def get_campaign_recipients(campaign_name):
	"""
	If campaign is Draft → return live filter preview.
	Otherwise → return queue records.
	"""
	campaign = frappe.get_doc("CRM WhatsApp Campaign", campaign_name)

	if campaign.status != "Draft":
		queue_records = frappe.get_all(
			"CRM WhatsApp Queue",
			filters={"campaign": campaign.name},
			fields=["recipient_name", "recipient_phone", "status", "error_message"]
		)
		return {
			"source": "queue",
			"recipients": queue_records
		}
	else:
		recipients = get_recipients(campaign)
		formatted = []
		for r in recipients:
			formatted.append({
				"recipient_name": r["name"],
				"recipient_phone": r["phone"],
				"status": "Pending"
			})
		return {
			"source": "filters",
			"recipients": formatted
		}


# ---------------------------------------------------------------------------
# CAMPAIGN LIFECYCLE
# ---------------------------------------------------------------------------

@frappe.whitelist()
def start_campaign(campaign_name):
	"""
	Start or resume a campaign.
	- Draft → builds queue records then sets Running
	- Paused → resumes (sets Running, re-enqueues worker)
	- Scheduled → treated like Draft
	"""
	campaign = frappe.get_doc("CRM WhatsApp Campaign", campaign_name)

	if campaign.status not in ["Draft", "Scheduled", "Paused"]:
		frappe.throw("Campaign cannot be started in its current status")

	if campaign.status in ["Draft", "Scheduled"]:
		recipients = get_recipients(campaign)
		campaign.total_recipients = len(recipients)

		if not recipients:
			frappe.throw("No recipients match the filter criteria. Please adjust your filters.")

		template = frappe.get_doc("CRM WhatsApp Template", campaign.whatsapp_template)

		# Determine default attachment from template (if any)
		attachment = None
		if (
			template.allow_attachment
			and template.get("default_attachment")
			and len(template.default_attachment)
		):
			attachment = template.default_attachment[0].file

		for rec in recipients:
			message = render_template(template, rec)
			queue_doc = frappe.new_doc("CRM WhatsApp Queue")
			queue_doc.campaign = campaign.name
			queue_doc.whatsapp_template = campaign.whatsapp_template
			queue_doc.recipient_name = rec["name"]
			queue_doc.recipient_phone = rec["phone"]
			queue_doc.reference_doctype = rec["doctype"]
			queue_doc.reference_name = rec["docname"]
			queue_doc.message_content = message
			queue_doc.attachment = attachment or ""
			queue_doc.status = "Pending"
			queue_doc.queued_on = frappe.utils.now()
			queue_doc.insert(ignore_permissions=True)

	campaign.status = "Running"
	campaign.save(ignore_permissions=True)

	frappe.enqueue(
		"company.company.doctype.crm_whatsapp_campaign.crm_whatsapp_campaign.process_campaign",
		campaign_name=campaign.name,
		queue="long"
	)

	return {"message": "Campaign started"}


@frappe.whitelist()
def pause_campaign(campaign_name):
	"""Pause a running campaign. The background worker checks status on each iteration."""
	campaign = frappe.get_doc("CRM WhatsApp Campaign", campaign_name)

	if campaign.status != "Running":
		frappe.throw("Only running campaigns can be paused")

	campaign.status = "Paused"
	campaign.save(ignore_permissions=True)

	return {"message": "Campaign paused"}


@frappe.whitelist()
def cancel_campaign(campaign_name):
	"""Cancel a campaign (cannot cancel Completed campaigns)."""
	campaign = frappe.get_doc("CRM WhatsApp Campaign", campaign_name)

	if campaign.status == "Completed":
		frappe.throw("Completed campaigns cannot be cancelled")

	campaign.status = "Cancelled"
	campaign.save(ignore_permissions=True)

	return {"message": "Campaign cancelled"}


# ---------------------------------------------------------------------------
# BACKGROUND WORKER
# ---------------------------------------------------------------------------

def process_campaign(campaign_name):
	"""
	Background queue processor.
	Sends WhatsApp messages in batches, respecting Paused / Cancelled status.
	"""
	campaign = frappe.get_doc("CRM WhatsApp Campaign", campaign_name)
	from company.company.crm_whatsapp_api import send_whatsapp

	max_batch_size = 50
	batch_delay = 5
	max_retries = 3
	auto_retry = True

	# Allow override via CRM WhatsApp Settings if those fields exist
	try:
		wa_settings = frappe.get_single("CRM WhatsApp Settings")
		if hasattr(wa_settings, "max_messages_per_batch") and wa_settings.max_messages_per_batch:
			max_batch_size = int(wa_settings.max_messages_per_batch)
		if hasattr(wa_settings, "batch_delay") and wa_settings.batch_delay:
			batch_delay = int(wa_settings.batch_delay)
		if hasattr(wa_settings, "maximum_retry_count") and wa_settings.maximum_retry_count:
			max_retries = int(wa_settings.maximum_retry_count)
		if hasattr(wa_settings, "auto_retry_failed") and wa_settings.auto_retry_failed is not None:
			auto_retry = bool(wa_settings.auto_retry_failed)
	except Exception:
		pass

	while True:
		campaign.reload()
		if campaign.status in ["Paused", "Cancelled"]:
			break

		status_filter = ["Pending", "Failed"] if auto_retry else ["Pending"]

		queues = frappe.get_all(
			"CRM WhatsApp Queue",
			filters=[
				["campaign", "=", campaign.name],
				["status", "in", status_filter]
			],
			fields=["name", "status", "retry_count"],
			limit=max_batch_size
		)

		if not queues:
			break

		processed_any = False

		for row in queues:
			campaign.reload()
			if campaign.status in ["Paused", "Cancelled"]:
				break

			if row.status == "Failed" and (row.retry_count or 0) >= max_retries:
				continue

			queue_doc = frappe.get_doc("CRM WhatsApp Queue", row.name)
			processed_any = True

			try:
				queue_doc.status = "Processing"
				queue_doc.retry_count = (queue_doc.retry_count or 0) + 1
				queue_doc.save(ignore_permissions=True)

				template = None
				if queue_doc.whatsapp_template:
					try:
						template = frappe.get_doc("CRM WhatsApp Template", queue_doc.whatsapp_template)
					except Exception:
						pass

				response = send_whatsapp(
					phone=queue_doc.recipient_phone,
					message=queue_doc.message_content,
					attachment=queue_doc.attachment or None
				)

				if response.get("success") and template and template.allow_attachment and template.default_attachment and len(template.default_attachment) > 1:
					for idx, att in enumerate(template.default_attachment):
						if idx == 0:
							continue
						if att.file:
							send_whatsapp(
								phone=queue_doc.recipient_phone,
								message=None,
								attachment=att.file
							)

				if response.get("success"):
					queue_doc.status = "Sent"
					queue_doc.sent_on = frappe.utils.now()
					queue_doc.error_message = ""
				else:
					queue_doc.status = "Failed"
					queue_doc.error_message = str(
						response.get("error") or "Unknown error"
					)[:500]

				queue_doc.save(ignore_permissions=True)

			except Exception as e:
				queue_doc.status = "Failed"
				queue_doc.error_message = str(e)[:500]
				queue_doc.save(ignore_permissions=True)

			# Update campaign counters after each message
			campaign.sent_count = frappe.db.count(
				"CRM WhatsApp Queue", {"campaign": campaign.name, "status": "Sent"}
			)
			campaign.failed_count = frappe.db.count(
				"CRM WhatsApp Queue", {"campaign": campaign.name, "status": "Failed"}
			)
			campaign.save(ignore_permissions=True)

		if not processed_any:
			break

		time.sleep(batch_delay)

	# Mark Completed if all messages processed and campaign is still Running
	remaining = frappe.db.count(
		"CRM WhatsApp Queue",
		{
			"campaign": campaign.name,
			"status": ["in", ["Pending", "Processing"]]
		}
	)

	campaign.reload()
	if remaining == 0 and campaign.status == "Running":
		campaign.status = "Completed"
		campaign.save(ignore_permissions=True)