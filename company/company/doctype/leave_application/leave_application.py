import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, get_url

class LeaveApplication(Document):

    # =================================================
    # EMPLOYEE SUBMITS LEAVE → MAIL HR (Background)
    # =================================================
    def on_submit(self):
        """Enqueue HR notifications in background to avoid submit delay"""
        # 🛡️ Prevent double enqueuing in the same request
        if frappe.flags.get(f"enqueued_submit_notification_{self.name}"):
            return

        frappe.enqueue(
            "company.company.doctype.leave_application.leave_application.send_submit_notification",
            doc_name=self.name,
            submitter_user=frappe.session.user,
            enqueue_after_commit=True
        )
        frappe.flags[f"enqueued_submit_notification_{self.name}"] = True

    def validate(self):
        self.validate_dates()

    def validate_dates(self):
        from frappe.utils import getdate
        if self.from_date and self.to_date:
            if getdate(self.to_date) < getdate(self.from_date):
                frappe.throw("To Date cannot be before From Date")

    # =================================================
    # ALL WORKFLOW CHANGES AFTER SUBMIT
    # =================================================
    def on_update_after_submit(self):
        before = self.get_doc_before_save()

        # 🚫 HARD STOP: first submit
        if before and before.docstatus == 0 and self.docstatus == 1:
            return

        self.send_workflow_mail()

        if self.workflow_state == "Approved" and (not before or before.workflow_state != "Approved"):
            from company.company.evaluation_automation import handle_leave_automation
            handle_leave_automation(self)

    # =================================================
    # HANDLE REJECTION / CANCELLATION
    # =================================================
    def on_cancel(self):
        hr_settings = self.get_hr_settings()
        hr_email = hr_settings.get("hr_email")
        hr_name = hr_settings.get("hr_name") or "HR Team"
        
        emp_emails, primary_email = self.get_employee_emails()
        sender = f"{hr_name} <{hr_email}>" if hr_email else None

        if emp_emails:
            self.send_email(
                recipients=emp_emails,
                subject="❌ Leave Rejected",
                header="Leave Rejected",
                icon="❌",
                intro="Your leave application has been rejected/cancelled.",
                greeting=f"Hello {self.employee_name},",
                color="#dc3545",
                sender=sender,
                reply_to=hr_email
            )

        # InnoChat Notification to Employee
        receiver = frappe.db.get_value("Employee", self.employee, "user")
        if receiver and receiver != frappe.session.user:
            content = (
                f"<b>❌ Leave Rejected</b><br><br>"
                f"<b>Employee:</b> {self.employee_name}<br>"
                f"<b>Leave Type:</b> {self.leave_type}<br>"
                f"<b>From:</b> {frappe.utils.formatdate(self.from_date)}<br>"
                f"<b>To:</b> {frappe.utils.formatdate(self.to_date)}<br><br>"
                f"Your leave application has been rejected/cancelled."
            )
            self.send_chat_notification(frappe.session.user, receiver, content)

    # =================================================
    # GET HR EMAIL SETTINGS
    # =================================================
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
                    frappe.log_error(title="Leave App: Chat Channel Creation Failed", message=frappe.as_json(log_data))

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

                # 5. Force Sidebar Refresh for HR
                # Explicitly publish to HR user's session to ensure sidebar update
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
                frappe.log_error(title="Leave App Chat Debug", message=frappe.as_json(log_data))
            else:
                log_data["error"] = "Room name could not be determined"
                frappe.log_error(title="Leave App Chat Failed", message=frappe.as_json(log_data))
                
        except Exception as e:
            log_data["exception"] = str(e)
            log_data["traceback"] = frappe.get_traceback()
            frappe.log_error(title="Leave Application Chat Notification Exception", message=frappe.as_json(log_data))


    # =================================================
    # GET EMPLOYEE EMAILS
    # =================================================
    def get_employee_emails(self):
        """Fetch both company email and personal email of the employee"""
        emp = frappe.db.get_value("Employee", self.employee, ["email", "personal_email"], as_dict=True)
        if not emp:
            return [], None
        
        emails = []
        primary_email = emp.email or emp.personal_email
        
        if emp.email:
            emails.append(emp.email)
        if emp.personal_email:
            emails.append(emp.personal_email)
            
        return list(set(emails)), primary_email

    # =================================================
    # 1️⃣ EMPLOYEE SUBMIT → HR
    # =================================================
    def send_submit_mail_to_hr(self):
        hr_settings = self.get_hr_settings()
        hr_email = hr_settings.get("hr_email")
        cc_emails = hr_settings.get("hr_cc_emails")

        emp_emails, primary_email = self.get_employee_emails()
        sender_name = f"{self.employee_name} <{primary_email}>" if primary_email else hr_email
    
        cc_list = []
        if cc_emails:
            cc_list = [e.strip() for e in cc_emails.replace("\n", ",").split(",") if e.strip()]
        
        if hr_email:
            self.send_email(
                recipients=[hr_email],
                cc=cc_list,
                subject=f"📩 New Leave Request - {self.employee_name}",
                header="New Leave Request",
                icon="📩",
                intro=f"{self.employee_name} has submitted a leave application.",
                greeting="Dear HR,",
                color="#0062cc",
                sender=sender_name,
                reply_to=primary_email or hr_email
            )

        # Notication to Chat

        """Send chat notification to HR when employee submits leave"""

        # Get HR users (receivers)
        hr_users = self.get_hr_users()
        
        # SENDER: Use current logged-in Frappe user ID (tabUser.name) directly
        # This is critical for InnoChat sidebar visibility and Firebase token matching
        sender = frappe.session.user
        
        if not hr_users:
            frappe.logger().debug(f"Leave App: No valid HR users found for chat notification")
            return

        content = (
            f"<b>📩 New Leave Request</b><br><br>"
            f"<b>Employee:</b> {self.employee_name}<br>"
            f"<b>Leave Type:</b> {self.leave_type}<br>"
            f"<b>From:</b> {formatdate(self.from_date)}<br>"
            f"<b>To:</b> {formatdate(self.to_date)}<br>"
            f"<b>Reason:</b> {self.reson or 'N/A'}<br><br>"
            f"Please review and take necessary action."
        )

        for receiver in hr_users:
            # Skip sending to self
            if receiver == sender:
                continue
                
            try:
                # Log final IDs being used for verification
                frappe.logger().debug(f"Leave App: Chat Dispatch -> Sender ID: {sender}, Receiver ID: {receiver}")
                self.send_chat_notification(sender, receiver, content)
            except Exception as e:
                frappe.log_error(title="Leave Application Submit Chat Loop Error", message=frappe.get_traceback())


    # =================================================
    # WORKFLOW MAIL HANDLER
    # =================================================
    def send_workflow_mail(self):

        before = self.get_doc_before_save()
        if not before:
            return

        previous_state = before.workflow_state
        current_state = self.workflow_state

        # 🚫 Skip if no workflow transition
        if previous_state == current_state:
            return

        hr_settings = self.get_hr_settings()
        hr_email = hr_settings.get("hr_email")
        hr_name = hr_settings.get("hr_name") or "HR Team"
        
        emp_emails, primary_email = self.get_employee_emails()
        hr_sender = f"{hr_name} <{hr_email}>" if hr_email else None
        employee_sender = f"{self.employee_name} <{primary_email}>" if primary_email else hr_email

        # -------------------------------------------------
        # HR → ASK CLARIFICATION → EMPLOYEE
        # -------------------------------------------------
        if current_state == "Clarification Requested":
            hr_msg = self.get_latest_hr_query()

            if emp_emails:
                self.send_email(
                    recipients=emp_emails,
                    subject="📩 Reply from HR - Leave Application",
                    header="Reply from HR",
                    icon="📩",
                    intro="HR has replied to your leave application.",
                    greeting=f"Hello {self.employee_name},",
                    extra_message=self.hr_message_block(hr_msg),
                    color="#ffc107",
                    sender=hr_sender,
                    reply_to=hr_email
                )

            # InnoChat Notification to Employee
            receiver = frappe.db.get_value("Employee", self.employee, "user")
            if receiver and receiver != frappe.session.user:
                content = (
                    f"<b>📩 Clarification Requested</b><br><br>"
                    f"<b>Employee:</b> {self.employee_name}<br>"
                    f"<b>Leave Type:</b> {self.leave_type}<br>"
                    f"<b>From:</b> {frappe.utils.formatdate(self.from_date)}<br>"
                    f"<b>To:</b> {frappe.utils.formatdate(self.to_date)}<br><br>"
                    f"HR has requested clarification on your leave application."
                )
                self.send_chat_notification(frappe.session.user, receiver, content)

        # -------------------------------------------------
        # EMPLOYEE → REPLY → HR
        # -------------------------------------------------
        elif current_state == "Pending" and previous_state == "Clarification Requested":
            emp_reply = self.get_latest_employee_reply()
            
            cc_emails = hr_settings.get("hr_cc_emails")
            cc_list = []
            if cc_emails:
                cc_list = [e.strip() for e in cc_emails.replace("\n", ",").split(",") if e.strip()]

            if hr_email:
                self.send_email(
                    recipients=[hr_email],
                    cc=cc_list,
                    subject=f"📩 Reply from Employee - {self.employee_name}",
                    header="Reply Received",
                    icon="📩",
                    intro=f"{self.employee_name} has replied to your clarification request.",
                    greeting="Dear HR,",
                    extra_message=self.employee_reply_block(emp_reply),
                    color="#0062cc",
                    sender=employee_sender,
                    reply_to=primary_email or hr_email
                )

            # InnoChat Notification to HR
            hr_users = self.get_hr_users()
            content = (
                f"<b>📩 Employee Reply</b><br><br>"
                f"<b>Employee:</b> {self.employee_name}<br>"
                f"<b>Leave Type:</b> {self.leave_type}<br>"
                f"<b>From:</b> {frappe.utils.formatdate(self.from_date)}<br>"
                f"<b>To:</b> {frappe.utils.formatdate(self.to_date)}<br><br>"
                f"Employee has replied to the clarification request."
            )
            for hr_user in hr_users:
                if hr_user != frappe.session.user:
                    self.send_chat_notification(frappe.session.user, hr_user, content)

        # -------------------------------------------------
        # HR → APPROVE → EMPLOYEE ONLY
        # -------------------------------------------------
        elif current_state == "Approved":
            if emp_emails:
                self.send_email(
                    recipients=emp_emails,
                    subject="✅ Leave Approved",
                    header="Leave Approved",
                    icon="✅",
                    intro="Your leave application has been approved.",
                    greeting=f"Hello {self.employee_name},",
                    color="#28a745",
                    sender=hr_sender,
                    reply_to=hr_email
                )

            # InnoChat Notification to Employee
            receiver = frappe.db.get_value("Employee", self.employee, "user")
            if receiver and receiver != frappe.session.user:
                content = (
                    f"<b>✅ Leave Approved</b><br><br>"
                    f"<b>Employee:</b> {self.employee_name}<br>"
                    f"<b>Leave Type:</b> {self.leave_type}<br>"
                    f"<b>From:</b> {frappe.utils.formatdate(self.from_date)}<br>"
                    f"<b>To:</b> {frappe.utils.formatdate(self.to_date)}<br><br>"
                    f"Your leave application has been approved."
                )
                self.send_chat_notification(frappe.session.user, receiver, content)

    # =================================================
    # FETCH LATEST HR QUERY
    # =================================================
    def get_latest_hr_query(self):
        for i in range(5, 0, -1):
            field = f"hr_query_{i}" if i > 1 else "hr_query"
            val = getattr(self, field, None)
            if val:
                return val
        return None

    # =================================================
    # FETCH LATEST EMPLOYEE REPLY
    # =================================================
    def get_latest_employee_reply(self):
        for i in range(5, 0, -1):
            field = f"employee_reply_{i}" if i > 1 else "employee_reply"
            val = getattr(self, field, None)
            if val:
                return val
        return None

    # =================================================
    # HR MESSAGE BLOCK (YELLOW)
    # =================================================
    def hr_message_block(self, message):
        if not message:
            return ""

        return f"""
        <div style="
            margin-top:18px;
            padding:16px;
            background:#fff3cd;
            border-left:5px solid #ffc107;
            border-radius:6px;
        ">
            <b style="color:#856404;">HR Clarification:</b><br>
            <p style="margin:6px 0 0; font-style:italic;">
                “{message}”
            </p>
        </div>
        """

    # =================================================
    # EMPLOYEE REPLY BLOCK (BLUE)
    # =================================================
    def employee_reply_block(self, message):
        if not message:
            return ""

        return f"""
        <div style="
            margin-top:18px;
            padding:16px;
            background:#e1f5fe;
            border-left:5px solid #03a9f4;
            border-radius:6px;
        ">
            <b style="color:#01579b;">Employee Reply:</b><br>
            <p style="margin:6px 0 0; font-style:italic;">
                “{message}”
            </p>
        </div>
        """

    # =================================================
    # COMMON EMAIL SENDER
    # =================================================
    def send_email(
        self,
        recipients,
        subject,
        header,
        intro,
        greeting="Hello,",
        color="#28a745",
        icon="✅",
        cc=None,
        extra_message="",
        sender=None,
        reply_to=None
    ):
        from company.company.api import is_hrms_notification_enabled
        if not is_hrms_notification_enabled("leave_notification"):
            return
        
        # Determine background color for leave details block
        bg_color = "#f0fff4" # default green-ish
        if color == "#dc3545": bg_color = "#fff5f5" # red-ish
        elif color == "#ffc107": bg_color = "#fffdeb" # yellow-ish
        elif color == "#0062cc": bg_color = "#f0f7ff" # blue-ish

        leave_details = f"""
        <div style="background:{bg_color}; padding:15px; border-radius:8px; margin-top:20px; border:1px solid rgba(0,0,0,0.05);">
            <table style="width:100%; border-collapse:collapse;">
                <tr style="border-bottom: 1px solid rgba(0,0,0,0.05);">
                    <td style="padding:10px 0; color:#555;"><b>Employee</b></td>
                    <td style="padding:10px 0; text-align:right;">{self.employee_name}</td>
                </tr>
                <tr style="border-bottom: 1px solid rgba(0,0,0,0.05);">
                    <td style="padding:10px 0; color:#555;"><b>Leave Type</b></td>
                    <td style="padding:10px 0; text-align:right;">{self.leave_type}</td>
                </tr>
                <tr style="border-bottom: 1px solid rgba(0,0,0,0.05);">
                    <td style="padding:10px 0; color:#555;"><b>From</b></td>
                    <td style="padding:10px 0; text-align:right;">{formatdate(self.from_date)}</td>
                </tr>
                <tr style="border-bottom: 1px solid rgba(0,0,0,0.05);">
                    <td style="padding:10px 0; color:#555;"><b>To</b></td>
                    <td style="padding:10px 0; text-align:right;">{formatdate(self.to_date)}</td>
                </tr>
                <tr>
                    <td style="padding:10px 0; color:#555;"><b>Total Days</b></td>
                    <td style="padding:10px 0; text-align:right;">{self.total_days}</td>
                </tr>
            </table>
        </div>
        """

        message = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; padding: 40px 20px;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="background-color: {color}; padding: 15px 20px; color: #ffffff; border-bottom: 4px solid rgba(0,0,0,0.1);">
                    <table style="width:100%; border-collapse:collapse;">
                        <tr>
                            <td style="vertical-align: middle; width: 30px; font-size: 22px; line-height: 1;">
                                {icon}
                            </td>
                            <td style="vertical-align: middle; padding-left: 8px; font-size: 18px; font-weight: bold; line-height: 1;">
                                {header}
                            </td>
                        </tr>
                    </table>
                </div>
                
                <div style="padding: 30px; color: #333;">
                    <p style="font-size: 16px; margin-bottom: 5px;">{greeting}</p>
                    <p style="font-size: 15px; line-height: 1.5; color: #555;">{intro}</p>
                    
                    {leave_details}
                    
                    {extra_message}
                    
                    <!-- Action Button -->
                    <div style="text-align: center; margin-top: 30px;">
                        <a href="{get_url('leaves')}" 
                           style="background-color: {color}; color: #ffffff; padding: 12px 25px; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block;">
                            View Leave Application
                        </a>
                    </div>
                </div>
            </div>
            <div style="text-align: center; margin-top: 20px; color: #888; font-size: 12px;">
                This is an automated notification from Innoblitz ERP.
            </div>
        </div>
        """

        frappe.sendmail(
            recipients=[r for r in recipients if r],
            cc=cc,
            subject=subject,
            message=message,
            sender=sender,
            reply_to=reply_to,
            reference_doctype="Leave Application",
            reference_name=self.name
        )


def send_submit_notification(doc_name, submitter_user):
    """
    Background job to send submit notification to HR.
    Sets the session user to ensure InnoChat identifies the correct employee sender.
    """
    if not doc_name or not submitter_user:
        return
        
    # Set the session user to the actual submitter so existing notification logic 
    # uses the correct sender for chat messages.
    frappe.session.user = submitter_user
    
    try:
        doc = frappe.get_doc("Leave Application", doc_name)
        doc.send_submit_mail_to_hr()
    except Exception:
        frappe.log_error(title="Leave Application Background Notification Error")
