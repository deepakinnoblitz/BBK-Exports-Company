# Copyright (c) 2025, Company and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class AssetRequest(Document):
	def validate(self):
		if self.request_type in ["New Request", "Declaration"] and not self.asset_category:
			frappe.throw("Asset Category is mandatory for this request type.")
		
		if not self.purpose:
			frappe.throw("Purpose / Remarks is mandatory.")

	def on_update(self):
		# If workflow state is Approved and it hasn't been completed yet
		if self.workflow_state == "Approved" and self.status != "Completed":
			if self.request_type == "Declaration":
				self.process_asset_declaration()
			elif self.request_type == "Return Request":
				self.process_asset_return()
			# New Request relies on HR picking the asset and saving the request with assigned_asset

		if self.workflow_state == "Approved" and self.request_type == "New Request" and self.assigned_asset and self.status != "Completed":
			self.assign_asset_to_request()

	def process_asset_declaration(self):
		from frappe.utils import nowdate
		# Create the actual Asset automatically
		asset = frappe.get_doc({
			"doctype": "Asset",
			"asset_name": self.asset_name,
			"asset_tag": self.asset_tag,
			"category": self.asset_category,
			"current_status": "Assigned"
		})
		asset.insert(ignore_permissions=True)
		
		# Create Asset Assignment
		assignment = frappe.get_doc({
			"doctype": "Asset Assignment",
			"asset": asset.name,
			"assigned_to": self.employee,
			"assigned_on": nowdate(),
			"remarks": "Generated from Asset Declaration"
		})
		assignment.insert(ignore_permissions=True)

		self.db_set('assigned_asset', asset.name)
		self.db_set('status', 'Completed')
		self.db_set('workflow_state', 'Completed')

	def process_asset_return(self):
		from frappe.utils import nowdate
		actual_return_date = self.return_date if self.return_date else nowdate()
		if not self.asset:
			# Try to auto-find if the employee has exactly one active assignment
			active_assets = frappe.get_all("Asset Assignment", 
				filters={"assigned_to": self.employee, "returned_on": ["is", "not set"]}, 
				pluck="asset")
			
			if len(active_assets) == 1:
				self.asset = active_assets[0]
				self.db_set('asset', self.asset)
			else:
				frappe.throw("Return Request must have an Asset specified. Multiple active assets found, please specify which one is being returned.")
			
		# Find the active assignment
		assignment = frappe.db.get_value("Asset Assignment", {"asset": self.asset, "assigned_to": self.employee, "returned_on": ["is", "not set"]}, "name")
		if assignment:
			frappe.db.set_value("Asset Assignment", assignment, "returned_on", actual_return_date)

		# Mark Asset as available
		frappe.db.set_value("Asset", self.asset, "current_status", "Available")
		
		self.db_set('status', 'Completed')
		self.db_set('workflow_state', 'Completed')

	def assign_asset_to_request(self):
		from frappe.utils import nowdate
		# Create Assignment
		assignment = frappe.get_doc({
			"doctype": "Asset Assignment",
			"asset": self.assigned_asset,
			"assigned_to": self.employee,
			"assigned_on": nowdate(),
			"remarks": "Generated from Asset Request"
		})
		assignment.insert(ignore_permissions=True)
		
		# Mark Asset as assigned
		frappe.db.set_value("Asset", self.assigned_asset, "current_status", "Assigned")

		self.db_set('status', 'Completed')
		self.db_set('workflow_state', 'Completed')

