# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import re
import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, validate_email_address, get_url
import datetime


class TaskManager(Document):

	def validate(self):
		self.validate_due_date()
		self.validate_closing_fields()

	def send_chat_notification(self, sender_email, receiver_email, content):
		"""Send a chat message via clefincode_chat. Create channel if it doesn't exist."""
		try:
			from clefincode_chat.api.api_1_2_1.api import send, create_channel, get_profile_id
			
			# Check if direct room exists
			room_name = frappe.db.sql("""
				SELECT c.name
				FROM `tabClefinCode Chat Channel` c
				JOIN `tabClefinCode Chat Channel User` u1 ON u1.parent = c.name
				JOIN `tabClefinCode Chat Channel User` u2 ON u2.parent = c.name
				WHERE c.type = 'Direct'
				AND c.is_parent = 1
				AND u1.user = %s
				AND u2.user = %s
			""", (sender_email, receiver_email), pluck=True)

			if room_name:
				room_name = room_name[0]
			else:
				# Create channel
				users = [
					{"email": sender_email, "platform": "Chat"},
					{"email": receiver_email, "platform": "Chat"}
				]
				sender_name = frappe.db.get_value("User", sender_email, "full_name") or sender_email
				res = create_channel(
					channel_name="", # Direct chats usually have empty channel_name
					users=json.dumps(users),
					type="Direct",
					last_message=content,
					creator_email=sender_email,
					creator=sender_name
				)
				if res and res.get("results"):
					room_name = res["results"][0]["room"]

			if room_name:
				sender_name = frappe.db.get_value("User", sender_email, "full_name") or sender_email
				send(
					content=content,
					user=sender_name,
					room=room_name,
					email=sender_email
				)
		except Exception as e:
			frappe.log_error(title="Task Manager Chat Notification Error", message=frappe.get_traceback())

	def before_save(self):
		# Auto-set closed_by and closed_on when status changes to Completed
		if self.status == "Completed" and not self.closed_by:
			self.closed_by = frappe.session.user
			self.closed_on = now_datetime()

		# If status changed away from Completed (Reopened), clear closing fields
		if self.status == "Reopened":
			self.closed_by = None
			self.closed_on = None

			self.append("history", {
				"event": "Reopened",
				"done_by": frappe.session.user,
				"done_on": now_datetime(),
				"remarks": _("Task reopened for further work.")
			})

	def validate_due_date(self):
		if self.due_date:
			from frappe.utils import getdate, today
			if getdate(self.due_date) < getdate(today()):
				# Just warn, don't block (task might be backlogged)
				frappe.msgprint(
					_("Due Date {0} is in the past.").format(self.due_date),
					indicator="orange",
					alert=True,
				)

	def validate_closing_fields(self):
		"""Validate required fields before marking as Completed."""
		if self.status == "Completed":
			if not self.assignees:
				frappe.throw(_("Please add at least one <b>Assignee</b> before saving."))



	def get_task_managers_emails(self):
		"""Get emails of all active users with the 'Task Manager' role."""
		manager_users = frappe.get_all(
			"Has Role",
			filters={"role": "Task Manager", "parenttype": "User"},
			pluck="parent"
		)
		if not manager_users:
			return []

		emails = [
			frappe.db.get_value("User", u, "email") or u
			for u in manager_users
		]
		return [e for e in emails if e]


	def after_insert(self):
		"""Send notification to all assignees when task is created."""
		frappe.enqueue(
			"company.company.doctype.task_manager.task_manager.send_after_insert_notifications",
			doc_name=self.name,
			action_user=frappe.session.user,
			enqueue_after_commit=True
		)

		frappe.publish_realtime(event="task_manager_updated", message={"name": self.name, "event": "insert"})

	def on_update(self):
		"""Send notifications based on status changes."""
		frappe.publish_realtime(event="task_manager_updated", message={"name": self.name, "event": "update"})
		doc_before_save = self.get_doc_before_save()
		if not doc_before_save:
			return

		old_status = doc_before_save.get("status")
		new_status = self.status

		if old_status != new_status:
			frappe.enqueue(
				"company.company.doctype.task_manager.task_manager.send_on_update_notifications",
				doc_name=self.name,
				action_user=frappe.session.user,
				old_status=old_status,
				new_status=new_status,
				enqueue_after_commit=True
			)

	def on_trash(self):
		frappe.publish_realtime(event="task_manager_updated", message={"name": self.name, "event": "trash"})


	def send_task_notification(self, subject, message, notify_assignees=True, notify_managers=True):
		"""Create in-app Notification Log entries."""
		target_users = set()

		# Collect assignee user IDs
		if notify_assignees and self.assignees:
			for row in self.assignees:
				u = row.user or frappe.db.get_value("Employee", row.employee, "user")
				if u: target_users.add(u)

		# Collect Task Manager role user IDs
		if notify_managers:
			manager_users = frappe.get_all("Has Role", filters={"role": "Task Manager", "parenttype": "User"}, pluck="parent")
			target_users.update(manager_users)

		for user in target_users:
			try:
				frappe.get_doc({
					"doctype": "Notification Log",
					"subject": subject,
					"email_content": message,
					"for_user": user,
					"type": "Alert",
					"document_type": "Task Manager",
					"document_name": self.name,
				}).insert(ignore_permissions=True)
			except Exception:
				pass



	def notify_assignees(self, event):
		"""Send an email notification to ALL assignees."""
		from company.company.api import is_hrms_notification_enabled
		if not is_hrms_notification_enabled("task_notification"):
			return

		if not self.assignees:
			return

		subject_map = {
			"assigned": _("New Task Assigned: {0}").format(self.title),
			"completed": _("Task Completed: {0}").format(self.title),
			"reopened": _("Task Reopened: {0}").format(self.title),
		}

		content_map = {
			"assigned": {
				"header": "New Task Assigned",
				"header_color": "#0891b2",
				"body": "You have been assigned a new task. Please review it and get started.",
				"tag": "Assigned",
			},
			"completed": {
				"header": "Task Completed",
				"header_color": "#16a34a",
				"body": "Great work! The task has been marked as Completed.",
				"tag": "Completed",
			},
			"reopened": {
				"header": "Task Reopened",
				"header_color": "#ea580c",
				"body": "The task has been Reopened. Please review and take action.",
				"tag": "Reopened",
			},
		}

		ctx = content_map.get(event)
		if not ctx:
			return

		for row in self.assignees:
			user_id = row.user
			if not user_id:
				user_id = frappe.db.get_value("Employee", row.employee, "user")
			if not user_id:
				continue

			# Get email preferentially from Employee, then User
			user_email = frappe.db.get_value("Employee", row.employee, "email") or (user_id if "@" in user_id else frappe.db.get_value("User", user_id, "email"))
			if not user_email:
				continue

			greeting = "Hello, {0}".format(row.employee_name or "Team Member")
			message = get_task_email_html(
				task_name=self.name,
				task_title=self.title,
				priority=self.priority,
				due_date=self.due_date,
				project=self.project,
				department=self.department,
				greeting=greeting,
				body=ctx["body"],
				header=ctx["header"],
				header_color=ctx["header_color"],
				tag=ctx["tag"],
			)

			frappe.sendmail(
				recipients=[user_email],
				subject=subject_map.get(event, "Task Update"),
				message=message,
				delayed=False,
			)

	def notify_hr(self, event):
		"""Notify the Task Creator about task updates."""
		from company.company.api import is_hrms_notification_enabled
		if not is_hrms_notification_enabled("task_notification"):
			return

		if not self.owner:
			return
		
		# Only notify if owner is not the current user
		if self.owner == frappe.session.user:
			return
		
		emails = [self.owner]

		assignee_names = ", ".join([r.employee_name or r.employee for r in self.assignees])

		if event == "completed":
			subject = _("Task Completed: {0}").format(self.title)
			ctx = {
				"header": "Task Completed",
				"header_color": "#16a34a",
				"body": "The task has been marked as <b>Completed</b> by {0}.".format(assignee_names),
				"tag": "Completed",
			}
		elif event == "in_progress":
			subject = _("Task In Progress: {0}").format(self.title)
			ctx = {
				"header": "Task In Progress",
				"header_color": "#0891b2",
				"body": "The task is now <b>In Progress</b> by {0}.".format(assignee_names),
				"tag": "In Progress",
			}
		else:
			return

		message = get_task_email_html(
			task_name=self.name,
			task_title=self.title,
			priority=self.priority,
			due_date=self.due_date,
			project=self.project,
			department=self.department,
			greeting="Hello, Task Manager",
			body=ctx["body"],
			header=ctx["header"],
			header_color=ctx["header_color"],
			tag=ctx["tag"],
		)

		frappe.sendmail(
			recipients=emails,
			subject=subject,
			message=message,
			delayed=False,
		)


