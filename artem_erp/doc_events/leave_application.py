# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import datetime

import frappe
from frappe import _
from frappe.utils import (
	cint,
	flt,
	formatdate,
	getdate,
	to_timedelta,
)


@frappe.whitelist()
def get_partial_day_details(
	employee: str,
	date: str,
	leave_type: str | None = None,
	partial_day_type: str | None = None,
	duration_minutes: int | str | None = None,
) -> dict:
	"""
	Fetch active shift and calculate adjusted time for Partial Day Leave Application.
	Returns:
	{
	    "is_partial_day": bool,
	    "max_duration": int,
	    "shift": str,
	    "shift_start": str,
	    "shift_end": str,
	    "adjusted_time": str
	}
	"""
	if not employee or not date:
		return {}

	date = getdate(date)
	duration_minutes = cint(duration_minutes)

	max_duration = 0
	is_partial_day = False
	if leave_type:
		leave_type_doc = frappe.db.get_value(
			"Leave Type",
			leave_type,
			["custom_is_partial_day", "custom_partial_day_max_duration"],
			as_dict=True,
		)
		if leave_type_doc:
			is_partial_day = bool(cint(leave_type_doc.custom_is_partial_day))
			max_duration = cint(leave_type_doc.custom_partial_day_max_duration)

	shift_info = get_active_shift_for_employee(employee, date)
	if not shift_info:
		return {
			"is_partial_day": is_partial_day,
			"max_duration": max_duration,
			"shift": None,
			"shift_start": None,
			"shift_end": None,
			"adjusted_time": None,
			"error": _("No active Shift Assignment found for {0} on {1}").format(employee, formatdate(date)),
		}

	adjusted_time = None
	if partial_day_type and duration_minutes > 0:
		adjusted_time = calculate_adjusted_time_str(
			shift_info.get("start_time"),
			shift_info.get("end_time"),
			partial_day_type,
			duration_minutes,
		)

	return {
		"is_partial_day": is_partial_day,
		"max_duration": max_duration,
		"shift": shift_info.get("name"),
		"shift_start": str(shift_info.get("start_time")),
		"shift_end": str(shift_info.get("end_time")),
		"adjusted_time": adjusted_time,
	}


def get_active_shift_for_employee(employee: str, date) -> dict | None:
	"""
	Retrieve active Shift Type for employee on the given date from Shift Assignment.
	"""
	date = getdate(date)
	assignments = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": employee,
			"start_date": ["<=", date],
			"docstatus": 1,
			"status": "Active",
		},
		fields=["shift_type", "start_date", "end_date"],
		order_by="start_date desc",
	)

	shift_type_name = None
	for sa in assignments:
		if sa.end_date and getdate(sa.end_date) < date:
			continue
		shift_type_name = sa.shift_type
		break

	if not shift_type_name:
		# Fallback to employee default shift if any
		shift_type_name = frappe.db.get_value("Employee", employee, "default_shift")

	if not shift_type_name:
		return None

	shift_doc = frappe.get_cached_doc("Shift Type", shift_type_name)
	return {
		"name": shift_doc.name,
		"start_time": shift_doc.start_time,
		"end_time": shift_doc.end_time,
	}


