# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

from collections import defaultdict
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import (
	cint,
	flt,
	get_datetime,
	get_time,
	getdate,
)

try:
	from hrms.hr.doctype.employee_checkin.employee_checkin import (
		get_overtime_data,
		time_diff_in_hours,
		update_attendance_in_checkins,
	)
	from hrms.hr.doctype.shift_assignment.shift_assignment import (
		get_actual_start_end_datetime_of_shift,
	)
except ImportError:

	def get_overtime_data(*args, **kwargs):
		return {}

	def time_diff_in_hours(*args, **kwargs):
		return 0

	def update_attendance_in_checkins(*args, **kwargs):
		return

	def get_actual_start_end_datetime_of_shift(*args, **kwargs):
		return None, None


@frappe.whitelist()
def process_delayed_employee_checkins():
	"""
	Hourly scheduled task (hourly_long) to process delayed/late-uploaded Employee Checkin
	records and update existing Attendance records instead of skipping them.

	1. Identifies Employee Checkin records uploaded after Attendance was marked.
	2. Disables the skip_auto_attendance flag on those late check-in records.
	3. Recalculates working hours, status, in/out time based on shift rules.
	4. Updates the existing Attendance records and links check-in records without
	   creating duplicate Attendance records.
	"""
	try:
		# 1. Resolve shifts for unlinked checkins that might be missing shift details
		resolve_unassigned_checkin_shifts()

		# 2. Find candidate late-uploaded check-in records
		candidates = get_delayed_checkin_candidates()
		if not candidates:
			return {
				"success": True,
				"total_delayed_checkins": 0,
				"attendances_updated": 0,
				"message": _("No delayed employee checkin records found to process."),
			}

		# 3. Group delayed checkins by (attendance_name, employee, attendance_date, shift)
		groups = defaultdict(list)
		for row in candidates:
			att_date = row.attendance_date or (
				getdate(row.shift_start) if row.shift_start else getdate(row.time)
			)
			key = (row.attendance_name, row.employee, att_date, row.shift)
			groups[key].append(row)

		updated_attendances = []
		total_processed_checkins = 0

		for (att_name, employee, att_date, shift), delayed_checkins in groups.items():
			try:
				success = process_single_attendance_delayed_checkins(
					attendance_name=att_name,
					employee=employee,
					attendance_date=att_date,
					shift=shift,
					delayed_checkins=delayed_checkins,
				)
				if success:
					updated_attendances.append(att_name)
					total_processed_checkins += len(delayed_checkins)
			except Exception as err:
				delayed_names = [ck.checkin_name for ck in delayed_checkins]
				frappe.log_error(
					title=f"Delayed Attendance: Update Failed for {att_name} ({employee})",
					message=(
						f"Failed to update Attendance {att_name} for Employee {employee} on {att_date}.\n"
						f"Shift: {shift}\n"
						f"Delayed Checkins ({len(delayed_checkins)}): {delayed_names}\n"
						f"Error: {err!s}\n\nTraceback:\n{frappe.get_traceback()}"
					),
				)

		return {
			"success": True,
			"total_delayed_checkins": total_processed_checkins,
			"attendances_updated": len(updated_attendances),
			"updated_attendances": updated_attendances,
		}

	except Exception as err:
		frappe.log_error(
			title="Delayed Attendance: Scheduler Execution Failed",
			message=(
				f"Critical error in process_delayed_employee_checkins:\n{err!s}\n\n"
				f"Traceback:\n{frappe.get_traceback()}"
			),
		)
		return {
			"success": False,
			"error": str(err),
			"total_delayed_checkins": 0,
			"attendances_updated": 0,
		}


def resolve_unassigned_checkin_shifts():
	"""
	Ensures unlinked Employee Checkin records with missing shift details
	have their shift resolved if an active Shift Assignment exists.
	"""
	try:
		unassigned = frappe.db.get_all(
			"Employee Checkin",
			filters=[
				["attendance", "in", ["", None]],
				["shift", "in", ["", None]],
			],
			fields=["name", "employee", "time"],
		)
	except Exception as err:
		frappe.log_error(
			title="Delayed Attendance: Query Unassigned Checkins Failed",
			message=f"Failed to fetch unassigned Employee Checkins:\n{err!s}\n\nTraceback:\n{frappe.get_traceback()}",
		)
		return

	for ck in unassigned:
		try:
			shift_timings = get_actual_start_end_datetime_of_shift(ck.employee, get_datetime(ck.time), True)
			if shift_timings:
				frappe.db.set_value(
					"Employee Checkin",
					ck.name,
					{
						"shift": shift_timings.shift_type.name,
						"shift_start": shift_timings.start_datetime,
						"shift_end": shift_timings.end_datetime,
						"shift_actual_start": shift_timings.actual_start,
						"shift_actual_end": shift_timings.actual_end,
						"offshift": 0,
					},
					update_modified=False,
				)
		except Exception as err:
			frappe.log_error(
				title=f"Delayed Attendance: Shift Resolution Failed for {ck.name}",
				message=(
					f"Failed resolving shift for Employee Checkin {ck.name} (Employee: {ck.employee}, Time: {ck.time}):\n"
					f"{err!s}\n\nTraceback:\n{frappe.get_traceback()}"
				),
			)


