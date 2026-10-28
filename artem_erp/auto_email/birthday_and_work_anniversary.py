# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import calendar

import frappe
from frappe.utils import getdate, today

from artem_erp.auto_email.utils import (
	clean_email,
	get_artem_settings,
	get_configured_cc,
	get_employee_recipient_email,
	get_ordinal,
	parse_cc_recipients,
)


def get_birthday_employees(target_date) -> list[dict]:
	"""
	Query all active employees whose birthday falls on target_date.
	Includes Feb 29 birthdays on Feb 28 in non-leap years.
	"""
	t_date = getdate(target_date)
	is_leap_year = calendar.isleap(t_date.year)
	is_feb_28_non_leap = t_date.month == 2 and t_date.day == 28 and not is_leap_year

	employees = frappe.get_all(
		"Employee",
		filters={
			"status": "Active",
			"date_of_birth": ["is", "set"],
		},
		fields=[
			"name",
			"employee_name",
			"first_name",
			"last_name",
			"date_of_birth",
			"date_of_joining",
			"company",
			"department",
			"designation",
			"prefered_email",
			"prefered_contact_email",
			"company_email",
			"personal_email",
			"user_id",
			"image",
		],
		order_by="employee_name asc",
	)

	matching_employees = []
	for emp in employees:
		dob = getdate(emp.get("date_of_birth"))
		if not dob:
			continue

		if dob.month == t_date.month:
			if is_feb_28_non_leap:
				if dob.day in (28, 29):
					matching_employees.append(emp)
			elif dob.day == t_date.day:
				matching_employees.append(emp)

	return matching_employees


def get_work_anniversary_employees(target_date) -> list[dict]:
	"""
	Query all active employees whose work anniversary falls on target_date.
	Excludes employees who joined in the current target year (anniversary >= 1 year).
	Includes Feb 29 joining dates on Feb 28 in non-leap years.
	"""
	t_date = getdate(target_date)
	is_leap_year = calendar.isleap(t_date.year)
	is_feb_28_non_leap = t_date.month == 2 and t_date.day == 28 and not is_leap_year

	employees = frappe.get_all(
		"Employee",
		filters={
			"status": "Active",
			"date_of_joining": ["is", "set"],
		},
		fields=[
			"name",
			"employee_name",
			"first_name",
			"last_name",
			"date_of_birth",
			"date_of_joining",
			"company",
			"department",
			"designation",
			"prefered_email",
			"prefered_contact_email",
			"company_email",
			"personal_email",
			"user_id",
			"image",
		],
		order_by="employee_name asc",
	)

	matching_employees = []
	for emp in employees:
		doj = getdate(emp.get("date_of_joining"))
		if not doj:
			continue

		if doj.year < t_date.year and doj.month == t_date.month:
			if is_feb_28_non_leap:
				if doj.day in (28, 29):
					matching_employees.append(emp)
			elif doj.day == t_date.day:
				matching_employees.append(emp)

	return matching_employees


def is_already_sent_today(
	emp_id: str, event_type: str, target_date, template_name: str | None = None
) -> bool:
	"""
	Duplicate Prevention:
	Check whether a birthday or work anniversary email has already been sent
	or queued for the specified employee on the target date.
	Ensures an employee receives only one birthday and one anniversary email per day.
	"""
	t_date = getdate(target_date)

	# 1. Check existing Communication records linked to this Employee for today
	comms = frappe.get_all(
		"Communication",
		filters={
			"reference_doctype": "Employee",
			"reference_name": emp_id,
		},
		fields=["name", "subject", "email_template", "communication_date", "creation"],
	)

	for comm in comms:
		comm_date = getdate(comm.get("communication_date") or comm.get("creation"))
		if comm_date == t_date:
			comm_template = comm.get("email_template") or ""
			comm_subject = (comm.get("subject") or "").lower()

			if template_name and comm_template == template_name:
				return True

			if event_type == "birthday" and (
				"birthday" in comm_subject or "birthday" in comm_template.lower()
			):
				return True

			if event_type == "work_anniversary" and (
				"anniversary" in comm_subject or "anniversary" in comm_template.lower()
			):
				return True

	# 2. Check pending or sent Email Queue records for today
	queues = frappe.get_all(
		"Email Queue",
		filters={
			"reference_doctype": "Employee",
			"reference_name": emp_id,
			"creation": ["between", [f"{t_date} 00:00:00", f"{t_date} 23:59:59"]],
			"status": ["!=", "Error"],
		},
		fields=["name", "message"],
	)

	for q in queues:
		msg = (q.get("message") or "").lower()
		if event_type == "birthday" and "birthday" in msg:
			return True
		if event_type == "work_anniversary" and "anniversary" in msg:
			return True

	return False


