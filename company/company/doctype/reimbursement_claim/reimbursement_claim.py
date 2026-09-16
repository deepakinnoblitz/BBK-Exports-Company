import json
import frappe
from frappe.model.document import Document

class ReimbursementClaim(Document):
    def on_submit(self):
        """Enqueue HR notifications in background to avoid submit delay"""
        # 🛡️ Prevent double enqueuing in the same request
        if frappe.flags.get(f"enqueued_submit_notification_{self.name}"):
            return

        frappe.enqueue(
            "company.company.doctype.reimbursement_claim.reimbursement_claim.send_submit_notification",
            doc_name=self.name,
            submitter_user=frappe.session.user,
            enqueue_after_commit=True
        )
        frappe.flags[f"enqueued_submit_notification_{self.name}"] = True

    def after_insert(self):
        """Auto-submit the document immediately after creation"""
        try:
            if self.docstatus == 0:
                self.submit()
                
                # Real-time update for list refresh
                frappe.publish_realtime(
                    event="reimbursement_claim_updated",
                    message={"name": self.name, "status": "Submitted"}
                )
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Auto-Submit Error")

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
                    frappe.log_error(title="Reimbursement Claim: Chat Channel Creation Failed", message=frappe.as_json(log_data))

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
                frappe.log_error(title="Reimbursement Claim Chat Debug", message=frappe.as_json(log_data))
            else:
                log_data["error"] = "Room name could not be determined"
                frappe.log_error(title="Reimbursement Claim Chat Failed", message=frappe.as_json(log_data))
                
        except Exception as e:
            log_data["exception"] = str(e)
            log_data["traceback"] = frappe.get_traceback()
            frappe.log_error(title="Reimbursement Claim Chat Notification Exception", message=frappe.as_json(log_data))

    # ----------------------------------------
    # 2️⃣ + 3️⃣ + 4️⃣ Handle workflow updates after submit
    # ----------------------------------------
    def on_update_after_submit(self):
        before = self.get_doc_before_save()

        # 🚫 HARD STOP: first submit
        if before and before.docstatus == 0 and self.docstatus == 1:
            return

        current_state = self.workflow_state
        previous_state = before.workflow_state if before else None
        
        user = frappe.session.user
        approver_name = frappe.db.get_value("User", user, "full_name")
        approver_email = frappe.db.get_value("User", user, "email")

		# ----------------------------------------
		# 2️⃣ Send approval email ONLY on state transition to Approved
		# ----------------------------------------
        if current_state == "Approved" and previous_state != "Approved":
            frappe.db.set_value(self.doctype, self.name, "approved_by", user, update_modified=False)
            self.notify_employee_on_approval(approver_name, approver_email)

		# ----------------------------------------
		# 4️⃣ Send Paid mail — ONLY on state transition to Paid
		# ----------------------------------------
        if current_state == "Paid" and previous_state != "Paid":
            frappe.db.set_value(self.doctype, self.name, "paid_by", user, update_modified=False)
            self.notify_employee_on_payment(approver_name, approver_email)

        # Real-time update for list refresh
        frappe.publish_realtime(
            event="reimbursement_claim_updated",
            message={"name": self.name, "status": current_state}
        )

    def on_cancel(self):
        current_state = self.workflow_state
        previous_state = self.get_db_value("workflow_state")
        user = frappe.session.user

        approver_name = frappe.db.get_value("User", user, "full_name")
        approver_email = frappe.db.get_value("User", user, "email")
		
        # ----------------------------------------
		# 3️⃣ Send Rejection mail normally
		# ----------------------------------------
        if current_state == "Rejected":
            frappe.db.set_value(self.doctype, self.name, "approved_by", user, update_modified=False)
            self.notify_employee_on_rejection(approver_name, approver_email)

        # Real-time update for list refresh
        frappe.publish_realtime(
            event="reimbursement_claim_updated",
            message={"name": self.name, "status": "Rejected"}
        )


    # -------------------------------------------------------------------
    # 1️⃣ Email — Notify HR on Submission (Blue Theme)
    # -------------------------------------------------------------------
    def notify_hr_on_submission(self):
        # 1️⃣ InnoChat Notification to HR (Separate from email toggle)
        hr_users = self.get_hr_users()
        sender_user = frappe.session.user
        
        content = (
            f"<b>🧾 New Reimbursement Claim Submitted</b><br><br>"
            f"<b>Employee:</b> {self.employee_name}<br>"
            f"<b>Claim Type:</b> {self.claim_type}<br>"
            f"<b>Amount:</b> ₹ {self.amount}<br>"
            f"<b>Date of Expense:</b> {self.date_of_expense}<br><br>"
            f"Please review and take necessary action."
        )

        for receiver in hr_users:
            if receiver != sender_user:
                try:
                    self.send_chat_notification(sender_user, receiver, content)
                except Exception:
                    frappe.log_error(title="Reimbursement Claim Submit Chat Loop Error", message=frappe.get_traceback())

        # 2️⃣ Email Notification (Toggle Dependent)
        from company.company.api import is_hrms_notification_enabled
        if not is_hrms_notification_enabled("reimbursement_notification"):
            return

        hr_settings = self.get_hr_settings()
        hr_email = hr_settings.get("hr_email")
        cc_emails = hr_settings.get("hr_cc_emails")

        if not hr_email:
            return

        employee_email = frappe.db.get_value("Employee", self.employee, "personal_email")
        sender_name = f"{self.employee_name} <{employee_email}>" if employee_email else hr_email

        cc_list = []
        if cc_emails:
            cc_list = [e.strip() for e in cc_emails.replace("\n", ",").split(",") if e.strip()]

        message = f"""
        <div style="font-family:'Poppins',Arial;background:#e6f3ff;padding:40px;">
            <div style="max-width:600px;margin:auto;background:white;border-radius:14px;
                        box-shadow:0 4px 12px rgba(0,128,255,0.15);overflow:hidden;">
                
                <div style="background:#0d6efd;color:white;padding:20px 26px;font-size:18px;font-weight:600;">
                    🧾 New Reimbursement Claim Submitted
                </div>

                <div style="padding:26px;color:#333;line-height:1.6;">
                    <p>Dear HR,</p>
                    <p><b>{self.employee_name}</b> has submitted a reimbursement claim.</p>

                    <table style="width:100%;font-size:13px;margin-top:18px;border-collapse:collapse;">
                        <tr style="background:#f0f7ff;">
                            <td style="padding:10px 12px;font-weight:600;">Claim Type</td>
                            <td style="padding:10px 12px;">{self.claim_type}</td>
                        </tr>
                        <tr style="background:#f7fbff;">
                            <td style="padding:10px 12px;font-weight:600;">Amount</td>
                            <td style="padding:10px 12px;">₹ {self.amount}</td>
                        </tr>
                        <tr style="background:#f0f7ff;">
                            <td style="padding:10px 12px;font-weight:600;">Date of Expense</td>
                            <td style="padding:10px 12px;">{self.date_of_expense}</td>
                        </tr>
                    </table>

                    <div style="text-align:center;margin-top:28px;">
                        <a href="{frappe.utils.get_url('/app/reimbursement-claim/' + self.name)}"
                            style="background:#0d6efd;color:white;padding:12px 24px;text-decoration:none;
                            border-radius:8px;font-weight:500;">Open Claim</a>
                    </div>
                </div>
            </div>
        </div>
        """

        frappe.sendmail(
            recipients=[hr_email],
            cc=cc_list,
            subject=f"🧾 Reimbursement Claim Submitted - {self.employee_name}",
            message=message,
            sender=sender_name,
            reply_to=employee_email or hr_email,
            reference_doctype=self.doctype,
            reference_name=self.name,
        )

    # -------------------------------------------------------------------
    # 2️⃣ Email — Notify Employee on Approval (Green Theme)
    # -------------------------------------------------------------------
    def notify_employee_on_approval(self, approver_name, approver_email):
        # 1️⃣ InnoChat Notification to Employee (Separate from email toggle)
        receiver = self.get_employee_user()
        sender_user = frappe.session.user
        if receiver and receiver != sender_user:
            content = (
                f"<b>✅ Reimbursement Approved</b><br><br>"
                f"<b>Claim Type:</b> {self.claim_type}<br>"
                f"<b>Amount:</b> ₹ {self.amount}<br><br>"
                f"Your reimbursement claim has been approved."
            )
            self.send_chat_notification(sender_user, receiver, content)

        # 2️⃣ Email Notification (Toggle Dependent)
        from company.company.api import is_hrms_notification_enabled
        if not is_hrms_notification_enabled("reimbursement_notification"):
            return

        company_email = frappe.db.get_value("Employee", self.employee, "email")
        personal_email = frappe.db.get_value("Employee", self.employee, "personal_email")

        recipients = [email for email in [company_email, personal_email] if email]

        if not recipients:
            return

        message = f"""
        <div style="font-family:'Poppins',Arial;background:#f1fff4;padding:40px;">
            <div style="max-width:600px;margin:auto;background:white;border-radius:14px;
                box-shadow:0 4px 12px rgba(0,128,0,0.15);overflow:hidden;">
                
                <div style="background:#28a745;color:white;padding:20px 26px;font-size:18px;font-weight:600;">
                    ✅ Reimbursement Approved
                </div>

                <div style="padding:26px;color:#333;">
                    <p>Hello <b>{self.employee_name}</b>,</p>
                    <p>Your reimbursement claim has been <b style="color:#28a745;">approved</b>.</p>

                    <p><b>Approved By:</b> {approver_name} ({approver_email})</p>

                    <table style="width:100%;font-size:13px;margin-top:20px;border-collapse:collapse;">
                        <tr style="background:#e7f9ed;">
                            <td style="padding:10px 12px;font-weight:600;">Claim Type</td>
                            <td style="padding:10px 12px;">{self.claim_type}</td>
                        </tr>
                        <tr style="background:#f5fff7;">
                            <td style="padding:10px 12px;font-weight:600;">Amount</td>
                            <td style="padding:10px 12px;">₹ {self.amount}</td>
                        </tr>
                    </table>

                    <div style="text-align:center;margin-top:28px;">
                        <a href="{frappe.utils.get_url('reimbursement-claims')}"
                        style="background:#28a745;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;">
                        View Claim</a>
                    </div>
                </div>
            </div>
        </div>
        """

        hr_settings = self.get_hr_settings()
        hr_email = hr_settings.get("hr_email")
        hr_name = hr_settings.get("hr_name") or "HR Team"
        sender = f"{hr_name} <{hr_email}>" if hr_email else None

        frappe.sendmail(
            recipients=recipients,
            subject=f"✅ Reimbursement Approved - {self.claim_type}",
            message=message,
            sender=sender,
            reply_to=hr_email,
            reference_doctype=self.doctype,
            reference_name=self.name
        )

    # -------------------------------------------------------------------
    # 3️⃣ Email — Notify Employee on Rejection (Red Theme)
    # -------------------------------------------------------------------
    def notify_employee_on_rejection(self, rejector_name, rejector_email):
        # 1️⃣ InnoChat Notification to Employee (Separate from email toggle)
        receiver = self.get_employee_user()
        sender_user = frappe.session.user
        if receiver and receiver != sender_user:
            content = (
                f"<b>❌ Reimbursement Rejected</b><br><br>"
                f"<b>Claim Type:</b> {self.claim_type}<br>"
                f"<b>Amount:</b> ₹ {self.amount}<br><br>"
                f"Your reimbursement claim has been rejected."
            )
            self.send_chat_notification(sender_user, receiver, content)

        # 2️⃣ Email Notification (Toggle Dependent)
        from company.company.api import is_hrms_notification_enabled
        if not is_hrms_notification_enabled("reimbursement_notification"):
            return

        company_email = frappe.db.get_value("Employee", self.employee, "email")
        personal_email = frappe.db.get_value("Employee", self.employee, "personal_email")

        recipients = [email for email in [company_email, personal_email] if email]

        if not recipients:
            return

        message = f"""
        <div style="font-family:'Poppins',Arial;background:#fff1f1;padding:40px;">
            <div style="max-width:600px;margin:auto;background:white;border-radius:14px;
                box-shadow:0 4px 12px rgba(255,0,0,0.15);overflow:hidden;">
                
                <div style="background:#dc3545;color:white;padding:20px 26px;font-size:18px;font-weight:600;">
                    ❌ Reimbursement Rejected
                </div>

                <div style="padding:26px;color:#333;">
                    <p>Hello <b>{self.employee_name}</b>,</p>
                    <p>Your reimbursement claim has been <b style="color:#dc3545;">rejected</b>.</p>

                    <p><b>Rejected By:</b> {rejector_name} ({rejector_email})</p>

                    <table style="width:100%;font-size:13px;margin-top:20px;border-collapse:collapse;">
                        <tr style="background:#ffe8e8;">
                            <td style="padding:10px 12px;font-weight:600;">Claim Type</td>
                            <td style="padding:10px 12px;">{self.claim_type}</td>
                        </tr>
                        <tr style="background:#fff5f5;">
                            <td style="padding:10px 12px;font-weight:600;">Amount</td>
                            <td style="padding:10px 12px;">₹ {self.amount}</td>
                        </tr>
                    </table>

                    <div style="text-align:center;margin-top:28px;">
                        <a href="{frappe.utils.get_url('reimbursement-claims')}"
                        style="background:#dc3545;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;">
                        View Claim</a>
                    </div>
                </div>
            </div>
        </div>
        """

        hr_settings = self.get_hr_settings()
        hr_email = hr_settings.get("hr_email")
        hr_name = hr_settings.get("hr_name") or "HR Team"
        sender = f"{hr_name} <{hr_email}>" if hr_email else None

        frappe.sendmail(
            recipients=recipients,
            subject=f"❌ Reimbursement Rejected - {self.claim_type}",
            message=message,
            sender=sender,
            reply_to=hr_email,
            reference_doctype=self.doctype,
            reference_name=self.name
        )

    # -------------------------------------------------------------------
    # 4️⃣ Email — Notify Employee on Payment (Green-Blue Theme)
    # -------------------------------------------------------------------
    def notify_employee_on_payment(self, approver_name, approver_email):
        # 1️⃣ InnoChat Notification to Employee (Separate from email toggle)
        receiver = self.get_employee_user()
        sender_user = frappe.session.user
        if receiver and receiver != sender_user:
            content = (
                f"<b>💰 Reimbursement Paid</b><br><br>"
                f"<b>Claim Type:</b> {self.claim_type}<br>"
                f"<b>Amount:</b> ₹ {self.amount}<br>"
                f"<b>Payment Reference:</b> {self.payment_reference or '-'}<br><br>"
                f"Your reimbursement has been paid."
            )
            self.send_chat_notification(sender_user, receiver, content)

        # 2️⃣ Email Notification (Toggle Dependent)
        from company.company.api import is_hrms_notification_enabled
        if not is_hrms_notification_enabled("reimbursement_notification"):
            return

        company_email = frappe.db.get_value("Employee", self.employee, "email")
        personal_email = frappe.db.get_value("Employee", self.employee, "personal_email")

        recipients = [email for email in [company_email, personal_email] if email]

        if not recipients:
            return

        message = f"""
        <div style="font-family:'Poppins',Arial;background:#e7f7ff;padding:40px;">
            <div style="max-width:600px;margin:auto;background:white;border-radius:14px;
                box-shadow:0 4px 12px rgba(0,128,255,0.15);overflow:hidden;">
                
                <div style="background:#007bff;color:white;padding:20px 26px;font-size:18px;font-weight:600;">
                    💰 Reimbursement Paid
                </div>

                <div style="padding:26px;color:#333;">
                    <p>Hello <b>{self.employee_name}</b>,</p>
                    <p>Your reimbursement amount has been <b style="color:#007bff;">paid</b>.</p>

                    <table style="width:100%;font-size:13px;margin-top:20px;border-collapse:collapse;">
                        <tr style="background:#eaf4ff;">
                            <td style="padding:10px 12px;font-weight:600;">Claim Type</td>
                            <td style="padding:10px 12px;">{self.claim_type}</td>
                        </tr>
                        <tr style="background:#f5faff;">
                            <td style="padding:10px 12px;font-weight:600;">Amount Paid</td>
                            <td style="padding:10px 12px;">₹ {self.amount}</td>
                        </tr>
                        <tr style="background:#eaf4ff;">
                            <td style="padding:10px 12px;font-weight:600;">Payment Reference</td>
                            <td style="padding:10px 12px;">{self.payment_reference or '-'}</td>
                        </tr>
                    </table>

                    <div style="text-align:center;margin-top:28px;">
                        <a href="{frappe.utils.get_url('reimbursement-claims')}"
                        style="background:#007bff;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;">
                        View Claim</a>
                    </div>
                </div>
            </div>
        </div>
        """

        hr_settings = self.get_hr_settings()
        hr_email = hr_settings.get("hr_email")
        hr_name = hr_settings.get("hr_name") or "HR Team"
        sender = f"{hr_name} <{hr_email}>" if hr_email else None

        frappe.sendmail(
            recipients=recipients,
            subject=f"💰 Reimbursement Paid - {self.claim_type}",
            message=message,
            sender=sender,
            reply_to=hr_email,
            reference_doctype=self.doctype,
            reference_name=self.name
        )


def send_submit_notification(doc_name, submitter_user):
    """
    Background job to send submit notification to HR.
    Sets the session user to ensure InnoChat identifies the correct employee sender.
    """
    if not doc_name or not submitter_user:
        return

    frappe.session.user = submitter_user

    try:
        doc = frappe.get_doc("Reimbursement Claim", doc_name)
        doc.notify_hr_on_submission()
    except Exception:
        frappe.log_error(title="Reimbursement Claim Background Notification Error")
