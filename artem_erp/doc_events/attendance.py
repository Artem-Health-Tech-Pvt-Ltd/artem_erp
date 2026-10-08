# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate


@frappe.whitelist()
def can_create_attendance_request(
	employee: str | None = None,
	attendance_date: str | None = None,
	status: str | None = None,
	attendance_name: str | None = None,
	is_new: bool | str = False,
) -> dict:
	"""
	Check whether 'Create Attendance Request' button should be displayed:
	1. Attendance Status is Absent AND no Leave Application covering attendance_date.
	2. Attendance Status is Half Day AND no Leave Application for the remaining/other half of the day.
	3. Attendance does not exist for the employee/date AND no Leave Application for that date.
	The button should NOT be displayed when the relevant period is already covered by a Leave Application.
	"""
	if not employee or not attendance_date:
		return {"can_create": False, "half_day": False}

	attendance_date = getdate(attendance_date)
	is_new = frappe.parse_json(is_new) if isinstance(is_new, str) else bool(is_new)

	# Fetch active Leave Applications for employee covering attendance_date
	# docstatus < 2 means Draft (0) or Submitted (1), excluding Cancelled (2) and Rejected
	leave_applications = frappe.get_all(
		"Leave Application",
		filters={
			"employee": employee,
			"docstatus": ["<", 2],
			"status": ["!=", "Rejected"],
			"from_date": ["<=", attendance_date],
			"to_date": [">=", attendance_date],
		},
		fields=[
			"name",
			"half_day",
			"half_day_date",
			"total_leave_days",
			"from_date",
			"to_date",
			"status",
			"docstatus",
		],
	)

	has_full_day_leave = False
	has_half_day_leave = False

	for la in leave_applications:
		is_half_day_on_date = flt(la.total_leave_days) == 0.5 or (
			la.half_day and la.half_day_date and getdate(la.half_day_date) == attendance_date
		)
		if is_half_day_on_date:
			has_half_day_leave = True
		else:
			has_full_day_leave = True

	# If the entire day is already covered by a full-day Leave Application
	if has_full_day_leave:
		return {
			"can_create": False,
			"half_day": False,
			"reason": "Date is covered by full-day Leave Application",
		}

	# Check whether an Attendance record exists in DB for this employee and date
	existing_attendance = None
	if attendance_name and not is_new and frappe.db.exists("Attendance", attendance_name):
		existing_attendance = frappe.db.get_value(
			"Attendance",
			attendance_name,
			["name", "status", "docstatus"],
			as_dict=True,
		)
	else:
		existing_attendance = frappe.db.get_value(
			"Attendance",
			{
				"employee": employee,
				"attendance_date": attendance_date,
				"docstatus": ["<", 2],
			},
			["name", "status", "docstatus"],
			as_dict=True,
		)

	# Effective status from current form or existing DB record
	current_status = status
	if not current_status and existing_attendance:
		current_status = existing_attendance.status

	# Case 1: Attendance Status is Absent
	if current_status == "Absent":
		if has_half_day_leave:
			# Half day on leave, so attendance request is eligible for the other half
			return {
				"can_create": True,
				"half_day": True,
				"reason": "Absent with other half covered by leave",
			}
		return {
			"can_create": True,
			"half_day": False,
			"reason": "Absent with no leave application",
		}

	# Case 2: Attendance Status is Half Day
	elif current_status == "Half Day":
		if has_half_day_leave:
			# Remaining half is already covered by a Leave Application
			return {
				"can_create": False,
				"half_day": False,
				"reason": "Remaining half of the day is already covered by Leave Application",
			}
		# No leave application for the other half.
		# Note: We must NOT set half_day=True here because ERPNext treats a Half Day request
		# on an already Half Day attendance as 'status unchanged' and rejects it.
		# The request is to regularize the day to Present.
		return {
			"can_create": True,
			"half_day": False,
			"reason": "Half Day with no leave for the other half",
		}

	# Case 3: Attendance does not exist for the employee/date
	elif not existing_attendance:
		if not leave_applications:
			return {
				"can_create": True,
				"half_day": False,
				"reason": "Attendance does not exist and no Leave Application for date",
			}
		return {
			"can_create": False,
			"half_day": False,
			"reason": "Relevant period covered by Leave Application",
		}

	# Other statuses like Present, Work From Home, On Leave
	return {
		"can_create": False,
		"half_day": False,
		"reason": f"Attendance status is {current_status}",
	}