def get_task_email_html(task_name, task_title, priority, due_date, project, department,
					   greeting, body, header, header_color, tag):
	"""Generate a premium HTML email template for task notifications."""
	base_url = frappe.utils.get_url()
	task_url = "{0}/task-manager/".format(base_url)
	logo_url = "https://erp.innoblitz.in/assets/company/crm/assets/logo/Innoblitz_logo.png"

	priority_colors = {
		"High": "#dc2626",
		"Medium": "#d97706",
		"Low": "#16a34a",
	}
	priority_color = priority_colors.get(priority or "Medium", "#d97706")

	# Format date
	formatted_due_date = "N/A"
	if due_date:
		try:
			from frappe.utils import format_date
			formatted_due_date = format_date(due_date, "dd-mm-yyyy")
		except:
			try:
				formatted_due_date = __import__('datetime').datetime.strptime(str(due_date), '%Y-%m-%d').strftime('%d-%m-%Y')
			except:
				formatted_due_date = str(due_date)

	return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<title>{header}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet" type="text/css" />
<style type="text/css">
	@media only screen and (max-width: 600px) {{
		.main-table {{ width: 100% !important; }}
		.responsive-td {{ display: block !important; width: 100% !important; box-sizing: border-box !important; }}
		.label-td {{ padding-bottom: 0 !important; padding-top: 10px !important; }}
		.value-td {{ padding-top: 2px !important; padding-bottom: 10px !important; }}
		.mobile-padding {{ padding-left: 20px !important; padding-right: 20px !important; }}
	}}
