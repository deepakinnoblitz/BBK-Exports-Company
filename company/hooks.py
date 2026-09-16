app_name = "company"
app_title = "Innoblitz"
app_publisher = "deepak"
app_description = "Company "
app_email = "deepak@gmail.com"
app_license = "mit"

app_include_js = [
    # "/assets/company/js/leads.js",
    # "/assets/company/js/quotation.js",
    "/assets/company/js/estimation.js",
    "/assets/company/js/invoice.js",
    "/assets/company/js/purchase.js",
    # "/assets/company/js/expenses.js",
    "/assets/company/js/custom.js?v=1",
    "/assets/company/js/attendance.js",
    "/assets/company/js/salary_slip.js",
    "/assets/company/js/salary_list.js",
    "/assets/company/js/attendance_list.js",
    "/assets/company/js/wfh_attendance_list.js",
    "/assets/company/js/firebase_init.js?v=2",
    "/assets/company/js/pwa_init.js?v=2",
    # "/assets/company/js/socket.io.min.js",
    # "/assets/company/js/socket_init.js",
    "/assets/company/js/custom_link_formatter.js",
    "/assets/company/js/custom_badge.js",
    "/assets/company/js/custom_back_button.js",
    "/assets/company/js/birthday_animation.js",
    "/assets/company/js/custom_sidebar_menu.js",
    # "/assets/company/js/default_phone_no.js",
    "/assets/company/js/logo.js",
    "/assets/company/js/clear_cache.js?v=2",
    # "/assets/company/js/profile_picture.js",
    "/assets/company/js/event_popup.js",
    "/assets/company/js/parent_sidebar.js?v=1",
    "/assets/company/js/global_list_actions.js",
    # "/assets/company/js/expense_list.js",
    # "/assets/company/js/income_list.js",
    "/assets/company/js/sidebar-active-state.js",
    "/assets/company/js/expense_tracker.js?v=2",
    "/assets/company/js/auto_refresh.js?v=3",
    "/assets/company/js/list_pagination.js",
    "/assets/company/js/desk_redirect.js?v=4",
]

app_include_css = "/assets/company/css/custom.css?v=17"


doc_events = {
    "Estimation": {
        "before_insert": "company.company.api.before_insert_estimation"
    },
    "Invoice": {
        "before_insert": "company.company.api.before_insert_invoice"
    },
    "Invoice Collection": {
        "after_insert": "company.company.api.update_invoice_received_balance",
        "validate": "company.company.api.validate_invoice_collection",
        "on_update": "company.company.api.update_invoice_received_balance",
        "on_trash": "company.company.api.update_invoice_received_balance"
    },
    "Purchase": {
        "validate": "company.company.api.validate_purchase_with_collections"
    },
    "Purchase Collection": {
        "validate": "company.company.api.validate_purchase_collection",
        "on_update": "company.company.api.update_purchase_paid_balance",
        "on_trash": "company.company.api.update_purchase_paid_balance"
    },
    "Expenses": {
        "before_insert": "company.company.api.before_insert_expense"
    },
    "Leave Application": {
        "validate": "company.company.api.validate_leave_balance",
        "before_submit": "company.company.api.validate_leave_balance",
        "on_submit": [
            "company.company.api.create_unread_entry_for_hr"
        ],
        "on_change": [
            # "company.company.api.update_permission_allocation"
            "company.company.api.update_leave_allocation"
        ],
        "after_insert": "company.company.api.auto_submit_leave_application"
    },
    "Employee Evaluation": {
        "after_insert": "company.company.api.auto_submit_employee_evaluation"
    },
    # "Attendance": {
    #     "on_update": "company.company.api.update_leave_allocation_from_attendance",
    # },
    "WFH Attendance": {
        "on_submit": "company.company.api.create_unread_entry_for_hr"
    },
    "Reimbursement Claim": {
        "after_insert": "company.company.api.create_unread_entry_for_hr"
    },
    "Request": {
        "after_insert": "company.company.api.create_unread_entry_for_hr"
    },
    "Asset Request": {
        "after_insert": "company.company.api.create_unread_entry_for_hr",
        "on_update": "company.company.api.create_unread_entry_for_employee"
    },
    # "Salary Slip": {
    #     "on_submit": "company.company.api.salary_slip_after_submit"
    # },
    "Attendance": {
        "after_insert": "company.company.evaluation_automation.handle_attendance_automation",
        "on_update": "company.company.evaluation_automation.handle_attendance_automation"
    },
    "Task Manager": {
        "on_update": "company.company.evaluation_automation.handle_task_automation"
    },
    "Employee Session": {
        "after_insert": "company.company.evaluation_automation.handle_daily_log_automation",
        "on_update": "company.company.evaluation_automation.handle_daily_log_automation"
    },
    "Employee Break": {
        "after_insert": "company.company.presence_api.update_session_break_hours",
        "on_update": "company.company.presence_api.update_session_break_hours",
        "on_trash": "company.company.presence_api.update_session_break_hours"
    },
    "Event": {
        "on_update": [
            "company.company.crm_api.sync_event_to_call",
            "company.company.crm_api.sync_event_to_meeting",
            "company.company.crm_api.sync_event_to_todo"
        ],
        "validate": "company.company.crm_api.validate_event",
        "on_trash": "company.company.crm_api.delete_linked_record_on_event_trash"
    },
    "ToDo": {
        "after_insert": "company.company.crm_api.create_event_for_todo",
        "on_update": "company.company.crm_api.update_event_for_todo",
        "on_trash": "company.company.crm_api.delete_event_for_todo"
    },
    "Lead": {
        "on_update": "company.company.doctype.crm_whatsapp_automation.crm_whatsapp_automation.evaluate_automations",
        "on_update": "company.company.doctype.crm_email_automation.crm_email_automation.evaluate_automations"
    },
    "Deal": {
        "on_update": "company.company.doctype.crm_whatsapp_automation.crm_whatsapp_automation.evaluate_automations",
        "on_update": "company.company.doctype.crm_email_automation.crm_email_automation.evaluate_automations"
    }
}


