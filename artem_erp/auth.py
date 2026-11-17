import frappe


def redirect_employee_on_login(login_manager):
	"""
	Hooked into frappe's `on_login` event in `LoginManager.post_login()`.
	Redirects Employee and Manager users to their Employee Dashboard workspace upon login.
	System Managers and HR Managers continue to have standard desk access.
	"""
	user = login_manager.user
	if not user or user in ("Guest", "Administrator"):
		return

	roles = set(frappe.get_roles(user))

	# Only redirect Employee and Manager roles
	if not ({"Employee", "Manager"} & roles):
		return

	# Do not redirect administrative roles who need full standard desk access
	if {"System Manager", "HR Manager", "HR User"} & roles:
		return

	target_url = "/desk/employee-dashboard"

	# 1. Ensure User default_workspace is set to Employee Dashboard
	try:
		if frappe.db.get_value("User", user, "default_workspace") != "Employee Dashboard":
			frappe.db.set_value("User", user, "default_workspace", "Employee Dashboard")
	except Exception:
		pass

	# 2. Cache the home_page for this user session
	frappe.cache.hset("home_page", user, target_url)

	# 3. Cache redirect_after_login
	frappe.cache.hset("redirect_after_login", user, target_url)

	# 4. Populate response dictionary for login handlers
	if hasattr(frappe.local, "response") and isinstance(frappe.local.response, dict):
		frappe.local.response["home_page"] = target_url
		frappe.local.response["redirect_to"] = target_url
