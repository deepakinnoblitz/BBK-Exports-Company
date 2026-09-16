import json
import frappe
from frappe.model.document import Document
from datetime import datetime, timedelta, date, time

class WFHAttendance(Document):
    def validate(self):
        """Automatically set date and calculate total hours"""
        if not self.date:
            self.date = date.today()

        # 🚫 Check for duplicate request on same date for same employee
        existing = frappe.db.exists(
            "WFH Attendance",
            {
                "employee": self.employee,
                "date": self.date,
                "name": ["!=", self.name],  # exclude current record (for edits)
                "docstatus": ["<", 2]       # exclude cancelled
            }
        )

        if existing:
            frappe.throw(
                f"A WFH Attendance request already exists for <b>{self.date}</b> "
            )

        # ✅ Calculate total hours
        self.calculate_total_hours()

    def before_update_after_submit(self):
        """Recalculate hours even after submission"""
        self.calculate_total_hours()

    def calculate_total_hours(self):
        if self.from_time and self.to_time:
            from_dt = self._get_datetime(self.from_time)
            to_dt = self._get_datetime(self.to_time)

            if from_dt and to_dt:
                # Handle overnight (e.g., 22:00 → 02:00)
                if to_dt < from_dt:
                    to_dt += timedelta(days=1)

                diff = to_dt - from_dt
                total_minutes = int(diff.total_seconds() / 60)
                hours = total_minutes // 60
                minutes = total_minutes % 60
                self.total_hours = f"{hours}:{minutes:02d}"
            else:
                self.total_hours = ""
        else:
            self.total_hours = ""

    def after_insert(self):
        """Auto-submit the document immediately after creation"""
        try:
            if self.docstatus == 0:
                frappe.db.commit()  # ensure insert is saved before submit
                self.submit()
                
                # ✅ Set state to Pending AFTER submission
                frappe.db.set_value(self.doctype, self.name, "workflow_state", "Pending", update_modified=False)
                
                frappe.msgprint("✅ WFH Attendance Submitted.")
                
                # Notifications
                self.notify_hr_for_approval()
                self.notify_hr_chat_on_submission()
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "WFH Auto Submit Failed")

    def on_update_after_submit(self):
        """Triggered when HR approves (docstatus=1)"""
        if self.workflow_state == "Approved":
            current_user = frappe.session.user

            # ✅ Set approved_by if not already set
            if not self.approved_by:
                frappe.db.set_value(
                    self.doctype,
                    self.name,
                    "approved_by",
                    current_user,
                    update_modified=False
                )

            # ✅ Create or update Attendance record
            self.create_or_update_attendance()
            
            # Notifications
            self.notify_employee_on_approval()
            self.notify_employee_chat_on_approval()

    def on_cancel(self):
        """Triggered when HR rejects (docstatus=2)"""
        if self.workflow_state == "Rejected":
            frappe.db.set_value(
                self.doctype,
                self.name,
                "approved_by",
                frappe.session.user,
                update_modified=False
            )
            
            # Notifications
            self.notify_employee_on_rejection()
            self.notify_employee_chat_on_rejection()

    def create_or_update_attendance(self):
        """Creates or updates Attendance record when HR approves"""
        existing_attendance = frappe.db.exists(
            "Attendance",
            {"employee": self.employee, "attendance_date": self.date}
        )

        # Helper: ensure string format for time fields
        def to_str_time(t):
            if isinstance(t, timedelta):
                total_seconds = int(t.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            elif isinstance(t, time):
                return t.strftime("%H:%M:%S")
            elif isinstance(t, str):
                return t
            return None

        in_time_str = to_str_time(self.from_time)
        out_time_str = to_str_time(self.to_time)

        if existing_attendance:
            # 📝 Update existing attendance
            attendance = frappe.get_doc("Attendance", existing_attendance)
            attendance.status = "Present"
            attendance.in_time = in_time_str
            attendance.out_time = out_time_str
            attendance.total_working_hours = self.total_hours
            attendance.save(ignore_permissions=True)
        else:
            # ➕ Create new attendance
            attendance = frappe.get_doc({
                "doctype": "Attendance",
                "employee": self.employee,
                "attendance_date": self.date,
                "status": "Present",
                "in_time": in_time_str,
                "out_time": out_time_str,
                "manual": 1,
                "total_working_hours": self.total_hours
            })
            attendance.insert(ignore_permissions=True)

    def _get_datetime(self, t):
        """Helper to normalize time field (handles str, timedelta, time)"""
        if not t:
            return None

        # Use a fixed base date to ensure all times are compared on the same day
        base_date = date(1900, 1, 1)

        if isinstance(t, str):
            for fmt in ("%H:%M:%S", "%H:%M"):
                try:
                    # strptime defaults to 1900-01-01
                    return datetime.strptime(t, fmt)
                except ValueError:
                    continue
            frappe.throw(f"Invalid time format: {t}. Expected HH:MM:SS or HH:MM")
        elif isinstance(t, timedelta):
            return datetime.combine(base_date, time.min) + t
        elif isinstance(t, time):
            return datetime.combine(base_date, t)
        
        return None

    def get_hr_settings(self):
        """Fetch HR email and CC from Company Email Settings"""
        settings = frappe.get_all(
            "Company Email Settings",
            fields=["hr_email", "hr_cc_emails", "hr_name"],
            limit=1
        )
        if settings:
            return settings[0]
        return {}

    def get_employee_user(self):
        """Get the user linked to the employee"""
        return frappe.db.get_value("Employee", self.employee, "user")

    def get_hr_users(self):
        """Get valid HR User IDs for chat notifications"""
        roles = ["HR"]
        role_users = frappe.get_all(
            "Has Role",
            filters={"role": ["in", roles], "parenttype": "User"},
            pluck="parent"
        )
        # Filter unique and active users
        hr_users = [u for u in set(role_users) if frappe.db.get_value("User", u, "enabled")]

        return list(set(hr_users))

    def send_chat_notification(self, sender, receiver, content):
        """Send a chat message via clefincode_chat. Create/Verify channel and send message."""
        log_data = {
            "sender_id": sender,
            "receiver_id": receiver,
            "content": content
        }
        
        try:
            from clefincode_chat.api.api_1_2_1.api import send, create_channel, share_doctype, get_profile_id
            
            # 1. Check if direct room exists (Using system IDs)
            room_name = frappe.db.sql("""
                SELECT c.name
                FROM `tabClefinCode Chat Channel` c
                JOIN `tabClefinCode Chat Channel User` u1 ON u1.parent = c.name
                JOIN `tabClefinCode Chat Channel User` u2 ON u2.parent = c.name
                WHERE c.type = 'Direct'
                AND c.is_parent = 1
                AND u1.user = %s
                AND u2.user = %s
            """, (sender, receiver), pluck=True)

            if room_name:
                room_name = room_name[0]
                log_data["room_name_found"] = room_name
                # Ensure HR receiver is active and not removed
                frappe.db.sql("""
                    UPDATE `tabClefinCode Chat Channel User`
                    SET is_removed = 0, active = 1
                    WHERE parent = %s AND user = %s
                """, (room_name, receiver))
                # Ensure document sharing is active
                share_doctype("ClefinCode Chat Channel", room_name, receiver)
            else:
                # 2. Create channel using system IDs
                users = [
                    {"email": sender, "platform": "Chat"},
                    {"email": receiver, "platform": "Chat"}
                ]
                sender_full_name = frappe.db.get_value("User", sender, "full_name") or sender
                res = create_channel(
                    channel_name="", 
                    users=json.dumps(users),
                    type="Direct",
                    last_message=content,
                    creator_email=sender,
                    creator=sender_full_name
                )
                log_data["create_channel_response"] = res
                
                if res and res.get("results"):
                    room_name = res["results"][0]["room"]
                    log_data["new_room_name"] = room_name
                else:
                    frappe.log_error(title="WFH App: Chat Channel Creation Failed", message=frappe.as_json(log_data))

            if room_name:
                # 3. Diagnostic Logging: Verify Membership State
                members = frappe.get_all("ClefinCode Chat Channel User", 
                                        filters={"parent": room_name}, 
                                        fields=["user", "is_removed", "active"])
                log_data["channel_members_final"] = members

                sender_full_name = frappe.db.get_value("User", sender, "full_name") or sender
                
                # 4. Send the message
                send_res = send(
                    content=content,
                    user=sender_full_name,
                    room=room_name,
                    email=sender
                )
                log_data["send_response"] = send_res
                
                if send_res and isinstance(send_res, dict) and send_res.get("results"):
                    log_data["message_name"] = send_res["results"][0].get("new_message_name")

                # 5. Force Sidebar Refresh
                refresh_data = {
                    "room": room_name,
                    "realtime_type": "update_room",
                    "content": content,
                    "user": sender_full_name,
                    "sender_email": sender,
                    "room_type": "Direct"
                }
                frappe.publish_realtime(event="update_room", message=refresh_data, user=receiver)
                frappe.publish_realtime(event="new_chat_notification", message=refresh_data, user=receiver)
                
                # Final log to verify success and parameters
                frappe.log_error(title="WFH Chat Debug", message=frappe.as_json(log_data))
            else:
                log_data["error"] = "Room name could not be determined"
                frappe.log_error(title="WFH Chat Failed", message=frappe.as_json(log_data))
                
        except Exception as e:
            log_data["exception"] = str(e)
            log_data["traceback"] = frappe.get_traceback()
            frappe.log_error(title="WFH Chat Notification Exception", message=frappe.as_json(log_data))

    def notify_hr_chat_on_submission(self):
        """InnoChat Notification to HR (Separate from email toggle)"""
        hr_users = self.get_hr_users()
        sender_user = frappe.session.user
        
        content = (
            f"<b>📩 New WFH Request</b><br><br>"
            f"<b>Employee:</b> {self.employee_name}<br>"
            f"<b>Date:</b> {frappe.utils.formatdate(self.date)}<br>"
            f"<b>From:</b> {self.from_time or '-'}<br>"
            f"<b>To:</b> {self.to_time or '-'}<br>"
            f"<b>Total Hours:</b> {self.total_hours or 'N/A'}<br><br>"
            f"Please review and take necessary action."
        )

        for receiver in hr_users:
            if receiver != sender_user:
                try:
                    self.send_chat_notification(sender_user, receiver, content)
                except Exception:
                    frappe.log_error(title="WFH Submit Chat Loop Error", message=frappe.get_traceback())

    def notify_hr_for_approval(self):
        """Send email notification to HR when employee submits WFH Attendance"""
        from company.company.api import is_hrms_notification_enabled
        if not is_hrms_notification_enabled("wfh_notification"):
            return

        hr_settings = self.get_hr_settings()
        hr_email = hr_settings.get("hr_email")
        cc_emails = hr_settings.get("hr_cc_emails")

        if not hr_email:
            return

        employee_email = frappe.db.get_value("Employee", self.employee, "personal_email")
        sender = f"{self.employee_name} <{employee_email}>" if employee_email else hr_email

        cc_list = []
        if cc_emails:
            cc_list = [e.strip() for e in cc_emails.replace("\n", ",").split(",") if e.strip()]


        # Build sleek purple-styled table
        attendance_details = f"""
            <table style="width:100%; border-collapse:collapse; font-size:14px; border-radius:8px; overflow:hidden;">
                <tr style="background:#f4e8ff;">
                    <td style="padding:10px 12px; font-weight:600; width:160px;">Employee</td>
                    <td style="padding:10px 12px;">{self.employee_name} ({self.employee})</td>
                </tr>
                <tr style="background:#faf7ff;">
                    <td style="padding:10px 12px; font-weight:600;">Date</td>
                    <td style="padding:10px 12px;">{frappe.utils.formatdate(self.date)}</td>
                </tr>
                <tr style="background:#f4e8ff;">
                    <td style="padding:10px 12px; font-weight:600;">From Time</td>
                    <td style="padding:10px 12px;">{self.from_time}</td>
                </tr>
                <tr style="background:#faf7ff;">
                    <td style="padding:10px 12px; font-weight:600;">To Time</td>
                    <td style="padding:10px 12px;">{self.to_time}</td>
                </tr>
                <tr style="background:#f4e8ff;">
                    <td style="padding:10px 12px; font-weight:600;">Total Hours</td>
                    <td style="padding:10px 12px;">{self.total_hours or 'N/A'}</td>
                </tr>
                <tr style="background:#faf7ff;">
                    <td style="padding:10px 12px; font-weight:600;">Task Description</td>
                    <td style="padding:10px 12px;">{self.task_description or '—'}</td>
                </tr>
            </table>
        """

        
        message = f"""
        <div style="font-family: 'Poppins', 'Segoe UI', Arial, sans-serif; background:#f5f2ff; padding:40px;">
            <div style="max-width:600px; margin:auto; background:white; border-radius:14px; 
                        box-shadow:0 4px 10px rgba(110, 0, 180, 0.1); overflow:hidden;">
                
                <div style="background:#7B2CBF; color:white; padding:20px 26px; font-size:18px; 
                            font-weight:600; letter-spacing:0.4px;">
                    New WFH Attendance Request
                </div>

                <div style="padding:26px; color:#333;">
                    <p style="font-size:15px;">Dear <b>HR</b>,</p>
                    <p style="font-size:14px; line-height:1.6; margin-bottom:20px;">
                        A new <b>WFH Attendance</b> request has been submitted by 
                        <b>{self.employee_name}</b> and is pending your approval.
                    </p>

                    <div style="border:1px solid #e0d2ff; border-radius:8px;">
                        {attendance_details}
                    </div>

                    <p style="font-size:14px; color:#555; margin-top:24px;">
                        Please review the request and take the necessary action.
                    </p>

                    <div style="margin-top:30px; text-align:center;">
                        <a href="{frappe.utils.get_url('wfh-attendance')}" 
                        style="background:#7B2CBF; color:white; padding:12px 24px; text-decoration:none; 
                                border-radius:8px; font-size:14px; font-weight:500; letter-spacing:0.3px; display:inline-block;">
                            View in ERP
                        </a>
                    </div>
                </div>

                <div style="background:#f4e8ff; padding:12px 20px; text-align:center; font-size:12px; color:#7B2CBF;">
                    This is an automated notification from your ERP system.
                </div>
            </div>
        </div>
        """

        try:
            frappe.sendmail(
                recipients=[hr_email],
                cc=cc_list,
                subject=f"WFH Approval Request - {self.employee_name} ({frappe.utils.formatdate(self.date)})",
                message=message,
                sender=sender,
                reply_to=employee_email or hr_email,
                reference_doctype=self.doctype,
                reference_name=self.name
            )
        except Exception as e:
            frappe.log_error(f"WFH Submit Mail Error: {str(e)}", "WFH Email Debug")

    def notify_employee_chat_on_approval(self):
        """InnoChat Notification to Employee (Separate from email toggle)"""
        receiver = self.get_employee_user()
        sender_user = frappe.session.user
        if receiver and receiver != sender_user:
            content = (
                f"<b>✅ WFH Approved</b><br><br>"
                f"<b>Date:</b> {frappe.utils.formatdate(self.date)}<br>"
                f"<b>From:</b> {self.from_time or '-'}<br>"
                f"<b>To:</b> {self.to_time or '-'}<br><br>"
                f"Your WFH request has been approved."
            )
            self.send_chat_notification(sender_user, receiver, content)

    def notify_employee_on_approval(self):
        """Send mail to employee when HR approves"""
        from company.company.api import is_hrms_notification_enabled
        if not is_hrms_notification_enabled("wfh_notification"):
            return

        hr_settings = self.get_hr_settings()
        hr_email = hr_settings.get("hr_email")
        hr_name = hr_settings.get("hr_name") or "HR Team"
        sender = f"{hr_name} <{hr_email}>" if hr_email else None

        personal_email, company_email = frappe.db.get_value("Employee", self.employee, ["personal_email", "email"])
        recipients = [r for r in [personal_email, company_email] if r]
        if not recipients:
            return

        message = f"""
        <div style="font-family: 'Poppins', 'Segoe UI', Arial, sans-serif; background:#f5f2ff; padding:40px;">
            <div style="max-width:600px; margin:auto; background:white; border-radius:14px;
                        box-shadow:0 4px 12px rgba(0,128,0,0.15); overflow:hidden;">
                
                <div style="background:#28a745; color:white; padding:20px 26px; font-size:18px; font-weight:600;">
                    ✅ WFH Request Approved
                </div>

                <div style="padding:26px; color:#333; font-size:14px; line-height:1.6;">
                    <p>Dear <b>{self.employee_name}</b>,</p>
                    <p>Your <b>Work From Home</b> request has been 
                    <b style="color:#28a745;">approved</b> by HR.</p>

                    <table style="width:100%; border-collapse:collapse; font-size:13px; margin-top:18px; border-radius:8px; overflow:hidden;">
                        <tr style="background:#eaf8f0;">
                            <td style="padding:10px 12px; font-weight:600; width:160px;">Date</td>
                            <td style="padding:10px 12px;">{frappe.utils.formatdate(self.date)}</td>
                        </tr>
                        <tr style="background:#f6fff9;">
                            <td style="padding:10px 12px; font-weight:600;">From Time</td>
                            <td style="padding:10px 12px;">{self.from_time or '-'}</td>
                        </tr>
                        <tr style="background:#eaf8f0;">
                            <td style="padding:10px 12px; font-weight:600;">To Time</td>
                            <td style="padding:10px 12px;">{self.to_time or '-'}</td>
                        </tr>
                        <tr style="background:#f6fff9;">
                            <td style="padding:10px 12px; font-weight:600;">Total Hours</td>
                            <td style="padding:10px 12px;">{self.total_hours or 'N/A'}</td>
                        </tr>
                    </table>

                    <div style="text-align:center; margin-top:28px;">
                        <a href="{frappe.utils.get_url('wfh-attendance')}"
                        style="background:#28a745; color:white; padding:12px 24px; text-decoration:none;
                                 border-radius:8px; font-size:14px; font-weight:500;">
                        View in ERP
                        </a>
                    </div>
                </div>

                <div style="background:#d4edda; padding:12px 20px; text-align:center;
                            font-size:12px; color:#155724;">
                    This is an automated message from your ERP system.
                </div>
            </div>
        </div>
        """

        frappe.sendmail(
            recipients=recipients,
            subject=f"✅ WFH Approved - {frappe.utils.formatdate(self.date)}",
            message=message,
            sender=sender,
            reply_to=hr_email,
            reference_doctype=self.doctype,
            reference_name=self.name
        )

    def notify_employee_chat_on_rejection(self):
        """InnoChat Notification to Employee (Separate from email toggle)"""
        receiver = self.get_employee_user()
        sender_user = frappe.session.user
        if receiver and receiver != sender_user:
            content = (
                f"<b>❌ WFH Rejected</b><br><br>"
                f"<b>Date:</b> {frappe.utils.formatdate(self.date)}<br><br>"
                f"Your WFH request has been rejected."
            )
            self.send_chat_notification(sender_user, receiver, content)

    def notify_employee_on_rejection(self):
        """Send mail to employee when HR rejects"""
        from company.company.api import is_hrms_notification_enabled
        if not is_hrms_notification_enabled("wfh_notification"):
            return

        hr_settings = self.get_hr_settings()
        hr_email = hr_settings.get("hr_email")
        hr_name = hr_settings.get("hr_name") or "HR Team"
        sender = f"{hr_name} <{hr_email}>" if hr_email else None

        personal_email, company_email = frappe.db.get_value("Employee", self.employee, ["personal_email", "email"])
        recipients = [r for r in [personal_email, company_email] if r]
        if not recipients:
            return

        message = f"""
        <div style="font-family: 'Poppins', 'Segoe UI', Arial, sans-serif; background:#f5f2ff; padding:40px;">
            <div style="max-width:600px; margin:auto; background:white; border-radius:14px;
                        box-shadow:0 4px 12px rgba(220,53,69,0.15); overflow:hidden;">
                
                <div style="background:#dc3545; color:white; padding:20px 26px; font-size:18px; font-weight:600;">
                    ❌ WFH Request Rejected
                </div>

                <div style="padding:26px; color:#333; font-size:14px; line-height:1.6;">
                    <p>Dear <b>{self.employee_name}</b>,</p>
                    <p>Your <b>Work From Home</b> request has been 
                    <b style="color:#dc3545;">rejected</b> by HR.</p>

                    <table style="width:100%; border-collapse:collapse; font-size:13px; margin-top:18px; border-radius:8px; overflow:hidden;">
                        <tr style="background:#f8d7da;">
                            <td style="padding:10px 12px; font-weight:600; width:160px;">Date</td>
                            <td style="padding:10px 12px;">{frappe.utils.formatdate(self.date)}</td>
                        </tr>
                        <tr style="background:#fff5f5;">
                            <td style="padding:10px 12px; font-weight:600;">From Time</td>
                            <td style="padding:10px 12px;">{self.from_time or '-'}</td>
                        </tr>
                        <tr style="background:#f8d7da;">
                            <td style="padding:10px 12px; font-weight:600;">To Time</td>
                            <td style="padding:10px 12px;">{self.to_time or '-'}</td>
                        </tr>
                    </table>

                    <div style="text-align:center; margin-top:28px;">
                        <a href="{frappe.utils.get_url('wfh-attendance')}"
                        style="background:#dc3545; color:white; padding:12px 24px; text-decoration:none;
                                border-radius:8px; font-size:14px; font-weight:500;">
                        View Request
                        </a>
                    </div>
                </div>

                <div style="background:#f8d7da; padding:12px 20px; text-align:center;
                            font-size:12px; color:#721c24;">
                    This is an automated message from your ERP system.
                </div>
            </div>
        </div>
        """

        frappe.sendmail(
            recipients=recipients,
            subject=f"❌ WFH Rejected - {frappe.utils.formatdate(self.date)}",
            message=message,
            sender=sender,
            reply_to=hr_email,
            reference_doctype=self.doctype,
            reference_name=self.name
        )


@frappe.whitelist()
def handle_workflow_action(docname, action):
    """
    Whitelisted API to Approve or Reject WFH Attendance.
    Triggers attendance creation and mail functionality.
    """
    if not docname or not action:
        frappe.throw("Document Name and Action are required")

    # Check for HR or System Manager roles
    user_roles = frappe.get_roles()
    if not ("HR" in user_roles or "System Manager" in user_roles):
        frappe.throw("Only HR or System Managers can approve/reject WFH requests", frappe.PermissionError)

    doc = frappe.get_doc("WFH Attendance", docname)

    if doc.workflow_state != "Pending":
        frappe.throw(f"Workflow Action is only allowed for 'Pending' requests. Current state: {doc.workflow_state}")

    if action == "Approve":
        doc.workflow_state = "Approved"
        # Since it's already submitted, saving it triggers on_update_after_submit
        doc.save(ignore_permissions=True)
        
        # Push real-time update
        frappe.publish_realtime(
            event="wfh_attendance_updated",
            message={"name": docname, "workflow_state": "Approved", "action": "Approve"},
        )
        return {"status": "success", "message": f"WFH Attendance {docname} Approved"}

    elif action == "Reject":
        doc.workflow_state = "Rejected"
        # Cancelling the document triggers on_cancel hook
        doc.cancel()
        
        # Push real-time update
        frappe.publish_realtime(
            event="wfh_attendance_updated",
            message={"name": docname, "workflow_state": "Rejected", "action": "Reject"},
        )
        return {"status": "success", "message": f"WFH Attendance {docname} Rejected"}

    else:
        frappe.throw(f"Invalid Action: {action}. Expected 'Approve' or 'Reject'")
