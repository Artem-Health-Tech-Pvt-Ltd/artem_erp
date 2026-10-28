# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, format_date, getdate, today

from artem_erp.auto_email.utils import (
	get_artem_settings,
	get_employee_recipient_email,
)


def get_required_working_hours(att) -> str:
	"""
	Determine required working hours string for the attendance record dynamically:
	1. If Partial Day Leave was approved, check custom_adjusted_required_hours.
	2. If standard_working_hours is explicitly set on Attendance, use that.
	3. Fetch employee's shift (from att.shift, Employee default_shift, or active Shift Assignment)
	   and calculate exact duration from Shift Type start_time to end_time
	   (e.g., Ahmedabad HO: 9:30 to 19:00 = 9.5 hrs, Mumbai: 9:30 to 18:30 = 9.0 hrs).
	4. Fallback to shift's working_hours_threshold_for_half_day or HR Settings standard_working_hours.
	"""
	if att.get("custom_adjusted_required_hours"):
		val = flt(att.get("custom_adjusted_required_hours"))
		if val > 0:
			return f"{val:.1f} hrs"

	if att.get("standard_working_hours"):
		val = flt(att.get("standard_working_hours"))
		if val > 0:
			return f"{val:.1f} hrs"

	emp_id = att.get("employee")
	shift_name = att.get("shift")
	if not shift_name and emp_id:
		shift_name = frappe.db.get_value("Employee", emp_id, "default_shift") or frappe.db.get_value(
			"Shift Assignment", {"employee": emp_id, "status": "Active"}, "shift_type"
		)

	if shift_name:
		try:
			shift_doc = frappe.get_cached_doc("Shift Type", shift_name)
			if shift_doc.start_time and shift_doc.end_time:
				st = shift_doc.start_time
				et = shift_doc.end_time
				if hasattr(et, "total_seconds") and hasattr(st, "total_seconds"):
					diff_sec = (et - st).total_seconds()
				else:
					st_parts = str(st).split(":")
					et_parts = str(et).split(":")
					diff_sec = (int(et_parts[0]) * 3600 + int(et_parts[1]) * 60) - (
						int(st_parts[0]) * 3600 + int(st_parts[1]) * 60
					)
				if diff_sec < 0:
					diff_sec += 24 * 3600
				hours = diff_sec / 3600.0
				if hours > 0:
					return f"{hours:.1f} hrs"

			th = flt(shift_doc.working_hours_threshold_for_half_day)
			if th > 0:
				return f"{th:.1f} hrs"
		except Exception:
			pass

	hr_std = flt(frappe.db.get_single_value("HR Settings", "standard_working_hours"))
	if hr_std > 0:
		return f"{hr_std:.1f} hrs"

	return "9.5 hrs" if "ahmedabad" in str(shift_name).lower() else "9.0 hrs"


def get_missing_punches_label(att) -> str:
	"""
	Determine whether punches were missing for this attendance.
	"""
	in_time = att.get("in_time")
	out_time = att.get("out_time")
	working_hours = flt(att.get("working_hours"))

	if not in_time and not out_time:
		return "Yes (Missing both Punch-In and Punch-Out)"
	if not in_time:
		return "Yes (Missing Punch-In)"
	if not out_time:
		return "Yes (Missing Punch-Out)"
	if working_hours <= 0:
		return "Yes (0 working hours recorded)"

	return "No"


def get_penalty_leave_type(att, penalty_status: str | None = None) -> str:
	"""
	Determine the leave type / penalty status deducted for the attendance record.
	"""
	if att.get("leave_type"):
		return att.get("leave_type")
	if penalty_status:
		return penalty_status
	if att.get("status"):
		return att.get("status")
	return "None"


def is_penalty_notification_already_sent(attendance_name: str, template_name: str | None = None) -> bool:
	"""
	Duplicate Prevention:
	Check if a penalty notification email has already been sent or queued for this Attendance record.
	"""
	comms = frappe.get_all(
		"Communication",
		filters={
			"reference_doctype": "Attendance",
			"reference_name": attendance_name,
		},
		fields=["name", "email_template", "subject"],
	)

	for c in comms:
		comm_template = c.get("email_template") or ""
		comm_subject = (c.get("subject") or "").lower()
		if template_name and comm_template == template_name:
			return True
		if "penalty" in comm_subject or "penalty" in comm_template.lower():
			return True

	queues = frappe.get_all(
		"Email Queue",
		filters={
			"reference_doctype": "Attendance",
			"reference_name": attendance_name,
			"status": ["!=", "Error"],
		},
		fields=["name", "message"],
	)

	for q in queues:
		msg = (q.get("message") or "").lower()
		if "penalty" in msg:
			return True

	return False