def get_delayed_checkin_candidates():
	"""
	Identifies Employee Checkin records that were uploaded after Attendance
	was already marked for the corresponding date, or where Attendance already
	exists and the checkin is unlinked / marked skip_auto_attendance = 1.
	"""
	query = """
		SELECT
			ec.name AS checkin_name,
			ec.employee,
			ec.time,
			ec.log_type,
			ec.shift,
			ec.shift_start,
			ec.shift_end,
			ec.shift_actual_start,
			ec.shift_actual_end,
			ec.skip_auto_attendance,
			ec.attendance,
			ec.offshift,
			ec.overtime_type,
			ec.creation AS checkin_creation,
			att.name AS attendance_name,
			att.attendance_date,
			att.status AS attendance_status,
			att.docstatus AS attendance_docstatus,
			att.creation AS attendance_creation
		FROM `tabEmployee Checkin` ec
		INNER JOIN `tabAttendance` att
			ON att.employee = ec.employee
			AND att.docstatus < 2
			AND att.attendance_date = CASE
				WHEN ec.shift_start IS NOT NULL THEN DATE(ec.shift_start)
				ELSE DATE(ec.time)
			END
			AND (
				att.shift IS NULL
				OR att.shift = ''
				OR ec.shift IS NULL
				OR ec.shift = ''
				OR att.shift = ec.shift
			)
		WHERE (ec.attendance IS NULL OR ec.attendance = '')
		  AND (
			  ec.skip_auto_attendance = 1
			  OR ec.creation >= att.creation
			  OR att.name IS NOT NULL
		  )
		ORDER BY ec.employee, att.attendance_date, ec.time ASC
	"""
	try:
		return frappe.db.sql(query, as_dict=True)
	except Exception as err:
		frappe.log_error(
			title="Delayed Attendance: Candidate Query Failed",
			message=f"SQL error in get_delayed_checkin_candidates:\n{err!s}\n\nTraceback:\n{frappe.get_traceback()}",
		)
		return []


