# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import format_date, get_url_to_form, today

from artem_erp.auto_email.utils import (
	format_date_range,
	get_artem_settings,
	get_employee_recipient_email,
)


def is_attendance_request_notification_already_sent(request_name: str, status: str) -> bool:
	"""
	Check if a notification email for this Attendance Request and status
	('Pending Approval', 'Approved', 'Rejected') has already been sent or logged.
	"""
	if not request_name or not status:
		return False

	# 1. Check existing Communication records linked to this Attendance Request
	comms = frappe.get_all(
		"Communication",
		filters={
			"reference_name": request_name,
		},
		fields=["name", "subject"],
	)
	for c in comms:
		subject = c.get("subject") or ""
		if status in subject:
			return True

	# 2. Check pending Email Queue records
	queues = frappe.get_all(
		"Email Queue",
		filters={
			"reference_doctype": "Attendance Request",
			"reference_name": request_name,
		},
		fields=["name", "message"],
	)
	for q in queues:
		msg = q.get("message") or ""
		if status in msg:
			return True

	return False


def get_request_recipient(doc, status: str) -> tuple[str | None, str | None]:
	"""
	Determine recipient email and recipient name for the given status:
	- 'Pending Approval': Sent to employee's Reporting Manager.
	- 'Approved' / 'Rejected': Sent to the Employee who requested it.

	Generates an Error Log immediately with a clear title and description if any required
	data (employee, reporting manager, preferred/company email) is missing.

	Returns tuple: (recipient_email, recipient_name)
	"""
	req_name = doc.get("name") or "New Attendance Request"
	emp_id = doc.get("employee")
	if not emp_id:
		frappe.log_error(
			title=f"Employee Missing on Attendance Request {req_name}",
			message=_(
				"Cannot send Attendance Request {0} notification for '{1}'. "
				"The Attendance Request has no Employee specified."
			).format(status, req_name),
			reference_doctype="Attendance Request",
			reference_name=doc.get("name"),
		)
		return None, None

	emp_fields = [
		"name",
		"employee_name",
		"reports_to",
		"prefered_email",
		"company_email",
	]
	emp = frappe.db.get_value("Employee", emp_id, emp_fields, as_dict=True)
	if not emp:
		frappe.log_error(
			title=f"Employee '{emp_id}' Not Found",
			message=_(
				"Cannot send Attendance Request {0} notification for '{1}'. "
				"Employee '{2}' does not exist in the database."
			).format(status, req_name, emp_id),
			reference_doctype="Attendance Request",
			reference_name=doc.get("name"),
		)
		return None, None

	if status == "Pending Approval":
		reports_to = emp.get("reports_to")
		if not reports_to:
			frappe.log_error(
				title=f"No Reporting Manager Found for Employee {emp_id}",
				message=_(
					"Cannot send Attendance Request {0} notification for '{1}'. "
					"Employee '{2}' ({3}) has no Reporting Manager ('reports_to') assigned."
				).format(status, req_name, emp_id, emp.get("employee_name")),
				reference_doctype="Attendance Request",
				reference_name=doc.get("name"),
			)
			return None, None

		manager = frappe.db.get_value("Employee", reports_to, emp_fields, as_dict=True)
		if not manager:
			frappe.log_error(
				title=f"Reporting Manager '{reports_to}' Not Found",
				message=_(
					"Cannot send Attendance Request {0} notification for '{1}'. "
					"Reporting Manager '{2}' assigned to employee '{3}' does not exist."
				).format(status, req_name, reports_to, emp_id),
				reference_doctype="Attendance Request",
				reference_name=doc.get("name"),
			)
			return None, None

		mgr_email = get_employee_recipient_email(manager)
		if not mgr_email:
			frappe.log_error(
				title=f"No Email Found for Reporting Manager {reports_to}",
				message=_(
					"Cannot send Attendance Request {0} notification for '{1}'. "
					"Reporting Manager '{2}' ({3}) has no valid preferred or company email address configured."
				).format(status, req_name, reports_to, manager.get("employee_name")),
				reference_doctype="Attendance Request",
				reference_name=doc.get("name"),
			)
			return None, None

		return mgr_email, manager.get("employee_name") or _("Reporting Manager")

	else:
		# Approved or Rejected -> Recipient is the Employee
		emp_email = get_employee_recipient_email(emp)
		if not emp_email:
			frappe.log_error(
				title=f"No Email Found for Employee {emp_id}",
				message=_(
					"Cannot send Attendance Request {0} notification for '{1}'. "
					"Employee '{2}' ({3}) has no valid preferred or company email address configured."
				).format(status, req_name, emp_id, emp.get("employee_name")),
				reference_doctype="Attendance Request",
				reference_name=doc.get("name"),
			)
			return None, None

		return emp_email, doc.get("employee_name") or emp.get("employee_name") or _("Employee")