def record_email_communication(
	emp_id: str,
	recipient_email: str,
	cc_recipients: list[str],
	subject: str,
	message: str,
	template_name: str,
	target_date,
):
	"""
	Create a permanent Communication record for the sent email to prevent duplicate sends
	and maintain audit trail in Frappe.
	"""
	try:
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Automated Message",
				"communication_medium": "Email",
				"sent_or_received": "Sent",
				"reference_doctype": "Employee",
				"reference_name": emp_id,
				"subject": subject,
				"content": message,
				"recipients": recipient_email,
				"cc": ", ".join(cc_recipients) if cc_recipients else "",
				"email_template": template_name,
				"communication_date": target_date,
			}
		)
		comm.insert(ignore_permissions=True)
		return comm.name
	except Exception as e:
		frappe.log_error(
			title=f"Failed to Record Communication for {emp_id}",
			message=f"Could not record email communication for {emp_id}: {e}\n\n{frappe.get_traceback()}",
			reference_doctype="Employee",
			reference_name=emp_id,
		)
		return None


def send_birthday_wishes(date=None) -> dict:
	"""
	Send birthday wishes to employees celebrating birthdays on the given date (default today).
	Emails are sent to the employee with configured company team in CC.
	Subject and body are fetched dynamically from the Email Template configured in Artem Setting.
	Generates Error Log for any missing template, email, or configuration.
	Ensures only one birthday email is sent per employee per day.
	"""
	target_date = getdate(date) if date else getdate(today())
	artem_setting = get_artem_settings()

	if not artem_setting:
		return {"sent": 0, "skipped": 0, "errors": 1, "message": "Artem Setting could not be loaded"}

	template_name = artem_setting.get("employee_birthday_email_template") or artem_setting.get(
		"employee_birthday_email"
	)
	if not template_name:
		frappe.log_error(
			title="Employee Birthday Email Template Not Configured",
			message=(
				"Employee Birthday Email Template is not linked in Artem Setting. "
				"Please go to Artem Setting > Auto Email Configuration and select an Employee Birthday Email Template."
			),
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return {"sent": 0, "skipped": 0, "errors": 1, "message": "Birthday Email Template not configured"}

	if not frappe.db.exists("Email Template", template_name):
		frappe.log_error(
			title="Employee Birthday Email Template Not Found",
			message=(
				f"The Email Template '{template_name}' configured for Employee Birthday in Artem Setting "
				"does not exist in Email Template doctype. Please configure a valid template."
			),
			reference_doctype="Email Template",
			reference_name=template_name,
		)
		return {
			"sent": 0,
			"skipped": 0,
			"errors": 1,
			"message": f"Email Template '{template_name}' not found",
		}

	try:
		template_doc = frappe.get_doc("Email Template", template_name)
	except Exception as e:
		frappe.log_error(
			title="Failed to Load Birthday Email Template",
			message=f"Could not load Email Template '{template_name}': {e}\n\n{frappe.get_traceback()}",
			reference_doctype="Email Template",
			reference_name=template_name,
		)
		return {"sent": 0, "skipped": 0, "errors": 1, "message": f"Could not load template '{template_name}'"}

	# Retrieve CC recipients
	cc_recipients = get_configured_cc(artem_setting)
	if not cc_recipients:
		frappe.log_error(
			title="Company Team CC Emails Missing in Artem Setting",
			message=(
				"Required configuration 'Company Team CC Emails' is missing or not configured "
				"in Artem Setting under Auto Email Configuration. Birthday emails must include company team in CC."
			),
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)

	employees = get_birthday_employees(target_date)
	sent_count = 0
	skipped_count = 0
	error_count = 0

	for emp in employees:
		emp_id = emp.get("name")
		emp_name = emp.get("employee_name") or emp.get("first_name") or emp_id

		# Duplicate prevention check
		if is_already_sent_today(emp_id, "birthday", target_date, template_name):
			skipped_count += 1
			continue

		recipient_email = get_employee_recipient_email(emp)
		if not recipient_email:
			error_count += 1
			frappe.log_error(
				title=f"Missing Email Address for Employee {emp_id}",
				message=(
					f"Cannot send birthday email to employee {emp_name} ({emp_id}). "
					"No valid email address is configured (checked prefered_email and company_email)."
				),
				reference_doctype="Employee",
				reference_name=emp_id,
			)
			continue

		# Prepare Jinja rendering context
		context = dict(emp)
		context.update(
			{
				"doc": emp,
				"employee": emp,
				"employee_name": emp_name,
				"first_name": emp.get("first_name"),
				"last_name": emp.get("last_name"),
				"company": emp.get("company"),
				"department": emp.get("department"),
				"designation": emp.get("designation"),
				"target_date": target_date,
			}
		)

		try:
			raw_subject = template_doc.subject
			raw_message = template_doc.response or template_doc.get("message") or ""

			rendered_subject = frappe.render_template(raw_subject, context)  # nosemgrep
			rendered_message = frappe.render_template(raw_message, context)  # nosemgrep
		except Exception as e:
			error_count += 1
			frappe.log_error(
				title=f"Error Rendering Birthday Email for {emp_id}",
				message=(
					f"Failed to render Birthday Email Template '{template_name}' for employee {emp_name} ({emp_id}): "
					f"{e}\n\n{frappe.get_traceback()}"
				),
				reference_doctype="Employee",
				reference_name=emp_id,
			)
			continue

		# Exclude celebrating employee's emails from CC list so they never appear in CC
		clean_recip = recipient_email.lower().strip()
		emp_all_emails = {
			clean_recip,
			(emp.get("company_email") or "").lower().strip(),
			(emp.get("personal_email") or "").lower().strip(),
			(emp.get("user_id") or "").lower().strip(),
			(emp.get("prefered_email") or "").lower().strip(),
		}
		emp_all_emails.discard("")

		filtered_ccs = [cc for cc in cc_recipients if clean_email(cc) not in emp_all_emails]

		formatted_recipient = f'"{emp_name}" <{recipient_email}>' if emp_name else recipient_email

		comm_name = None
		try:
			comm_name = record_email_communication(
				emp_id=emp_id,
				recipient_email=formatted_recipient,
				cc_recipients=filtered_ccs,
				subject=rendered_subject,
				message=rendered_message,
				template_name=template_name,
				target_date=target_date,
			)

			frappe.sendmail(
				recipients=[formatted_recipient],
				cc=filtered_ccs,
				expose_recipients="header",
				subject=rendered_subject,
				message=rendered_message,
				reference_doctype="Employee",
				reference_name=emp_id,
				communication=comm_name,
			)
			sent_count += 1
		except Exception as e:
			error_count += 1
			if comm_name:
				try:
					frappe.db.delete("Communication", {"name": comm_name})
				except Exception:
					pass
			frappe.log_error(
				title=f"Failed to Send Birthday Email to {emp_id}",
				message=(
					f"Failed to send birthday email to {recipient_email} for employee {emp_name} ({emp_id}): "
					f"{e}\n\n{frappe.get_traceback()}"
				),
				reference_doctype="Employee",
				reference_name=emp_id,
			)

	return {
		"sent": sent_count,
		"skipped": skipped_count,
		"errors": error_count,
		"total_eligible": len(employees),
	}


def send_work_anniversary_wishes(date=None) -> dict:
	"""
	Send work anniversary wishes to employees celebrating work anniversaries on the given date (default today).
	Emails are sent to the employee with configured company team in CC.
	Subject and body are fetched dynamically from the Email Template configured in Artem Setting.
	Generates Error Log for any missing template, email, or configuration.
	Ensures only one work anniversary email is sent per employee per day.
	"""
	target_date = getdate(date) if date else getdate(today())
	artem_setting = get_artem_settings()

	if not artem_setting:
		return {"sent": 0, "skipped": 0, "errors": 1, "message": "Artem Setting could not be loaded"}

	template_name = artem_setting.get("employee_work_anniversary_email_template")
	if not template_name:
		frappe.log_error(
			title="Employee Work Anniversary Email Template Not Configured",
			message=(
				"Employee Work Anniversary Email Template is not linked in Artem Setting. "
				"Please go to Artem Setting > Auto Email Configuration and select an Employee Work Anniversary Email Template."
			),
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return {
			"sent": 0,
			"skipped": 0,
			"errors": 1,
			"message": "Work Anniversary Email Template not configured",
		}

	if not frappe.db.exists("Email Template", template_name):
		frappe.log_error(
			title="Employee Work Anniversary Email Template Not Found",
			message=(
				f"The Email Template '{template_name}' configured for Employee Work Anniversary in Artem Setting "
				"does not exist in Email Template doctype. Please configure a valid template."
			),
			reference_doctype="Email Template",
			reference_name=template_name,
		)
		return {
			"sent": 0,
			"skipped": 0,
			"errors": 1,
			"message": f"Email Template '{template_name}' not found",
		}

	try:
		template_doc = frappe.get_doc("Email Template", template_name)
	except Exception as e:
		frappe.log_error(
			title="Failed to Load Work Anniversary Email Template",
			message=f"Could not load Email Template '{template_name}': {e}\n\n{frappe.get_traceback()}",
			reference_doctype="Email Template",
			reference_name=template_name,
		)
		return {"sent": 0, "skipped": 0, "errors": 1, "message": f"Could not load template '{template_name}'"}

	# Retrieve CC recipients
	cc_recipients = get_configured_cc(artem_setting)
	if not cc_recipients:
		frappe.log_error(
			title="Company Team CC Emails Missing in Artem Setting",
			message=(
				"Required configuration 'Company Team CC Emails' is missing or not configured "
				"in Artem Setting under Auto Email Configuration. Work anniversary emails must include company team in CC."
			),
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)

	employees = get_work_anniversary_employees(target_date)
	sent_count = 0
	skipped_count = 0
	error_count = 0

	for emp in employees:
		emp_id = emp.get("name")
		emp_name = emp.get("employee_name") or emp.get("first_name") or emp_id

		# Duplicate prevention check
		if is_already_sent_today(emp_id, "work_anniversary", target_date, template_name):
			skipped_count += 1
			continue

		recipient_email = get_employee_recipient_email(emp)
		if not recipient_email:
			error_count += 1
			frappe.log_error(
				title=f"Missing Email Address for Employee {emp_id}",
				message=(
					f"Cannot send work anniversary email to employee {emp_name} ({emp_id}). "
					"No valid email address is configured (checked prefered_email and company_email)."
				),
				reference_doctype="Employee",
				reference_name=emp_id,
			)
			continue

		joining_date = emp.get("date_of_joining")
		if not joining_date:
			error_count += 1
			frappe.log_error(
				title=f"Missing Date of Joining for Employee {emp_id}",
				message=f"Cannot send work anniversary email to employee {emp_name} ({emp_id}). Date of joining is missing on Employee record.",
				reference_doctype="Employee",
				reference_name=emp_id,
			)
			continue

		completed_years = target_date.year - getdate(joining_date).year
		if completed_years <= 0:
			# Employee joined in current year; not an anniversary yet
			continue

		# Prepare Jinja rendering context
		context = dict(emp)
		context.update(
			{
				"doc": emp,
				"employee": emp,
				"employee_name": emp_name,
				"first_name": emp.get("first_name"),
				"last_name": emp.get("last_name"),
				"company": emp.get("company"),
				"department": emp.get("department"),
				"designation": emp.get("designation"),
				"date_of_joining": joining_date,
				"completed_years": completed_years,
				"years_completed": completed_years,
				"ordinal_anniversary": get_ordinal(completed_years),
				"target_date": target_date,
			}
		)

		try:
			raw_subject = template_doc.subject
			raw_message = template_doc.response or template_doc.get("message") or ""

			rendered_subject = frappe.render_template(raw_subject, context)  # nosemgrep
			rendered_message = frappe.render_template(raw_message, context)  # nosemgrep
		except Exception as e:
			error_count += 1
			frappe.log_error(
				title=f"Error Rendering Work Anniversary Email for {emp_id}",
				message=(
					f"Failed to render Work Anniversary Email Template '{template_name}' for employee {emp_name} ({emp_id}): "
					f"{e}\n\n{frappe.get_traceback()}"
				),
				reference_doctype="Employee",
				reference_name=emp_id,
			)
			continue

		# Exclude celebrating employee's emails from CC list so they never appear in CC
		clean_recip = recipient_email.lower().strip()
		emp_all_emails = {
			clean_recip,
			(emp.get("company_email") or "").lower().strip(),
			(emp.get("personal_email") or "").lower().strip(),
			(emp.get("user_id") or "").lower().strip(),
			(emp.get("prefered_email") or "").lower().strip(),
		}
		emp_all_emails.discard("")

		filtered_ccs = [cc for cc in cc_recipients if clean_email(cc) not in emp_all_emails]

		formatted_recipient = f'"{emp_name}" <{recipient_email}>' if emp_name else recipient_email

		comm_name = None
		try:
			comm_name = record_email_communication(
				emp_id=emp_id,
				recipient_email=formatted_recipient,
				cc_recipients=filtered_ccs,
				subject=rendered_subject,
				message=rendered_message,
				template_name=template_name,
				target_date=target_date,
			)

			frappe.sendmail(
				recipients=[formatted_recipient],
				cc=filtered_ccs,
				expose_recipients="header",
				subject=rendered_subject,
				message=rendered_message,
				reference_doctype="Employee",
				reference_name=emp_id,
				communication=comm_name,
			)
			sent_count += 1
		except Exception as e:
			error_count += 1
			if comm_name:
				try:
					frappe.db.delete("Communication", {"name": comm_name})
				except Exception:
					pass
			frappe.log_error(
				title=f"Failed to Send Work Anniversary Email to {emp_id}",
				message=(
					f"Failed to send work anniversary email to {recipient_email} for employee {emp_name} ({emp_id}): "
					f"{e}\n\n{frappe.get_traceback()}"
				),
				reference_doctype="Employee",
				reference_name=emp_id,
			)

	return {
		"sent": sent_count,
		"skipped": skipped_count,
		"errors": error_count,
		"total_eligible": len(employees),
	}


def send_birthday_and_anniversary_wishes(date=None) -> dict:
	"""
	Scheduled entry point to process both birthday and work anniversary wishes.
	Triggered daily at 9:30 AM via cron hook (30 9 * * *).
	"""
	birthday_result = send_birthday_wishes(date=date)
	anniversary_result = send_work_anniversary_wishes(date=date)

	return {
		"birthday": birthday_result,
		"anniversary": anniversary_result,
	}
