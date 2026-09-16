import frappe
from frappe import _
from frappe.model.document import Document
from datetime import datetime, timedelta
import calendar

class CRMEmailAutomation(Document):
	def validate(self):
		# Sync is_active check with status — only for scheduled automations.
		# Status-change automations (Deal/Lead trigger) are always "Active" once enabled;
		# they do NOT use the scheduler so is_active is not the right gate.
		if not self.for_status_change:
			if self.is_active:
				if self.status in ["Draft", "Paused"]:
					self.status = "Active"
			else:
				if self.status == "Active":
					self.status = "Paused"

		# Validate transitions
		if self.for_status_change:
			if self.trigger_event == "Lead Workflow State Change" and self.previous_workflow_state and self.workflow_state:
				if self.previous_workflow_state == self.workflow_state:
					frappe.throw(_("Previous Workflow State and Target Workflow State cannot be the same."))
			elif self.trigger_event == "Deal Stage Change" and self.previous_deal_stage and self.current_deal_stage:
				if self.previous_deal_stage == self.current_deal_stage:
					frappe.throw(_("Previous Deal Stage and Current Deal Stage cannot be the same."))

		# If active, calculate next run on
		if self.status == "Active" and self.start_date and self.run_time:
			self.next_run_on = calculate_next_run(
				self.frequency,
				self.start_date,
				self.run_time,
				self.week_day,
				self.day_of_month,
				self.last_run_on
			)
		else:
			self.next_run_on = None

def add_months(sourcedate, months):
	month = sourcedate.month - 1 + months
	year = sourcedate.year + month // 12
	month = month % 12 + 1
	day = min(sourcedate.day, calendar.monthrange(year, month)[1])
	return datetime(year, month, day, sourcedate.hour, sourcedate.minute, sourcedate.second)

def set_day_of_month(sourcedate, day):
	max_days = calendar.monthrange(sourcedate.year, sourcedate.month)[1]
	target_day = min(day, max_days)
	return sourcedate.replace(day=target_day)

def calculate_next_run(frequency, start_date, run_time_str, week_day=None, day_of_month=None, last_run=None):
	current_time = frappe.utils.now_datetime()
	
	# Parse run_time
	time_parts = [int(p) for p in str(run_time_str).split(":")]
	run_hour = time_parts[0]
	run_minute = time_parts[1] if len(time_parts) > 1 else 0
	run_second = time_parts[2] if len(time_parts) > 2 else 0

	base_date = frappe.utils.getdate(start_date)
	if last_run:
		base_date = max(base_date, frappe.utils.getdate(last_run))

	next_run = datetime.combine(base_date, datetime.min.time()).replace(
		hour=run_hour, minute=run_minute, second=run_second
	)

	# Adjust if next_run falls in past or matches last run
	iterations = 0
	while next_run <= current_time and iterations < 1000:
		iterations += 1
		if frequency == "Once":
			break
		elif frequency == "Daily":
			next_run += timedelta(days=1)
		elif frequency == "Weekly":
			next_run += timedelta(days=1)
			wd_map = {
				"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
				"Friday": 4, "Saturday": 5, "Sunday": 6
			}
			target_wd = wd_map.get(week_day, 0)
			while next_run.weekday() != target_wd:
				next_run += timedelta(days=1)
		elif frequency == "Monthly":
			next_run = add_months(next_run, 1)
			target_day = int(day_of_month) if day_of_month else 1
			next_run = set_day_of_month(next_run, target_day)
		elif frequency == "Yearly":
			next_run = next_run.replace(year=next_run.year + 1)

	return next_run

