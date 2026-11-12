import frappe
from frappe.tests import IntegrationTestCase

from company.company.utils.employee_validation import (
	check_employee_field_value,
	normalize_and_validate_phone,
	validate_identity_format,
)

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class IntegrationTestEmployee(IntegrationTestCase):
	"""Tests for Employee country-aware phone validation and unique identity fields."""

	def _make_employee(self, emp_id: str, **overrides):
		doc = frappe.new_doc("Employee")
		doc.employee_id = emp_id
		doc.employee_name = f"Test {emp_id}"
		doc.email = f"{emp_id.lower()}@example.com"
		doc.date_of_joining = "2026-01-01"
		doc.status = "Active"
		for key, val in overrides.items():
			doc.set(key, val)
		doc.insert(ignore_permissions=True)
		return doc

	def test_phone_validation_country_specific(self):
		# Valid India 10-digit formats -> canonical +91-9876543210
		self.assertEqual(
			normalize_and_validate_phone("+91 9876543210", "Personal Phone Number"),
			("+91-9876543210", "+919876543210"),
		)
		self.assertEqual(
			normalize_and_validate_phone("9876543210", "Personal Phone Number"),
			("+91-9876543210", "+919876543210"),
		)
		# Valid international numbers (UAE 9 digits, US 10 digits, UK mobile)
		self.assertEqual(
			normalize_and_validate_phone("+971 50 123 4567", "Personal Phone Number"),
			("+971-501234567", "+971501234567"),
		)
		self.assertEqual(
			normalize_and_validate_phone("+1 650 253 0000", "Personal Phone Number"),
			("+1-6502530000", "+16502530000"),
		)
		self.assertEqual(
			normalize_and_validate_phone("+44 7911 123456", "Personal Phone Number"),
			("+44-7911123456", "+447911123456"),
		)
		# Bare dial codes treated as empty optional values
		self.assertEqual(normalize_and_validate_phone("+91", "Personal Phone Number"), (None, None))
		self.assertEqual(normalize_and_validate_phone("+1", "Personal Phone Number"), (None, None))

		# Wrong lengths / invalid prefixes rejected with country message
		with self.assertRaises(frappe.ValidationError):
			normalize_and_validate_phone("+91 987654321", "Personal Phone Number")
		with self.assertRaises(frappe.ValidationError):
			normalize_and_validate_phone("+91 98765432101", "Personal Phone Number")
		with self.assertRaises(frappe.ValidationError):
			normalize_and_validate_phone("+91 5555555555", "Personal Phone Number")
		with self.assertRaises(frappe.ValidationError):
			normalize_and_validate_phone("+1 650 253 000", "Personal Phone Number")
		with self.assertRaises(frappe.ValidationError):
			normalize_and_validate_phone("+123", "Personal Phone Number")

	def test_statutory_format_normalization_and_validation(self):
		self.assertEqual(validate_identity_format("aadhar_number", "1234 5678 9012"), "123456789012")
		self.assertEqual(validate_identity_format("pan_number", "abcde 1234 f"), "ABCDE1234F")
		self.assertEqual(validate_identity_format("uan_number", "1094-6700-0099"), "109467000099")
		self.assertEqual(validate_identity_format("esi_no", "51 326096303960597"), "51326096303960597")
		self.assertEqual(validate_identity_format("pf_number", " tn/mas/12345/0000099 "), "TN/MAS/12345/0000099")

		with self.assertRaises(frappe.ValidationError):
			validate_identity_format("aadhar_number", "1234567890")
		with self.assertRaises(frappe.ValidationError):
			validate_identity_format("pan_number", "INVALIDPAN")
		with self.assertRaises(frappe.ValidationError):
			validate_identity_format("uan_number", "123456")
		with self.assertRaises(frappe.ValidationError):
			validate_identity_format("esi_no", "ABC123")

	def test_employee_uniqueness_for_statutory_and_phone_fields(self):
		emp1 = self._make_employee(
			"TESTVAL001",
			phone="+91 9999888877",
			office_phone_number="+91 9999888800",
			aadhar_number="2345 6789 0123",
			pan_number="abcde1234f",
			uan_number="109900112233",
			esi_no="51000000000000001",
			pf_number="tn/mas/99999/0000001",
		)
		self.assertEqual(emp1.phone, "+91-9999888877")
		self.assertEqual(emp1.aadhar_number, "234567890123")
		self.assertEqual(emp1.pan_number, "ABCDE1234F")
		self.assertEqual(emp1.pf_number, "TN/MAS/99999/0000001")

		# Updating own record is allowed
		emp1.employee_name = "Test TESTVAL001 Updated"
		emp1.save()

		# Office phone MAY be shared across employees (no uniqueness error)
		emp_office_shared = self._make_employee(
			"TESTVAL002",
			office_phone_number="+91-9999888800",
			aadhar_number="234567890124",
		)
		self.assertEqual(emp_office_shared.office_phone_number, "+91-9999888800")

		# Duplicate Personal Phone across separator format blocked
		with self.assertRaises(frappe.ValidationError):
			self._make_employee("TESTVALDUP1", phone="9999888877")

		# Duplicate Aadhar blocked even with spaces
		with self.assertRaises(frappe.ValidationError):
			self._make_employee("TESTVALDUP2", aadhar_number="2345-6789-0123")

		# Duplicate PAN blocked even in lowercase
		with self.assertRaises(frappe.ValidationError):
			self._make_employee("TESTVALDUP3", pan_number="ABCDE1234F")

		# Duplicate UAN, ESI, PF blocked
		with self.assertRaises(frappe.ValidationError):
			self._make_employee("TESTVALDUP4", uan_number="109900112233")
		with self.assertRaises(frappe.ValidationError):
			self._make_employee("TESTVALDUP5", esi_no="51000000000000001")
		with self.assertRaises(frappe.ValidationError):
			self._make_employee("TESTVALDUP6", pf_number="TN/MAS/99999/0000001")

		# Empty optional values allowed for multiple employees (normalized to NULL)
		emp_blank_a = self._make_employee("TESTVALBLANK1", phone="+91", pan_number="")
		emp_blank_b = self._make_employee("TESTVALBLANK2", phone="", pan_number="   ")
		self.assertIsNone(emp_blank_a.phone)
		self.assertIsNone(emp_blank_b.pan_number)

		# Live availability helper reports self as available and duplicate as unavailable
		self.assertTrue(check_employee_field_value("aadhar_number", "2345 6789 0123", emp1.name)["available"])
		self.assertFalse(check_employee_field_value("aadhar_number", "2345 6789 0123", emp_blank_a.name)["available"])
		self.assertFalse(check_employee_field_value("phone", "+91-999988887", None)["valid"])
