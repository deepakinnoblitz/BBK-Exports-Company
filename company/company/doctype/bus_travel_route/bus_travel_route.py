import json
import frappe
from frappe.model.document import Document


class BusTravelRoute(Document):
	pass


@frappe.whitelist()
def save_bus_travel_route(
	name=None,
	route_name=None,
	bus_number=None,
	driver_contact=None,
	status="Active",
	description=None,
	points=None,
):
	if isinstance(points, str):
		try:
			points = json.loads(points)
		except Exception:
			points = []

	if name and frappe.db.exists("Bus Travel Route", name):
		doc = frappe.get_doc("Bus Travel Route", name)
	else:
		doc = frappe.new_doc("Bus Travel Route")

	if route_name:
		doc.route_name = route_name.strip()
	doc.bus_number = (bus_number or "").strip() or None
	doc.driver_contact = (driver_contact or "").strip() or None
	doc.status = status or "Active"
	doc.description = (description or "").strip() or None

	doc.set("points", [])
	if points and isinstance(points, list):
		for p in points:
			if isinstance(p, dict) and p.get("point_name"):
				doc.append(
					"points",
					{
						"point_name": p.get("point_name").strip(),
						"pickup_time": p.get("pickup_time") or None,
						"drop_time": p.get("drop_time") or None,
					},
				)

	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return doc.as_dict()
