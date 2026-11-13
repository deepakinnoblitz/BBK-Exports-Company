# Copyright (c) 2026, deepak and Contributors
# See license.txt

import os

import frappe
from frappe.tests import IntegrationTestCase

from company.company.doctype.hrms_settings.hrms_settings import (
	DEFAULT_COMPANY_NAME,
	get_public_branding,
	is_safe_logo_url,
)
from company.company.frontend_api import get_app_branding
from company.company.tds import DEFAULT_TDS_NEW_SLABS_JSON

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class IntegrationTestHRMSSettings(IntegrationTestCase):
	"""Integration tests for HRMSSettings branding validation and public branding endpoint."""

	def setUp(self):
		super().setUp()
		self._prev_user = frappe.session.user
		frappe.set_user("Administrator")
		self._orig_singles = frappe.db.get_singles_dict("HRMS Settings")
		self._created_files = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for file_name in self._created_files:
			if frappe.db.exists("File", file_name):
				frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)

		frappe.db.delete("Singles", {"doctype": "HRMS Settings"})
		for field, value in self._orig_singles.items():
			if field != "doctype":
				frappe.db.sql(
					"""INSERT INTO `tabSingles` (doctype, field, value) VALUES (%s, %s, %s)""",
					("HRMS Settings", field, value),
				)
		frappe.clear_document_cache("HRMS Settings", "HRMS Settings")
		frappe.set_user(self._prev_user)
		super().tearDown()

	def test_guest_branding_only_exposes_safe_public_fields(self):
		frappe.db.set_single_value("HRMS Settings", "app_logo", "/private/files/legacy-logo.png")
		frappe.db.set_single_value("HRMS Settings", "company_name", "  Acme Apparel  ")

		frappe.set_user("Guest")
		branding = get_app_branding()

		self.assertEqual(set(branding.keys()), {"app_logo", "company_name"})
		self.assertEqual(branding["app_logo"], "")
		self.assertEqual(branding["company_name"], "Acme Apparel")

	def test_company_name_unset_vs_explicit_empty(self):
		frappe.db.delete("Singles", {"doctype": "HRMS Settings", "field": "company_name"})
		frappe.clear_document_cache("HRMS Settings", "HRMS Settings")
		self.assertEqual(get_public_branding()["company_name"], DEFAULT_COMPANY_NAME)

		frappe.db.set_single_value("HRMS Settings", "company_name", "")
		frappe.clear_document_cache("HRMS Settings", "HRMS Settings")
		self.assertEqual(get_public_branding()["company_name"], "")

	def test_rejects_unsafe_logo_urls(self):
		unsafe_urls = [
			"javascript:alert(1)",
			"data:text/html,<script>alert(1)</script>",
			"//evil.example.com/logo.png",
			"/files/../secrets/logo.png",
			"/files/evil.html",
		]
		for url in unsafe_urls:
			self.assertFalse(is_safe_logo_url(url, allow_private=True), f"Expected unsafe: {url}")
			doc = frappe.get_doc("HRMS Settings", "HRMS Settings")
			doc.app_logo = url
			with self.assertRaises(frappe.ValidationError):
				doc.save(ignore_permissions=True)

	def test_validate_converts_private_logo_file_to_public(self):
		unique_name = f"test_brand_logo_{frappe.generate_hash(length=6)}.png"
		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": unique_name,
				"content": b"\x89PNG\r\n\x1a\n",
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		self._created_files.append(file_doc.name)

		self.assertTrue(file_doc.file_url.startswith("/private/files/"))

		doc = frappe.get_doc("HRMS Settings", "HRMS Settings")
		doc.app_logo = file_doc.file_url
		doc.company_name = "  New Horizon Exports  "
		doc.save(ignore_permissions=True)

		self.assertTrue(doc.app_logo.startswith("/files/"))
		self.assertEqual(doc.company_name, "New Horizon Exports")
		self.assertEqual(frappe.db.get_value("File", file_doc.name, "is_private"), 0)

		public_path = frappe.get_site_path("public", doc.app_logo.lstrip("/"))
		self.assertTrue(os.path.exists(public_path))

		frappe.set_user("Guest")
		branding = get_app_branding()
		self.assertEqual(branding["app_logo"], doc.app_logo)
		self.assertEqual(branding["company_name"], "New Horizon Exports")

	def test_rejects_invalid_tds_settings(self):
		doc = frappe.get_doc("HRMS Settings", "HRMS Settings")
		doc.tds_standard_deduction_new = -1000
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

		doc = frappe.get_doc("HRMS Settings", "HRMS Settings")
		doc.tds_cess_rate = 25.0
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

		doc = frappe.get_doc("HRMS Settings", "HRMS Settings")
		doc.tds_new_regime_slabs = '[{"from_amount": 0, "to_amount": 500000, "rate_percent": 0}, {"from_amount": 400000, "to_amount": null, "rate_percent": 10}]'
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_accepts_fy_2026_27_new_regime_tds_defaults(self):
		doc = frappe.get_doc("HRMS Settings", "HRMS Settings")
		doc.enable_tds = 1
		doc.tds_standard_deduction_new = 75000
		doc.tds_rebate_limit_87a_new = 1200000
		doc.tds_enable_marginal_relief = 1
		doc.tds_cess_rate = 4.0
		doc.tds_new_regime_slabs = DEFAULT_TDS_NEW_SLABS_JSON
		doc.save(ignore_permissions=True)
		self.assertEqual(float(doc.tds_rebate_limit_87a_new), 1200000.0)
