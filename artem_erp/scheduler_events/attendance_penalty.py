# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import (
	cint,
	flt,
	get_first_day,
	getdate,
)


def has_leave_or_attendance_request(att):
	"""
	Check if the employee has a Leave Application or Attendance Request covering the attendance date.
	Considers records even if they are in Draft (not necessarily approved/submitted), as long as not Cancelled or Rejected.
	"""
	if att.get("leave_application") or att.get("leave_type") or att.get("attendance_request"):
		return True

	if att.get("status") == "On Leave":
		return True

	# Check for Leave Application covering attendance_date (Draft or Approved, not Rejected/Cancelled)
	leave_filters = {
		"employee": att.employee,
		"docstatus": ["<", 2],
		"status": ["!=", "Rejected"],
		"from_date": ["<=", att.attendance_date],
		"to_date": [">=", att.attendance_date],
	}
	if frappe.db.exists("Leave Application", leave_filters):
		return True

	# Check for Attendance Request covering attendance_date (Draft or Submitted, not Cancelled)
	att_req_filters = {
		"employee": att.employee,
		"docstatus": ["<", 2],
		"from_date": ["<=", att.attendance_date],
		"to_date": [">=", att.attendance_date],
	}
	if frappe.db.exists("Attendance Request", att_req_filters):
		return True

	return False


def is_working_hours_completed(att):
	"""
	Check if employee completed the required minimum daily working hours.
	"""
	# If status is Half Day or Absent, working hours were not completed
	if att.status in ("Half Day", "Absent"):
		return False

	# If shift has thresholds, check actual working_hours against them
	if att.get("shift"):
		shift_doc = frappe.get_cached_doc("Shift Type", att.shift)
		threshold_half_day = flt(shift_doc.working_hours_threshold_for_half_day)
		threshold_absent = flt(shift_doc.working_hours_threshold_for_absent)
		working_hours = flt(att.working_hours)

		if threshold_absent and working_hours < threshold_absent:
			return False
		if threshold_half_day and working_hours < threshold_half_day:
			return False

	if att.status == "Present":
		return True

	return flt(att.working_hours) > 0


def determine_penalty_status(att):
	"""
	Determine whether attendance should be marked as Half Day or Absent based on actual working hours.
	"""
	working_hours = flt(att.working_hours)

	if att.get("shift"):
		shift_doc = frappe.get_cached_doc("Shift Type", att.shift)
		threshold_absent = flt(shift_doc.working_hours_threshold_for_absent)
		threshold_half_day = flt(shift_doc.working_hours_threshold_for_half_day)

		if threshold_absent and working_hours < threshold_absent:
			return "Absent"
		if threshold_half_day:
			return "Half Day" if working_hours >= threshold_half_day else "Absent"

	standard_hours = flt(getattr(att, "standard_working_hours", 0) or 0)
	if standard_hours:
		if working_hours < (standard_hours / 2):
			return "Absent"
		return "Half Day"

	if working_hours > 0:
		return "Half Day"
	return "Absent"


def get_prior_allowed_late_entries_in_month(employee, start_of_month, up_to_date=None, exclude_names=None):
	"""
	Count allowed late entries without penalty in the same calendar month for this employee.
	Only counts late entries where the employee completed minimum required working hours.
	"""
	filters = {
		"employee": employee,
		"docstatus": ["<", 2],
		"late_entry": 1,
		"custom_penalty": 0,
		"attendance_date": [">=", start_of_month],
	}
	if up_to_date:
		filters["attendance_date"] = ["between", [start_of_month, up_to_date]]

	records = frappe.get_all(
		"Attendance",
		filters=filters,
		fields=[
			"name",
			"employee",
			"attendance_date",
			"status",
			"working_hours",
			"shift",
			"late_entry",
			"leave_type",
			"leave_application",
			"attendance_request",
		],
	)

	exclude_set = set(exclude_names or [])
	count = 0
	for r in records:
		if r.name in exclude_set:
			continue
		if is_working_hours_completed(r) and not has_leave_or_attendance_request(r):
			count += 1

	return count