</style>
</head>
<body style="margin: 0; padding: 0; background-color: #f6f9fc; font-family: 'Poppins', Arial, sans-serif;">
	<table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f6f9fc;">
		<tr>
			<td align="center" style="padding: 40px 0;">
				<table border="0" cellpadding="0" cellspacing="0" width="600" style="border-collapse: collapse; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); max-width: 600px;" class="main-table">
					<!-- Logo Section -->
					<tr>
						<td align="center" style="padding: 40px 40px 30px 40px;">
							<img src="{logo_url}" alt="Logo" width="220" style="display: block; max-width: 100%; height: auto;" />
						</td>
					</tr>
					
					<!-- Header Section -->
					<tr>
						<td align="center" style="padding: 0 40px 25px 40px;">
							<h1 style="color: {header_color}; font-size: 28px; margin: 0; font-weight: 700; line-height: 1.2;">{header}</h1>
						</td>
					</tr>

					<!-- Message Section -->
					<tr>
						<td class="mobile-padding" style="padding: 20px 40px 30px 40px; color: #4a5568; font-size: 16px; line-height: 26px;">
							<p style="margin: 0 0 15px 0; color: #2d3748;"><b>{greeting}</b></p>
							<p style="margin: 0;">{body}</p>
						</td>
					</tr>

					<!-- Task Details Card -->
					<tr>
						<td class="mobile-padding" style="padding: 0 40px 40px 40px;">
							<table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; border-collapse: separate;">
								<tr>
									<td style="padding: 25px;">
										<h2 style="font-size: 18px; margin: 0 0 20px 0; color: #1a202c; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; font-weight: 700;">Task Details</h2>
										
										<table border="0" cellpadding="0" cellspacing="0" width="100%">
											<!-- Title -->
											<tr>
												<td class="responsive-td label-td" width="130" valign="top" style="padding: 10px 0; font-weight: 700; color: #718096; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em;">Task Title:</td>
												<td class="responsive-td value-td" valign="top" style="padding: 10px 0; color: #2d3748; font-size: 15px; font-weight: 600; word-break: break-word;">{task_title}</td>
											</tr>
											<!-- Priority -->
											<tr>
												<td class="responsive-td label-td" width="130" valign="top" style="padding: 10px 0; font-weight: 700; color: #718096; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em;">Priority:</td>
												<td class="responsive-td value-td" valign="top" style="padding: 10px 0; color: {priority_color}; font-size: 15px; font-weight: 700;">{priority}</td>
											</tr>
											<!-- Due Date -->
											<tr>
												<td class="responsive-td label-td" width="130" valign="top" style="padding: 10px 0; font-weight: 700; color: #718096; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em;">Due Date:</td>
												<td class="responsive-td value-td" valign="top" style="padding: 10px 0; color: #2d3748; font-size: 15px; font-weight: 600;">{formatted_due_date}</td>
											</tr>
											<!-- Project -->
											<tr>
												<td class="responsive-td label-td" width="130" valign="top" style="padding: 10px 0; font-weight: 700; color: #718096; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em;">Project:</td>
												<td class="responsive-td value-td" valign="top" style="padding: 10px 0; color: #2d3748; font-size: 15px; font-weight: 600; word-break: break-word;">{project or "N/A"}</td>
											</tr>
											<!-- Department -->
											<tr>
												<td class="responsive-td label-td" width="130" valign="top" style="padding: 10px 0; font-weight: 700; color: #718096; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em;">Department:</td>
												<td class="responsive-td value-td" valign="top" style="padding: 10px 0; color: #2d3748; font-size: 15px; font-weight: 600; word-break: break-word;">{department or "N/A"}</td>
											</tr>
										</table>
									</td>
								</tr>
							</table>
						</td>
					</tr>

					<!-- CTA Button -->
					<tr>
						<td align="center" style="padding: 0 40px 50px 40px;">
							<table border="0" cellpadding="0" cellspacing="0" width="100%">
								<tr>
									<td align="center" bgcolor="{header_color}" style="border-radius: 8px;">
										<a href="{task_url}" target="_blank" style="padding: 18px 30px; color: #ffffff; text-decoration: none; font-size: 16px; font-weight: 700; display: block; letter-spacing: 0.025em;">Open Task Details</a>
									</td>
								</tr>
							</table>
						</td>
					</tr>

					<!-- Footer -->
					<tr>
						<td align="center" style="padding: 30px 40px; background-color: #f7fafc; border-top: 1px solid #edf2f7; color: #a0aec0; font-size: 12px; line-height: 1.5;">
							<p style="margin: 0;">This is an automated notification from Task Manager.<br/>Please do not reply to this email.</p>
						</td>
					</tr>
				</table>
			</td>
		</tr>
	</table>
