# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


import re
from urllib.parse import quote
from frappe.model.document import Document

class CRMEmailCampaign(Document):
	pass

def get_recipients(campaign):
	doctype_map = {
		"Lead": "Lead",
		"Contact": "Contacts",
		"Account": "Accounts"
	}
	doctype = doctype_map.get(campaign.target_type)
	if not doctype:
		return []

	db_filters = []
	for row in campaign.filters:
		actual_field = getattr(row, "field_name", None) or row.get("field_name")
		if not actual_field:
			continue
		
		# If the operator is Like or Not Like, format the value for SQL
		val = getattr(row, "value", None) or row.get("value")
		operator = getattr(row, "operator", None) or row.get("operator") or "="
		if operator in ["Like", "Not Like"] and val:
			if not val.startswith("%") and not val.endswith("%"):
				val = f"%{val}%"

		db_filters.append([doctype, actual_field, operator, val])

	name_field = "lead_name" if doctype == "Lead" else ("first_name" if doctype == "Contacts" else "account_name")

	try:
		records = frappe.get_all(
			doctype,
			filters=db_filters,
			fields=["name", "email", name_field]
		)
	except Exception as e:
		frappe.log_error(f"Error querying campaign recipients: {str(e)}", "CRM Campaign Filter")
		return []

	recipients = []
	for rec in records:
		email = rec.get("email")
		if doctype == "Accounts":
			# Search for contacts linked to this Account
			account_name = rec.get("account_name")
			linked_contacts = frappe.db.sql("""
				SELECT email, first_name
				FROM `tabContacts` c
				JOIN `tabContact Company` cc ON cc.parent = c.name
				WHERE cc.company_name = %s
			""", (account_name,), as_dict=True)
			
			if linked_contacts:
				for contact in linked_contacts:
					if contact.get("email"):
						recipients.append({
							"name": contact.get("first_name") or rec.get(name_field) or rec.get("name"),
							"email": contact.get("email"),
							"doctype": doctype,
							"docname": rec.get("name")
						})
			else:
				# Fallback to owner_name if it contains @
				owner_email = rec.get("owner_name") or rec.get("owner")
				if owner_email and "@" in owner_email:
					recipients.append({
						"name": rec.get(name_field) or rec.get("name"),
						"email": owner_email,
						"doctype": doctype,
						"docname": rec.get("name")
					})
		else:
			if email:
				recipients.append({
					"name": rec.get(name_field) or rec.get("name"),
					"email": email,
					"doctype": doctype,
					"docname": rec.get("name")
				})
	return recipients

def render_template(template_doc, recipient_info):
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
		"email": recipient_info.get("email", ""),
		"mobile_no": "",
		"owner": "",
		"current_date": frappe.utils.formatdate(frappe.utils.nowdate(), "yyyy-MM-dd")
	}

	if context["lead_name"]:
		parts = context["lead_name"].split(" ", 1)
		context["first_name"] = parts[0]
		context["last_name"] = parts[1] if len(parts) > 1 else ""

	if ref_doc:
		context["owner"] = ref_doc.get("owner_name") or ref_doc.get("owner") or ""
		if ref_doc.doctype == "Lead":
			context["lead_name"] = ref_doc.get("lead_name") or context["lead_name"]
			if context["lead_name"]:
				parts = context["lead_name"].split(" ", 1)
				context["first_name"] = parts[0]
				context["last_name"] = parts[1] if len(parts) > 1 else ""
			context["company_name"] = ref_doc.get("company_name") or ""
			context["mobile_no"] = ref_doc.get("phone_number") or ""
		elif ref_doc.doctype == "Contacts":
			context["lead_name"] = ref_doc.get("first_name") or context["lead_name"]
			context["first_name"] = ref_doc.get("first_name") or context["first_name"]
			context["last_name"] = ""
			if ref_doc.company_name:
				context["company_name"] = ref_doc.company_name[0].company_name or ""
			context["mobile_no"] = ref_doc.get("phone") or ""
		elif ref_doc.doctype == "Accounts":
			context["lead_name"] = ref_doc.get("account_name") or context["lead_name"]
			context["first_name"] = ref_doc.get("account_name") or context["first_name"]
			context["company_name"] = ref_doc.get("account_name") or ""
			context["mobile_no"] = ref_doc.get("phone_number") or ""

	subject = template_doc.subject or ""
	content = template_doc.email_content or ""
	footer = template_doc.footer_content or ""

	try:
		subject = frappe.render_template(subject, context)
		content = frappe.render_template(content, context)
		if footer:
			footer = frappe.render_template(footer, context)
	except Exception:
		for key, val in context.items():
			placeholder = "{{" + key + "}}"
			subject = subject.replace(placeholder, str(val))
			content = content.replace(placeholder, str(val))
			if footer:
				footer = footer.replace(placeholder, str(val))

	full_html = content
	if footer:
		full_html += "<br><br>" + footer

	return subject, full_html

