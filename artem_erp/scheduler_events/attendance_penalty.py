# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import (
	cint,
	flt,
	get_first_day,
	getdate,
)

from artem_erp.doc_events.attendance import (
	is_within_early_exit_window,
	is_within_late_arrival_window,
)


def classify_attendance_leave_coverage(att):
	"""
	Classify leave or attendance request coverage for the attendance record in priority order:
	1. Full-Day Leave
	2. Attendance Request
	3. Partial Day Leave (Approved)
	4. Half-Day Leave
	5. No Leave

	Returns dict:
	{
	    "type": "Full-Day Leave" | "Attendance Request" | "Partial Day Leave" | "Half-Day Leave" | "No Leave",
	    "partial_day_type": "Late Arrival" | "Early Exit" | None,
	    "partial_day_duration": int,
	    "leave_application": str | None,
	}
	"""
	# Priority 2: Check Attendance Request (direct field or in DB)
	if att.get("attendance_request"):
		return {
			"type": "Attendance Request",
			"partial_day_type": None,
			"partial_day_duration": 0,
			"leave_application": None,
		}

	att_req_filters = {
		"employee": att.employee,
		"docstatus": ["<", 2],
		"from_date": ["<=", att.attendance_date],
		"to_date": [">=", att.attendance_date],
	}
	if frappe.db.exists("Attendance Request", att_req_filters):
		return {
			"type": "Attendance Request",
			"partial_day_type": None,
			"partial_day_duration": 0,
			"leave_application": None,
		}

	# Check Leave Application covering attendance_date (docstatus < 2, not Rejected)
	leave_filters = {
		"employee": att.employee,
		"docstatus": ["<", 2],
		"status": ["!=", "Rejected"],
		"from_date": ["<=", att.attendance_date],
		"to_date": [">=", att.attendance_date],
	}
	leave_apps = frappe.get_all(
		"Leave Application",
		filters=leave_filters,
		fields=[
			"name",
			"leave_type",
			"docstatus",
			"status",
			"half_day",
			"total_leave_days",
			"custom_is_partial_day_leave",
			"custom_partial_day_type",
			"custom_partial_day_duration",
		],
		order_by="creation desc",
	)

	# Also check attendance's own fields if set
	if att.get("custom_is_partial_day") and att.get("custom_partial_day_duration"):
		return {
			"type": "Partial Day Leave",
			"partial_day_type": att.get("custom_partial_day_type"),
			"partial_day_duration": cint(att.get("custom_partial_day_duration")),
			"leave_application": att.get("leave_application"),
		}

	for la in leave_apps:
		# Check if Partial Day Leave
		if cint(la.custom_is_partial_day_leave):
			# Requirement 10: Only Approved Partial Day Leave provides attendance allowance
			if la.docstatus == 1 and la.status == "Approved":
				return {
					"type": "Partial Day Leave",
					"partial_day_type": la.custom_partial_day_type,
					"partial_day_duration": cint(la.custom_partial_day_duration),
					"leave_application": la.name,
				}
			# Unapproved Partial Day provides no allowance
			continue

		# Non-Partial Day Leave: Check Half-Day vs Full-Day
		if cint(la.half_day) or flt(la.total_leave_days) == 0.5:
			return {
				"type": "Half-Day Leave",
				"partial_day_type": None,
				"partial_day_duration": 0,
				"leave_application": la.name,
			}
		else:
			# Priority 1: Full-Day Leave
			return {
				"type": "Full-Day Leave",
				"partial_day_type": None,
				"partial_day_duration": 0,
				"leave_application": la.name,
			}

	# Check attendance status directly
	if att.get("status") == "On Leave":
		return {
			"type": "Full-Day Leave",
			"partial_day_type": None,
			"partial_day_duration": 0,
			"leave_application": None,
		}

	return {
		"type": "No Leave",
		"partial_day_type": None,
		"partial_day_duration": 0,
		"leave_application": None,
	}


def has_leave_or_attendance_request(att):
	"""
	Backward-compatible helper.
	Returns True for Full-Day Leave and Attendance Request where penalties are skipped entirely.
	"""
	classification = classify_attendance_leave_coverage(att)
	return classification["type"] in ("Full-Day Leave", "Attendance Request")


def is_working_hours_completed(att, partial_day_duration=0):
	"""
	Check if employee completed the required minimum daily working hours.
	If partial_day_duration > 0, working hours thresholds are reduced by the approved allowance.
	"""
	# If status is Half Day or Absent without partial day, working hours were not completed
	if att.status in ("Half Day", "Absent") and not partial_day_duration:
		return False

	allowance_hours = flt(partial_day_duration) / 60.0

	# If shift has thresholds, check actual working_hours against adjusted thresholds
	if att.get("shift"):
		shift_doc = frappe.get_cached_doc("Shift Type", att.shift)
		threshold_half_day = flt(shift_doc.working_hours_threshold_for_half_day)
		threshold_absent = flt(shift_doc.working_hours_threshold_for_absent)
		working_hours = flt(att.working_hours)

		if threshold_absent:
			threshold_absent = max(0.0, threshold_absent - allowance_hours)
		if threshold_half_day:
			threshold_half_day = max(0.0, threshold_half_day - allowance_hours)

		if threshold_absent and working_hours < threshold_absent:
			return False
		if threshold_half_day and working_hours < threshold_half_day:
			return False

	# If attendance record has custom adjusted required hours
	if partial_day_duration and att.get("custom_adjusted_required_hours"):
		adj_required = flt(att.get("custom_adjusted_required_hours"))
		if adj_required > 0 and flt(att.working_hours) < adj_required:
			return False

	if att.status == "Present":
		return True

	return flt(att.working_hours) > 0