def process_single_attendance_delayed_checkins(
	attendance_name: str,
	employee: str,
	attendance_date,
	shift: str | None,
	delayed_checkins: list,
) -> bool:
	"""
	Processes delayed checkin records for a single Attendance record:
	1. Disables skip_auto_attendance on late-uploaded checkin records.
	2. Fetches all shift logs for this employee and date (both existing & delayed).
	3. Recalculates working hours, status, in/out time using Shift Type rules.
	4. Updates the existing Attendance record without creating a duplicate.
	5. Links all checkin records to the Attendance record.
	"""
	delayed_names = [ck.checkin_name for ck in delayed_checkins]

	if not frappe.db.exists("Attendance", attendance_name):
		frappe.log_error(
			title=f"Delayed Attendance: Attendance Not Found {attendance_name}",
			message=f"Attendance record {attendance_name} for employee {employee} on {attendance_date} no longer exists.",
		)
		return False

	att_doc = frappe.get_doc("Attendance", attendance_name)
	if att_doc.docstatus == 2:
		# Do not process cancelled Attendance
		frappe.log_error(
			title=f"Delayed Attendance: Skipping Cancelled Attendance {attendance_name}",
			message=(
				f"Attendance {attendance_name} for employee {employee} on {attendance_date} is cancelled (docstatus=2). "
				f"Cannot attach delayed checkins: {delayed_names}."
			),
		)
		return False

	# 1. Disable skip_auto_attendance on delayed check-ins
	try:
		EmployeeCheckin = frappe.qb.DocType("Employee Checkin")
		(
			frappe.qb.update(EmployeeCheckin)
			.set(EmployeeCheckin.skip_auto_attendance, 0)
			.where(EmployeeCheckin.name.isin(delayed_names))
		).run()
	except Exception as err:
		frappe.log_error(
			title=f"Delayed Attendance: Reset skip_auto_attendance Failed ({attendance_name})",
			message=(
				f"Failed to reset skip_auto_attendance for checkins {delayed_names} linked to {attendance_name}:\n"
				f"{err!s}\n\nTraceback:\n{frappe.get_traceback()}"
			),
		)
		raise err

	target_shift_start = delayed_checkins[0].get("shift_start") if delayed_checkins else None
	applicable_shift = shift or getattr(att_doc, "shift", None)

	# 2. Fetch all valid shift logs (both already linked and newly uploaded)
	all_shift_logs = get_all_shift_logs(
		employee=employee,
		shift=applicable_shift,
		attendance_date=attendance_date,
		target_shift_start=target_shift_start,
	)

	if not all_shift_logs:
		frappe.log_error(
			title=f"Delayed Attendance: No Shift Logs Found for {attendance_name}",
			message=(
				f"Attendance {attendance_name} for employee {employee} on {attendance_date} (Shift: {applicable_shift}) "
				f"has delayed checkins {delayed_names}, but no shift logs could be retrieved."
			),
		)
		return False

	# Ensure skip_auto_attendance is 0 for all matched logs
	all_log_names = [l.name for l in all_shift_logs]
	try:
		(
			frappe.qb.update(EmployeeCheckin)
			.set(EmployeeCheckin.skip_auto_attendance, 0)
			.where(EmployeeCheckin.name.isin(all_log_names))
		).run()
	except Exception as err:
		frappe.log_error(
			title=f"Delayed Attendance: Reset All Logs skip_auto_attendance Failed ({attendance_name})",
			message=(
				f"Failed setting skip_auto_attendance=0 for all logs {all_log_names} on {attendance_name}:\n"
				f"{err!s}\n\nTraceback:\n{frappe.get_traceback()}"
			),
		)

	# 3. Recalculate attendance parameters from checkin logs
	calculated = calculate_attendance_for_logs(
		employee=employee,
		shift=applicable_shift,
		attendance_date=attendance_date,
		shift_logs=all_shift_logs,
	)
	if not calculated:
		frappe.log_error(
			title=f"Delayed Attendance: Calculation Failed for {attendance_name}",
			message=(
				f"calculate_attendance_for_logs returned None for Attendance {attendance_name} "
				f"(Employee: {employee}, Shift: {applicable_shift}, Date: {attendance_date}, Logs: {all_log_names})."
			),
		)
		return False

	# 4. Check Leave Applications
	has_full_day_leave = frappe.db.exists(
		"Leave Application",
		{
			"employee": employee,
			"from_date": ["<=", attendance_date],
			"to_date": [">=", attendance_date],
			"status": "Approved",
			"docstatus": 1,
			"half_day": 0,
		},
	)
	has_half_day_leave = frappe.db.exists(
		"Leave Application",
		{
			"employee": employee,
			"from_date": ["<=", attendance_date],
			"to_date": [">=", attendance_date],
			"status": "Approved",
			"docstatus": 1,
			"half_day": 1,
		},
	)

	half_day_status = None
	if has_full_day_leave or att_doc.status == "On Leave":
		final_status = "On Leave"
	elif has_half_day_leave or (att_doc.status == "Half Day" and getattr(att_doc, "leave_type", None)):
		final_status = "Half Day"
		half_day_status = "Present" if calculated["status"] in ("Present", "Half Day") else "Absent"
	else:
		final_status = calculated["status"]
		if final_status == "Half Day":
			half_day_status = "Present"

	# Set recalculated fields on att_doc
	att_doc.working_hours = calculated["working_hours"]
	att_doc.in_time = calculated["in_time"]
	att_doc.out_time = calculated["out_time"]
	att_doc.late_entry = calculated["late_entry"]
	att_doc.early_exit = calculated["early_exit"]
	att_doc.status = final_status
	if applicable_shift:
		att_doc.shift = applicable_shift

	# Apply Artem ERP Partial Day leave adjustments if applicable
	try:
		from artem_erp.doc_events.attendance import apply_partial_day_to_attendance

		apply_partial_day_to_attendance(att_doc)
	except Exception as err:
		frappe.log_error(
			title=f"Delayed Attendance: Partial Day Adjustment Failed for {attendance_name}",
			message=(
				f"Failed applying partial day adjustment on Attendance {attendance_name} for employee {employee}:\n"
				f"{err!s}\n\nTraceback:\n{frappe.get_traceback()}"
			),
		)

	# Calculate overtime if applicable
	overtime_values = {}
	overtime_type = all_shift_logs[0].get("overtime_type")
	if overtime_type and att_doc.status == "Present" and applicable_shift:
		try:
			overtime_data = get_overtime_data(applicable_shift, calculated["working_hours"])
			if overtime_data:
				overtime_values = {
					"overtime_type": overtime_type,
					"standard_working_hours": overtime_data.get("standard_working_hours"),
					"actual_overtime_duration": overtime_data.get("actual_overtime_duration"),
				}
		except Exception as err:
			frappe.log_error(
				title=f"Delayed Attendance: Overtime Calculation Failed for {attendance_name}",
				message=(
					f"Failed calculating overtime for Attendance {attendance_name} (Shift: {applicable_shift}):\n"
					f"{err!s}\n\nTraceback:\n{frappe.get_traceback()}"
				),
			)

	# 5. Build values dict and update Attendance in DB (avoid duplicate record creation)
	values_to_update = {
		"working_hours": att_doc.working_hours,
		"in_time": att_doc.in_time,
		"out_time": att_doc.out_time,
		"late_entry": att_doc.late_entry,
		"early_exit": att_doc.early_exit,
		"status": att_doc.status,
		"shift": att_doc.shift,
	}

	if att_doc.status == "Half Day":
		values_to_update["half_day_status"] = half_day_status
		values_to_update["modify_half_day_status"] = 0

	if overtime_values:
		values_to_update.update(overtime_values)

	if hasattr(att_doc, "custom_is_partial_day"):
		values_to_update["custom_is_partial_day"] = getattr(att_doc, "custom_is_partial_day", 0)
		values_to_update["custom_partial_day_type"] = getattr(att_doc, "custom_partial_day_type", None)
		values_to_update["custom_partial_day_duration"] = getattr(att_doc, "custom_partial_day_duration", 0)
		values_to_update["custom_adjusted_required_hours"] = getattr(
			att_doc, "custom_adjusted_required_hours", 0.0
		)

	if frappe.get_meta("Attendance").has_field("custom_penalty"):
		if final_status == "Present" and not att_doc.late_entry:
			values_to_update["custom_penalty"] = 0
		else:
			values_to_update["custom_penalty"] = cint(getattr(att_doc, "custom_penalty", 0))

	try:
		frappe.db.set_value("Attendance", attendance_name, values_to_update, update_modified=True)
	except Exception as err:
		frappe.log_error(
			title=f"Delayed Attendance: DB Update Failed for {attendance_name}",
			message=(
				f"Failed updating Attendance {attendance_name} for Employee {employee}.\n"
				f"Values: {frappe.as_json(values_to_update, indent=2)}\n\n"
				f"Error: {err!s}\n\nTraceback:\n{frappe.get_traceback()}"
			),
		)
		raise err

	# 6. Link all checkin records to this Attendance
	try:
		update_attendance_in_checkins(all_log_names, attendance_name)
	except Exception as err:
		frappe.log_error(
			title=f"Delayed Attendance: Checkin Linking Failed for {attendance_name}",
			message=(
				f"Failed linking checkin records {all_log_names} to Attendance {attendance_name}:\n"
				f"{err!s}\n\nTraceback:\n{frappe.get_traceback()}"
			),
		)
		raise err

	# 7. Add Comment to Attendance record
	try:
		att_doc.add_comment(
			"Comment",
			text=_("Attendance updated from delayed Employee Checkin record(s): {0}").format(
				", ".join(delayed_names)
			),
		)
	except Exception as err:
		frappe.log_error(
			title=f"Delayed Attendance: Comment Creation Failed for {attendance_name}",
			message=f"Failed adding comment to Attendance {attendance_name}:\n{err!s}\n\nTraceback:\n{frappe.get_traceback()}",
		)

	if not frappe.flags.in_test:
		frappe.db.commit()  # nosemgrep

	return True