def send_attendance_penalty_email(
	attendance, reason: str | None = None, penalty_status: str | None = None
) -> bool:
	"""
	Automatically notify an employee by email whenever an attendance penalty is applied.
	Fetches configuration and email template from Artem Setting.
	"""
	if isinstance(attendance, str):
		att = frappe.get_doc("Attendance", attendance)
	elif isinstance(attendance, dict):
		att = frappe._dict(attendance)
	else:
		att = attendance

	att_name = att.get("name")
	emp_id = att.get("employee")

	if not emp_id:
		frappe.log_error(
			title=f"Cannot Send Penalty Email for Attendance {att_name}",
			message=f"Attendance record {att_name} does not have an employee associated.",
			reference_doctype="Attendance",
			reference_name=att_name,
		)
		return False

	artem_setting = get_artem_settings()
	if not artem_setting:
		return False

	template_name = artem_setting.get("employee_attendance_penalty_notification_email_template")
	if not template_name:
		frappe.log_error(
			title="Attendance Penalty Notification Email Template Not Configured",
			message=(
				"Employee Attendance Penalty Notification Email Template is not linked in Artem Setting. "
				"Please go to Artem Setting > Auto Email Configuration and select a template."
			),
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return False

	if not frappe.db.exists("Email Template", template_name):
		frappe.log_error(
			title="Attendance Penalty Email Template Not Found",
			message=(
				f"The Email Template '{template_name}' configured in Artem Setting does not exist. "
				"Please configure a valid email template."
			),
			reference_doctype="Email Template",
			reference_name=template_name,
		)
		return False

	# Duplicate check: Do not send multiple penalty emails for the same attendance record
	if is_penalty_notification_already_sent(att_name, template_name):
		frappe.log_error(
			title=f"Attendance Penalty Email Already Sent for {att_name}",
			message=(
				f"An attendance penalty notification for attendance record {att_name} ({emp_id}) "
				"has already been sent or queued. Skipping duplicate send."
			),
			reference_doctype="Attendance",
			reference_name=att_name,
		)
		return False

	# Fetch Employee details
	employee_doc = frappe.get_all(
		"Employee",
		filters={"name": emp_id},
		fields=["name", "employee_name", "prefered_email", "company_email"],
		limit=1,
	)
	if not employee_doc:
		frappe.log_error(
			title=f"Employee {emp_id} Not Found",
			message=f"Could not find Employee record for ID '{emp_id}' while sending penalty notification.",
			reference_doctype="Attendance",
			reference_name=att_name,
		)
		return False

	emp_data = employee_doc[0]
	recipient_email = get_employee_recipient_email(emp_data)
	if not recipient_email:
		frappe.log_error(
			title=f"No Email Found for Employee {emp_id}",
			message=(
				f"Cannot send attendance penalty notification for {att_name}. "
				f"Employee '{emp_id}' ({emp_data.get('employee_name')}) has no valid preferred or company email configured."
			),
			reference_doctype="Attendance",
			reference_name=att_name,
		)
		return False

	try:
		template_doc = frappe.get_doc("Email Template", template_name)
	except Exception as e:
		frappe.log_error(
			title="Failed to Load Penalty Email Template",
			message=f"Could not load Email Template '{template_name}': {e}\n\n{frappe.get_traceback()}",
			reference_doctype="Email Template",
			reference_name=template_name,
		)
		return False

	att_date = att.get("attendance_date")
	penalty_date_str = (
		format_date(att_date, "medium") if att_date else format_date(getdate(today()), "medium")
	)
	emp_name = emp_data.get("employee_name") or emp_id
	penalty_reason = reason
	missing_punches = get_missing_punches_label(att)
	required_hours = get_required_working_hours(att)
	actual_hours = f"{flt(att.get('working_hours')):.2f} hrs"
	leave_type_str = get_penalty_leave_type(att, penalty_status)

	context = {
		"employee_name": emp_name,
		"employee": emp_id,
		"penalty_date": penalty_date_str,
		"penalty_reason": penalty_reason,
		"missing_punches": missing_punches,
		"required_working_hours": required_hours,
		"actual_working_hours": actual_hours,
		"leave_type": leave_type_str,
		"status": penalty_status or att.get("status") or "Absent",
		"attendance": att_name,
	}

	try:
		raw_subject = template_doc.subject or f"Apply Attendance Penalty On {penalty_date_str}"
		raw_message = template_doc.response or template_doc.get("message") or ""

		rendered_subject = frappe.render_template(raw_subject, context)  # nosemgrep
		rendered_message = frappe.render_template(raw_message, context)  # nosemgrep
	except Exception as e:
		frappe.log_error(
			title=f"Error Rendering Penalty Email for {att_name}",
			message=f"Failed to render penalty email template '{template_name}': {e}\n\n{frappe.get_traceback()}",
			reference_doctype="Attendance",
			reference_name=att_name,
		)
		return False

	comm_name = None
	try:
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Automated Message",
				"communication_medium": "Email",
				"sent_or_received": "Sent",
				"reference_doctype": "Attendance",
				"reference_name": att_name,
				"subject": rendered_subject,
				"content": rendered_message,
				"recipients": recipient_email,
				"email_template": template_name,
				"communication_date": today(),
			}
		)
		comm.insert(ignore_permissions=True)
		comm_name = comm.name

		frappe.sendmail(
			recipients=[recipient_email],
			subject=rendered_subject,
			message=rendered_message,
			reference_doctype="Attendance",
			reference_name=att_name,
			communication=comm_name,
		)
		return True
	except Exception as e:
		if comm_name:
			try:
				frappe.db.delete("Communication", {"name": comm_name})
			except Exception:
				pass
		frappe.log_error(
			title=f"Failed to Send Penalty Email for {att_name}",
			message=f"Failed to send attendance penalty email to {recipient_email}: {e}\n\n{frappe.get_traceback()}",
			reference_doctype="Attendance",
			reference_name=att_name,
		)
		return False