def calculate_adjusted_time_str(
	shift_start,
	shift_end,
	partial_day_type: str,
	duration_minutes: int,
) -> str | None:
	"""
	Calculate Adjusted Time string (HH:MM:SS) based on Partial Day Type and duration.
	Late Arrival = Shift Start + Partial Day Duration
	Early Exit   = Shift End - Partial Day Duration
	"""
	if not partial_day_type or duration_minutes <= 0:
		return None

	if partial_day_type == "Late Arrival":
		if not shift_start:
			return None
		base_td = to_timedelta(shift_start)
		adj_td = base_td + datetime.timedelta(minutes=duration_minutes)
	elif partial_day_type == "Early Exit":
		if not shift_end:
			return None
		base_td = to_timedelta(shift_end)
		adj_td = base_td - datetime.timedelta(minutes=duration_minutes)
	else:
		return None
	total_seconds = int(adj_td.total_seconds()) % 86400
	hours = total_seconds // 3600
	minutes = (total_seconds % 3600) // 60
	seconds = total_seconds % 60
	return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def validate(doc, method=None):
	"""
	Validate Partial Day fields on Leave Application.
	"""
	if not doc.leave_type:
		doc.custom_is_partial_day_leave = 0
		return

	leave_type_info = frappe.db.get_value(
		"Leave Type",
		doc.leave_type,
		["custom_is_partial_day", "custom_partial_day_max_duration"],
		as_dict=True,
	)

	is_partial_day = bool(leave_type_info and cint(leave_type_info.custom_is_partial_day))
	doc.custom_is_partial_day_leave = 1 if is_partial_day else 0

	if not is_partial_day:
		# Clear partial day fields for non-partial leave
		doc.custom_partial_day_type = None
		doc.custom_partial_day_duration = 0
		doc.custom_shift = None
		doc.custom_adjusted_time = None
		return

	# Partial Day specific validations
	# 1. From Date and To Date must be identical (single day only)
	if doc.from_date != doc.to_date:
		frappe.throw(
			_(
				"Partial Day Leave can only be applied for a single working day (From Date and To Date must be the same)."
			)
		)

	# 2. Cannot combine Partial Day with Half Day
	if doc.half_day:
		frappe.throw(_("Partial Day Leave cannot be combined with Half Day."))

	# 3. Partial Day Type is required
	if not doc.custom_partial_day_type:
		frappe.throw(_("Partial Day Type (Late Arrival or Early Exit) is required."))

	if doc.custom_partial_day_type not in ("Late Arrival", "Early Exit"):
		frappe.throw(_("Invalid Partial Day Type. Must be 'Late Arrival' or 'Early Exit'."))

	# 4. Partial Day Duration validation
	duration = cint(doc.custom_partial_day_duration)
	if duration <= 0:
		frappe.throw(_("Partial Day Duration must be greater than 0 minutes."))

	max_duration = cint(leave_type_info.get("custom_partial_day_max_duration"))
	if duration > max_duration:
		frappe.throw(
			_(
				"Requested Partial Day Duration ({0} minutes) exceeds the maximum allowed duration of {1} minutes for {2}."
			).format(duration, max_duration, doc.leave_type)
		)

	# 5. Shift assignment and adjusted time calculation
	shift_info = get_active_shift_for_employee(doc.employee, doc.from_date)
	if not shift_info:
		frappe.throw(
			_("No active Shift Assignment found for employee {0} on {1}.").format(
				doc.employee_name or doc.employee, formatdate(doc.from_date)
			)
		)

	doc.custom_shift = shift_info.get("name")
	adj_time = calculate_adjusted_time_str(
		shift_info.get("start_time"),
		shift_info.get("end_time"),
		doc.custom_partial_day_type,
		duration,
	)
	if not adj_time:
		frappe.throw(_("Could not calculate Adjusted Time for the assigned shift."))
	doc.custom_adjusted_time = adj_time

	# 6. Ensure total_leave_days is 1.0 for Partial Day leave consumption
	doc.total_leave_days = 1.0


def on_submit(doc, method=None):
	"""
	When Leave Application is approved / submitted:
	If Partial Day Leave, update linked Attendance records so they reflect
	adjusted required hours and do not stay marked as 'On Leave'.
	"""
	if not doc.custom_is_partial_day_leave:
		return

	from artem_erp.doc_events.attendance import sync_partial_day_attendance_for_leave

	sync_partial_day_attendance_for_leave(doc)


def on_cancel(doc, method=None):
	"""
	When Leave Application is cancelled:
	Remove partial day allowances from linked Attendance.
	"""
	if not doc.custom_is_partial_day_leave:
		return

	from artem_erp.doc_events.attendance import clear_partial_day_attendance_for_leave

	clear_partial_day_attendance_for_leave(doc)
