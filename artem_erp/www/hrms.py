import frappe

try:
	from hrms.www.hrms import get_boot
except ImportError:

	def get_boot(*args, **kwargs):
		return {}


no_cache = 1


def get_context(context):
	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosempgrep
	context.csrf_token = csrf_token
	context.boot = get_boot()
	context.site_name = frappe.local.site
	if "__messages" not in context.boot:
		context.boot["__messages"] = {}
	context.boot["__messages"]["Login to Frappe HR"] = "Login to Artem HR"
	context.boot["__messages"]["Install Frappe HR"] = "Install Artem HR"
	context.boot["__messages"]["Frappe HR"] = "Artem HR"
	return context