def determine_penalty_status(att, partial_day_duration=0):
	"""
	Determine whether attendance should be marked as Half Day or Absent based on actual working hours.
	Applies partial day allowance to thresholds if provided.
	"""
	if isinstance(att, str):
		att = frappe.get_doc("Attendance", att)

	working_hours = flt(att.working_hours)
	allowance_hours = flt(partial_day_duration) / 60.0

	if att.get("shift"):
		shift_doc = frappe.get_cached_doc("Shift Type", att.shift)
		threshold_absent = flt(shift_doc.working_hours_threshold_for_absent)
		threshold_half_day = flt(shift_doc.working_hours_threshold_for_half_day)

		if threshold_absent:
			threshold_absent = max(0.0, threshold_absent - allowance_hours)
		if threshold_half_day:
			threshold_half_day = max(0.0, threshold_half_day - allowance_hours)

		if threshold_absent and working_hours < threshold_absent:
			return "Absent"
		if not threshold_absent and threshold_half_day and working_hours < (threshold_half_day / 2.0):
			return "Absent"
		return "Half Day"

	standard_hours = flt(getattr(att, "standard_working_hours", 0) or 0)
	if standard_hours:
		adjusted_standard = max(0.0, standard_hours - allowance_hours)
		if working_hours < (adjusted_standard / 2.0):
			return "Absent"
		return "Half Day"

	if working_hours > 0:
		return "Half Day"
	return "Absent"


def is_half_day_leave_hours_completed(att):
	"""
	Requirement 18: If an employee takes Half Day Leave, check whether they completed
	the minimum required working hours for the working portion of the day.
	Returns True if completed, False if incomplete.
	"""
	working_hours = flt(att.working_hours)
	if working_hours <= 0:
		return False

	if att.get("shift"):
		shift_doc = frappe.get_cached_doc("Shift Type", att.shift)
		threshold_half_day = flt(shift_doc.working_hours_threshold_for_half_day)
		if threshold_half_day:
			# Employee must work at least the half-day threshold
			return working_hours >= threshold_half_day

	standard_hours = flt(getattr(att, "standard_working_hours", 0) or 0)
	if standard_hours:
		return working_hours >= (standard_hours / 2.0)

	return working_hours >= 4.0


def is_late_arrival_covered(att, partial_day_type, partial_day_duration):
	"""
	Check if late entry is covered by an approved Late Arrival Partial Day allowance.
	"""
	if partial_day_type != "Late Arrival" or partial_day_duration <= 0:
		return False

	if not att.get("shift"):
		return True

	try:
		shift_doc = frappe.get_cached_doc("Shift Type", att.shift)
		shift_start = shift_doc.start_time
		late_threshold = cint(getattr(shift_doc, "late_entry_grace_period", 0))
		return is_within_late_arrival_window(
			att.get("in_time"), shift_start, partial_day_duration, late_threshold
		)
	except Exception:
		return True


def is_early_exit_covered(att, partial_day_type, partial_day_duration):
	"""
	Check if early exit is covered by an approved Early Exit Partial Day allowance.
	"""
	if partial_day_type != "Early Exit" or partial_day_duration <= 0:
		return False

	if not att.get("shift"):
		return True

	try:
		shift_doc = frappe.get_cached_doc("Shift Type", att.shift)
		shift_end = shift_doc.end_time
		return is_within_early_exit_window(att.get("out_time"), shift_end, partial_day_duration, 0)
	except Exception:
		return True


