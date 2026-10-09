# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import datetime

import frappe
from frappe.utils import (
	cint,
	flt,
	getdate,
	time_diff_in_hours,
	to_timedelta,
)


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
			"total_leave_days",
			"from_date",
			"to_date",
			"status",
			"docstatus",
			"custom_is_partial_day_leave",
		],
	)

	has_full_day_leave = False
	has_half_day_leave = False

	for la in leave_applications:
		if cint(la.get("custom_is_partial_day_leave")):
			continue
		if la.half_day or flt(la.total_leave_days) == 0.5:
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
			return {
				"can_create": False,
				"half_day": False,
				"reason": "Remaining half of the day is already covered by Leave Application",
			}
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

	return {
		"can_create": False,
		"half_day": False,
		"reason": f"Attendance status is {current_status}",
	}


def get_shift_duration_hours(shift_name: str | None) -> float:
	"""
	Calculate total shift duration in hours from Shift Type start and end time.
	"""

	if not shift_name:
		return None

	shift_doc = frappe.get_cached_doc("Shift Type", shift_name)
	if shift_doc.start_time and shift_doc.end_time:
		diff = time_diff_in_hours(str(shift_doc.end_time), str(shift_doc.start_time))
		if diff < 0:
			diff += 24.0
		if diff > 0:
			return flt(diff, 2)


def _to_timedelta_safe(val):
	"""
	Safely convert a string, datetime.time, or datetime.datetime object to a datetime.timedelta.
	"""
	if not val:
		return None
	if isinstance(val, datetime.datetime):
		val = val.time()
	return to_timedelta(val)


def is_within_late_arrival_window(
	in_time, shift_start, duration_minutes: int, threshold_minutes: int = 0
) -> bool:
	"""
	Checks if employee arrival is within the approved Partial Day Late Arrival window.
	"""
	if not in_time or not shift_start:
		return True

	in_td = _to_timedelta_safe(in_time)
	start_td = _to_timedelta_safe(shift_start)
	if not in_td or not start_td:
		return True

	max_allowed_td = start_td + datetime.timedelta(minutes=duration_minutes + threshold_minutes)
	return in_td <= max_allowed_td


def is_within_early_exit_window(
	out_time, shift_end, duration_minutes: int, threshold_minutes: int = 0
) -> bool:
	"""
	Checks if employee departure is within the approved Partial Day Early Exit window.
	"""
	if not out_time or not shift_end:
		return True

	out_td = _to_timedelta_safe(out_time)
	end_td = _to_timedelta_safe(shift_end)
	if not out_td or not end_td:
		return True

	min_allowed_td = end_td - datetime.timedelta(minutes=duration_minutes + threshold_minutes)
	return out_td >= min_allowed_td


