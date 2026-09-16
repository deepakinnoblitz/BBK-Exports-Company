import frappe
from frappe.tests import IntegrationTestCase
from datetime import datetime, date
from company.company.doctype.crm_email_automation.crm_email_automation import (
	calculate_next_run,
	process_email_automations
)

class IntegrationTestCRMEmailAutomation(IntegrationTestCase):
	def test_calculate_next_run_daily(self):
		# Calculate next daily run
		next_run = calculate_next_run(
			frequency="Daily",
			start_date="2026-06-10",
			run_time_str="09:00:00",
			last_run=None
		)
		self.assertTrue(next_run > frappe.utils.now_datetime())
		self.assertEqual(next_run.hour, 9)
		self.assertEqual(next_run.minute, 0)

	def test_calculate_next_run_once(self):
		# Calculate once next run
		next_run = calculate_next_run(
			frequency="Once",
			start_date="2026-06-12",
			run_time_str="10:00:00",
			last_run=None
		)
		self.assertEqual(next_run.date(), date(2026, 6, 12))
		self.assertEqual(next_run.hour, 10)

	def test_scheduler_creates_campaign(self):
		# Create test lead
		lead = frappe.get_doc({
			"doctype": "Lead",
			"lead_name": "Automation Tester",
			"email": "auto_test@example.com",
			"phone_number": "+919876543210",
			"leads_type": "Incoming",
			"leads_from": "Website",
			"status": "Not Converted",
			"phone_numbers": [{"phone": "+919876543210"}]
		})
		lead.flags.ignore_links = True
		lead.insert(ignore_permissions=True)

		# Create test template
		template = frappe.get_doc({
			"doctype": "CRM Email Template",
			"template_name": "Automation Template",
			"category": "Welcome",
			"subject": "Auto Test",
			"email_content": "Automated email body.",
			"is_active": 1
		}).insert(ignore_permissions=True)

		# Create automation record scheduled in past (so it runs immediately)
		automation = frappe.get_doc({
			"doctype": "CRM Email Automation",
			"automation_name": "Test Automation Task",
			"is_active": 1,
			"status": "Active",
			"email_template": template.name,
			"target_type": "Lead",
			"frequency": "Once",
			"start_date": "2026-06-01",
			"run_time": "09:00:00",
			"create_separate_campaign": 1,
			"send_immediately": 0
		})
		automation.append("filters", {
			"field_name": "workflow_status",
			"operator": "=",
			"value": "New Lead"
		})
		automation.flags.ignore_links = True
		automation.insert(ignore_permissions=True)

		# Force process_email_automations
		process_email_automations()

		# Retrieve updated automation doc
		automation.reload()
		self.assertEqual(automation.status, "Completed")
		self.assertEqual(automation.total_runs, 1)
		self.assertTrue(automation.last_campaign)

		# Clean up
		automation.delete()
		if automation.last_campaign:
			frappe.delete_doc("CRM Email Campaign", automation.last_campaign, ignore_permissions=True)
		template.delete()
		lead.delete()