def get_all_shift_logs(employee: str, shift: str | None, attendance_date, target_shift_start=None) -> list:
	"""
	Fetches all Employee Checkin logs for the employee corresponding to the
	specified shift and attendance date.
	"""
	filters = {
		"employee": employee,
		"offshift": 0,
	}
	if shift:
		filters["shift"] = shift

	# Optimize query: filter by target_shift_start or date range around attendance_date
	if target_shift_start:
		filters["shift_start"] = target_shift_start
	else:
		att_date = getdate(attendance_date)
		filters["time"] = [
			"between",
			[f"{att_date - timedelta(days=1)} 00:00:00", f"{att_date + timedelta(days=1)} 23:59:59"],
		]

	try:
		logs = frappe.get_all(
			"Employee Checkin",
			filters=filters,
			fields=[
				"name",
				"employee",
				"log_type",
				"time",
				"shift",
				"shift_start",
				"shift_end",
				"shift_actual_start",
				"shift_actual_end",
				"device_id",
				"overtime_type",
				"skip_auto_attendance",
				"attendance",
			],
			order_by="time asc",
		)
	except Exception as err:
		frappe.log_error(
			title=f"Delayed Attendance: Fetch Shift Logs Failed for {employee}",
			message=(
				f"Failed to fetch checkin logs for Employee {employee} (Shift: {shift}, Date: {attendance_date}):\n"
				f"{err!s}\n\nTraceback:\n{frappe.get_traceback()}"
			),
		)
		return []

	matched_logs = []
	for l in logs:
		if log_belongs_to_shift_date(l, attendance_date, target_shift_start):
			matched_logs.append(l)

	return matched_logs


