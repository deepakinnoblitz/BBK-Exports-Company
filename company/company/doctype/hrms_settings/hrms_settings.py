from posixpath import splitext
from urllib.parse import unquote, urlparse

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from company.company.tds import MAX_CESS_RATE_PERCENT, validate_tds_slabs

DEFAULT_COMPANY_NAME = "BBK EXPORTS"
MAX_COMPANY_NAME_LENGTH = 140
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}


def is_safe_logo_url(url: str | None, allow_private: bool = False) -> bool:
	"""Validate that a logo URL is a safe relative upload/asset path or http(s) URL."""
	if not url:
		return False

	trimmed = str(url).strip()
	if not trimmed or any(ord(ch) < 32 for ch in trimmed):
		return False

	parsed = urlparse(trimmed)
	if parsed.scheme:
		if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
			return False
		return True

	# Block protocol-relative URLs (//evil.example) and traversal segments
	if trimmed.startswith("//") or ".." in unquote(trimmed):
		return False

	allowed_prefixes = ["/files/", "/assets/"]
	if allow_private:
		allowed_prefixes.append("/private/files/")

	if not any(trimmed.startswith(prefix) for prefix in allowed_prefixes):
		return False

	_, ext = splitext(parsed.path.lower())
	if ext and ext not in ALLOWED_LOGO_EXTENSIONS:
		return False

	return True


def resolve_company_name(singles: dict) -> str:
	"""Return configured Company Name, distinguishing unset (None) from intentionally cleared ('')."""
	if "company_name" not in singles or singles.get("company_name") is None:
		return DEFAULT_COMPANY_NAME
	return str(singles.get("company_name")).strip()


def get_public_branding() -> dict[str, str]:
	"""Return strictly public branding fields without exposing private HRMS Settings."""
	singles = frappe.db.get_singles_dict("HRMS Settings")
	raw_logo = (singles.get("app_logo") or "").strip()
	# Never return /private/files/* or unsafe URLs to unauthenticated callers
	app_logo = raw_logo if is_safe_logo_url(raw_logo, allow_private=False) else ""
	company_name = resolve_company_name(singles)
	return {
		"app_logo": app_logo,
		"company_name": company_name,
	}


class HRMSSettings(Document):
	"""Single DocType storing organization branding and HRMS configuration."""

	def validate(self):
		self._validate_company_name()
		self._validate_and_publish_app_logo()
		self._validate_tds_settings()

	def _validate_tds_settings(self):
		non_negative_fields = [
			("tds_standard_deduction_new", _("Standard Deduction (New Regime)")),
			("tds_standard_deduction_old", _("Standard Deduction (Old Regime)")),
			("tds_rebate_limit_87a_new", _("Section 87A Rebate Threshold (New Regime)")),
			("tds_rebate_limit_87a_old", _("Section 87A Rebate Threshold (Old Regime)")),
		]
		for fieldname, label in non_negative_fields:
			val = getattr(self, fieldname, None)
			if val is not None and flt(val) < 0:
				frappe.throw(_("{0} cannot be negative.").format(label))

		cess_val = getattr(self, "tds_cess_rate", None)
		if cess_val is not None and (flt(cess_val) < 0 or flt(cess_val) > MAX_CESS_RATE_PERCENT):
			frappe.throw(
				_("Health & Education Cess (%) must be between 0 and {0}.").format(MAX_CESS_RATE_PERCENT)
			)

		validate_tds_slabs(getattr(self, "tds_new_regime_slabs", None), _("New Tax Regime Slabs"))
		validate_tds_slabs(getattr(self, "tds_old_regime_slabs", None), _("Old Tax Regime Slabs"))

	def _validate_company_name(self):
		if self.company_name is None:
			return
		cleaned = str(self.company_name).strip()
		if len(cleaned) > MAX_COMPANY_NAME_LENGTH:
			frappe.throw(
				_("Company Name cannot exceed {0} characters.").format(MAX_COMPANY_NAME_LENGTH)
			)
		self.company_name = cleaned

	def _validate_and_publish_app_logo(self):
		if not self.app_logo:
			self.app_logo = ""
			return

		cleaned_url = str(self.app_logo).strip()
		if not is_safe_logo_url(cleaned_url, allow_private=True):
			frappe.throw(_("Invalid Application Logo URL. Please upload a valid image file."))

		self.app_logo = cleaned_url
		self._ensure_logo_file_public()

	def _ensure_logo_file_public(self):
		if not self.app_logo.startswith("/private/files/"):
			return

		file_name = frappe.db.get_value(
			"File",
			{"file_url": self.app_logo},
			"name",
		)
		if not file_name:
			return

		file_doc = frappe.get_doc("File", file_name)
		if file_doc.is_private:
			file_doc.is_private = 0
			file_doc.save(ignore_permissions=True)
		if file_doc.file_url:
			self.app_logo = file_doc.file_url
