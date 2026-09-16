# Copyright (c) 2026, Ahmad Kamaleddin and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from company.company.api import send_automated_chat_message

class ManualChatMessage(Document):
	@frappe.whitelist()
	def get_receivers(self):
		"""
		Returns a list of receiver emails based on select_all_users or child table.
		"""
		if self.select_all_users:
			return get_all_users()
		
		return [d.receiver for d in self.receivers if d.receiver]

	@frappe.whitelist()
	def send_bulk_messages(self):
		if not self.sender:
			frappe.throw("Sender is required")
		if not self.content:
			frappe.throw("Content is required")
		
		receivers = self.get_receivers()
		if not receivers:
			frappe.throw("At least one receiver is required")

		# Add to queue
		for receiver in receivers:
			self.add_to_queue(self.sender, receiver, self.content)

		# Trigger background processing
		frappe.enqueue(
			"company.company.api.process_chat_message_queue",
			queue="long",
			at_front=True
		)

		frappe.msgprint(f"Queued {len(receivers)} messages for background processing.")
		return {"success": len(receivers)}

	def add_to_queue(self, sender, receiver, content):
		"""
		Creates a record in Chat Message Queue.
		"""
		queue_doc = frappe.new_doc("Chat Message Queue")
		queue_doc.sender = sender
		queue_doc.receiver = receiver
		queue_doc.content = content
		queue_doc.manual_chat_message = self.name
		queue_doc.status = "Pending"
		queue_doc.insert(ignore_permissions=True)
		return queue_doc

	def process_scheduled_send(self):
		"""
		Called by cron job to send scheduled message.
		"""
		from frappe.utils import now_datetime, nowdate, getdate
		from company.company.api import is_working_day

		# Log entry
		frappe.logger().info(f"[SCHEDULED SEND] Starting check...")
		
		if not self.is_scheduled:
			frappe.logger().info(f"[SCHEDULED SEND] Skipped: is_scheduled = {self.is_scheduled}")
			return

		today = getdate(nowdate())
		last_sent = getdate(self.last_sent_date) if self.last_sent_date else None
		
		frappe.logger().info(f"[SCHEDULED SEND] Today: {today}, Last sent: {last_sent}")
		
		if last_sent and last_sent >= today:
			frappe.logger().info(f"[SCHEDULED SEND] Skipped: Already sent today (last_sent={last_sent}, today={today})")
			return

		# Check working day
		if not is_working_day(today):
			frappe.logger().info(f"[SCHEDULED SEND] Skipped: Not a working day")
			return

		# Check time
		now_time = now_datetime().time()
		trigger_time_str = str(self.trigger_time)
		frappe.logger().info(f"[SCHEDULED SEND] Time check: now={str(now_time)}, trigger={trigger_time_str}")
		
		if str(now_time) < trigger_time_str:
			frappe.logger().info(f"[SCHEDULED SEND] Skipped: Time not reached yet")
			return

		# All checks passed, add to queue
		receivers = self.get_receivers()
		frappe.logger().info(f"[SCHEDULED SEND] Processing {len(receivers)} receivers")
		
		for receiver in receivers:
			self.add_to_queue(self.sender, receiver, self.content)
		
		# Trigger background processing
		if receivers:
			frappe.enqueue(
				"company.company.api.process_chat_message_queue",
				queue="long",
				at_front=True
			)
			frappe.logger().info(f"[SCHEDULED SEND] Queued {len(receivers)} messages for processing")
		
		# Update last sent date
		self.db_set("last_sent_date", today)
		frappe.db.commit()
		frappe.logger().info(f"[SCHEDULED SEND] Completed successfully")

	@frappe.whitelist()
	def test_scheduled_send(self):
		"""
		Bypasses time/date checks to test the sending logic via queue.
		"""
		receivers = self.get_receivers()
		if not receivers:
			frappe.throw("No receivers found (check 'Select All Users' or receivers table)")
		
		for receiver in receivers:
			self.add_to_queue(self.sender, receiver, self.content)
		
		frappe.enqueue(
			"company.company.api.process_chat_message_queue",
			queue="long",
			at_front=True
		)
		
		return f"Test complete. Queued {len(receivers)} messages for processing."

@frappe.whitelist()
def get_all_users():
	"""
	Returns all enabled users except Guest and Administrator.
	"""
	users = frappe.get_all("User", filters={"enabled": 1, "name": ["not in", ["Guest", "Administrator"]]}, fields=["name"])
	return [u.name for u in users]
