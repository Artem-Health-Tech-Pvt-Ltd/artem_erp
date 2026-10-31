# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today

from artem_erp.auto_email.utils import (
	format_date_range,
	get_artem_settings,
	get_employee_recipient_email,
	get_initials,
	get_leave_emoji,
)


def get_employees_on_leave(target_date) -> dict[str, dict]:
	"""
	Identify employees who have an approved or requested Leave Application on target_date.
	Returns mapping of employee_id -> leave info dict.
	"""
	t_date = getdate(target_date)
	t_date_str = str(t_date)

	leave_records = frappe.get_all(
		"Leave Application",
		filters={
			"docstatus": ["<", 2],
			"status": ["not in", ["Rejected", "Cancelled"]],
			"from_date": ["<=", t_date_str],
			"to_date": [">=", t_date_str],
		},
		fields=[
			"name",
			"employee",
			"employee_name",
			"department",
			"leave_type",
			"from_date",
			"to_date",
			"half_day",
			"status",
		],
		order_by="from_date asc",
	)

	on_leave: dict[str, dict] = {}
	for la in leave_records:
		emp_id = la.get("employee")
		if not emp_id or emp_id in on_leave:
			continue

		on_leave[emp_id] = {
			"employee": emp_id,
			"employee_name": la.get("employee_name") or emp_id,
			"department": la.get("department"),
			"leave_type": la.get("leave_type") or "Leave",
			"from_date": la.get("from_date"),
			"to_date": la.get("to_date"),
			"date_range": format_date_range(la.get("from_date"), la.get("to_date")),
			"half_day": la.get("half_day"),
			"status": la.get("status"),
		}

	return on_leave


def get_employees_working_remotely(target_date) -> dict[str, dict]:
	"""
	Identify employees who have an approved or requested Attendance Request
	for Work From Home (WFH) on target_date.
	Returns mapping of employee_id -> wfh info dict.
	"""
	t_date = getdate(target_date)
	t_date_str = str(t_date)

	wfh_records = frappe.get_all(
		"Attendance Request",
		filters={
			"docstatus": ["<", 2],
			"reason": "Work From Home",
			"from_date": ["<=", t_date_str],
			"to_date": [">=", t_date_str],
		},
		fields=[
			"name",
			"employee",
			"employee_name",
			"department",
			"reason",
			"explanation",
			"from_date",
			"to_date",
			"half_day",
			*(
				["workflow_state"]
				if frappe.get_meta("Attendance Request").has_field("workflow_state")
				else []
			),
			"docstatus",
		],
		order_by="from_date asc",
	)

	wfh_employees: dict[str, dict] = {}
	for ar in wfh_records:
		if (ar.get("workflow_state") or "").lower() in ("rejected", "cancelled"):
			continue

		emp_id = ar.get("employee")
		if not emp_id or emp_id in wfh_employees:
			continue

		wfh_employees[emp_id] = {
			"employee": emp_id,
			"employee_name": ar.get("employee_name") or emp_id,
			"department": ar.get("department"),
			"reason": ar.get("reason"),
			"explanation": ar.get("explanation"),
			"from_date": ar.get("from_date"),
			"to_date": ar.get("to_date"),
			"date_range": format_date_range(ar.get("from_date"), ar.get("to_date")),
			"half_day": ar.get("half_day"),
		}

	return wfh_employees


