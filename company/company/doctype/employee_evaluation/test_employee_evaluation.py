# Copyright (c) 2026, Innoblitz and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

class TestPersonalityEvent(FrappeTestCase):
	def setUp(self):
		print("\n--- [SETUP] Preparing test data ---")
		# Create a test employee if not exists
		if not frappe.db.exists("Employee", "TEST-EMP-001"):
			self.employee = frappe.get_doc({
				"doctype": "Employee",
				"employee_id": "TEST-EMP-001",
				"employee_name": "Test Employee",
				"email": "test@example.com",
				"user": "Administrator",
				"evaluation_score": 100
			}).insert()
		else:
			self.employee = frappe.get_doc("Employee", "TEST-EMP-001")
			self.employee.evaluation_score = 100
			self.employee.save()

		# Create a test trait
		if not frappe.db.exists("Evaluation Trait", "Teamwork"):
			self.trait = frappe.get_doc({
				"doctype": "Evaluation Trait",
				"trait_name": "Teamwork",
				"reward_score": 2,
				"penalty_score": 5
			}).insert()
		else:
			self.trait = frappe.get_doc("Evaluation Trait", "Teamwork")

	def test_score_calculation_agree(self):
		print("Running: test_score_calculation_agree...")
		event = frappe.get_doc({
			"doctype": "Employee Evaluation",
			"employee": self.employee.name,
			"trait": self.trait.name,
			"evaluation_type": "Agree"
		})
		event.insert()
		self.assertEqual(event.score_change, 2)
		event.submit()
		
		# Check employee score
		self.employee.reload()
		self.assertEqual(self.employee.evaluation_score, 100) # Capped at 100
		print("Result: [SUCCESS] Score remained 100 (capped).")

	def test_score_calculation_disagree(self):
		print("Running: test_score_calculation_disagree...")
		# First reduce score
		self.employee.evaluation_score = 90
		self.employee.save()

		event = frappe.get_doc({
			"doctype": "Employee Evaluation",
			"employee": self.employee.name,
			"trait": self.trait.name,
			"evaluation_type": "Disagree"
		})
		event.insert()
		self.assertEqual(event.score_change, -5)
		event.submit()
		
		# Check employee score
		self.employee.reload()
		self.assertEqual(self.employee.evaluation_score, 85)
		self.assertEqual(self.employee.evaluation_status, "Good")
		print(f"Result: [SUCCESS] Score decreased from 90 to {self.employee.evaluation_score}.")

	def test_score_limits(self):
		print("Running: test_score_limits...")
		# Test minimum limit
		self.employee.evaluation_score = 2
		self.employee.save()

		event = frappe.get_doc({
			"doctype": "Employee Evaluation",
			"employee": self.employee.name,
			"trait": self.trait.name,
			"evaluation_type": "Disagree"
		})
		event.insert()
		event.submit()
		
		self.employee.reload()
		self.assertEqual(self.employee.evaluation_score, 0)
		self.assertEqual(self.employee.evaluation_status, "Needs Improvement")
		print("Result: [SUCCESS] Score hit floor at 0.")

	def test_score_cancellation(self):
		print("Running: test_score_cancellation...")
		self.employee.evaluation_score = 90
		self.employee.save()

		event = frappe.get_doc({
			"doctype": "Employee Evaluation",
			"employee": self.employee.name,
			"trait": self.trait.name,
			"evaluation_type": "Disagree"
		})
		event.insert()
		event.submit()
		
		self.employee.reload()
		self.assertEqual(self.employee.evaluation_score, 85)

		event.cancel()
		self.employee.reload()
		self.assertEqual(self.employee.evaluation_score, 90) # Should be back to 90
		print("Result: [SUCCESS] Score reverted to 90 after cancellation.")

	def test_score_calculation_neutral(self):
		print("Running: test_score_calculation_neutral...")
		self.employee.evaluation_score = 90
		self.employee.save()

		event = frappe.get_doc({
			"doctype": "Employee Evaluation",
			"employee": self.employee.name,
			"trait": self.trait.name,
			"evaluation_type": "Neutral"
		})
		event.insert()
		self.assertEqual(event.score_change, 0)
		event.submit()
		
		self.employee.reload()
		self.assertEqual(self.employee.evaluation_score, 90)
		print("Result: [SUCCESS] Score remained 90 for Neutral evaluation.")

	def tearDown(self):
		frappe.db.rollback()
		print("--- [TEARDOWN] Database Rollback ---")