@frappe.whitelist(allow_guest=True)
def unsubscribe(email):
	return "<h3>You have been successfully unsubscribed from our mailing list.</h3>"

@frappe.whitelist()
def get_filter_fields(target_type):
    doctype_map = {
        "Lead": "Lead",
        "Contact": "Contacts",
        "Account": "Accounts",
    }

    doctype = doctype_map.get(target_type)
    if not doctype:
        return []

    meta = frappe.get_meta(doctype)
    fields = []

    # Add common/system fields
    if meta.has_field("workflow_status"):
        fields.append({
            "value": "workflow_status",
            "label": "Workflow State"
        })

    fields.extend([
        {
            "value": "owner",
            "label": "Owner"
        },
        {
            "value": "creation",
            "label": "Created Date"
        },
        {
            "value": "modified",
            "label": "Modified Date"
        },
    ])

    allowed_fieldtypes = [
        "Data",
        "Select",
        "Link",
        "Autocomplete",
        "Check",
        "Date",
        "Datetime",
        "Time",
        "Int",
        "Float",
        "Currency",
    ]

    ignored_fields = {
        "workflow_status",
        "owner",
        "creation",
        "modified",
    }

    for field in meta.fields:
        # Ignore hidden fields
        if field.hidden:
            continue
        if field.read_only:
            continue

        # Ignore unwanted field types
        if field.fieldtype not in allowed_fieldtypes:
            continue

        # Ignore duplicate/system fields
        if field.fieldname in ignored_fields:
            continue

        fields.append({
            "value": field.fieldname,
            "label": field.label or field.fieldname,
        })

    # Sort alphabetically (keep system fields on top)
    system_fields = fields[:4]
    other_fields = sorted(fields[4:], key=lambda x: x["label"].lower())

    return system_fields + other_fields

@frappe.whitelist()
def get_filter_value_options(target_type, field_name):
	doctype_map = {
		"Lead": "Lead",
		"Contact": "Contacts",
		"Account": "Accounts"
	}
	doctype = doctype_map.get(target_type)
	if not doctype:
		return []

	actual_field = field_name

	# Handle Workflow Status specifically by querying active workflow states
	if actual_field == "workflow_status":
		workflow_name = frappe.db.get_value("Workflow", {"document_type": doctype, "is_active": 1}, "name")
		if workflow_name:
			states = frappe.get_all("Workflow Document State", filters={"parent": workflow_name}, fields=["state"])
			options = [s.get("state") for s in states if s.get("state")]
			if options:
				return sorted(list(set(options)))

	meta = frappe.get_meta(doctype)
	if not meta.has_field(actual_field):
		return []

	# If Select field, extract options from field metadata
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


@frappe.whitelist()
def calculate_recipients(campaign_name):
	campaign = frappe.get_doc("CRM Email Campaign", campaign_name)
	recipients = get_recipients(campaign)
	campaign.total_recipients = len(recipients)
	campaign.save(ignore_permissions=True)
	return campaign.total_recipients