def get_eligible_attendance_records(up_to_date=None, **kwargs):
	"""
	Fetch Attendance records eligible for penalty processing:
	- Attendance records where attendance_date <= cutoff_date (defaults to today)
	- Docstatus is active (docstatus < 2)
	- custom_penalty is not already enabled (custom_penalty == 0)
	- Candidate for penalty: either status is Half Day/Absent or late_entry is enabled
	"""
	if not frappe.get_meta("Attendance").has_field("custom_penalty"):
		return []

	cutoff_date = getdate(up_to_date) if up_to_date else getdate()

	filters = {
		"docstatus": ["<", 2],
		"custom_penalty": 0,
		"attendance_date": ["<=", cutoff_date],
	}

	or_filters = [
		{"status": ["in", ["Half Day", "Absent"]]},
		{"late_entry": 1},
	]

	return frappe.get_all(
		"Attendance",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"employee",
			"attendance_date",
			"status",
			"working_hours",
			"shift",
			"late_entry",
			"leave_type",
			"leave_application",
			"attendance_request",
			"creation",
		],
		order_by="attendance_date asc, creation asc",
	)


def process_attendance_penalties(up_to_date=None, **kwargs):
	"""
	Daily scheduler job to process attendance penalties based on:
	1. Late Entry monthly allowance (Artem Setting: apply_late_entry_penalty, allowed_late_entries_per_month)
	2. Insufficient working hours resulting in Half Day or Absent (Artem Setting: apply_attendance_penalty)
	3. Late Entry + Insufficient working hours
	Excludes records covered by approved Leave or Attendance Request.
	"""
	if not frappe.get_meta("Attendance").has_field("custom_penalty"):
		frappe.log_error(
			"Attendance penalty processing skipped: custom_penalty field not found on Attendance DocType."
		)
		return []

	settings = frappe.get_cached_doc("Artem Setting")

	apply_attendance_penalty = cint(settings.get("apply_attendance_penalty"))
	apply_late_entry_penalty = cint(settings.get("apply_late_entry_penalty"))
	allowed_late_entries_per_month = cint(settings.get("allowed_late_entries_per_month")) or 2

	# If neither penalty is enabled, exit early
	if not apply_attendance_penalty and not apply_late_entry_penalty:
		return []

	eligible_records = get_eligible_attendance_records(up_to_date=up_to_date)
	if not eligible_records:
		return []

	# Sort records by employee, attendance_date, creation to process chronologically per employee
	eligible_records.sort(key=lambda r: (r.employee, getdate(r.attendance_date), r.creation))

	batch_names = [r.name for r in eligible_records]
	month_allowed_late_counts = {}
	processed_records = []

	for att in eligible_records:
		# Rule 7: Leave and Attendance Request records must be excluded from working-hours/late penalty
		if has_leave_or_attendance_request(att):
			continue

		wh_completed = is_working_hours_completed(att)

		if not wh_completed:
			# Scenario 3 & 4: Insufficient working hours (Late Entry: Yes or No, WH: No, Leave: No)
			if apply_attendance_penalty:
				penalty_status = (
					att.status if att.status in ("Half Day", "Absent") else determine_penalty_status(att)
				)
				frappe.db.set_value(
					"Attendance",
					att.name,
					{"custom_penalty": 1, "status": penalty_status},
				)
				processed_records.append(att.name)
		else:
			# Working hours completed
			if cint(att.late_entry) and apply_late_entry_penalty:
				month_start = get_first_day(att.attendance_date)
				month_key = (att.employee, month_start)

				if month_key not in month_allowed_late_counts:
					month_allowed_late_counts[month_key] = get_prior_allowed_late_entries_in_month(
						att.employee,
						month_start,
						up_to_date=att.attendance_date,
						exclude_names=batch_names,
					)

				if month_allowed_late_counts[month_key] < allowed_late_entries_per_month:
					# Scenario 1: Allowed late entry without penalty (e.g. 1st or 2nd)
					month_allowed_late_counts[month_key] += 1
				else:
					# Scenario 2: Exceeds allowed late entries in calendar month (3rd+)
					penalty_status = determine_penalty_status(att)
					frappe.db.set_value(
						"Attendance",
						att.name,
						{"custom_penalty": 1, "status": penalty_status},
					)
					processed_records.append(att.name)

	if processed_records:
		frappe.db.commit()  # nosemgrep

	return processed_records
