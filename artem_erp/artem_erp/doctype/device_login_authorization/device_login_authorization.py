import uuid

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class DeviceLoginAuthorization(Document):
	def before_insert(self):
		if not self.token_string:
			self.token_string = str(uuid.uuid4())
		if not self.request_date:
			self.request_date = now_datetime()
		if not self.last_login_time:
			self.last_login_time = now_datetime()
		if not self.status:
			self.status = "Pending Onboarding"

		# Ensure employee is linked
		if not self.employee and self.user_id:
			self.employee = frappe.db.get_value(
				"Employee", {"user_id": self.user_id, "status": "Active"}, "name"
			)
			if not self.employee:
				self.employee = frappe.db.get_value("Employee", {"user_id": self.user_id}, "name")

		if self.employee and not self.employee_name:
			self.employee_name = frappe.db.get_value("Employee", self.employee, "employee_name")

	def validate(self):
		# Prevent non-pending initial creation
		if self.is_new() and self.status != "Pending Onboarding":
			self.status = "Pending Onboarding"

		# Check previous status to detect state transition
		prev_doc = self.get_doc_before_save()
		prev_status = prev_doc.status if prev_doc else "Pending Onboarding"

		# If status is changing, enforce reporting manager permissions
		if self.status != prev_status:
			self.validate_status_transition(prev_status, self.status)

		if self.status == "Blocked" and not (self.remarks and self.remarks.strip()):
			frappe.throw(_("Remarks are mandatory when blocking a device."))

	def validate_status_transition(self, prev_status, next_status):
		# Only Reporting Manager, System Manager, or Administrator can change status
		self.check_reporting_manager_permission()

		# Disallow changing from Blocked
		if prev_status == "Blocked":
			frappe.throw(_("A blocked device authorization cannot be reactivated."))

		if next_status == "Blocked" and not (self.remarks and self.remarks.strip()):
			frappe.throw(_("Remarks are mandatory when blocking a device."))

		# Restriction: Only one device token can be in the Authorized state for a user at a time.
		# If a user already has an authorized device token, any other device registration request
		# for the same user that is in Pending Onboarding cannot be authorized until the existing authorized token is Blocked.
		if next_status == "Authorized":
			existing_authorized = frappe.db.get_value(
				"Device Login Authorization",
				{
					"user_id": self.user_id,
					"status": "Authorized",
					"name": ["!=", self.name or ""],
					"docstatus": ["<", 2],
				},
				["name", "device_information"],
				as_dict=True,
			)

			if existing_authorized:
				frappe.throw(
					_(
						"User '{0}' already has an authorized device ({1}). "
						"Only one device can be in the Authorized state at a time. "
						"Any other device request cannot be authorized until the existing authorized device is Blocked."
					).format(self.user_id, existing_authorized.name)
				)

			# Restriction: The same device token cannot be authorized for another user.
			if self.token_string:
				other_user_authorized = frappe.db.get_value(
					"Device Login Authorization",
					{
						"token_string": self.token_string,
						"user_id": ["!=", self.user_id],
						"status": "Authorized",
						"name": ["!=", self.name or ""],
						"docstatus": ["<", 2],
					},
					["name", "user_id"],
					as_dict=True,
				)

				if other_user_authorized:
					frappe.throw(
						_(
							"This device is already authorized for user '{0}' ({1}). "
							"The same device cannot be authorized for another user."
						).format(other_user_authorized.user_id, other_user_authorized.name)
					)

		# If moving to Authorized or Blocked, record auditor info
		self.authorized_by = frappe.session.user
		self.authorization_date = now_datetime()

	def check_reporting_manager_permission(self):
		user = frappe.session.user
		if not user:
			frappe.throw(_("User session required to perform this action."))

		# Administrator & System Manager always have permission
		if user == "Administrator" or "System Manager" in frappe.get_roles(user):
			return True

		# Employee cannot self-approve
		if self.user_id and user == self.user_id:
			frappe.throw(
				_("Self approval is not allowed. Employees cannot authorize or block their own devices.")
			)

		# Verify Reporting Manager
		if not self.employee:
			frappe.throw(_("Cannot verify reporting manager: No employee associated with this request."))

		reports_to = frappe.db.get_value("Employee", self.employee, "reports_to")
		if not reports_to:
			frappe.throw(_("Employee has no Reporting Manager configured. Please contact System Manager."))

		manager_user = frappe.db.get_value("Employee", reports_to, "user_id")
		if manager_user != user:
			frappe.throw(
				_("Only the employee's Reporting Manager ({0}) can authorize or block this device.").format(
					manager_user or reports_to
				)
			)

		return True

	def on_update(self):
		if self.status == "Authorized":
			self.apply_authorized()
		elif self.status == "Blocked":
			self.apply_blocked()

	def before_update_after_submit(self):
		self.validate()

	def on_update_after_submit(self):
		if self.status == "Authorized":
			self.apply_authorized()
		elif self.status == "Blocked":
			self.apply_blocked()

	def on_submit(self):
		if self.status == "Pending Onboarding":
			frappe.throw(
				_("Cannot submit a Device Login Authorization record while in Pending Onboarding status.")
			)
		elif self.status == "Authorized":
			self.apply_authorized()
		elif self.status == "Blocked":
			self.apply_blocked()

	def on_cancel(self):
		# If this authorized device is cancelled, revoke user's authorized token
		if self.user_id:
			user_token = frappe.db.get_value("User", self.user_id, "custom_authorized_device_token")
			if user_token == self.token_string:
				frappe.db.set_value(
					"User",
					self.user_id,
					{
						"custom_authorized_device_token": "",
						"custom_device_authorization_status": "Pending Onboarding",
					},
				)
				frappe.sessions.clear_sessions(user=self.user_id, force=True)

	def apply_authorized(self):
		if not self.user_id:
			return

		user_doc = frappe.get_doc("User", self.user_id)
		user_doc.custom_authorized_device_token = self.token_string
		user_doc.custom_device_authorization_status = "Authorized"
		user_doc.flags.ignore_permissions = True
		user_doc.save()

	def apply_blocked(self):
		if not self.user_id:
			return

		user_doc = frappe.get_doc("User", self.user_id)
		# Only clear user token if it matches this blocked token
		if user_doc.custom_authorized_device_token == self.token_string:
			user_doc.custom_authorized_device_token = ""

			# Check if another authorized device exists for this user
			other_auth = frappe.db.get_value(
				"Device Login Authorization",
				{
					"user_id": self.user_id,
					"status": "Authorized",
					"name": ["!=", self.name],
					"docstatus": ["<", 2],
				},
				"token_string",
			)

			if other_auth:
				user_doc.custom_authorized_device_token = other_auth
				user_doc.custom_device_authorization_status = "Authorized"
			else:
				user_doc.custom_device_authorization_status = "Pending Onboarding"

			user_doc.flags.ignore_permissions = True
			user_doc.save()

			# Terminate active sessions for that user
			frappe.sessions.clear_sessions(user=self.user_id, force=True)

	@frappe.whitelist()
	def authorize_device(self, remarks: str | None = None):
		self.check_reporting_manager_permission()
		if remarks:
			self.remarks = remarks
		self.status = "Authorized"
		self.authorized_by = frappe.session.user
		self.authorization_date = now_datetime()
		if self.docstatus == 0:
			self.submit()
		else:
			self.save()
		return {"status": self.status, "name": self.name}

	@frappe.whitelist()
	def block_device(self, remarks: str | None = None):
		self.check_reporting_manager_permission()
		if remarks:
			self.remarks = remarks
		if not (self.remarks and self.remarks.strip()):
			frappe.throw(_("Remarks are mandatory when blocking a device."))
		self.status = "Blocked"
		self.authorized_by = frappe.session.user
		self.authorization_date = now_datetime()
		if self.docstatus == 0:
			self.submit()
		else:
			self.save()
		return {"status": self.status, "name": self.name}