def build_template_context(doc, status: str, recipient_name: str) -> dict:
	"""
	Build Jinja template context matching all variables expected in the
	Attendance Request Notification email template.
	"""
	from_date = doc.get("from_date")
	to_date = doc.get("to_date")

	if from_date and to_date and str(from_date) != str(to_date):
		attendance_date_str = format_date_range(from_date, to_date)
	elif from_date:
		attendance_date_str = format_date(from_date)
	else:
		attendance_date_str = "-"

	if doc.get("half_day"):
		hd_parts = ["Yes"]
		if doc.get("custom_half_day_type"):
			hd_parts.append(f"({doc.get('custom_half_day_type')})")
		if doc.get("half_day_date"):
			hd_parts.append(f"on {format_date(doc.get('half_day_date'))}")
		half_day_str = " ".join(hd_parts)
	else:
		half_day_str = "No"

	# Determine reviewer/approver name
	if status == "Pending Approval":
		approver_name = "-"
	else:
		user_full_name = None
		if frappe.session and frappe.session.user and frappe.session.user not in ("Guest", ""):
			user_full_name = frappe.utils.get_fullname(frappe.session.user)
		if not user_full_name and doc.get("modified_by"):
			user_full_name = frappe.utils.get_fullname(doc.get("modified_by"))
		approver_name = user_full_name or _("Reporting Manager")

	explanation = doc.get("explanation") or "-"
	reason_val = doc.get("reason") or "Attendance Request"

	url = get_url_to_form("Attendance Request", doc.name) if doc.get("name") else ""
	doc_id = doc.get("name") or _("View Request")
	request_link = f'<a href="{url}">{doc_id}</a>' if url else ""

	return {
		"recipient_name": recipient_name,
		"employee_name": doc.get("employee_name") or doc.get("employee"),
		"request_type": reason_val,
		"attendance_date": attendance_date_str,
		"from_date": format_date(from_date) if from_date else "-",
		"to_date": format_date(to_date) if to_date else "-",
		"half_day": half_day_str,
		"reason": explanation if explanation != "-" else reason_val,
		"status": status,
		"approver_name": approver_name,
		"remarks": explanation,
		"request_url": request_link,
		"raw_request_url": url,
		"doc": doc,
	}