@frappe.whitelist()
def process_email_automations():
	# Check if email automation is globally enabled
	try:
		settings = frappe.get_single("CRM Email Settings")
		if not settings.enable_email_automation:
			return
	except Exception:
		pass

	now = frappe.utils.now_datetime()
	
	# Fetch active automations whose schedule has reached
	active_automations = frappe.get_all(
		"CRM Email Automation",
		filters={
			"status": "Active",
			"next_run_on": ["<=", now]
		},
		fields=["name"]
	)

	for row in active_automations:
		auto_doc = frappe.get_doc("CRM Email Automation", row.name)
		
		try:
			# 1. Create separate Campaign if enabled
			campaign_name = f"{auto_doc.automation_name} - {frappe.utils.nowdate()}"
			
			campaign = frappe.new_doc("CRM Email Campaign")
			campaign.campaign_name = campaign_name
			campaign.email_template = auto_doc.email_template
			campaign.target_type = auto_doc.target_type
			campaign.subject = auto_doc.subject_override or ""
			campaign.status = "Draft"
			campaign.send_immediately = auto_doc.send_immediately
			campaign.insert(ignore_permissions=True)

			# Copy filters
			for f in auto_doc.filters:
				campaign.append("filters", {
					"field_name": f.field_name,
					"operator": f.operator,
					"value": f.value
				})
			campaign.save(ignore_permissions=True)

			# 2. Calculate recipients & trigger Campaign Sending
			from company.company.doctype.crm_email_campaign.crm_email_campaign import calculate_recipients, start_campaign
			recipients_count = calculate_recipients(campaign.name)
			
			if recipients_count > 0:
				start_campaign(campaign.name)
			else:
				# Campaign will mark itself completed/empty
				campaign.status = "Completed"
				campaign.save(ignore_permissions=True)

			# 3. Update Automation metrics
			auto_doc.last_campaign = campaign.name
			auto_doc.total_runs = (auto_doc.total_runs or 0) + 1
			auto_doc.last_run_on = now
			auto_doc.total_recipients = (auto_doc.total_recipients or 0) + recipients_count

			# 4. Schedule next run or complete automation
			if auto_doc.frequency == "Once":
				auto_doc.status = "Completed"
				auto_doc.is_active = 0
				auto_doc.next_run_on = None
			else:
				# Calculate new next run time
				auto_doc.next_run_on = calculate_next_run(
					auto_doc.frequency,
					auto_doc.start_date,
					auto_doc.run_time,
					auto_doc.week_day,
					auto_doc.day_of_month,
					now
				)
			
			auto_doc.save(ignore_permissions=True)
			
		except Exception as e:
			frappe.log_error(f"Error processing email automation {auto_doc.name}: {str(e)}", "CRM Email Automation Error")
			
			if auto_doc.auto_pause_on_error:
				auto_doc.status = "Failed"
				auto_doc.is_active = 0
				auto_doc.next_run_on = None
				auto_doc.save(ignore_permissions=True)


#-----------------------------------------------------------------------
# Status Changes
#-----------------------------------------------------------------------

