import uuid

import frappe
from frappe import _
from frappe.utils import cstr, now_datetime

COOKIE_NAME = "device_token"
HEADER_NAME = "X-Device-Token"
COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year in seconds


def get_device_token_from_request():
	"""
	Extracts device token from:
	1. Request cookies ('device_token')
	2. Request HTTP headers ('X-Device-Token' or 'device-token')
	3. Form dictionary ('device_token')
	"""
	token = None

	if hasattr(frappe.local, "request") and frappe.local.request:
		# Check cookies
		if hasattr(frappe.local.request, "cookies") and frappe.local.request.cookies:
			token = frappe.local.request.cookies.get(COOKIE_NAME)

		# Check headers if not in cookie
		if not token:
			token = frappe.get_request_header(HEADER_NAME) or frappe.get_request_header("device-token")

	# Check form_dict (mobile app payloads or query params)
	if not token and hasattr(frappe.local, "form_dict") and frappe.local.form_dict:
		token = frappe.local.form_dict.get(COOKIE_NAME)

	return token.strip() if token else None


def set_device_token_response(token):
	"""
	Stores token in:
	1. HttpOnly, SameSite=Lax, Secure (if HTTPS) cookie
	2. Response header 'X-Device-Token'
	3. frappe.response dictionary
	"""
	if not token:
		return

	# Set cookie
	if hasattr(frappe.local, "cookie_manager") and frappe.local.cookie_manager:
		secure = False
		if hasattr(frappe.local, "request") and frappe.local.request:
			secure = frappe.local.request.scheme == "https"

		frappe.local.cookie_manager.set_cookie(
			COOKIE_NAME,
			token,
			max_age=COOKIE_MAX_AGE,
			httponly=True,
			samesite="Lax",
			secure=secure,
		)

	# Set response header
	if hasattr(frappe.local, "response_headers") and frappe.local.response_headers is not None:
		try:
			if hasattr(frappe.local.response_headers, "set"):
				frappe.local.response_headers.set(HEADER_NAME, token)
			elif hasattr(frappe.local.response_headers, "append"):
				frappe.local.response_headers.append((HEADER_NAME, token))
			else:
				frappe.local.response_headers[HEADER_NAME] = token
		except Exception:
			pass

	# Set frappe.response for mobile API callers
	if hasattr(frappe.local, "response") and isinstance(frappe.local.response, dict):
		frappe.local.response["device_token"] = token


def get_device_info():
	"""
	Retrieves client User-Agent or device info from request headers.
	"""
	if hasattr(frappe.local, "request") and frappe.local.request:
		user_agent = frappe.get_request_header("User-Agent") or "Unknown Device"
		return user_agent[:140]
	return "Unknown Device"


def get_employee_for_user(user):
	"""
	Finds the Employee record linked to the given user.
	"""
	emp = frappe.db.get_value(
		"Employee",
		{"user_id": user, "status": "Active"},
		["name", "employee_name", "reports_to"],
		as_dict=True,
	)
	if not emp:
		emp = frappe.db.get_value(
			"Employee",
			{"user_id": user},
			["name", "employee_name", "reports_to"],
			as_dict=True,
		)
	return emp


def log_device_audit(user, message, status="Failed"):
	"""
	Audit logging for device login attempts.
	"""
	try:
		ip = getattr(frappe.local, "request_ip", None) or "127.0.0.1"
		device_info = get_device_info()
		log_msg = f"[Device Authorization] User: {user} | IP: {ip} | Device: {device_info} | Status: {status} | {message}"
		frappe.logger("artem_erp.device_login").info(log_msg)
	except Exception:
		pass