def log_belongs_to_shift_date(log, attendance_date, target_shift_start=None) -> bool:
	"""
	Checks whether a checkin log belongs to the specified attendance date / shift.
	"""
	if target_shift_start and log.shift_start:
		return get_datetime(log.shift_start) == get_datetime(target_shift_start)
	if log.shift_start:
		return getdate(log.shift_start) == getdate(attendance_date)
	if log.shift_actual_start and log.shift_actual_end:
		log_time = get_datetime(log.time)
		return get_datetime(log.shift_actual_start) <= log_time <= get_datetime(log.shift_actual_end)
	return getdate(log.time) == getdate(attendance_date)


def calculate_attendance_for_logs(
	employee: str, shift: str | None, attendance_date, shift_logs: list
) -> dict | None:
	"""
	Calculates working hours, in/out times, late entry, early exit, and attendance status
	from checkin logs according to the configured Shift Type rules.
	"""
	if not shift_logs:
		return None

	try:
		shift_doc = frappe.get_cached_doc("Shift Type", shift) if shift else None

		for l in shift_logs:
			l.time = get_datetime(l.time)
			if l.shift_start:
				l.shift_start = get_datetime(l.shift_start)
			elif shift_doc and shift_doc.start_time:
				l.shift_start = datetime.combine(getdate(attendance_date), get_time(shift_doc.start_time))
			else:
				l.shift_start = l.time

			if l.shift_end:
				l.shift_end = get_datetime(l.shift_end)
			elif shift_doc and shift_doc.end_time:
				if get_time(shift_doc.end_time) < get_time(shift_doc.start_time):
					l.shift_end = datetime.combine(
						getdate(attendance_date) + timedelta(days=1), get_time(shift_doc.end_time)
					)
				else:
					l.shift_end = datetime.combine(getdate(attendance_date), get_time(shift_doc.end_time))
			else:
				l.shift_end = l.time

		if shift_doc:
			working_hours_threshold_for_half_day = flt(shift_doc.working_hours_threshold_for_half_day)
			working_hours_threshold_for_absent = flt(shift_doc.working_hours_threshold_for_absent)

			if hasattr(shift_doc, "is_half_holiday") and shift_doc.is_half_holiday(employee, attendance_date):
				working_hours_threshold_for_half_day = working_hours_threshold_for_half_day / 2
				working_hours_threshold_for_absent = working_hours_threshold_for_absent / 2

			(
				status,
				working_hours,
				late_entry,
				early_exit,
				in_time,
				out_time,
			) = shift_doc.get_attendance(
				shift_logs, working_hours_threshold_for_absent, working_hours_threshold_for_half_day
			)
		else:
			in_time = shift_logs[0].time
			out_time = shift_logs[-1].time if len(shift_logs) >= 2 else None
			working_hours = time_diff_in_hours(in_time, out_time) if out_time else 0.0
			late_entry = False
			early_exit = False
			status = "Present" if working_hours >= 4.0 else ("Half Day" if working_hours > 0 else "Absent")

		return {
			"status": status,
			"working_hours": working_hours,
			"late_entry": 1 if late_entry else 0,
			"early_exit": 1 if early_exit else 0,
			"in_time": in_time,
			"out_time": out_time,
		}

	except Exception as err:
		frappe.log_error(
			title=f"Delayed Attendance: Calculation Error for {employee}",
			message=(
				f"Failed calculating attendance for Employee {employee} (Shift: {shift}, Date: {attendance_date}):\n"
				f"{err!s}\n\nTraceback:\n{frappe.get_traceback()}"
			),
		)
		return None
