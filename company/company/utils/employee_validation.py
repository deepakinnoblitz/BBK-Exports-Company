import re
from typing import Any, Callable, Optional

import frappe
import phonenumbers
from phonenumbers import PhoneNumberFormat

PHONE_FIELDS = ("phone", "office_phone_number")
NULLABLE_IDENTITY_FIELDS = (
    "phone",
    "office_phone_number",
    "personal_email",
    "aadhar_number",
    "pan_number",
    "uan_number",
    "esi_no",
    "pf_number",
)


def _strip_all_whitespace_and_hyphens(val: str) -> str:
    cleaned = _clean_excel_phone_artifacts(val)
    return re.sub(r"[\s-]+", "", cleaned).strip()


def _normalize_pan(val: str) -> str:
    return re.sub(r"\s+", "", val).upper()


def _normalize_pf(val: str) -> str:
    return re.sub(r"\s+", "", val).upper()


EMPLOYEE_IDENTITY_RULES: dict[str, dict[str, Any]] = {
    "aadhar_number": {
        "label": "Aadhar Number",
        "normalize": _strip_all_whitespace_and_hyphens,
        "pattern": re.compile(r"^\d{12}$"),
        "format_error": "Aadhar Number must be a valid 12-digit number.",
        "sql_norm": "REPLACE(REPLACE(TRIM(`aadhar_number`), ' ', ''), '-', '')",
        "unique": True,
    },
    "pan_number": {
        "label": "PAN Number",
        "normalize": _normalize_pan,
        "pattern": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$"),
        "format_error": "PAN Number must follow the valid 10-character format (e.g., ABCDE1234F).",
        "sql_norm": "UPPER(REPLACE(TRIM(`pan_number`), ' ', ''))",
        "unique": True,
    },
    "uan_number": {
        "label": "UAN Number",
        "normalize": lambda v: _strip_all_whitespace_and_hyphens(v).upper(),
        "pattern": re.compile(r"^\d{12}$"),
        "format_error": "UAN Number must be a valid 12-digit number.",
        "sql_norm": "UPPER(REPLACE(REPLACE(TRIM(`uan_number`), ' ', ''), '-', ''))",
        "unique": True,
    },
    "esi_no": {
        "label": "ESI No",
        "normalize": lambda v: _strip_all_whitespace_and_hyphens(v).upper(),
        "pattern": re.compile(r"^\d{10,17}$"),
        "format_error": "ESI No must be a valid 10 to 17-digit number.",
        "sql_norm": "UPPER(REPLACE(REPLACE(TRIM(`esi_no`), ' ', ''), '-', ''))",
        "unique": True,
    },
    "pf_number": {
        "label": "PF Number",
        "normalize": _normalize_pf,
        "pattern": None,
        "format_error": None,
        "sql_norm": "UPPER(REPLACE(TRIM(`pf_number`), ' ', ''))",
        "unique": True,
    },
}


def _clean_excel_phone_artifacts(raw_val: Any) -> str:
    """Convert raw Excel/UI phone inputs into a clean string before parsing."""
    if raw_val is None:
        return ""
    s = str(raw_val).strip()
    if not s:
        return ""
    # Handle Excel float/scientific artifacts like '9.19876E+11' or '9876543210.0'
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?[eE]\+[0-9]+", s):
        try:
            s = str(int(float(s)))
        except Exception:
            pass
    elif s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s.strip()


def _is_dial_code_only(raw_str: str) -> bool:
    """Return True when input only holds an international dial prefix (e.g. '+91', '+1') with no subscriber digits."""
    if not raw_str:
        return True
    compact = re.sub(r"[\s-]+", "", raw_str)
    if not compact:
        return True
    if not compact.startswith("+"):
        return False
    digits = compact[1:]
    if not digits:
        return True
    if not digits.isdigit() or len(digits) > 3:
        return False
    # Exact match against ITU country calling codes so e.g. '+123' is NOT misread as '+1'
    return int(digits) in phonenumbers.COUNTRY_CODE_TO_REGION_CODE