</body>
</html>"""

def hhmm_to_float(hhmm):
	if not hhmm:
		return 0.0
	try:
		parts = hhmm.split(':')
		if len(parts) != 2:
			return 0.0
		h, m = map(int, parts)
		return h + (m / 60.0)
	except (ValueError, TypeError):
		return 0.0

@frappe.whitelist()
def close_task(task_name, hours_spent, remarks, attachment=None):
	"""API endpoint called from the frontend Close Task dialog."""
	doc = frappe.get_doc("Task Manager", task_name)

	if doc.status == "Completed":
		frappe.throw(_("This task is already Completed."))

	# Validate input
	if not hours_spent:
		frappe.throw(_("Please enter <b>Hours Spent</b> before closing the task."))
	if not remarks:
		frappe.throw(_("Please add <b>Remarks</b> before closing the task."))
	
	# Validate HH:MM format (HH: 1-5 digits, MM: 00-59)
	if not re.match(r"^([0-9]{1,5}):([0-5][0-9])$", hours_spent):
		frappe.throw(_("<b>Hours Spent</b> must be in <b>HH:MM</b> format (MM: 00-59). Example: 02:30"))
		
	if doc.attachment_required and not attachment:
		frappe.throw(_("This task requires an <b>Attachment</b> before it can be closed."))

	doc.status = "Completed"
	doc.append("history", {
		"event": "Closed",
		"done_by": frappe.session.user,
		"done_on": now_datetime(),
		"hours_spent": hours_spent,
		"remarks": remarks,
		"closing_attachment": attachment
	})

	doc.save()
	# Send Chat Notification to the Task Creator (Owner)
	content = f"<b>Task Closed:</b> {doc.title}<br><b>Hours Spent:</b> {hours_spent}<br><b>Remarks:</b> {remarks}"
	
	frappe.enqueue(
		"company.company.doctype.task_manager.task_manager.send_manual_chat_notification",
		doc_name=doc.name,
		action_user=frappe.session.user,
		content=content,
		enqueue_after_commit=True
	)

	return {"message": "Task closed successfully", "status": doc.status}


@frappe.whitelist()
def reopen_task(task_name, remarks):
	"""API endpoint called from the frontend to Reopen a completed task."""
	doc = frappe.get_doc("Task Manager", task_name)

	if doc.status != "Completed":
		frappe.throw(_("Only Completed tasks can be Reopened."))

	# Check if the caller is Task Manager, HR, or System Manager
	allowed_roles = ["Task Manager", "HR", "System Manager", "Administrator"]
	user_roles = frappe.get_roles(frappe.session.user)
	if not any(r in user_roles for r in allowed_roles):
		frappe.throw(_("Access denied. Only Task Managers can Reopen a task."))

	if not remarks:
		frappe.throw(_("Please enter <b>Remarks</b> before reopening the task."))

	doc.status = "Reopened"
	doc.append("history", {
		"event": "Reopened",
		"done_by": frappe.session.user,
		"done_on": now_datetime(),
		"remarks": remarks
	})

	doc.save()
	return {"message": "Task reopened successfully", "status": doc.status}



@frappe.whitelist()
def put_on_hold_task(task_name, remarks):
	"""API endpoint to move task to On Hold status."""
	doc = frappe.get_doc("Task Manager", task_name)

	if doc.status == "Completed":
		frappe.throw(_("Cannot put a Completed task on hold."))

	if doc.status == "On Hold":
		frappe.throw(_("This task is already On Hold."))

	if not remarks:
		frappe.throw(_("Please enter <b>Remarks</b> before putting the task on hold."))

	doc.status = "On Hold"
	doc.append("history", {
		"event": "On Hold",
		"done_by": frappe.session.user,
		"done_on": now_datetime(),
		"remarks": remarks
	})

	# Send Chat Notification to the Task Creator (Owner)
	content = f"<b>Task On Hold:</b> {doc.title}<br><b>Remarks:</b> {remarks}"
	
	frappe.enqueue(
		"company.company.doctype.task_manager.task_manager.send_manual_chat_notification",
		doc_name=doc.name,
		action_user=frappe.session.user,
		content=content,
		enqueue_after_commit=True
	)

	doc.save()
	return {"message": "Task put on hold successfully", "status": doc.status}

@frappe.whitelist()
def resume_task(task_name, remarks=None):
	"""API endpoint to move task from On Hold to In Progress status."""
	doc = frappe.get_doc("Task Manager", task_name)

	if doc.status != "On Hold":
		frappe.throw(_("Only tasks that are On Hold can be resumed."))

	doc.status = "In Progress"
	doc.append("history", {
		"event": "Resumed",
		"done_by": frappe.session.user,
		"done_on": now_datetime(),
		"remarks": remarks or _("Task resumed.")
	})

	# Send Chat Notification to the Task Creator (Owner)
	content = f"<b>Task Resumed:</b> {doc.title}"
	if remarks:
		content += f"<br><b>Remarks:</b> {remarks}"
	
	frappe.enqueue(
		"company.company.doctype.task_manager.task_manager.send_manual_chat_notification",
		doc_name=doc.name,
		action_user=frappe.session.user,
		content=content,
		enqueue_after_commit=True
	)

	doc.save()
	return {"message": "Task resumed successfully", "status": doc.status}


@frappe.whitelist()
def accept_task(task_name):
	"""API endpoint to move task to In Progress status."""
	doc = frappe.get_doc("Task Manager", task_name)

	if doc.status == "In Progress":
		frappe.throw(_("This task is already In Progress."))

	doc.status = "In Progress"
	doc.append("history", {
		"event": "Accepted",
		"done_by": frappe.session.user,
		"done_on": now_datetime(),
		"remarks": _("Task accepted and work started.")
	})

	# Send Chat Notification to the Task Creator (Owner) before save triggers on_update
	content = f"<b>Task Accepted:</b> {doc.title}<br>Work has started."
	
	frappe.enqueue(
		"company.company.doctype.task_manager.task_manager.send_manual_chat_notification",
		doc_name=doc.name,
		action_user=frappe.session.user,
		content=content,
		enqueue_after_commit=True
	)

	doc.save()

	return {"message": "Task accepted successfully", "status": doc.status}


@frappe.whitelist()
def get_my_tasks():
	"""Return tasks where the current user is one of the assignees."""
	# Get parent names where user is an assignee
	task_names = frappe.get_all(
		"Task Manager Assignee",
		filters={"user": frappe.session.user},
		pluck="parent"
	)
	
	if not task_names:
		return []

	return frappe.get_all(
		"Task Manager",
		filters={"name": ["in", task_names]},
		fields=["name", "title", "status", "priority", "due_date", "project"],
		order_by="due_date asc",
	)


@frappe.whitelist()
def get_all_tasks(status=None, assignee=None):
	"""Return all tasks. HR only."""
	allowed_roles = ["Task Manager", "System Manager"]
	user_roles = frappe.get_roles(frappe.session.user)
	if not any(r in user_roles for r in allowed_roles):
		frappe.throw(_("Access denied. Only Task Managers can view all tasks."))

	filters = {}
	if status:
		filters["status"] = status
	if assignee:
		# Filter by user in the child table
		task_names = frappe.get_all(
			"Task Manager Assignee",
			filters={"user": assignee},
			pluck="parent"
		)
		if not task_names:
			return []
		filters["name"] = ["in", task_names]

	return frappe.get_all(
		"Task Manager",
		filters=filters,
		fields=[
			"name", "title", "status", "priority", "due_date",
			"project"
		],
		order_by="creation desc",
	)


@frappe.whitelist()
def get_employees_from_department(department):
	"""Return all active employees belonging to the specified department."""
	if not department:
		return []

	return frappe.get_all(
		"Employee",
		filters={
			"department": department,
			"status": "Active"
		},
		fields=["name", "employee_name", "user", "department"],
		ignore_permissions=True
	)


@frappe.whitelist()
def get_all_active_employees():
	"""Return all active employees, bypassing user permissions.
	Used by the Task Manager assignee dropdown so Team Leads can assign
	tasks to any employee, not just those visible under their own permissions.
	"""
	return frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "user"],
		order_by="employee_name asc",
		ignore_permissions=True
	)


@frappe.whitelist()
def get_assignees(task_names):
	"""API endpoint to fetch assignees for a list of tasks."""
	if isinstance(task_names, str):
		import json
		task_names = json.loads(task_names)
	
	if not task_names:
		return []

	return frappe.db.sql("""
		SELECT 
			tma.name, tma.parent, tma.employee, tma.employee_name, tma.user,
			emp.profile_picture as profile_pic
		FROM `tabTask Manager Assignee` tma
		LEFT JOIN `tabEmployee` emp ON tma.employee = emp.name
		WHERE tma.parent IN %s
	""", (task_names,), as_dict=1)

@frappe.whitelist()
def get_task_histories(task_names):
	"""API endpoint to fetch history entries for a list of tasks."""
	if isinstance(task_names, str):
		import json
		task_names = json.loads(task_names)
	
	if not task_names:
		return []

	return frappe.get_all(
		"Task Manager History",
		filters={"parent": ["in", task_names]},
		fields=["name", "parent", "event", "done_by", "done_on", "hours_spent", "remarks"],
		order_by="done_on asc"
	)


def send_after_insert_notifications(doc_name, action_user):
	"""Background task for after_insert notifications"""
	if not doc_name or not action_user:
		return

	frappe.session.user = action_user
	try:
		doc = frappe.get_doc("Task Manager", doc_name)
		# Call existing notification functions
		doc.notify_assignees("assigned")
		
		# Send Chat Notification from current user
		if doc.assignees:
			sender = frappe.db.get_value("User", action_user, "email") or action_user
			for row in doc.assignees:
				receiver = row.user or frappe.db.get_value("Employee", row.employee, "user")
				if receiver and receiver != sender:
					# Get first name for the greeting
					emp_name = row.employee_name or frappe.db.get_value("Employee", row.employee, "employee_name") or "Team"
					first_name = emp_name.split(" ")[0]
					
					formatted_date = frappe.utils.format_date(doc.due_date, "dd MMM YYYY") if doc.due_date else "N/A"
					project_info = f"{doc.project}: " if doc.project else ""
					
					content = (
						f"<b>Hi {first_name} 👋</b><br><br>"
						f"<b>New Task Assigned:</b> {project_info}{doc.title}<br>"
						f"<b>Due Date:</b> {formatted_date}<br><br>"
						f"Please review the task details and proceed accordingly."
					)
					doc.send_chat_notification(sender, receiver, content)
	except Exception:
		frappe.log_error(title="Task Manager after_insert Notification Error", message=frappe.get_traceback())


def send_on_update_notifications(doc_name, action_user, old_status, new_status):
	"""Background task for on_update notifications"""
	if not doc_name or not action_user:
		return

	frappe.session.user = action_user
	try:
		doc = frappe.get_doc("Task Manager", doc_name)
		if old_status != new_status:
			if new_status == "Completed":
				# Notify Task Manager (HR) only via email — not the assignees
				doc.notify_hr("completed")
				# Send Chat Notification to the Task Creator (Owner)
				content = f"<b>Task Completed:</b> {doc.title} by {action_user}"
				sender = frappe.db.get_value("User", action_user, "email") or action_user
				if doc.owner and doc.owner != sender:
					doc.send_chat_notification(sender, doc.owner, content)

			elif new_status == "Reopened":
				doc.notify_assignees("reopened")
				# Send Chat Notification from Task Manager who reopened it
				if doc.assignees:
					sender = frappe.db.get_value("User", action_user, "email") or action_user
					for row in doc.assignees:
						receiver = row.user or frappe.db.get_value("Employee", row.employee, "user")
						if receiver and receiver != sender:
							# Get first name for the greeting
							emp_name = row.employee_name or frappe.db.get_value("Employee", row.employee, "employee_name") or "Team"
							first_name = emp_name.split(" ")[0]
							
							project_info = f"{doc.project}: " if doc.project else ""
							
							content = (
								f"<b>Hi {first_name} 👋</b><br><br>"
								f"<b>Task Reopened:</b> {project_info}{doc.title}<br><br>"
								f"Please review the task and take necessary action."
							)
							doc.send_chat_notification(sender, receiver, content)

			elif new_status == "In Progress":
				doc.notify_hr("in_progress")
				# Send Chat Notification to the Task Creator (Owner)
				content = f"<b>Task In Progress:</b> {doc.title} by {action_user}"
				sender = frappe.db.get_value("User", action_user, "email") or action_user
				if doc.owner and doc.owner != sender:
					doc.send_chat_notification(sender, doc.owner, content)
	except Exception:
		frappe.log_error(title="Task Manager on_update Notification Error", message=frappe.get_traceback())


def send_manual_chat_notification(doc_name, action_user, content):
	"""Background task for manual chat notifications (close, hold, resume, accept)"""
	if not doc_name or not action_user:
		return

	frappe.session.user = action_user
	try:
		doc = frappe.get_doc("Task Manager", doc_name)
		sender = frappe.db.get_value("User", action_user, "email") or action_user
		if doc.owner and doc.owner != sender:
			doc.send_chat_notification(sender, doc.owner, content)
	except Exception:
		frappe.log_error(title="Task Manager Manual Chat Notification Error", message=frappe.get_traceback())