def on_login(login_manager):
	"""
	Hooked into frappe's `on_login` event in `LoginManager.post_login()`.
	Validates device authorization before a session is created.
	"""
	user = login_manager.user
	if not user or user in ("Guest", "Administrator"):
		return

	enable_restriction = frappe.db.get_value("User", user, "custom_enable_device_login_restriction")
	if not enable_restriction:
		return

	token = get_device_token_from_request()
	device_info = get_device_info()
	employee = get_employee_for_user(user)

	# -------------------------------------------------------------------------
	# RULE 2: If the same user has an authorized device token but the token
	# received from the browser cookie is different, prevent the login.
	# -------------------------------------------------------------------------
	user_authorized_token = frappe.db.get_value("User", user, "custom_authorized_device_token")
	if user_authorized_token:
		if not token or token != user_authorized_token:
			set_device_token_response(token)
			log_device_audit(
				user,
				"Login prevented: Token does not match user's authorized device token",
				status="Rejected",
			)
			frappe.throw(
				_("Access Denied: This browser or device is not your authorized device."),
				frappe.AuthenticationError,
			)

	# -------------------------------------------------------------------------
	# RULE 3: If a different user attempts to log in using a browser cookie
	# containing a device token that is already authorized for another user,
	# prevent the login.
	# -------------------------------------------------------------------------
	if token:
		other_auth = frappe.db.get_value(
			"Device Login Authorization",
			{
				"token_string": token,
				"status": "Authorized",
				"user_id": ["!=", user],
				"docstatus": ["<", 2],
			},
			["name", "user_id"],
			as_dict=True,
		)
		if not other_auth:
			other_user = frappe.db.get_value(
				"User",
				{
					"custom_authorized_device_token": token,
					"name": ["!=", user],
				},
				"name",
			)
			if other_user:
				other_auth = {"user_id": other_user}

		if other_auth:
			set_device_token_response(token)
			log_device_audit(
				user,
				f"Login prevented: Token is already authorized for another user ({other_auth['user_id']})",
				status="Rejected",
			)
			frappe.throw(
				_(
					"Access Denied: This browser or device is already authorized for another user ({0})."
				).format(other_auth["user_id"]),
				frappe.AuthenticationError,
			)

	# Check for existing record for THIS user with THIS token
	record = None
	if token:
		record = frappe.db.get_value(
			"Device Login Authorization",
			{"token_string": token, "user_id": user},
			["name", "status", "docstatus"],
			as_dict=True,
		)

	# If record is Blocked, prevent login for restricted users
	if record and record.status == "Blocked":
		set_device_token_response(token)
		log_device_audit(user, f"Login attempt from blocked device ({record.name})", status="Blocked")
		frappe.throw(
			_(
				"Access Denied: This browser or device has been blocked. Please contact your Reporting Manager."
			),
			frappe.AuthenticationError,
		)

	# -------------------------------------------------------------------------
	# RULE 1: Allow login without authorization. Users should be allowed to log
	# in even if their previous login is still pending manager authorization.
	# The system updates the last_login_time field with the current login time.
	# -------------------------------------------------------------------------
	if record:
		set_device_token_response(token)
		frappe.db.set_value("Device Login Authorization", record.name, "last_login_time", now_datetime())
		frappe.db.commit()  # nosemgrep
		log_device_audit(
			user,
			f"Successful login from device ({record.name}) - Status: {record.status}",
			status=record.status,
		)
		return

	# If no record exists for THIS user with this token:
	# Keep the existing browser token so both users share the device token,
	# or generate a new token if browser has no token.
	use_token = token if token else str(uuid.uuid4())
	set_device_token_response(use_token)

	auth_doc = frappe.get_doc(
		{
			"doctype": "Device Login Authorization",
			"user_id": user,
			"employee": employee.name if employee else None,
			"employee_name": employee.employee_name if employee else None,
			"token_string": use_token,
			"status": "Pending Onboarding",
			"device_information": device_info,
			"request_date": now_datetime(),
			"last_login_time": now_datetime(),
		}
	)
	auth_doc.flags.ignore_permissions = True
	auth_doc.insert()

	curr_status = frappe.db.get_value("User", user, "custom_device_authorization_status")
	if curr_status != "Authorized":
		frappe.db.set_value("User", user, "custom_device_authorization_status", "Pending Onboarding")

	frappe.db.commit()  # nosemgrep
	log_device_audit(
		user,
		f"New device registered ({auth_doc.name}) for token {use_token} - Login allowed",
		status="Pending",
	)
	return