def apply_partial_day_to_attendance(doc, method=None):
	"""
	Attendance validate event hook.
	Applies approved Partial Day Leave Application details to Attendance:
	- Stores partial day metadata
	- Calculates adjusted required working hours
	- Prevents status from being set to 'On Leave' (sets to 'Present' if attended)
	- Suppresses late_entry or early_exit flags if within approved partial day allowance
	"""
	if isinstance(doc, str):
		doc = frappe.get_doc("Attendance", doc)

	if not doc.employee or not doc.attendance_date:
		return

	attendance_date = getdate(doc.attendance_date)

	# Fetch Approved Partial Day Leave Application for this date
	approved_partial_day = frappe.db.get_value(
		"Leave Application",
		filters={
			"employee": doc.employee,
			"from_date": ["<=", attendance_date],
			"to_date": [">=", attendance_date],
			"docstatus": 1,
			"status": "Approved",
			"custom_is_partial_day_leave": 1,
		},
		fieldname=[
			"name",
			"leave_type",
			"custom_partial_day_type",
			"custom_partial_day_duration",
			"custom_shift",
			"custom_adjusted_time",
		],
		as_dict=True,
	)

	if approved_partial_day:
		duration_mins = cint(approved_partial_day.custom_partial_day_duration)
		partial_day_type = approved_partial_day.custom_partial_day_type
		applicable_shift = doc.shift or approved_partial_day.custom_shift

		doc.custom_is_partial_day = 1
		doc.custom_partial_day_type = partial_day_type
		doc.custom_partial_day_duration = duration_mins

		# Calculate adjusted required working hours
		normal_shift_hours = get_shift_duration_hours(applicable_shift)
		allowance_hours = flt(duration_mins) / 60.0
		adjusted_hours = max(0.0, flt(normal_shift_hours - allowance_hours, 2))
		doc.custom_adjusted_required_hours = adjusted_hours

		# Evaluate status based on actual working hours and adjusted requirements
		actual_wh = flt(doc.working_hours)
		if actual_wh > 0:
			if actual_wh >= adjusted_hours:
				doc.status = "Present"
				if getattr(doc, "custom_penalty", 0):
					doc.custom_penalty = 0
			else:
				# Did not complete adjusted required working hours
				threshold_absent = 0.0
				if applicable_shift:
					shift_doc = frappe.get_cached_doc("Shift Type", applicable_shift)
					threshold_absent = max(
						0.0, flt(shift_doc.working_hours_threshold_for_absent) - allowance_hours
					)

				if threshold_absent and actual_wh < threshold_absent:
					doc.status = "Absent"
				else:
					doc.status = "Half Day"
		elif doc.status == "On Leave":
			# If 0 working hours, Partial Day leave does not give full-day attendance
			doc.status = "Absent"

		# Check late entry / early exit suppression
		shift_start = None
		shift_end = None
		late_threshold = 0
		if applicable_shift:
			shift_doc = frappe.get_cached_doc("Shift Type", applicable_shift)
			shift_start = shift_doc.start_time
			shift_end = shift_doc.end_time
			late_threshold = cint(getattr(shift_doc, "late_entry_grace_period", 0))

		if partial_day_type == "Late Arrival" and doc.late_entry:
			if is_within_late_arrival_window(doc.in_time, shift_start, duration_mins, late_threshold):
				doc.late_entry = 0

		if partial_day_type == "Early Exit" and doc.early_exit:
			if is_within_early_exit_window(doc.out_time, shift_end, duration_mins, 0):
				doc.early_exit = 0

	else:
		# No approved Partial Day Leave
		doc.custom_is_partial_day = 0
		doc.custom_partial_day_type = None
		doc.custom_partial_day_duration = 0
		doc.custom_adjusted_required_hours = 0.0


def sync_partial_day_attendance_for_leave(leave_doc):
	"""
	Triggered when a Partial Day Leave Application is approved / submitted.
	Finds existing Attendance record and updates it with Partial Day allowances.
	If working hours meet the adjusted required hours and a penalty was applied,
	the penalty is removed and status is set to Present.
	"""
	if not leave_doc.employee or not leave_doc.from_date:
		return

	att_name = frappe.db.get_value(
		"Attendance",
		{
			"employee": leave_doc.employee,
			"attendance_date": leave_doc.from_date,
			"docstatus": ["<", 2],
		},
		"name",
	)

	if att_name:
		att_doc = frappe.get_doc("Attendance", att_name)
		apply_partial_day_to_attendance(att_doc)

		# Build dict of updated values to ensure changes persist even if doc is submitted (docstatus 1)
		updated_values = {
			"custom_is_partial_day": att_doc.custom_is_partial_day,
			"custom_partial_day_type": att_doc.custom_partial_day_type,
			"custom_partial_day_duration": att_doc.custom_partial_day_duration,
			"custom_adjusted_required_hours": att_doc.custom_adjusted_required_hours,
			"status": att_doc.status,
			"late_entry": att_doc.late_entry,
			"early_exit": att_doc.early_exit,
		}

		if frappe.get_meta("Attendance").has_field("custom_penalty"):
			updated_values["custom_penalty"] = cint(getattr(att_doc, "custom_penalty", 0))

		frappe.db.set_value("Attendance", att_name, updated_values, update_modified=False)


def clear_partial_day_attendance_for_leave(leave_doc):
	"""
	Triggered when a Partial Day Leave Application is cancelled.
	Clears Partial Day allowances from linked Attendance.
	"""
	if not leave_doc.employee or not leave_doc.from_date:
		return

	att_name = frappe.db.get_value(
		"Attendance",
		{
			"employee": leave_doc.employee,
			"attendance_date": leave_doc.from_date,
			"docstatus": ["<", 2],
		},
		"name",
	)

	if att_name:
		att_doc = frappe.get_doc("Attendance", att_name)
		att_doc.custom_is_partial_day = 0
		att_doc.custom_partial_day_type = None
		att_doc.custom_partial_day_duration = 0
		att_doc.custom_adjusted_required_hours = 0.0
		att_doc.flags.ignore_permissions = True
		att_doc.flags.ignore_validate = True
		att_doc.save()
