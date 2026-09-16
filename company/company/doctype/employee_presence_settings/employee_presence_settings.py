import frappe
from frappe.model.document import Document

class EmployeePresenceSettings(Document):
    def validate(self):
        # Ensure thresholds are logical
        if self.enable_auto_status:
            if self.offline_threshold <= self.break_threshold:
                frappe.throw("Auto-Offline threshold must be greater than Break threshold.")
            if self.break_threshold <= self.away_threshold:
                frappe.throw("Break threshold must be greater than Away threshold.")
            if self.away_threshold <= self.idle_threshold:
                frappe.throw("Away threshold must be greater than Idle threshold.")

    def on_update(self):
        # Broadcast to all users via socket whenever saved (even from Desk)
        frappe.publish_realtime("presence_settings_update", {
            "enable_auto_status": self.enable_auto_status,
            "idle_threshold": self.idle_threshold,
            "away_threshold": self.away_threshold,
            "break_threshold": self.break_threshold,
            "offline_threshold": self.offline_threshold,
            "enable_auto_resume_break": self.enable_auto_resume_break,
            "event_mousemove": self.event_mousemove,
            "event_keydown": self.event_keydown,
            "event_scroll": self.event_scroll,
            "event_click": self.event_click,
            "event_touchstart": self.event_touchstart,
            "enable_location_tracking": self.enable_location_tracking,
            "track_on_login": self.track_on_login,
            "track_on_logout": self.track_on_logout,
            "track_on_status_change": self.track_on_status_change,
            "tracking_interval_minutes": self.tracking_interval_minutes,
            "minimum_gps_accuracy": self.minimum_gps_accuracy,
            "location_tracking_target": getattr(self, "location_tracking_target", "All Employees"),
            "tracked_employees": frappe.parse_json(getattr(self, "tracked_employees", None) or "[]")
        })

@frappe.whitelist()
def get_presence_settings():
    settings = frappe.get_single("Employee Presence Settings")
    tracked = getattr(settings, "tracked_employees", None) or "[]"

    # Ensure location triggers default to 1 (True) if missing or 0 in DB
    t_login = getattr(settings, "track_on_login", 1)
    t_logout = getattr(settings, "track_on_logout", 1)
    t_status = getattr(settings, "track_on_status_change", 1)

    if not t_login:
        t_login = 1
    if not t_logout:
        t_logout = 1
    if not t_status:
        t_status = 1

    return {
        "enable_auto_status": settings.enable_auto_status,
        "idle_threshold": settings.idle_threshold,
        "away_threshold": settings.away_threshold,
        "break_threshold": settings.break_threshold,
        "offline_threshold": settings.offline_threshold,
        "enable_auto_resume_break": settings.enable_auto_resume_break,
        "event_mousemove": settings.event_mousemove,
        "event_keydown": settings.event_keydown,
        "event_scroll": settings.event_scroll,
        "event_click": settings.event_click,
        "event_touchstart": settings.event_touchstart,
        "enable_location_tracking": settings.enable_location_tracking,
        "track_on_login": t_login,
        "track_on_logout": t_logout,
        "track_on_status_change": t_status,
        "tracking_interval_minutes": settings.tracking_interval_minutes,
        "minimum_gps_accuracy": settings.minimum_gps_accuracy,
        "location_tracking_target": getattr(settings, "location_tracking_target", "All Employees") or "All Employees",
        "tracked_employees": frappe.parse_json(tracked) if isinstance(tracked, str) else (tracked or [])
    }

@frappe.whitelist()
def set_presence_settings(enable_auto_status, idle_threshold=60, away_threshold=300, break_threshold=900, enable_auto_resume_break=1, **kwargs):
    # Only HR or System Manager can change settings
    roles = frappe.get_roles(frappe.session.user)
    if "HR" not in roles and "System Manager" not in roles and "Administrator" not in roles:
        frappe.throw("Not permitted to change presence settings", frappe.PermissionError)
        
    settings = frappe.get_single("Employee Presence Settings")
    settings.enable_auto_status = frappe.parse_json(enable_auto_status)
    settings.idle_threshold = frappe.parse_json(idle_threshold)
    settings.away_threshold = frappe.parse_json(away_threshold)
    settings.break_threshold = frappe.parse_json(break_threshold)
    if "offline_threshold" in kwargs:
        settings.offline_threshold = frappe.parse_json(kwargs["offline_threshold"])
    settings.enable_auto_resume_break = frappe.parse_json(enable_auto_resume_break)
    
    # Update checkboxes
    for field in [
        "event_mousemove", "event_keydown", "event_scroll", "event_click", "event_touchstart",
        "enable_location_tracking", "track_on_login", "track_on_logout", "track_on_status_change"
    ]:
        if field in kwargs:
            setattr(settings, field, frappe.parse_json(kwargs[field]))
        elif field in ["track_on_login", "track_on_logout", "track_on_status_change"]:
            setattr(settings, field, 1)
        else:
            setattr(settings, field, 0)

    if "tracking_interval_minutes" in kwargs:
        settings.tracking_interval_minutes = frappe.parse_json(kwargs["tracking_interval_minutes"])
    if "minimum_gps_accuracy" in kwargs:
        settings.minimum_gps_accuracy = frappe.parse_json(kwargs["minimum_gps_accuracy"])
    if "location_tracking_target" in kwargs:
        val = kwargs["location_tracking_target"]
        if isinstance(val, str) and ((val.startswith('"') and val.endswith('"')) or (val.startswith('[') and val.endswith(']'))):
            val = frappe.parse_json(val)
        settings.location_tracking_target = str(val)
    if "tracked_employees" in kwargs:
        tracked_val = kwargs["tracked_employees"]
        if isinstance(tracked_val, (list, tuple)):
            settings.tracked_employees = frappe.as_json(tracked_val)
        elif isinstance(tracked_val, str):
            try:
                parsed = frappe.parse_json(tracked_val)
                settings.tracked_employees = frappe.as_json(parsed) if isinstance(parsed, (list, tuple)) else tracked_val
            except Exception:
                settings.tracked_employees = tracked_val
        else:
            settings.tracked_employees = str(tracked_val)
            
    settings.save()
    
    return {"status": "success"}
