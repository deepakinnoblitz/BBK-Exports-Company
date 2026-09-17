# Copyright (c) 2026, Innoblitz and contributors
# For license information, please see license.txt

import requests
from datetime import datetime
import frappe
from frappe.utils import get_datetime, format_datetime


class SmartOfficeClient:
    """
    API client for communicating with SmartOffice WebAPI (v1.0.1).
    """

    def __init__(self, base_url=None, api_key=None):
        if not base_url or not api_key:
            settings = frappe.get_single("Biometric Settings")
            self.base_url = (base_url or settings.api_base_url or "").strip().rstrip("/")
            self.api_key = api_key or settings.get_password("api_key") or ""
        else:
            self.base_url = base_url.strip().rstrip("/")
            self.api_key = api_key

        if not self.base_url:
            frappe.throw("SmartOffice API Base URL is not configured in Biometric Settings.")
        if not self.api_key:
            frappe.throw("SmartOffice API Key is not configured in Biometric Settings.")

    def _get_url(self, endpoint: str) -> str:
        clean_endpoint = endpoint.lstrip("/")
        # If base_url already contains 'api/v2/WebAPI', append only the method
        if "api/v2/WebAPI" in self.base_url:
            if clean_endpoint.startswith("api/v2/WebAPI/"):
                clean_endpoint = clean_endpoint.replace("api/v2/WebAPI/", "")
            return f"{self.base_url}/{clean_endpoint}"
        return f"{self.base_url}/{clean_endpoint}"

    def get_device_logs(self, from_date, to_date):
        """
        Fetch biometric logs from SmartOffice between FromDate and ToDate.
        Format: YYYY-MM-DD HH:mm:ss or YYYY-MM-DD
        Endpoint: GET /api/v2/WebAPI/GetDeviceLogs
        """
        from_str = self._format_date(from_date)
        to_str = self._format_date(to_date)

        url = self._get_url("api/v2/WebAPI/GetDeviceLogs")
        params = {
            "APIKey": self.api_key,
            "FromDate": from_str,
            "ToDate": to_str,
        }

        try:
            response = requests.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            frappe.log_error(f"SmartOffice GetDeviceLogs Request Failed: {e}", "SmartOffice Integration")
            raise ConnectionError(f"Failed to connect to SmartOffice server at {url}: {str(e)}")

        if not response.ok:
            error_text = response.text
            raise Exception(f"SmartOffice API Error ({response.status_code}): {error_text}")

        try:
            data = response.json()
        except Exception:
            raise Exception(f"SmartOffice returned non-JSON response: {response.text[:200]}")

        # Check for error dict: {"status": false, "message": "Invalid API Key."}
        if isinstance(data, dict):
            if data.get("status") is False or data.get("status") == "failure":
                msg = data.get("message") or "SmartOffice API returned error status"
                raise Exception(f"SmartOffice Error: {msg}")
            # If records array is wrapped
            if "records" in data and isinstance(data["records"], list):
                return self._normalize_logs(data["records"])
            return []

        if isinstance(data, list):
            return self._normalize_logs(data)

        return []

    def _normalize_logs(self, raw_logs):
        """
        Normalize raw log records to a standardized format:
        - employee_code: stripped string
        - log_datetime: parsed datetime object or standard YYYY-MM-DD HH:mm:ss
        - punch_direction: uppercase IN/OUT or AUTO
        - serial_number: device serial
        """
        normalized = []
        for item in raw_logs:
            if not isinstance(item, dict):
                continue

            raw_code = item.get("EmployeeCode") or item.get("employee_code") or ""
            employee_code = str(raw_code).strip()
            if not employee_code:
                continue

            raw_date = item.get("LogDate") or item.get("log_date") or ""
            if not raw_date:
                continue

            try:
                log_dt = get_datetime(str(raw_date).strip())
            except Exception:
                continue

            raw_direction = str(item.get("PunchDirection") or item.get("punch_direction") or "AUTO").strip().upper()
            if raw_direction in ["IN", "OUT"]:
                punch_direction = raw_direction
            else:
                punch_direction = "AUTO"

            serial_number = str(item.get("SerialNumber") or item.get("serial_number") or "").strip()

            temp = item.get("Temperature")
            try:
                temperature = float(temp) if temp is not None else None
            except (ValueError, TypeError):
                temperature = None

            temp_state = str(item.get("TemperatureState") or "").strip() or None

            normalized.append({
                "employee_code": employee_code,
                "log_datetime": log_dt,
                "punch_direction": punch_direction,
                "serial_number": serial_number,
                "temperature": temperature,
                "temperature_state": temp_state,
                "raw_data": item
            })

        return normalized

    def _format_date(self, dt_val) -> str:
        if isinstance(dt_val, str):
            return dt_val.strip()
        if isinstance(dt_val, datetime):
            return format_datetime(dt_val, "yyyy-MM-dd HH:mm:ss")
        return str(dt_val)
