# Copyright (c) 2025, deepak and contributors
# For license information, please see license.txt

import re
import frappe
from frappe import _
from frappe.model.document import Document


def is_bank_name_matching(input_name: str, expected_name: str) -> bool:
	if not input_name or not expected_name:
		return False
	a = input_name.strip().lower()
	b = expected_name.strip().lower()
	if a == b:
		return True

	def sanitize(s: str) -> str:
		s = re.sub(r"[^a-z0-9\s]", " ", s)
		s = re.sub(r"\b(ltd|limited|bank|the)\b", "", s)
		return " ".join(s.split())

	clean_a = sanitize(a)
	clean_b = sanitize(b)

	if clean_a and clean_b:
		if clean_a == clean_b:
			return True
		if len(clean_a) >= 4 and len(clean_b) >= 4:
			if clean_a in clean_b or clean_b in clean_a:
				return True

	raw_a = re.sub(r"[^a-z0-9]", "", a)
	raw_b = re.sub(r"[^a-z0-9]", "", b)
	return len(raw_a) >= 3 and raw_a == raw_b


class BankAccount(Document):
	def validate(self):
		self.validate_account_number()
		self.validate_ifsc_and_bank_name()

	def validate_account_number(self):
		if not self.account_number:
			frappe.throw(_("Account Number is required."))

		self.account_number = str(self.account_number).strip()

		# Must contain only numeric digits
		if not self.account_number.isdigit():
			frappe.throw(_("Account Number must contain only numeric digits."))

		# Restrict duplicate account numbers across members
		filters = {"account_number": self.account_number}
		if not self.is_new():
			filters["name"] = ["!=", self.name]

		existing = frappe.db.get_value(
			"Bank Account",
			filters,
			["name", "bank_account_name"],
			as_dict=True,
		)
		if existing:
			member_name = existing.bank_account_name or existing.name
			frappe.throw(
				_("Account Number '{0}' already exists for member '{1}'. Account numbers must be unique across members.").format(
					self.account_number, member_name
				)
			)

	def validate_ifsc_and_bank_name(self):
		if self.ifsc_code:
			self.ifsc_code = str(self.ifsc_code).strip().upper()
			if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", self.ifsc_code):
				frappe.throw(_("Invalid IFSC Code '{0}'. Must be 11 characters (e.g. HDFC0000003).").format(self.ifsc_code))

			# Verify bank name matches entered IFSC code
			if self.bank_name:
				self.bank_name = str(self.bank_name).strip()
				try:
					from company.company.api import get_bank_details_by_ifsc
					res = get_bank_details_by_ifsc(self.ifsc_code)
					if res and res.get("success") and res.get("data"):
						expected_bank = res["data"].get("bank_name", "")
						if expected_bank and not is_bank_name_matching(self.bank_name, expected_bank):
							frappe.throw(
								_("Bank Name '{0}' does not match the entered IFSC code '{1}' (Expected: {2}).").format(
									self.bank_name, self.ifsc_code, expected_bank
								)
							)
				except Exception as e:
					if isinstance(e, frappe.ValidationError):
						raise
					frappe.log_error(f"IFSC bank verification error: {str(e)}", "Bank Account IFSC Validation")
