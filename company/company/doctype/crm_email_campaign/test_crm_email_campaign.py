# Copyright (c) 2026, deepak and Contributors
# See license.txt

# import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



import frappe
from frappe.tests import IntegrationTestCase
from company.company.doctype.crm_email_campaign.crm_email_campaign import (
	render_template,
	inject_tracking
)

class IntegrationTestCRMEmailCampaign(IntegrationTestCase):
	def setUp(self):
		self.lead = frappe.get_doc({
			"doctype": "Lead",
			"lead_name": "John Doe",
			"email": "johndoe@example.com",
			"company_name": "Test Company",
			"phone_number": "1234567890",
			"leads_type": "Incoming",
			"leads_from": "Website",
			"status": "Not Converted"
		}).insert(ignore_permissions=True)

		self.template = frappe.get_doc({
			"doctype": "CRM Email Template",
			"template_name": "Test Template",
			"category": "Welcome",
			"subject": "Hello {{first_name}} from {{company_name}}",
			"email_content": "Dear {{lead_name}}, your email is {{email}}.",
			"enable_open_tracking": 1,
			"enable_click_tracking": 1,
			"enable_unsubscribe": 1,
			"is_active": 1
		}).insert(ignore_permissions=True)

	def tearDown(self):
		self.lead.delete()
		self.template.delete()

	def test_template_rendering(self):
		recipient_info = {
			"name": self.lead.lead_name,
			"email": self.lead.email,
			"doctype": "Lead",
			"docname": self.lead.name
		}
		subject, body = render_template(self.template, recipient_info)
		self.assertEqual(subject, "Hello John from Test Company")
		self.assertIn("Dear John Doe, your email is johndoe@example.com.", body)

	def test_tracking_injection(self):
		content = '<a href="https://example.com/click-here">Link</a>'
		injected = inject_tracking(content, "test-queue-id", enable_open=True, enable_click=True)
		self.assertIn("track_click", injected)
		self.assertIn("track_open", injected)
		self.assertIn("url=https%3A//example.com/click-here", injected)
