app_name = "artem_erp"
app_title = "Artem Healthtech ERP"
app_publisher = "Artem Healthtech"
app_description = "ERPNext and HRMS customizations for Artem Healthtech"
app_email = "support@artemhealthtech.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "artem_erp",
# 		"logo": "/assets/artem_erp/logo.png",
# 		"title": "Artem ERP",
# 		"route": "/artem_erp",
# 		"has_permission": "artem_erp.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/artem_erp/css/artem_erp.css"
# app_include_js = "/assets/artem_erp/js/artem_erp.js"

# include js, css files in header of web template
# web_include_css = "/assets/artem_erp/css/artem_erp.css"
# web_include_js = "/assets/artem_erp/js/artem_erp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "artem_erp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
doctype_js = {
    "Shift Assignment": "public/js/shift_assignment.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "artem_erp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

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
# 	"methods": "artem_erp.utils.jinja_methods",
# 	"filters": "artem_erp.utils.jinja_filters"
# }

# Migration
# ------------------
after_migrate = "artem_erp.install.after_migrate"

# Installation
# ------------

# before_install = "artem_erp.install.before_install"
after_install = "artem_erp.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "artem_erp.uninstall.before_uninstall"
# after_uninstall = "artem_erp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "artem_erp.utils.before_app_install"
# after_app_install = "artem_erp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "artem_erp.utils.before_app_uninstall"
# after_app_uninstall = "artem_erp.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "artem_erp.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "artem_erp.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
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
# 		"artem_erp.tasks.all"
# 	],
# 	"daily": [
# 		"artem_erp.tasks.daily"
# 	],
# 	"hourly": [
# 		"artem_erp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"artem_erp.tasks.weekly"
# 	],
# 	"monthly": [
# 		"artem_erp.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "artem_erp.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
extend_doctype_class = {
	"Employee Checkin": "artem_erp.override.employee_checkin.CustomEmployeeCheckin"
}

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "artem_erp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "artem_erp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["artem_erp.utils.before_request"]
# after_request = ["artem_erp.utils.after_request"]

# Job Events
# ----------
# before_job = ["artem_erp.utils.before_job"]
# after_job = ["artem_erp.utils.after_job"]

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
# 	"artem_erp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