def build_availability_details_html(on_leave_list: list[dict], wfh_list: list[dict]) -> str:
	"""
	Build modern, email-client-safe card HTML for team availability details,
	matching the Daily Digest presentation (On Leave and Working Remotely).
	"""
	html_parts: list[str] = []

	# On Leave Card
	if on_leave_list:
		leave_rows: list[str] = []
		for emp in on_leave_list:
			initials = get_initials(emp.get("employee_name", ""))
			name = emp.get("employee_name", "")
			date_range = emp.get("date_range", "")
			leave_type = emp.get("leave_type") or "Leave"
			leave_emoji = get_leave_emoji(leave_type)

			details_text = (
				f"{date_range} &bull; {leave_emoji} {leave_type}"
				if date_range
				else f"{leave_emoji} {leave_type}"
			)

			row_html = f"""
				<tr>
					<td style="width: 44px; vertical-align: middle; padding: 8px 0;">
						<div style="width: 36px; height: 36px; border-radius: 50%; background-color: #fee2e2; color: #b91c1c; text-align: center; line-height: 36px; font-weight: 600; font-size: 13px;">
							{initials}
						</div>
					</td>
					<td style="vertical-align: middle; padding: 8px 0 8px 12px;">
						<div style="font-size: 14px; font-weight: 600; color: #1e293b; margin-bottom: 2px;">{name}</div>
						<div style="font-size: 12px; color: #64748b;">{details_text}</div>
					</td>
				</tr>
			"""
			leave_rows.append(row_html)

		distinct_emojis = {get_leave_emoji(emp.get("leave_type")) for emp in on_leave_list}
		header_emoji = distinct_emojis.pop() if len(distinct_emojis) == 1 else "🏖️"

		leave_card = f"""
			<div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
				<div style="font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 12px;">
					{header_emoji} On Leave
				</div>
				<table style="width: 100%; border-collapse: collapse;">
					{"".join(leave_rows)}
				</table>
			</div>
		"""
		html_parts.append(leave_card)

	# Working Remotely Card
	if wfh_list:
		wfh_rows: list[str] = []
		for emp in wfh_list:
			initials = get_initials(emp.get("employee_name", ""))
			name = emp.get("employee_name", "")
			date_range = emp.get("date_range", "")

			row_html = f"""
				<tr>
					<td style="width: 44px; vertical-align: middle; padding: 8px 0;">
						<div style="width: 36px; height: 36px; border-radius: 50%; background-color: #e0f2fe; color: #0369a1; text-align: center; line-height: 36px; font-weight: 600; font-size: 13px;">
							{initials}
						</div>
					</td>
					<td style="vertical-align: middle; padding: 8px 0 8px 12px;">
						<div style="font-size: 14px; font-weight: 600; color: #1e293b; margin-bottom: 2px;">{name}</div>
						<div style="font-size: 12px; color: #64748b;">{date_range}</div>
					</td>
				</tr>
			"""
			wfh_rows.append(row_html)

		wfh_card = f"""
			<div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
				<div style="font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 12px;">
					💻 Working Remotely
				</div>
				<table style="width: 100%; border-collapse: collapse;">
					{"".join(wfh_rows)}
				</table>
			</div>
		"""
		html_parts.append(wfh_card)

	return "\n".join(html_parts)


def is_department_notification_sent_today(
	department: str, target_date, template_name: str | None = None
) -> bool:
	"""
	Duplicate Prevention:
	Check whether team availability notification has already been sent to this department today.
	If already sent, logs an Error Log for troubleshooting and returns True.
	"""
	t_date = getdate(target_date)

	# 1. Check Communication records
	comms = frappe.get_all(
		"Communication",
		filters={
			"reference_doctype": "Department",
			"reference_name": department,
		},
		fields=["name", "subject", "email_template", "communication_date", "creation"],
	)

	for comm in comms:
		comm_date = getdate(comm.get("communication_date") or comm.get("creation"))
		if comm_date == t_date:
			comm_template = comm.get("email_template") or ""
			comm_subject = (comm.get("subject") or "").lower()

			if (template_name and comm_template == template_name) or (
				"availability" in comm_subject or "team availability" in comm_template.lower()
			):
				frappe.log_error(
					title=f"Team Availability Notification Already Sent for {department}",
					message=(
						f"Team availability notification for department '{department}' on {t_date} "
						f"was already sent via Communication {comm.get('name')}. Skipping duplicate send."
					),
					reference_doctype="Department",
					reference_name=department,
				)
				return True

	# 2. Check Email Queue records (currently queued / sending emails)
	queues = frappe.get_all(
		"Email Queue",
		filters={
			"reference_doctype": "Department",
			"reference_name": department,
			"status": ["in", ["Not Sent", "Sending"]],
		},
		fields=["name", "message", "communication"],
	)

	formatted_date = t_date.strftime("%d %b, %Y")
	date_str = str(t_date)

	for q in queues:
		comm_name = q.get("communication")
		if comm_name:
			comm_date = frappe.db.get_value("Communication", comm_name, "communication_date")
			if comm_date and getdate(comm_date) != t_date:
				continue

		msg = (q.get("message") or "").lower()
		if "availability" in msg and (formatted_date.lower() in msg or date_str in msg):
			frappe.log_error(
				title=f"Team Availability Notification Already Sent for {department}",
				message=(
					f"Team availability notification for department '{department}' on {t_date} "
					f"is already queued in Email Queue {q.get('name')}. Skipping duplicate send."
				),
				reference_doctype="Department",
				reference_name=department,
			)
			return True

	return False


