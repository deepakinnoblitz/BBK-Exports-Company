import json
import frappe
from frappe import _
from frappe.model.document import Document


class BusTravelRoute(Document):
	def validate(self):
		self.validate_unique_fields()

	def validate_unique_fields(self):
		bus_no = (self.bus_number or "").strip()
		contact = (self.driver_contact or "").strip()

		is_existing = not self.is_new() and bool(frappe.db.exists("Bus Travel Route", self.name))

		if bus_no:
			self.bus_number = bus_no
			if is_existing:
				existing = frappe.db.sql(
					"""
					SELECT name, route_name
					FROM `tabBus Travel Route`
					WHERE LOWER(TRIM(bus_number)) = LOWER(%s)
					AND name != %s
					LIMIT 1
					""",
					(bus_no, self.name),
					as_dict=True,
				)
			else:
				existing = frappe.db.sql(
					"""
					SELECT name, route_name
					FROM `tabBus Travel Route`
					WHERE LOWER(TRIM(bus_number)) = LOWER(%s)
					LIMIT 1
					""",
					(bus_no,),
					as_dict=True,
				)

			if existing:
				existing_title = existing[0].get("route_name") or existing[0].get("name")
				frappe.throw(
					_("Bus / Vehicle Number '{0}' already exists for Route '{1}'. Vehicle number must be unique.").format(
						bus_no, existing_title
					)
				)
		else:
			self.bus_number = ""

		if contact:
			self.driver_contact = contact
			if is_existing:
				existing = frappe.db.sql(
					"""
					SELECT name, route_name
					FROM `tabBus Travel Route`
					WHERE LOWER(TRIM(driver_contact)) = LOWER(%s)
					AND name != %s
					LIMIT 1
					""",
					(contact, self.name),
					as_dict=True,
				)
			else:
				existing = frappe.db.sql(
					"""
					SELECT name, route_name
					FROM `tabBus Travel Route`
					WHERE LOWER(TRIM(driver_contact)) = LOWER(%s)
					LIMIT 1
					""",
					(contact,),
					as_dict=True,
				)

			if existing:
				existing_title = existing[0].get("route_name") or existing[0].get("name")
				frappe.throw(
					_("Driver Contact '{0}' already exists for Route '{1}'. Driver contact must be unique.").format(
						contact, existing_title
					)
				)
		else:
			self.driver_contact = ""



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