def before_request():
	"""
	Validates active session requests against the user's authorized device token.
	Invalidates the session if device token is revoked, blocked, or missing.
	"""
	if not hasattr(frappe.local, "session") or not frappe.local.session:
		return

	user = frappe.session.user
	if not user or user in ("Guest", "Administrator"):
		return

	# Skip during background migrations or install
	if getattr(frappe.flags, "in_migrate", False) or getattr(frappe.flags, "in_install", False):
		return

	if not hasattr(frappe.local, "request") or not frappe.local.request:
		return

	path = getattr(frappe.local.request, "path", "")
	# Exempt logout or status checking endpoints
	if path in (
		"/api/method/logout",
		"/api/method/login",
		"/api/method/artem_erp.artem_erp.device_login.get_device_authorization_status",
	):
		return

	enable_restriction = frappe.db.get_value("User", user, "custom_enable_device_login_restriction")
	if not enable_restriction:
		return

	token = get_device_token_from_request()
	if not token:
		frappe.sessions.clear_sessions(user=user, force=True)
		frappe.throw(
			_("Session invalidated: Device authorization token missing."),
			frappe.AuthenticationError,
		)

	# Rule 2: If user has an authorized device token, request token must match it
	user_authorized_token = frappe.db.get_value("User", user, "custom_authorized_device_token")
	if user_authorized_token and token != user_authorized_token:
		frappe.sessions.clear_sessions(user=user, force=True)
		frappe.throw(
			_("Session invalidated: This browser or device is not your authorized device."),
			frappe.AuthenticationError,
		)

	# Rule 3: Check if token is authorized for another user
	other_auth = frappe.db.get_value(
		"Device Login Authorization",
		{
			"token_string": token,
			"status": "Authorized",
			"user_id": ["!=", user],
			"docstatus": ["<", 2],
		},
		"user_id",
	)
	if not other_auth:
		other_auth = frappe.db.get_value(
			"User",
			{
				"custom_authorized_device_token": token,
				"name": ["!=", user],
			},
			"name",
		)
	if other_auth:
		frappe.sessions.clear_sessions(user=user, force=True)
		frappe.throw(
			_("Session invalidated: This device token is authorized for another user."),
			frappe.AuthenticationError,
		)

	record = frappe.db.get_value(
		"Device Login Authorization",
		{"token_string": token, "user_id": user},
		["name", "status"],
		as_dict=True,
	)

	if not record:
		frappe.sessions.clear_sessions(user=user, force=True)
		frappe.throw(
			_("Session invalidated: Unrecognized browser or device token."),
			frappe.AuthenticationError,
		)

	if record.status == "Blocked":
		frappe.sessions.clear_sessions(user=user, force=True)
		frappe.throw(
			_("Session invalidated: This browser or device has been blocked."),
			frappe.AuthenticationError,
		)


def validate_user(doc, method=None):
	"""
	Prevents employees from modifying their own device restriction settings or tokens.
	Clears status and token when device restriction is disabled.
	"""
	user = frappe.session.user
	is_admin = not user or user == "Administrator" or "System Manager" in frappe.get_roles(user)

	if not is_admin and user == doc.name:
		prev = doc.get_doc_before_save()
		if prev:
			restricted_fields = [
				"custom_enable_device_login_restriction",
				"custom_authorized_device_token",
				"custom_device_authorization_status",
			]

			for f in restricted_fields:
				if doc.get(f) != prev.get(f):
					frappe.throw(
						_(
							"You are not allowed to change your own device authorization settings ({0})."
						).format(f)
					)

	if not doc.custom_enable_device_login_restriction:
		doc.custom_device_authorization_status = ""
		doc.custom_authorized_device_token = ""


# -------------------------------------------------------------
# Whitelisted API Methods for Frappe HR Mobile App & Web Clients
# -------------------------------------------------------------


@frappe.whitelist(allow_guest=False)
def get_device_authorization_status(token: str | None = None, user: str | None = None):
	"""
	Returns the device authorization status for a token or user.
	Callable by Frappe HR mobile app to check onboarding state.
	"""
	if not token:
		token = get_device_token_from_request()

	if not user and frappe.session.user != "Guest":
		user = frappe.session.user

	if not user and token:
		user = frappe.db.get_value("Device Login Authorization", {"token_string": token}, "user_id")

	if not user:
		return {"status": "Unknown", "is_restricted": False}

	is_restricted = frappe.db.get_value("User", user, "custom_enable_device_login_restriction")
	if not is_restricted:
		return {"status": "Not Restricted", "is_restricted": False, "user": user}

	if not token:
		return {
			"status": "No Token",
			"is_restricted": True,
			"user": user,
			"user_status": frappe.db.get_value("User", user, "custom_device_authorization_status"),
		}

	record = frappe.db.get_value(
		"Device Login Authorization",
		{"token_string": token, "user_id": user},
		["name", "status", "request_date", "authorization_date", "authorized_by"],
		as_dict=True,
	)

	if not record:
		return {"status": "Unregistered", "is_restricted": True, "token": token, "user": user}

	active_token = frappe.db.get_value("User", user, "custom_authorized_device_token")
	is_active = record.status == "Authorized" and active_token == token

	return {
		"status": record.status,
		"is_active_device": is_active,
		"is_restricted": True,
		"token": token,
		"user": user,
		"request_id": record.name,
		"request_date": record.request_date,
		"authorization_date": record.authorization_date,
		"authorized_by": record.authorized_by,
	}


@frappe.whitelist()
def get_my_devices():
	"""
	Lists all device authorizations for the current session user.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Login required."))

	return frappe.get_all(
		"Device Login Authorization",
		filters={"user_id": user},
		fields=[
			"name",
			"device_information",
			"status",
			"request_date",
			"authorization_date",
			"authorized_by",
			"remarks",
		],
		order_by="creation desc",
	)
