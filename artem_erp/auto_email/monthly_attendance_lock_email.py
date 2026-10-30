# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import cint, get_first_day, get_last_day, getdate, nowdate

from artem_erp.auto_email.utils import (
	clean_email,
	get_artem_settings,
	get_configured_cc,
)


def get_company_team_recipients(settings) -> list[str]:
	"""
	Retrieve recipient email addresses dynamically from Artem Setting.
	Extracts Email Groups configured in 'company_team_emails' and fetches
	all active member email addresses from Email Group Member (unsubscribed == 0).
	"""
	if not settings:
		return []
	return get_configured_cc(settings)


def is_attendance_lock_reminder_already_sent(current_date, template_name: str | None = None) -> bool:
	"""
	Check if the reminder was already sent for the current calendar month.
	"""
	start_date = get_first_day(current_date)
	end_date = get_last_day(current_date)

	filters = {
		"reference_doctype": "Email Template",
		"communication_date": ["between", [start_date, end_date]],
	}
	if template_name:
		filters["reference_name"] = template_name
		filters["email_template"] = template_name

	return bool(frappe.db.exists("Communication", filters))


def create_attendance_lock_notification_logs(
	subject: str, message: str, recipients: list[str], template_name: str | None = None
) -> list[str]:
	"""
	Create Notification Log entries for recipient users after sending the reminder successfully.
	"""
	if not recipients:
		return []

	clean_recipients = [clean_email(r) for r in recipients if clean_email(r)]
	if not clean_recipients:
		return []

	users = frappe.get_all(
		"User",
		filters={"name": ["in", clean_recipients], "enabled": 1},
		pluck="name",
	)
	by_email = frappe.get_all(
		"User",
		filters={"email": ["in", clean_recipients], "enabled": 1},
		pluck="name",
	)
	recipient_users = list(dict.fromkeys(users + by_email))

	created_logs: list[str] = []
	for user in recipient_users:
		try:
			doc = frappe.new_doc("Notification Log")
			doc.type = "Alert"
			doc.document_type = "Email Template"
			doc.document_name = template_name
			doc.subject = subject
			doc.for_user = user
			doc.email_content = message
			doc.insert(ignore_permissions=True)
			created_logs.append(doc.name)
		except Exception as e:
			frappe.log_error(
				title=f"Failed to Create Notification Log for {user}",
				message=f"Failed to create Notification Log for {user}: {e}\n\n{frappe.get_traceback()}",
				reference_doctype="Email Template",
				reference_name=template_name,
			)
	return created_logs