scheduler_events = {
    "all": [
        "company.company.employee_remainder_api.check_and_enqueue_reminders",
        "company.company.employee_remainder_api.process_remainder_queue",
        "company.company.presence_api.process_auto_breaks",
        "company.company.reminders.run_email_reminders",
        "company.company.doctype.crm_email_automation.crm_email_automation.process_email_automations"
    ],
    "daily": [
        "company.company.api.update_expired_renewals",
        "company.company.presence_api.daily_reset",
        "company.company.doctype.employee_monthly_award.employee_monthly_award.calculate_monthly_awards",
    ]
}


# Website Route Rules
# -------------------
# Handle client-side routing for React SPA
# Website Route Rules
# -------------------
# Handle client-side routing for React SPA
# List of all top-level routes used by the React SPA
spa_routes = [
    "leads", "users", "user-permissions", "user-profile", "my-profile", "chat",
    "contacts", "accounts", "deals", "events", "calls", "meetings", "todo",
    "products", "invoices", "estimations", "blog", "employee", "attendance",
    "leaves", "leave-allocations", "payroll", "requests", "announcements",
    "asset", "asset-assignments", "timesheets", "wfh-attendance", "import-attendance",
    "timesheet-reports", "expenses", "crm-expense-tracker", "expense-tracker",
    "holidays", "reimbursement-claims", "renewals-tracker", "salary-slips",
    "job-openings", "job-applicants", "interviews", "purchase",
    "invoice-collections", "purchase-collections", "reports", "access-denied",
    "sign-in", "salary-slips", "user-profile", "task-manager", "daily-log", "badges", 
    "employee-monthly-award" , "employee-evaluation", "reminders", "employee-referrals", 
    "employee-overall-report", "department", "project", "activity-type", "claim-type", 
    "bank-account", "asset-category", "asset-category", "performance-criteria-category", 
    "designation", "salary-structure-component", "leave-type", "settings", "master", "proposals",
    "email-templates", "email-campaigns", "email-automations", "email-settings", "whatsapp-templates",
    "whatsapp-automation", "whatsapp-settings", "whatsapp-campaigns", "lead-integration", "sales-target-entry", "role-permissions"
]

website_route_rules = []
for r in spa_routes:
    website_route_rules.append({"from_route": f"/{r}/<path:app_path>", "to_route": "crm"})
    website_route_rules.append({"from_route": f"/{r}", "to_route": "crm"})

home_page = "crm"


extend_bootinfo = "company.company.api.extend_bootinfo"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "company",
# 		"logo": "/assets/company/logo.png",
# 		"title": "Company",
# 		"route": "/company",
# 		"has_permission": "company.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/company/css/company.css"
# app_include_js = "/assets/company/js/company.js"

# include js, css files in header of web template
# web_include_css = "/assets/company/css/company.css"
# web_include_js = "/assets/company/js/company.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "company/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "company/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
role_home_page = {
    "Employee": "crm",
    "HR": "crm"
}

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "company.utils.jinja_methods",
# 	"filters": "company.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "company.install.before_install"
# after_install = "company.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "company.uninstall.before_uninstall"
# after_uninstall = "company.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "company.utils.before_app_install"
# after_app_install = "company.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "company.utils.before_app_uninstall"
# after_app_uninstall = "company.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "company.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways
permission_query_conditions = {
	"Leave Application": "company.company.api.get_leave_application_permission_query_conditions",
	"Request": "company.company.api.get_request_permission_query_conditions",
	"WFH Attendance": "company.company.api.get_wfh_attendance_permission_query_conditions",
	"Reimbursement Claim": "company.company.api.get_reimbursement_claim_permission_query_conditions",
}
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"company.tasks.all"
# 	],
# 	"daily": [
# 		"company.tasks.daily"
# 	],
# 	"hourly": [
# 		"company.tasks.hourly"
# 	],
# 	"weekly": [
# 		"company.tasks.weekly"
# 	],
# 	"monthly": [
# 		"company.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "company.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "company.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "company.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "company.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["company.utils.before_request"]
# after_request = ["company.utils.after_request"]

# Job Events
# ----------
# before_job = ["company.utils.before_job"]
# after_job = ["company.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"company.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
    {"dt": "Custom Field", "filters": [["fieldname", "=", "custom_permissions"]]}
]

