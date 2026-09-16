# Copyright (c) 2025, deepak and Contributors
# See license.txt

# import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestInvoiceCollection(IntegrationTestCase):
	"""
	Integration tests for InvoiceCollection.
	Use this class for testing interactions between multiple components.
	"""

	def test_invoice_collection_summary_report(self):
		import importlib
		module = importlib.import_module("company.company.report.invoice_&_collection_summary.invoice_&_collection_summary")
		execute = module.execute

		columns, data, message, chart, summary = execute()
		self.assertIsInstance(columns, list)
		self.assertIsInstance(data, list)
		self.assertIsInstance(summary, list)

		# Ensure columns match expected schema
		col_labels = [c["label"] for c in columns]
		self.assertIn("ID", col_labels)
		self.assertIn("Invoice No", col_labels)
		self.assertIn("Date", col_labels)
		self.assertIn("Mode", col_labels)
		self.assertIn("Amount to Pay", col_labels)
		self.assertIn("Amount", col_labels)
		self.assertIn("Pending", col_labels)