def get_permission_query_conditions(user=None):
	if not user:
		user = frappe.session.user

	if (
		user == "Administrator"
		or "System Manager" in frappe.get_roles(user)
		or "HR Manager" in frappe.get_roles(user)
	):
		return ""

	user_emp = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
	if not user_emp:
		user_emp = frappe.db.get_value("Employee", {"user_id": user}, "name")

	conditions = [f"`tabDevice Login Authorization`.`user_id` = {frappe.db.escape(user)}"]

	if user_emp:
		conditions.append(
			f"`tabDevice Login Authorization`.`employee` IN (SELECT name FROM `tabEmployee` WHERE reports_to = {frappe.db.escape(user_emp)})"
		)

	return f"({' OR '.join(conditions)})"


def has_permission(doc, ptype="read", user=None):
	if not user:
		user = frappe.session.user

	if (
		user == "Administrator"
		or "System Manager" in frappe.get_roles(user)
		or "HR Manager" in frappe.get_roles(user)
	):
		return True

	is_owner = doc.user_id == user

	# Check if user is the reporting manager
	is_manager = False
	if doc.employee:
		reports_to = frappe.db.get_value("Employee", doc.employee, "reports_to")
		if reports_to:
			manager_user = frappe.db.get_value("Employee", reports_to, "user_id")
			if manager_user == user:
				is_manager = True

	if ptype == "read":
		if is_owner or is_manager or "HR User" in frappe.get_roles(user):
			return True
		return False

	if ptype in ("write", "submit", "cancel"):
		# User cannot write/submit their own device authorization
		if is_owner and not is_manager:
			return False
		if is_manager:
			return True

	return False