@frappe.whitelist()
def get_matching_automation(
    target_type,
    trigger_event,
    current_state=None,
    previous_state=None,
):
    """
    Return the first enabled automation matching the trigger.
    """

    # Normalize target_type to match DB options (Lead, Contact, Account, Deals, Proposals)
    db_target_type = target_type
    if target_type == "Deal":
        db_target_type = "Deals"
    elif target_type == "Proposal":
        db_target_type = "Proposals"
    elif target_type == "Contacts":
        db_target_type = "Contact"
    elif target_type == "Accounts":
        db_target_type = "Account"

    filters = {
        "is_active": 1,
        "target_type": db_target_type,
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
            filters["current_deal_stage"] = current_state
        if previous_state:
            filters["previous_deal_stage"] = previous_state

    automation = frappe.get_all(
        "CRM Email Automation",
        filters=filters,
        fields=["name"],
        limit=1,
    )

    if not automation:
        return None

    return frappe.get_doc("CRM Email Automation", automation[0].name)


def replace_template_variables(message, doc, proposal_name=None):
    """
    Render template message using Frappe's Jinja environment.
    Provides {{ doc.fieldname }} and standard Frappe utilities.
    Returns HTML-formatted content (HTML tags are preserved).
    """
    if not message:
        return ""

    try:
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
        
        return rendered
        
    except Exception as e:
        frappe.log_error(f"Template Render Error: {str(e)}", "Email Automation Error")
        return message

def build_email_message(automation, doc, proposal_name=None):
    """
    Render the email body from the selected template.
    Returns only the email body (without subject).
    """

    template = frappe.get_doc(
        "CRM Email Template",
        automation.email_template
    )

    body = replace_template_variables(
        template.email_content or "",
        doc,
        proposal_name,
    )

    footer = replace_template_variables(
        template.footer_content or "",
        doc,
        proposal_name,
    )

    return "\n\n".join(
        part for part in [body, footer] if part
    )


def evaluate_automations(doc, method=None):
    """
    Evaluates global document updates to trigger Email Automations.
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
        target_type=doc.doctype,
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
    Return Email automation preview.
    Accepts an optional proposal_name to render the preview for a specific proposal.
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
        target_type=doctype,
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
        "preview": build_email_message(automation, doc, proposal_name),
        "show_confirmation": automation.show_confirmation_dialog,
    }

@frappe.whitelist()
def get_proposal_attachments(proposal_name):
    """
    Get all attachments/files uploaded for the given Proposal.
    """
    if not proposal_name:
        return []
    attachments = frappe.get_all(
        "Proposal Attachment",
        filters={"parent": proposal_name},
        fields=["name", "file_name", "attachment", "file_size"]
    )
    for att in attachments:
        att["file_url"] = att.get("attachment")
    return attachments

@frappe.whitelist()
def send_automation_message(automation_name, doctype, docname, proposal_name=None, attachments=None):
    """
    Triggered manually via Frappe msgprint dialog confirmation.
    """
    automation = frappe.get_doc("CRM Email Automation", automation_name)
    doc = frappe.get_doc(doctype, docname)
    _execute_automation(automation, doc, proposal_name, attachments)


def _execute_automation(automation, doc, proposal_name=None, attachments=None):
    """
    Execute CRM Email Automation.
    """

    # ------------------------------------------------------------------
    # Evaluate Conditions
    # ------------------------------------------------------------------
    if automation.get("conditions"):
        for condition in automation.conditions:
            doc_value = doc.get(condition.field_name)
            expected_value = condition.value

            if (
                condition.operator == "Equals"
                and str(doc_value) != str(expected_value)
            ):
                return

            if (
                condition.operator == "Not Equals"
                and str(doc_value) == str(expected_value)
            ):
                return

    # ------------------------------------------------------------------
    # Build Email
    # ------------------------------------------------------------------
    template = frappe.get_doc(
        "CRM Email Template",
        automation.email_template
    )

    subject = replace_template_variables(
        automation.subject_override or template.subject or "",
        doc,
        proposal_name,
    )

    message = build_email_message(
        automation,
        doc,
        proposal_name,
    )

    # ------------------------------------------------------------------
    # Get Recipient Email
    # ------------------------------------------------------------------
    recipient = get_email_address(doc)

    if not recipient:
        frappe.log_error(
            f"Email Automation failed for {doc.doctype} {doc.name}: No email address found.",
            "CRM Email Automation",
        )
        return

    # ------------------------------------------------------------------
    # Send Email
    # ------------------------------------------------------------------
    try:
        reply_to = template.reply_to_email if template.reply_to_email else None

        mail_args = {
            "recipients": [recipient],
            "subject": subject,
            "message": message,
            "reply_to": reply_to,
            "delayed": False,
        }

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
                # Frappe sendmail expects attachments list to contain dicts like {"file_url": "..."}
                # or similar format.
                mail_args["attachments"] = [{"file_url": att.get("file_url")} for att in parsed_attachments if att.get("file_url")]

        frappe.sendmail(**mail_args)

        frappe.logger().info(
            f"Email Automation sent successfully to {recipient}"
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "CRM Email Automation Error",
        )
        return

    # ------------------------------------------------------------------
    # Update Automation Statistics
    # ------------------------------------------------------------------
    automation.last_run_on = frappe.utils.now_datetime()
    automation.total_runs = (automation.total_runs or 0) + 1
    automation.total_recipients = (
        automation.total_recipients or 0
    ) + 1

    automation.save(ignore_permissions=True)

def get_email_address(doc):
    """
    Return the best email address for the given document.
    """

    # ------------------------------------------------------------------
    # Lead
    # ------------------------------------------------------------------
    if doc.doctype == "Lead":

        if doc.email:
            return doc.email

        if getattr(doc, "emails", None):
            for row in doc.emails:
                if row.email:
                    return row.email

        return None

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------
    elif doc.doctype == "Contacts":

        if doc.email:
            return doc.email

        return None

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------
    elif doc.doctype == "Accounts":

        contact = frappe.db.sql(
            """
            SELECT c.email
            FROM `tabContacts` c
            INNER JOIN `tabContact Company` cc
                ON cc.parent = c.name
            WHERE cc.company_name = %s
            AND IFNULL(c.email, '') != ''
            ORDER BY c.creation ASC
            LIMIT 1
            """,
            (doc.account_name,),
            as_dict=True,
        )

        if contact:
            return contact[0].email

        return None

    # ------------------------------------------------------------------
    # Deal
    # ------------------------------------------------------------------
    elif doc.doctype == "Deal":

        # Contact
        if getattr(doc, "contact", None):
            email = frappe.db.get_value(
                "Contacts",
                doc.contact,
                "email",
            )
            if email:
                return email

        # Lead
        if getattr(doc, "lead", None):
            email = frappe.db.get_value(
                "Lead",
                doc.lead,
                "email",
            )
            if email:
                return email

        # Account
        if getattr(doc, "account", None):
            account = frappe.get_doc("Accounts", doc.account)
            return get_email_address(account)

        return None

    return None