def send_attendance_request_notification(doc, status: str, attach_to_timeline: bool = True) -> bool:
	"""
	Main function to send Attendance Request notification:
	- Fetches template dynamically from Artem Setting.attendance_request_notification_email_template.
	- Resolves recipient (Reporting Manager on create, Employee on approve/reject).
	- Prevents duplicate sending.
	- Generates detailed Error Log if any configuration, recipient email, or data is missing.
	- If attach_to_timeline is False, sends the email without displaying it in the form comments timeline.
	"""
	req_name = doc.get("name") or "New Attendance Request"

	# Normalize status to match template Jinja conditionals
	if status in ("Pending", "Pending Approval", "Draft"):
		norm_status = "Pending Approval"
	elif status == "Approved":
		norm_status = "Approved"
	elif status == "Rejected":
		norm_status = "Rejected"
	else:
		norm_status = status

	# 1. Duplicate check
	if doc.get("name") and is_attendance_request_notification_already_sent(doc.name, norm_status):
		return False

	# 2. Fetch Artem Settings and configured Email Template
	settings = get_artem_settings()
	template_name = settings.get("attendance_request_notification_email_template")
	if not template_name:
		frappe.log_error(
			title="Attendance Request Notification Email Template Not Configured",
			message=(
				f"Cannot send Attendance Request {norm_status} notification for '{req_name}'. "
				"The field 'attendance_request_notification_email_template' is not configured in Artem Setting."
			),
			reference_doctype="Attendance Request",
			reference_name=doc.get("name"),
		)
		return False

	if not frappe.db.exists("Email Template", template_name):
		frappe.log_error(
			title=f"Email Template '{template_name}' Not Found",
			message=(
				f"Cannot send Attendance Request {norm_status} notification for '{req_name}'. "
				f"The Email Template '{template_name}' configured in Artem Setting does not exist in the system."
			),
			reference_doctype="Attendance Request",
			reference_name=doc.get("name"),
		)
		return False

	# 3. Resolve Recipient (logs clear, specific Error Log if missing)
	recipient_email, recipient_name = get_request_recipient(doc, norm_status)
	if not recipient_email:
		return False

	# 4. Render Email Template
	try:
		email_template = frappe.get_cached_doc("Email Template", template_name)
		context = build_template_context(doc, norm_status, recipient_name)

		rendered_subject = frappe.render_template(email_template.subject or "", context)  # nosemgrep
		template_body = email_template.response_html or email_template.response or ""
		rendered_message = frappe.render_template(template_body, context)  # nosemgrep
	except Exception as e:
		frappe.log_error(
			title=f"Failed to Render Attendance Request Email Template for {req_name}",
			message=(
				f"Error rendering Email Template '{template_name}' for Attendance Request '{req_name}':\n"
				f"{e}\n\n{frappe.get_traceback()}"
			),
			reference_doctype="Attendance Request",
			reference_name=doc.get("name"),
		)
		return False

	# 5. Insert Communication record & Send Email
	comm_name = None
	try:
		if doc.get("name"):
			comm_data = {
				"doctype": "Communication",
				"communication_type": "Automated Message",
				"communication_medium": "Email",
				"sent_or_received": "Sent",
				"reference_name": doc.name,
				"subject": rendered_subject,
				"content": rendered_message,
				"recipients": recipient_email,
				"email_template": template_name,
				"communication_date": today(),
			}
			if attach_to_timeline:
				comm_data["reference_doctype"] = "Attendance Request"

			comm = frappe.get_doc(comm_data)
			comm.insert(ignore_permissions=True, ignore_links=True)
			comm_name = comm.name

		sendmail_kwargs = {
			"recipients": [recipient_email],
			"subject": rendered_subject,
			"message": rendered_message,
		}
		if attach_to_timeline and doc.get("name"):
			sendmail_kwargs["reference_doctype"] = "Attendance Request"
			sendmail_kwargs["reference_name"] = doc.name
			sendmail_kwargs["communication"] = comm_name

		frappe.sendmail(**sendmail_kwargs)
		return True
	except Exception as e:
		if comm_name:
			try:
				frappe.db.delete("Communication", {"name": comm_name})
			except Exception:
				pass
		frappe.log_error(
			title=f"Failed to Send Attendance Request Email for {req_name}",
			message=(
				f"Failed to send Attendance Request {norm_status} notification to '{recipient_email}':\n"
				f"{e}\n\n{frappe.get_traceback()}"
			),
			reference_doctype="Attendance Request",
			reference_name=doc.get("name"),
		)
		return False


# -------------------------------------------------------------------------
# Hook Handlers
# -------------------------------------------------------------------------


def on_attendance_request_created(doc, method=None):
	"""
	Triggered on 'after_insert':
	When an employee creates and saves an Attendance Request:
	Notify Reporting Manager with 'Pending Approval' (silently in background without attaching to comments).
	Display only the Frappe confirmation message to the employee.
	"""
	state = getattr(doc, "workflow_state", None)
	if state == "Approved" or doc.docstatus == 1:
		send_attendance_request_notification(doc, status="Approved", attach_to_timeline=False)
	elif state == "Rejected":
		send_attendance_request_notification(doc, status="Rejected", attach_to_timeline=False)
	else:
		send_attendance_request_notification(doc, status="Pending Approval", attach_to_timeline=False)
		frappe.msgprint(
			_("Attendance Request submitted. Notification email has been sent to your Reporting Manager.")
		)


def on_attendance_request_updated(doc, method=None):
	"""
	Triggered on 'on_update':
	When Attendance Request is updated (e.g. Workflow action Reject or Approve):
	Notify employee if approved or rejected.
	"""
	state = getattr(doc, "workflow_state", None)
	if state == "Rejected":
		send_attendance_request_notification(doc, status="Rejected", attach_to_timeline=False)
	elif state == "Approved" or doc.docstatus == 1:
		send_attendance_request_notification(doc, status="Approved", attach_to_timeline=False)


def on_attendance_request_submitted(doc, method=None):
	"""
	Triggered on 'on_submit':
	When Attendance Request is submitted (Approved):
	Notify employee informing them that their request has been approved.
	"""
	send_attendance_request_notification(doc, status="Approved", attach_to_timeline=False)