def _parse_phone_with_country(raw_str: str, default_region: str = "IN") -> phonenumbers.PhoneNumber:
    """Parse phone string into phonenumbers.PhoneNumber using explicit '+' or India fallback."""
    cleaned = raw_str.strip()
    if cleaned.startswith("+"):
        # Convert Frappe '+CC-NNNN' separator cleanly before parsing
        parse_target = re.sub(r"^(\+\d{1,4})-", r"\1 ", cleaned)
        return phonenumbers.parse(parse_target, None)

    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        raise phonenumbers.NumberParseException(
            phonenumbers.NumberParseException.NOT_A_NUMBER,
            "No digits present",
        )

    # Local 10-digit Indian numbers default to IN; leading 91 + 10 digits treated as +91
    if default_region == "IN":
        if len(digits) == 10:
            return phonenumbers.parse(digits, "IN")
        if len(digits) == 12 and digits.startswith("91"):
            return phonenumbers.parse(f"+{digits}", None)
        if digits.startswith("0") and len(digits) == 11:
            return phonenumbers.parse(digits, "IN")

    # Try international '+' form if length exceeds local format, otherwise use default_region
    try:
        parsed_intl = phonenumbers.parse(f"+{digits}", None)
        if phonenumbers.is_valid_number(parsed_intl):
            return parsed_intl
    except Exception:
        pass
    return phonenumbers.parse(cleaned, default_region)


def _build_phone_validation_error(
    field_label: str,
    parsed: Optional[phonenumbers.PhoneNumber] = None,
) -> str:
    if parsed and parsed.country_code:
        if parsed.country_code == 91:
            return f"Invalid {field_label} for India (+91): please enter a valid 10-digit number."
        region = phonenumbers.region_code_for_number(parsed)
        region_suffix = f" ({region})" if region else ""
        return (
            f"Invalid {field_label} for +{parsed.country_code}{region_suffix}: "
            "please enter a valid phone number for that country."
        )
    return f"Invalid {field_label}: please enter a valid phone number with country code."