def send_daily_team_availability_notifications(date=None) -> dict:
	"""
	Scheduled entry point: Send department-wise team availability notification emails
	every day at 8:00 AM (0 8 * * *).
	Groups employees by department, identifies employees on leave or working remotely,
	excludes unavailable employees from the recipient list, and sends notifications
	only when relevant availability changes exist.
	"""
	target_date = getdate(date) if date else getdate(today())
	artem_setting = get_artem_settings()

	if not artem_setting:
		return {
			"departments_sent": 0,
			"departments_skipped_duplicate": 0,
			"departments_no_availability": 0,
			"errors": 1,
			"message": "Artem Setting could not be loaded",
		}

	template_name = artem_setting.get("team_availability_notification_email_template")
	if not template_name:
		frappe.log_error(
			title="Team Availability Notification Email Template Not Configured",
			message=(
				"Team Availability Notification Email Template is not linked in Artem Setting. "
				"Please go to Artem Setting > Auto Email Configuration and select a template."
			),
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return {
			"departments_sent": 0,
			"departments_skipped_duplicate": 0,
			"departments_no_availability": 0,
			"errors": 1,
			"message": "Team Availability Email Template not configured in Artem Setting",
		}

	if not frappe.db.exists("Email Template", template_name):
		frappe.log_error(
			title="Team Availability Notification Email Template Not Found",
			message=(
				f"The Email Template '{template_name}' configured in Artem Setting "
				"does not exist in Email Template doctype. Please configure a valid template."
			),
			reference_doctype="Email Template",
			reference_name=template_name,
		)
		return {
			"departments_sent": 0,
			"departments_skipped_duplicate": 0,
			"departments_no_availability": 0,
			"errors": 1,
			"message": f"Email Template '{template_name}' not found",
		}

	try:
		template_doc = frappe.get_doc("Email Template", template_name)
	except Exception as e:
		frappe.log_error(
			title="Failed to Load Team Availability Email Template",
			message=f"Could not load Email Template '{template_name}': {e}\n\n{frappe.get_traceback()}",
			reference_doctype="Email Template",
			reference_name=template_name,
		)
		return {
			"departments_sent": 0,
			"departments_skipped_duplicate": 0,
			"departments_no_availability": 0,
			"errors": 1,
			"message": f"Could not load template '{template_name}'",
		}

	# Query active employees and map by department
	active_employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=[
			"name",
			"employee_name",
			"department",
			"company",
			"prefered_email",
			"company_email",
		],
		order_by="employee_name asc",
	)

	emp_dept_map: dict[str, str] = {}
	dept_employees_map: dict[str, list[dict]] = {}
	for emp in active_employees:
		dept = emp.get("department")
		emp_id = emp.get("name")
		if dept:
			emp_dept_map[emp_id] = dept
			dept_employees_map.setdefault(dept, []).append(emp)

	# Query leave and remote work records for target_date
	leave_map = get_employees_on_leave(target_date)
	wfh_map = get_employees_working_remotely(target_date)

	# Group unavailable employees by department (prioritizing current Employee master department)
	dept_on_leave: dict[str, list[dict]] = {}
	for emp_id, leave_info in leave_map.items():
		dept = (
			emp_dept_map.get(emp_id)
			or frappe.db.get_value("Employee", emp_id, "department")
			or leave_info.get("department")
		)
		if dept:
			leave_info["department"] = dept
			dept_on_leave.setdefault(dept, []).append(leave_info)

	dept_wfh: dict[str, list[dict]] = {}
	for emp_id, wfh_info in wfh_map.items():
		dept = (
			emp_dept_map.get(emp_id)
			or frappe.db.get_value("Employee", emp_id, "department")
			or wfh_info.get("department")
		)
		if dept:
			wfh_info["department"] = dept
			dept_wfh.setdefault(dept, []).append(wfh_info)

	sent_count = 0
	skipped_duplicate_count = 0
	no_availability_count = 0
	error_count = 0

	date_range_str = target_date.strftime("%d %b, %Y")

	for department, employees in dept_employees_map.items():
		on_leave_employees = dept_on_leave.get(department, [])
		wfh_employees = dept_wfh.get(department, [])

		# Requirement 7: Avoid sending emails when no relevant availability information exists
		if not on_leave_employees and not wfh_employees:
			no_availability_count += 1
			continue

		# Requirement 7: Ensure each department receives only one notification per scheduled run
		if is_department_notification_sent_today(department, target_date, template_name):
			skipped_duplicate_count += 1
			continue

		# Determine recipients:
		# 1. Available members and members working remotely (WFH) receive the notification.
		# 2. Members on leave also receive the notification when there are other colleagues on leave or working remotely
		#    (total_availability_count > 1) so team members can see each other's status.
		#    (If an employee is the only one on leave in the department, they are excluded to avoid self-only notice).
		total_availability_count = len(on_leave_employees) + len(wfh_employees)
		leave_employee_ids = {item.get("employee") for item in on_leave_employees}

		recipient_members = []
		for emp in employees:
			emp_id = emp.get("name")
			if emp_id not in leave_employee_ids:
				# In office or working remotely (WFH)
				recipient_members.append(emp)
			elif total_availability_count > 1:
				# On leave, but other colleagues also have availability events in the department
				recipient_members.append(emp)

		recipient_emails: list[str] = []
		for member in recipient_members:
			email = get_employee_recipient_email(member)
			if email and email not in recipient_emails:
				recipient_emails.append(email)

		if not recipient_emails:
			# Log error if no valid email could be resolved for remaining available members
			error_count += 1
			frappe.log_error(
				title=f"No Valid Recipients for Department {department}",
				message=(
					f"Cannot send team availability notification for department '{department}'. "
					"No available members have a valid email configured (checked prefered_email and company_email)."
				),
				reference_doctype="Department",
				reference_name=department,
			)
			continue

		# Build availability HTML details
		availability_details_html = build_availability_details_html(
			on_leave_list=on_leave_employees,
			wfh_list=wfh_employees,
		)

		context = {
			"date_range": date_range_str,
			"target_date": target_date,
			"department": department,
			"availability_details": availability_details_html,
			"on_leave_employees": on_leave_employees,
			"wfh_employees": wfh_employees,
			"on_leave_count": len(on_leave_employees),
			"wfh_count": len(wfh_employees),
		}

		try:
			raw_subject = template_doc.subject or f"Team Availability Update - {date_range_str}"
			raw_message = template_doc.response or template_doc.get("message") or ""

			rendered_subject = frappe.render_template(raw_subject, context)  # nosemgrep
			rendered_message = frappe.render_template(raw_message, context)  # nosemgrep
		except Exception as e:
			error_count += 1
			frappe.log_error(
				title=f"Error Rendering Team Availability Email for {department}",
				message=(
					f"Failed to render Team Availability Template '{template_name}' for department {department}: "
					f"{e}\n\n{frappe.get_traceback()}"
				),
				reference_doctype="Department",
				reference_name=department,
			)
			continue

		comm_name = None
		try:
			comm = frappe.get_doc(
				{
					"doctype": "Communication",
					"communication_type": "Automated Message",
					"communication_medium": "Email",
					"sent_or_received": "Sent",
					"reference_doctype": "Department",
					"reference_name": department,
					"subject": rendered_subject,
					"content": rendered_message,
					"recipients": ", ".join(recipient_emails),
					"email_template": template_name,
					"communication_date": target_date,
				}
			)
			comm.insert(ignore_permissions=True)
			comm_name = comm.name

			frappe.sendmail(
				recipients=recipient_emails,
				expose_recipients="header",
				subject=rendered_subject,
				message=rendered_message,
				reference_doctype="Department",
				reference_name=department,
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
				title=f"Failed to Send Team Availability Email for {department}",
				message=(
					f"Failed to send team availability email to department {department}: "
					f"{e}\n\n{frappe.get_traceback()}"
				),
				reference_doctype="Department",
				reference_name=department,
			)

	return {
		"departments_sent": sent_count,
		"departments_skipped_duplicate": skipped_duplicate_count,
		"departments_no_availability": no_availability_count,
		"errors": error_count,
	}