def get_prior_allowed_late_entries_in_month(employee, start_of_month, up_to_date=None, exclude_names=None):
	"""
	Count allowed late entries without penalty in the same calendar month for this employee.
	Only counts late entries where the employee completed minimum required working hours.
	Excludes late entries that were covered by an approved Partial Day Late Arrival.
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
			"in_time",
			"out_time",
			"leave_type",
			"leave_application",
			"attendance_request",
			"custom_is_partial_day",
			"custom_partial_day_type",
			"custom_partial_day_duration",
		],
	)

	exclude_set = set(exclude_names or [])
	count = 0
	for r in records:
		if r.name in exclude_set:
			continue

		coverage = classify_attendance_leave_coverage(r)
		if coverage["type"] in ("Full-Day Leave", "Attendance Request"):
			continue

		# If late entry was covered by approved Partial Day Late Arrival, do not count
		if coverage["type"] == "Partial Day Leave":
			if is_late_arrival_covered(r, coverage["partial_day_type"], coverage["partial_day_duration"]):
				continue

		if is_working_hours_completed(r, partial_day_duration=coverage["partial_day_duration"]):
			count += 1

	return count


def get_eligible_attendance_records(up_to_date=None, **kwargs):
	"""
	Fetch Attendance records eligible for penalty processing:
	- Attendance records where attendance_date <= cutoff_date (defaults to today)
	- Docstatus is active (docstatus < 2)
	- custom_penalty is not already enabled (custom_penalty == 0)
	- Candidate for penalty: status is Half Day/Absent, late_entry is enabled, or custom_is_partial_day is enabled
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

	if frappe.get_meta("Attendance").has_field("custom_is_partial_day"):
		or_filters.append({"custom_is_partial_day": 1})

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
			"early_exit",
			"in_time",
			"out_time",
			"leave_type",
			"leave_application",
			"attendance_request",
			"custom_is_partial_day",
			"custom_partial_day_type",
			"custom_partial_day_duration",
			"custom_adjusted_required_hours",
			"creation",
		],
		order_by="attendance_date asc, creation asc",
	)


def process_attendance_penalties(up_to_date=None, **kwargs):
	"""
	Daily scheduler job to process attendance penalties according to Priority Order:
	1. Full-Day Leave: Skip normal penalty processing.
	2. Attendance Request: Follow existing Attendance Request rules (skip).
	3. Partial Day Leave: Apply Partial Day allowance, adjust working hours, exempt covered Late/Early,
	   and penalize if adjusted working hours not completed.
	4. Half-Day Leave: Check working hours for working portion; if incomplete -> Absent + Penalty.
	5. No Leave: Standard penalty processing (working hours check + late entry allowance).
	"""
	if not frappe.get_meta("Attendance").has_field("custom_penalty"):
		frappe.log_error(
			"Attendance penalty processing skipped: custom_penalty field not found on Attendance DocType."
		)
		return []

	settings = frappe.get_cached_doc("Artem Setting")

	apply_attendance_penalty = cint(settings.get("apply_attendance_penalty"))
	apply_late_entry_penalty = cint(settings.get("apply_late_entry_penalty"))
	allowed_late_entries_per_month = cint(settings.get("allowed_late_entries_per_month"))

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
		coverage = classify_attendance_leave_coverage(att)
		cov_type = coverage["type"]

		# ---------------------------------------------------------
		# Priority 1: Full-Day Leave
		# ---------------------------------------------------------
		if cov_type == "Full-Day Leave":
			continue

		# ---------------------------------------------------------
		# Priority 2: Attendance Request
		# ---------------------------------------------------------
		if cov_type == "Attendance Request":
			continue

		# ---------------------------------------------------------
		# Priority 4: Half-Day Leave
		# Requirement 18: If Half Day Leave exists but employee did NOT
		# complete minimum required working hours: Attendance -> Absent + Penalty
		# ---------------------------------------------------------
		if cov_type == "Half-Day Leave":
			if not is_half_day_leave_hours_completed(att):
				if apply_attendance_penalty:
					frappe.db.set_value(
						"Attendance",
						att.name,
						{"custom_penalty": 1, "status": "Absent"},
					)
					processed_records.append(att.name)
			continue

		# ---------------------------------------------------------
		# Priority 3: Partial Day Leave
		# ---------------------------------------------------------
		if cov_type == "Partial Day Leave":
			partial_duration = coverage["partial_day_duration"]
			partial_type = coverage["partial_day_type"]

			wh_completed = is_working_hours_completed(att, partial_day_duration=partial_duration)

			if not wh_completed:
				if apply_attendance_penalty:
					penalty_status = determine_penalty_status(att, partial_day_duration=partial_duration)
					frappe.db.set_value(
						"Attendance",
						att.name,
						{"custom_penalty": 1, "status": penalty_status},
					)
					processed_records.append(att.name)
			else:
				# Working hours met with Partial Day adjustment
				if cint(att.late_entry) and apply_late_entry_penalty:
					# Check if Late Arrival is covered by Partial Day
					if is_late_arrival_covered(att, partial_type, partial_duration):
						# Covered: do not penalize
						pass
					else:
						# Excess delay beyond Partial Day allowance: apply normal late entry rules
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
							month_allowed_late_counts[month_key] += 1
						else:
							penalty_status = determine_penalty_status(
								att, partial_day_duration=partial_duration
							)
							frappe.db.set_value(
								"Attendance",
								att.name,
								{"custom_penalty": 1, "status": penalty_status},
							)
							processed_records.append(att.name)
			continue

		# ---------------------------------------------------------
		# Priority 5: No Leave (Standard Attendance Penalty Rules)
		# ---------------------------------------------------------
		wh_completed = is_working_hours_completed(att)

		if not wh_completed:
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
					month_allowed_late_counts[month_key] += 1
				else:
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