def normalize_and_validate_phone(
    value: Any,
    field_label: str = "Phone Number",
    default_region: str = "IN",
    required: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    """
    Validate a phone number using country-specific libphonenumber rules.

    Returns (canonical_storage, e164_key):
      - canonical_storage: '+<cc>-<national_number>' (or None when empty)
      - e164_key: '+<cc><national_number>' (or None when empty)
    Raises frappe.ValidationError via frappe.throw() if invalid.
    """
    cleaned = _clean_excel_phone_artifacts(value)
    if not cleaned or _is_dial_code_only(cleaned):
        if required:
            frappe.throw(frappe._(f"{field_label} is required."))
        return None, None

    parsed = None
    try:
        parsed = _parse_phone_with_country(cleaned, default_region=default_region)
    except Exception:
        frappe.throw(frappe._(_build_phone_validation_error(field_label, None)))

    is_valid = phonenumbers.is_valid_number(parsed)
    if parsed.country_code == 91 and len(str(parsed.national_number)) != 10:
        is_valid = False

    if not is_valid:
        frappe.throw(frappe._(_build_phone_validation_error(field_label, parsed)))

    canonical = f"+{parsed.country_code}-{parsed.national_number}"
    e164_key = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    return canonical, e164_key


def normalize_identity_value(fieldname: str, value: Any) -> Optional[str]:
    """Normalize an identity/statutory field; returns None when empty."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    rule = EMPLOYEE_IDENTITY_RULES.get(fieldname)
    if not rule:
        return raw
    normalizer: Callable[[str], str] = rule["normalize"]
    normalized = normalizer(raw)
    return normalized or None


def validate_identity_format(fieldname: str, value: Any) -> Optional[str]:
    """Normalize and format-validate a statutory field; throws ValidationError on mismatch."""
    normalized = normalize_identity_value(fieldname, value)
    if not normalized:
        return None
    rule = EMPLOYEE_IDENTITY_RULES.get(fieldname)
    if not rule:
        return normalized
    pattern = rule.get("pattern")
    if pattern and not pattern.match(normalized):
        frappe.throw(frappe._(rule["format_error"]))
    return normalized


def find_duplicate_employee_by_field(
    fieldname: str,
    normalized_value: str,
    exclude_employee: Optional[str] = None,
) -> Optional[dict[str, str]]:
    """Find another Employee holding the same normalized field value."""
    if not normalized_value:
        return None

    exclude_name = (exclude_employee or "").strip()

    if fieldname == "phone":
        digits_only = re.sub(r"\D", "", normalized_value)
        sql = """
            SELECT name, employee_name
            FROM `tabEmployee`
            WHERE COALESCE(TRIM(`phone`), '') != ''
              AND REPLACE(REPLACE(REPLACE(REPLACE(TRIM(`phone`), '-', ''), ' ', ''), '+', ''), '(', '') = %s
              AND name != %s
            LIMIT 1
        """
        rows = frappe.db.sql(sql, (digits_only, exclude_name), as_dict=True)
        return rows[0] if rows else None

    rule = EMPLOYEE_IDENTITY_RULES.get(fieldname)
    if not rule or not rule.get("unique"):
        return None

    sql_norm = rule["sql_norm"]
    sql = f"""
        SELECT name, employee_name
        FROM `tabEmployee`
        WHERE COALESCE(TRIM(`{fieldname}`), '') != ''
          AND {sql_norm} = %s
          AND name != %s
        LIMIT 1
    """
    rows = frappe.db.sql(sql, (normalized_value, exclude_name), as_dict=True)
    return rows[0] if rows else None


def check_employee_field_value(
    fieldname: str,
    value: Any,
    current_employee_id: Optional[str] = None,
) -> dict[str, Any]:
    """Validate format and check uniqueness for a single Employee field without mutating DB."""
    if fieldname in PHONE_FIELDS:
        label = "Personal Phone Number" if fieldname == "phone" else "Office Phone Number"
        cleaned = _clean_excel_phone_artifacts(value)
        if not cleaned or _is_dial_code_only(cleaned):
            return {"valid": True, "available": True, "normalized": None, "message": ""}
        try:
            canonical, e164_key = normalize_and_validate_phone(cleaned, field_label=label)
        except frappe.ValidationError as exc:
            return {"valid": False, "available": True, "normalized": None, "message": str(exc)}

        if fieldname == "phone" and e164_key:
            dup = find_duplicate_employee_by_field("phone", e164_key, current_employee_id)
            if dup:
                return {
                    "valid": True,
                    "available": False,
                    "normalized": canonical,
                    "message": (
                        f"Personal Phone Number '{canonical}' is already assigned to "
                        f"{dup['employee_name']} ({dup['name']})."
                    ),
                }
        return {"valid": True, "available": True, "normalized": canonical, "message": ""}

    if fieldname in EMPLOYEE_IDENTITY_RULES:
        rule = EMPLOYEE_IDENTITY_RULES[fieldname]
        label = rule["label"]
        normalized = normalize_identity_value(fieldname, value)
        if not normalized:
            return {"valid": True, "available": True, "normalized": None, "message": ""}

        pattern = rule.get("pattern")
        if pattern and not pattern.match(normalized):
            return {
                "valid": False,
                "available": True,
                "normalized": normalized,
                "message": rule["format_error"],
            }

        if rule.get("unique"):
            dup = find_duplicate_employee_by_field(fieldname, normalized, current_employee_id)
            if dup:
                return {
                    "valid": True,
                    "available": False,
                    "normalized": normalized,
                    "message": f"{label} '{normalized}' is already assigned to {dup['employee_name']} ({dup['name']}).",
                }
        return {"valid": True, "available": True, "normalized": normalized, "message": ""}

    return {"valid": True, "available": True, "normalized": value, "message": ""}


def validate_and_normalize_employee_fields(doc: Any) -> None:
    """Normalize nullable/phone/statutory fields and enforce format + uniqueness on Employee."""
    for fieldname in NULLABLE_IDENTITY_FIELDS:
        raw_val = doc.get(fieldname)
        if isinstance(raw_val, str) and not raw_val.strip():
            doc.set(fieldname, None)

    # Validate & normalize Phone Numbers (Personal & Office)
    phone_canonical, phone_e164 = normalize_and_validate_phone(
        doc.get("phone"),
        field_label="Personal Phone Number",
        default_region="IN",
    )
    doc.phone = phone_canonical
    if phone_e164:
        dup_phone = find_duplicate_employee_by_field("phone", phone_e164, doc.name)
        if dup_phone:
            frappe.throw(
                frappe._(
                    f"Personal Phone Number '{phone_canonical}' is already assigned to "
                    f"{dup_phone['employee_name']} ({dup_phone['name']})."
                )
            )

    office_canonical, _ = normalize_and_validate_phone(
        doc.get("office_phone_number"),
        field_label="Office Phone Number",
        default_region="IN",
    )
    doc.office_phone_number = office_canonical

    # Validate & normalize Statutory / Identity fields (Aadhar, PAN, UAN, ESI, PF)
    for fieldname, rule in EMPLOYEE_IDENTITY_RULES.items():
        normalized = validate_identity_format(fieldname, doc.get(fieldname))
        doc.set(fieldname, normalized)
        if normalized and rule.get("unique"):
            dup = find_duplicate_employee_by_field(fieldname, normalized, doc.name)
            if dup:
                frappe.throw(
                    frappe._(
                        f"{rule['label']} '{normalized}' is already assigned to "
                        f"{dup['employee_name']} ({dup['name']})."
                    )
                )