@frappe.whitelist()
def preview_recipients(target_type, filters=None):
    import json
    import frappe

    filters = json.loads(filters or "[]")

    filters = [
        frappe._dict(f)
        for f in filters
    ]

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
	campaign = frappe.get_doc("CRM Email Campaign", campaign_name)
	if campaign.status != "Draft":
		queue_records = frappe.get_all(
			"CRM Email Queue",
			filters={"campaign": campaign.name},
			fields=["recipient_name", "recipient_email", "status", "opened", "clicked", "error_message"]
		)
		return {
			"source": "queue",
			"recipients": queue_records
		}
	else:
		recipients = get_recipients(campaign)
		# format to match return structure
		formatted = []
		for r in recipients:
			formatted.append({
				"recipient_name": r["name"],
				"recipient_email": r["email"],
				"status": "Pending",
				"opened": 0,
				"clicked": 0
			})
		return {
			"source": "filters",
			"recipients": formatted
		}

def process_campaign(campaign_name):
	campaign = frappe.get_doc("CRM Email Campaign", campaign_name)
	import time

	max_batch_size = 100
	batch_delay = 5
	max_retries = 3
	auto_retry = True

	try:
		settings = frappe.get_single("CRM Email Settings")
		max_batch_size = int(settings.max_emails_per_batch or 100)
		batch_delay = int(settings.batch_delay or 5)
		max_retries = int(settings.maximum_retry_count or 3)
		auto_retry = bool(settings.auto_retry_failed_emails)
	except Exception:
		pass

	while True:
		campaign.reload()
		if campaign.status in ["Paused", "Cancelled"]:
			break

		db_filters = [
			["campaign", "=", campaign.name],
			["status", "in", ["Pending", "Failed"]]
		]
		
		if not auto_retry:
			db_filters = [
				["campaign", "=", campaign.name],
				["status", "=", "Pending"]
			]

		queues = frappe.get_all(
			"CRM Email Queue",
			filters=db_filters,
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

			queue_doc = frappe.get_doc("CRM Email Queue", row.name)
			processed_any = True

			try:
				queue_doc.status = "Processing"
				queue_doc.retry_count = (queue_doc.retry_count or 0) + 1
				queue_doc.save(ignore_permissions=True)

				send_campaign_email(queue_doc)

				queue_doc.status = "Sent"
				queue_doc.sent_on = frappe.utils.now()
				queue_doc.save(ignore_permissions=True)
			except Exception as e:
				queue_doc.status = "Failed"
				queue_doc.error_message = str(e)
				queue_doc.save(ignore_permissions=True)

			campaign.sent_count = frappe.db.count("CRM Email Queue", {"campaign": campaign.name, "status": "Sent"})
			campaign.failed_count = frappe.db.count("CRM Email Queue", {"campaign": campaign.name, "status": "Failed"})
			campaign.save(ignore_permissions=True)

		if not processed_any:
			break

		time.sleep(batch_delay)

	remaining = frappe.db.count(
		"CRM Email Queue",
		{
			"campaign": campaign.name,
			"status": ["in", ["Pending", "Processing"]]
		}
	)

	if remaining == 0 and campaign.status == "Running":
		campaign.status = "Completed"
		campaign.save(ignore_permissions=True)

@frappe.whitelist()
def start_campaign(campaign_name):
	campaign = frappe.get_doc("CRM Email Campaign", campaign_name)

	if campaign.status not in ["Draft", "Scheduled", "Paused"]:
		frappe.throw("Campaign cannot be started")

	if campaign.status == "Draft":
		recipients = get_recipients(campaign)
		campaign.total_recipients = len(recipients)
		if not recipients:
			frappe.throw("No recipients match the filter criteria")

		template = frappe.get_doc("CRM Email Template", campaign.email_template)
		for rec in recipients:
			subj, body = render_template(template, rec)
			queue_doc = frappe.new_doc("CRM Email Queue")
			queue_doc.campaign = campaign.name
			queue_doc.email_template = campaign.email_template
			queue_doc.recipient_name = rec["name"]
			queue_doc.recipient_email = rec["email"]
			queue_doc.reference_doctype = rec["doctype"]
			queue_doc.reference_name = rec["docname"]
			queue_doc.subject = subj
			queue_doc.email_content = body
			queue_doc.status = "Pending"
			queue_doc.queued_on = frappe.utils.now()
			queue_doc.insert(ignore_permissions=True)

	campaign.status = "Running"
	campaign.save(ignore_permissions=True)

	frappe.enqueue(
		"company.company.doctype.crm_email_campaign.crm_email_campaign.process_campaign",
		campaign_name=campaign.name,
		queue="long"
	)

	return {
		"message": "Campaign started"
	}

@frappe.whitelist()
def pause_campaign(campaign_name):
	campaign = frappe.get_doc("CRM Email Campaign", campaign_name)

	if campaign.status != "Running":
		frappe.throw("Only running campaigns can be paused")

	campaign.status = "Paused"
	campaign.save(ignore_permissions=True)

	return {
		"message": "Campaign paused"
	}

@frappe.whitelist()
def cancel_campaign(campaign_name):
	campaign = frappe.get_doc("CRM Email Campaign", campaign_name)

	if campaign.status == "Completed":
		frappe.throw("Completed campaign cannot be cancelled")

	campaign.status = "Cancelled"
	campaign.save(ignore_permissions=True)

	return {
		"message": "Campaign cancelled"
	}

@frappe.whitelist()
def send_campaign_email(queue_doc):
	attachments = []
	if queue_doc.email_template:
		template = frappe.get_cached_doc("CRM Email Template", queue_doc.email_template)
		for att in template.attachments:
			if att.file:
				attachments.append({"file_url": att.file})

	sender = None
	reply_to = None

	default_email_id = None
	default_name = None
	try:
		settings = frappe.get_single("CRM Email Settings")
		if settings.default_email_account:
			email_account = frappe.get_cached_doc("Email Account", settings.default_email_account)
			if email_account.email_id:
				default_email_id = email_account.email_id
				default_name = email_account.email_account_name or email_account.name or email_account.email_id
	except Exception:
		pass

	if queue_doc.email_template:
		template = frappe.get_cached_doc("CRM Email Template", queue_doc.email_template)
		
		# Sender display name from template, or default to email account name
		sender_display_name = template.sender_name or default_name
		
		if sender_display_name and default_email_id:
			sender = f"{sender_display_name} <{default_email_id}>"
		elif sender_display_name:
			sender = sender_display_name
		elif default_email_id:
			sender = f"{default_name} <{default_email_id}>"

		if template.reply_to_email:
			reply_to = template.reply_to_email
	else:
		if default_email_id:
			sender = f"{default_name} <{default_email_id}>"

	content = queue_doc.email_content

	if queue_doc.email_template:
		template = frappe.get_cached_doc("CRM Email Template", queue_doc.email_template)
		if template.enable_unsubscribe:
			unsub_link = f'<br><br><div style="text-align: center; font-size: 12px; color: #888888;"><a href="/api/method/company.company.doctype.crm_email_campaign.crm_email_campaign.unsubscribe?email={quote(queue_doc.recipient_email)}">Unsubscribe</a></div>'
			content += unsub_link

	mail_args = {
		"recipients": [queue_doc.recipient_email],
		"subject": queue_doc.subject,
		"content": content,
		"delayed": False
	}
	if sender:
		mail_args["sender"] = sender
	if reply_to:
		mail_args["reply_to"] = reply_to
	if attachments:
		mail_args["attachments"] = attachments

	frappe.sendmail(**mail_args)