def send_monthly_attendance_lock_reminder(target_date=None, force: bool = False) -> dict:
	"""
	Automated email reminder for Attendance Regularization & Monthly Attendance Lock.
	Runs on the reminder day configured dynamically in Artem Setting (attendance_lock_reminder_day).

	Requirements:
	- Send email using the template linked in Artem Settings (attendance_lock_notification_template).
	- Reminder day fetched dynamically from Artem Setting (attendance_lock_reminder_day).
	- Recipients (To): Email groups configured in Artem Setting.company_team_emails.
	- Log errors if template or email configuration is missing.
	- Create a Notification Log entry after sending the reminder successfully.
	"""
	current_date = getdate(target_date) if target_date else getdate(nowdate())

	# 1. Fetch Artem Setting
	settings = get_artem_settings()
	if not settings:
		frappe.log_error(
			title="Monthly Attendance Lock Reminder: Artem Setting Missing",
			message="Artem Setting single DocType could not be retrieved.",
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return {"status": "error", "message": "Artem Setting not found"}

	# 2. Fetch configured reminder day dynamically from Artem Setting
	reminder_day_val = getattr(settings, "attendance_lock_reminder_day", None)
	if not reminder_day_val:
		frappe.log_error(
			title="Monthly Attendance Lock Reminder: Reminder Day Not Configured",
			message="Field 'attendance_lock_reminder_day' is not configured in Artem Setting. Please configure a reminder day (1-31).",
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return {
			"status": "error",
			"message": "Field 'attendance_lock_reminder_day' is not configured in Artem Setting",
		}

	reminder_day = cint(reminder_day_val)
	if not (1 <= reminder_day <= 31):
		frappe.log_error(
			title="Monthly Attendance Lock Reminder: Invalid Reminder Day",
			message=f"Configured 'attendance_lock_reminder_day' ({reminder_day_val}) in Artem Setting is invalid. It must be between 1 and 31.",
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return {
			"status": "error",
			"message": f"Invalid 'attendance_lock_reminder_day' ({reminder_day_val}) in Artem Setting",
		}

	last_day = get_last_day(current_date).day
	effective_reminder_day = min(reminder_day, last_day)

	# Only run on the configured reminder day of the month unless explicitly forced
	if not force and current_date.day != effective_reminder_day:
		msg = (
			f"Skipping monthly attendance lock reminder: Today ({current_date.strftime('%d %b, %Y')}) "
			f"is day {current_date.day}, which is not the configured reminder day ({effective_reminder_day}). "
			f"To send today, set 'Attendance Lock Reminder Day' to {current_date.day} in Artem Setting."
		)
		frappe.log_error(
			title="Monthly Attendance Lock Reminder: Day Mismatch",
			message=msg,
			reference_doctype="Email Template",
			reference_name=getattr(settings, "attendance_lock_notification_template", None),
		)
		return {
			"status": "skipped",
			"message": msg,
		}

	# 2. Fetch Email Template configuration
	template_name = getattr(settings, "attendance_lock_notification_template", None)
	if not template_name:
		frappe.log_error(
			title="Monthly Attendance Lock Reminder: Template Configuration Missing",
			message="Field 'attendance_lock_notification_template' is not configured in Artem Setting.",
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return {
			"status": "error",
			"message": "Field 'attendance_lock_notification_template' is not configured in Artem Setting",
		}

	if not frappe.db.exists("Email Template", template_name):
		frappe.log_error(
			title="Monthly Attendance Lock Reminder: Email Template Not Found",
			message=f"Email Template '{template_name}' configured in Artem Setting does not exist.",
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return {
			"status": "error",
			"message": f"Email Template '{template_name}' does not exist",
		}

	# Check for duplicate sending in the current calendar month unless forced
	if not force and is_attendance_lock_reminder_already_sent(current_date, template_name):
		msg = f"Attendance lock reminder already sent for {current_date.strftime('%B %Y')}."
		frappe.log_error(
			title="Monthly Attendance Lock Reminder: Already Sent",
			message=msg,
			reference_doctype="Email Template",
			reference_name=template_name,
		)
		return {
			"status": "skipped",
			"message": msg,
		}

	template_doc = frappe.get_doc("Email Template", template_name)

	# 3. Fetch Recipients (To) from company_team_emails
	to_recipients = get_company_team_recipients(settings)
	if not to_recipients:
		frappe.log_error(
			title="Monthly Attendance Lock Reminder: No Recipients Found",
			message="No active recipient emails could be resolved from Artem Setting company_team_emails.",
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return {
			"status": "error",
			"message": "No recipients resolved from Artem Setting company_team_emails",
		}

	# 4. Render Subject and Message dynamically
	context = {
		"month_name": current_date.strftime("%B"),
		"year": current_date.year,
		"month_year": current_date.strftime("%B %Y"),
		"date": current_date.strftime("%d %b, %Y"),
		"reminder_day": effective_reminder_day,
		"company": frappe.defaults.get_user_default("company") or "Artem Health Tech",
		"settings": settings,
	}

	try:
		subject = frappe.render_template(template_doc.subject, context)  # nosemgrep
		message = frappe.render_template(template_doc.response or "", context)  # nosemgrep
	except Exception as e:
		frappe.log_error(
			title="Monthly Attendance Lock Reminder: Template Render Error",
			message=f"Failed to render email template '{template_name}': {e}\n\n{frappe.get_traceback()}",
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return {"status": "error", "message": f"Failed to render template: {e}"}

	# 5. Send Email and create Communication record (Only Recipients, No CC)
	comm_name = None
	try:
		comm = frappe.new_doc("Communication")
		comm.update(
			{
				"communication_type": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Sent",
				"subject": subject,
				"content": message,
				"recipients": ", ".join(to_recipients),
				"email_template": template_name,
				"communication_date": current_date,
				"reference_doctype": "Email Template",
				"reference_name": template_name,
			}
		)
		comm.insert(ignore_permissions=True)
		comm_name = comm.name

		frappe.sendmail(
			recipients=to_recipients,
			expose_recipients="header",
			subject=subject,
			message=message,
			reference_doctype="Email Template",
			reference_name=template_name,
			communication=comm_name,
		)
	except Exception as e:
		if comm_name:
			try:
				frappe.db.delete("Communication", {"name": comm_name})
			except Exception:
				pass
		frappe.log_error(
			title="Monthly Attendance Lock Reminder: Email Sending Failed",
			message=f"Failed to send email to recipients: {e}\n\n{frappe.get_traceback()}",
			reference_doctype="Email Template",
			reference_name=template_name,
		)
		return {"status": "error", "message": f"Email sending failed: {e}"}

	# 6. Create Notification Log entry after sending reminder successfully
	notification_logs = create_attendance_lock_notification_logs(
		subject, message, to_recipients, template_name=template_name
	)

	return {
		"status": "success",
		"recipients_count": len(to_recipients),
		"notification_logs_count": len(notification_logs),
		"communication": comm_name,
	}
