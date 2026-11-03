# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt


from datetime import date, time, timedelta

import frappe
from frappe import _
from frappe.utils import (
	cint,
	date_diff,
	format_date,
	getdate,
)
from hrms.utils import generate_date_range


@frappe.whitelist()
def get_company_attendance_regularization_config(
	company: str | None = None, employee: str | None = None
) -> dict:
	"""
	Retrieves attendance regularization configuration for a Company.
	Priority: If single-day restriction is enabled, max allowed days is effectively 1.
	"""
	if not company and employee:
		company = frappe.db.get_value("Employee", employee, "company")

	if not company:
		return {
			"enable_single_day": 0,
			"max_days": 0,
		}

	enable_single_day = cint(
		frappe.db.get_value("Company", company, "custom_enable_single_day_attendance_regularization")
	)
	max_days = cint(frappe.db.get_value("Company", company, "custom_max_attendance_request_days"))

	return {
		"enable_single_day": enable_single_day,
		"max_days": max_days,
	}


def get_inclusive_date_range_days(from_date: str | date, to_date: str | date) -> int:
	"""Calculates the inclusive calendar days duration between from_date and to_date."""
	if not from_date or not to_date:
		return 0
	return date_diff(getdate(to_date), getdate(from_date)) + 1


def format_time_24hr(time_val: time | timedelta | str | None) -> str:
	"""Formats a time value into 24-hour HH:MM format (e.g. '09:30', '13:00', '19:00')."""
	if not time_val:
		return ""
	if isinstance(time_val, timedelta):
		total_seconds = int(time_val.total_seconds())
		hours = (total_seconds // 3600) % 24
		minutes = (total_seconds % 3600) // 60
	elif isinstance(time_val, str):
		parts = time_val.split(":")
		hours = int(parts[0])
		minutes = int(parts[1]) if len(parts) > 1 else 0
	elif isinstance(time_val, time):
		hours = time_val.hour
		minutes = time_val.minute
	else:
		return str(time_val)

	return f"{hours:02d}:{minutes:02d}"


format_time_12hr = format_time_24hr


def get_shift_working_hours(shift_type: str | None) -> str:
	"""Returns the formatted working hours for a given Shift Type (e.g. '09:30 - 19:00')."""
	if not shift_type:
		return ""

	shift_timings = frappe.db.get_value(
		"Shift Type",
		shift_type,
		["start_time", "end_time"],
		as_dict=True,
	)
	if not shift_timings:
		return ""

	start_str = format_time_24hr(shift_timings.get("start_time"))
	end_str = format_time_24hr(shift_timings.get("end_time"))
	if start_str and end_str:
		return f"{start_str} - {end_str}"
	return start_str or end_str or ""


def get_shift_time_label(shift_type: str | None) -> str:
	"""Returns the formatted from and to time for a given Shift Type (e.g. 'From Time: 14:30 to To Time: 19:00')."""
	if not shift_type:
		return ""

	shift_timings = frappe.db.get_value(
		"Shift Type",
		shift_type,
		["start_time", "end_time"],
		as_dict=True,
	)
	if not shift_timings:
		return ""

	start_str = format_time_24hr(shift_timings.get("start_time"))
	end_str = format_time_24hr(shift_timings.get("end_time"))
	if start_str and end_str:
		return _("From Time: {0} to To Time: {1}").format(start_str, end_str)
	elif start_str:
		return _("From Time: {0}").format(start_str)
	elif end_str:
		return _("To Time: {0}").format(end_str)
	return ""


def get_shifts_for_date(employee: str, for_date: str | date) -> list[str]:
	"""
	Returns all applicable shift types for an employee on a given date.
	Checks active submitted Shift Assignments covering for_date.
	If none, checks all submitted Shift Assignments (backdated requests).
	If still none, falls back to default_shift from Employee master.
	"""
	if not employee or not for_date:
		return []

	for_date = getdate(for_date)

	assignment = frappe.qb.DocType("Shift Assignment")
	# 1. Look for active submitted assignments covering for_date
	assignments = (
		frappe.qb.from_(assignment)
		.select(
			assignment.name,
			assignment.shift_type,
			assignment.start_date,
			assignment.end_date,
			assignment.status,
			assignment.creation,
			assignment.modified,
		)
		.where(
			(assignment.employee == employee)
			& (assignment.docstatus == 1)
			& (assignment.status == "Active")
			& (assignment.start_date <= for_date)
			& (assignment.end_date.isnull() | (assignment.end_date >= for_date))
		)
		.orderby(assignment.creation, order=frappe.qb.desc)
		.run(as_dict=True)
	)

	# 2. If no active assignments found, check any submitted assignments covering for_date
	if not assignments:
		assignments = (
			frappe.qb.from_(assignment)
			.select(
				assignment.name,
				assignment.shift_type,
				assignment.start_date,
				assignment.end_date,
				assignment.status,
				assignment.creation,
				assignment.modified,
			)
			.where(
				(assignment.employee == employee)
				& (assignment.docstatus == 1)
				& (assignment.start_date <= for_date)
				& (assignment.end_date.isnull() | (assignment.end_date >= for_date))
			)
			.orderby(assignment.creation, order=frappe.qb.desc)
			.run(as_dict=True)
		)

	distinct_shifts = list(dict.fromkeys([a.get("shift_type") for a in assignments if a.get("shift_type")]))

	if not distinct_shifts:
		default_shift = frappe.db.get_value("Employee", employee, "default_shift", cache=True)
		return [default_shift] if default_shift else []

	return distinct_shifts


def get_effective_shift_for_date(employee: str, for_date: str | date) -> str | None:
	"""Returns the primary effective shift for an employee on a specific date."""
	shifts = get_shifts_for_date(employee, for_date)
	return shifts[0] if shifts else None


def get_shifts_for_date_range(
	employee: str, from_date: str | date, to_date: str | date
) -> tuple[list[dict], list[str]]:
	"""
	Returns:
	- date_shifts: list of dicts with date, shift, all_shifts
	- all_shifts: list of all distinct shift types found across the range
	"""
	date_shifts = []
	all_shifts_set = []

	if not employee or not from_date or not to_date:
		return date_shifts, all_shifts_set

	for dt in generate_date_range(getdate(from_date), getdate(to_date)):
		day_shifts = get_shifts_for_date(employee, dt)
		effective_shift = day_shifts[0] if day_shifts else None

		date_shifts.append(
			{
				"date": dt,
				"shift": effective_shift,
				"all_shifts": day_shifts,
			}
		)

		for s in day_shifts:
			if s and s not in all_shifts_set:
				all_shifts_set.append(s)

	return date_shifts, all_shifts_set


def group_consecutive_shifts(date_shifts: list[dict]) -> list[dict]:
	"""
	Groups consecutive dates having the same effective shift.
	Returns list of dicts with: shift, start_date, end_date, working_hours.
	"""
	if not date_shifts:
		return []

	groups = []
	current_group = None

	for item in date_shifts:
		dt = item["date"]
		shift = item["shift"]

		if current_group is None:
			current_group = {
				"shift": shift,
				"start_date": dt,
				"end_date": dt,
			}
		elif current_group["shift"] == shift:
			current_group["end_date"] = dt
		else:
			groups.append(current_group)
			current_group = {
				"shift": shift,
				"start_date": dt,
				"end_date": dt,
			}

	if current_group:
		groups.append(current_group)

	for g in groups:
		g["working_hours"] = get_shift_working_hours(g["shift"])

	return groups


def build_unassigned_dates_html_message(unassigned_dates: list[date | str]) -> str:
	"""Constructs validation message identifying specific dates that have no shift assigned."""
	title_text = _("No Shift Assigned")
	if len(unassigned_dates) == 1:
		d_str = format_date(unassigned_dates[0], "dd-mm-yyyy")
		intro_text = _(
			"No shift is assigned on {0}. Please ensure a shift is assigned before submitting an Attendance Request."
		).format(frappe.bold(d_str))
		items_html = ""
	else:
		intro_text = _(
			"No shift is assigned for the following date(s). Please ensure shifts are assigned before submitting an Attendance Request:"
		)
		items_html = '<ul style="margin: 0 0 10px 20px; padding: 0; color: #1f272e;">'
		for d in unassigned_dates:
			d_str = format_date(d, "dd-mm-yyyy")
			items_html += f'<li style="margin: 4px 0; font-size: 13px;"><b>{d_str}</b></li>'
		items_html += "</ul>"

	msg = (
		f'<div style="font-family: inherit; line-height: 1.5; white-space: normal !important; text-align: left; color: #1f272e; margin: 4px 0;">'
		f'<p style="margin: 0 0 8px 0; font-size: 14px; font-weight: bold; color: inherit;">{title_text}</p>'
		f'<p style="margin: 0 0 10px 0; font-size: 13px; color: inherit;">{intro_text}</p>'
		f"{items_html}"
		f"</div>"
	)
	return msg


def group_consecutive_date_wise_shifts(date_wise: list[dict]) -> list[dict]:
	"""
	Groups consecutive dates having identical shift assignments.
	Returns list of dicts with:
	- start_date, end_date
	- date_range_str (e.g. '04-11-2026 to 10-11-2026' or '03-11-2026')
	- shifts: list of shift names
	- shift_details: list of dicts with timing info
	"""
	if not date_wise:
		return []

	groups = []
	current_group = None

	for item in date_wise:
		dt = item["date"]
		shifts = item["shifts"]
		details = item.get("shift_details", [])

		if current_group is None:
			current_group = {
				"start_date": dt,
				"end_date": dt,
				"shifts": shifts,
				"shift_details": details,
			}
		elif current_group["shifts"] == shifts:
			current_group["end_date"] = dt
		else:
			groups.append(current_group)
			current_group = {
				"start_date": dt,
				"end_date": dt,
				"shifts": shifts,
				"shift_details": details,
			}

	if current_group:
		groups.append(current_group)

	for g in groups:
		if g["start_date"] == g["end_date"]:
			g["date_range_str"] = format_date(g["start_date"], "dd-mm-yyyy")
		else:
			g["date_range_str"] = (
				f"{format_date(g['start_date'], 'dd-mm-yyyy')} to {format_date(g['end_date'], 'dd-mm-yyyy')}"
			)

	return groups


def build_date_wise_multiple_shifts_html_message(date_wise: list[dict]) -> str:
	"""
	Constructs the grouped date range HTML validation message when multiple shifts are found across a date range.
	Groups consecutive dates having the same shift into a single date range row:
	Shift | Applicable Date Range | Shift Timings / Working Hours
	"""
	groups = group_consecutive_date_wise_shifts(date_wise)
	rows_html = ""
	for g in groups:
		date_range_str = g["date_range_str"]
		shifts = g["shifts"]
		details = g.get("shift_details", [])

		if not shifts:
			shift_cell = f'<span style="color: #e02424; font-weight: bold;">{_("No Shift Assigned")}</span>'
			time_cell = "-"
		elif len(shifts) == 1:
			s = shifts[0]
			time_label = details[0]["time_label"] if details else get_shift_time_label(s)
			shift_cell = f"<b>{s}</b>"
			time_cell = time_label or (details[0]["working_hours"] if details else "-")
		else:
			# Multiple shifts on this date/period
			shifts_badges = ", ".join(f"<b>{s}</b>" for s in shifts)
			shift_cell = f"<div>{shifts_badges}</div>"
			time_lines = []
			for sd in details:
				t = sd.get("time_label") or sd.get("working_hours") or ""
				time_lines.append(f"• <b>{sd['shift']}</b>: {t}" if t else f"• <b>{sd['shift']}</b>")
			time_cell = "<br>".join(time_lines)

		rows_html += (
			f"<tr>"
			f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; text-align: left; vertical-align: middle;">{shift_cell}</td>'
			f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; text-align: left; vertical-align: middle; white-space: nowrap;">{date_range_str}</td>'
			f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; text-align: left; vertical-align: middle;">{time_cell}</td>'
			f"</tr>"
		)

	title_text = _("Multiple Shifts Found in the Selected Date Range")
	intro_text = _(
		"The selected date range contains multiple shift assignments across different dates. "
		"Please create separate Attendance Requests for each shift period:"
	)
	col_shift = _("Shift")
	col_dates = _("Applicable Date Range")
	col_hours = _("Shift Timings / Working Hours")
	outro_text = _("Please create separate Attendance Requests for the below shift periods.")

	msg = (
		f'<div style="font-family: inherit; line-height: 1.5; white-space: normal !important; text-align: left; color: #1f272e; margin: 4px 0;">'
		f'<p style="margin: 0 0 8px 0; font-size: 14px; font-weight: bold; color: inherit;">{title_text}</p>'
		f'<p style="margin: 0 0 10px 0; font-size: 13px; color: inherit;">{intro_text}</p>'
		f"</div>"
		f'<p style="margin: 8px 0 0 0; font-size: 13px; color: inherit;">{outro_text}</p>'
		f"</div>"
		f'<div style="overflow-x: auto; margin-bottom: 10px; border-radius: 4px;">'
		f'<table class="table table-bordered" border="1" cellpadding="8" cellspacing="0" style="width: 100%; border-collapse: collapse; border: 1px solid #d1d8dd; margin: 0; background-color: #ffffff; font-size: 12px; color: #1f272e;">'
		f"<thead>"
		f'<tr style="background-color: #f7fafc; border-bottom: 1px solid #d1d8dd;">'
		f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; background-color: #f7fafc; color: #1f272e; font-weight: bold; text-align: left; white-space: nowrap;"><b>{col_shift}</b></td>'
		f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; background-color: #f7fafc; color: #1f272e; font-weight: bold; text-align: left; white-space: nowrap;"><b>{col_dates}</b></td>'
		f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; background-color: #f7fafc; color: #1f272e; font-weight: bold; text-align: left; white-space: nowrap;"><b>{col_hours}</b></td>'
		f"</tr>"
		f"</thead>"
		f"<tbody>"
		f"{rows_html}"
		f"</tbody>"
		f"</table>"
	)
	return msg


def build_multiple_shifts_html_message(shift_groups_or_date_wise: list[dict]) -> str:
	"""Constructs the HTML validation message when multiple shifts are found."""
	if shift_groups_or_date_wise and "shifts" in shift_groups_or_date_wise[0]:
		return build_date_wise_multiple_shifts_html_message(shift_groups_or_date_wise)

	# Format for legacy shift_groups list
	rows_html = ""
	for g in shift_groups_or_date_wise:
		shift_name = frappe.bold(g["shift"]) if g["shift"] else _("No Shift Assigned")
		if g["start_date"] == g["end_date"]:
			date_range_str = format_date(g["start_date"], "dd-mm-yyyy")
		else:
			date_range_str = (
				f"{format_date(g['start_date'], 'dd-mm-yyyy')} to {format_date(g['end_date'], 'dd-mm-yyyy')}"
			)

		working_hours = g.get("working_hours") or "-"
		rows_html += (
			f"<tr>"
			f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; text-align: left; vertical-align: middle;">{shift_name}</td>'
			f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; text-align: left; vertical-align: middle;">{date_range_str}</td>'
			f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; text-align: left; vertical-align: middle;">{working_hours}</td>'
			f"</tr>"
		)

	title_text = _("Multiple Shifts Found in the Selected Date Range")
	intro_text = _(
		"The selected date range contains multiple shift assignments. Please create separate Attendance Requests for each shift period."
	)
	col_shift = _("Shift")
	col_dates = _("Applicable Date Range")
	col_hours = _("Working Hours")
	outro_text = _("Please create separate Attendance Requests for the below shift periods.")

	msg = (
		f'<div style="font-family: inherit; line-height: 1.5; white-space: normal !important; text-align: left; color: #1f272e; margin: 4px 0;">'
		f'<p style="margin: 0 0 8px 0; font-size: 14px; font-weight: bold; color: inherit;">{title_text}</p>'
		f'<p style="margin: 0 0 10px 0; font-size: 13px; color: inherit;">{intro_text}</p>'
		f'<div style="overflow-x: auto; margin-bottom: 10px; border-radius: 4px;">'
		f'<table class="table table-bordered" border="1" cellpadding="8" cellspacing="0" style="width: 100%; border-collapse: collapse; border: 1px solid #d1d8dd; margin: 0; background-color: #ffffff; font-size: 12px; color: #1f272e;">'
		f"<thead>"
		f'<tr style="background-color: #f7fafc; border-bottom: 1px solid #d1d8dd;">'
		f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; background-color: #f7fafc; color: #1f272e; font-weight: bold; text-align: left; white-space: nowrap;"><b>{col_shift}</b></td>'
		f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; background-color: #f7fafc; color: #1f272e; font-weight: bold; text-align: left; white-space: nowrap;"><b>{col_dates}</b></td>'
		f'<td style="padding: 8px 12px; border: 1px solid #d1d8dd; background-color: #f7fafc; color: #1f272e; font-weight: bold; text-align: left; white-space: nowrap;"><b>{col_hours}</b></td>'
		f"</tr>"
		f"</thead>"
		f"<tbody>"
		f"{rows_html}"
		f"</tbody>"
		f"</table>"
		f"</div>"
		f'<p style="margin: 8px 0 0 0; font-size: 13px; color: inherit;">{outro_text}</p>'
		f"</div>"
	)
	return msg


def build_same_date_multiple_shifts_html_message(date_val: str | date, shifts: list[str]) -> str:
	"""Constructs the HTML validation message when multiple shifts are assigned on a date."""
	date_str = format_date(date_val, "dd-mm-yyyy")
	title_text = _("Shift Selection Required")
	intro_text = _(
		"Multiple shifts are assigned for the selected date ({0}). Please select a shift before submitting the Attendance Request:"
	).format(frappe.bold(date_str))

	items_html = ""
	for s in shifts:
		time_label = get_shift_time_label(s)
		wh_text = f" ({time_label})" if time_label else ""
		items_html += f'<li style="margin: 4px 0; font-size: 13px;"><b>{s}</b>{wh_text}</li>'

	msg = (
		f'<div style="font-family: inherit; line-height: 1.5; white-space: normal !important; text-align: left; color: #1f272e; margin: 4px 0;">'
		f'<p style="margin: 0 0 8px 0; font-size: 14px; font-weight: bold; color: inherit;">{title_text}</p>'
		f'<p style="margin: 0 0 8px 0; font-size: 13px; color: inherit;">{intro_text}</p>'
		f'<ul style="margin: 0 0 10px 20px; padding: 0; color: #1f272e;">'
		f"{items_html}"
		f"</ul>"
		f'<p style="margin: 8px 0 0 0; font-size: 13px; color: inherit;">'
		f"{_('Please select one of the applicable shifts from the Shift field.')}"
		f"</p>"
		f"</div>"
	)
	return msg


def get_date_wise_shift_analysis(
	employee: str, from_date: str | date, to_date: str | date | None = None
) -> dict:
	"""
	Validates and analyzes shift assignments date by date across the selected date range.
	"""
	if not to_date:
		to_date = from_date

	from_date = getdate(from_date)
	to_date = getdate(to_date)

	date_wise = []
	all_shifts = []

	for dt in generate_date_range(from_date, to_date):
		day_shifts = get_shifts_for_date(employee, dt)
		day_details = [
			{
				"shift": s,
				"time_label": get_shift_time_label(s),
				"working_hours": get_shift_working_hours(s),
			}
			for s in day_shifts
		]
		date_wise.append(
			{
				"date": dt,
				"date_str": format_date(dt, "dd-mm-yyyy"),
				"shifts": day_shifts,
				"shift_details": day_details,
				"has_shifts": bool(day_shifts),
				"is_single_shift": len(day_shifts) == 1,
				"is_multiple_shifts": len(day_shifts) > 1,
			}
		)

		for s in day_shifts:
			if s and s not in all_shifts:
				all_shifts.append(s)

	dates_with_no_shift = [d for d in date_wise if len(d["shifts"]) == 0]
	dates_with_multiple_shifts = [d for d in date_wise if len(d["shifts"]) > 1]

	# Common shifts assigned across ALL dates in the range
	if date_wise and not dates_with_no_shift:
		common_set = set(date_wise[0]["shifts"])
		for d in date_wise[1:]:
			common_set.intersection_update(set(d["shifts"]))
		common_shifts = [s for s in all_shifts if s in common_set]
	else:
		common_shifts = []

	common_shifts_details = [
		{
			"shift": s,
			"time_label": get_shift_time_label(s),
			"working_hours": get_shift_working_hours(s),
		}
		for s in common_shifts
	]

	is_single_day = len(date_wise) == 1
	has_unassigned_dates = len(dates_with_no_shift) > 0
	has_same_date_multiple_shifts = len(dates_with_multiple_shifts) > 0
	has_date_range_multiple_shifts = (
		(not is_single_day) and (len(common_shifts) == 0) and (not has_unassigned_dates)
	)

	if is_single_day:
		applicable_shifts = date_wise[0]["shifts"] if date_wise else []
		applicable_shifts_details = date_wise[0]["shift_details"] if date_wise else []
	else:
		applicable_shifts = common_shifts
		applicable_shifts_details = common_shifts_details

	unassigned_dates_message = (
		build_unassigned_dates_html_message([d["date"] for d in dates_with_no_shift])
		if has_unassigned_dates
		else None
	)

	multiple_shifts_message = (
		build_date_wise_multiple_shifts_html_message(date_wise) if has_date_range_multiple_shifts else None
	)

	same_date_shifts_message = None
	if is_single_day and has_same_date_multiple_shifts:
		same_date_shifts_message = build_same_date_multiple_shifts_html_message(
			date_wise[0]["date"], date_wise[0]["shifts"]
		)
	elif (not is_single_day) and len(common_shifts) > 1:
		same_date_shifts_message = build_same_date_multiple_shifts_html_message(
			date_wise[0]["date"], common_shifts
		)

	return {
		"is_single_day": is_single_day,
		"date_wise": date_wise,
		"all_shifts": all_shifts,
		"dates_with_no_shift": dates_with_no_shift,
		"dates_with_multiple_shifts": dates_with_multiple_shifts,
		"has_unassigned_dates": has_unassigned_dates,
		"unassigned_dates_message": unassigned_dates_message,
		"has_same_date_multiple_shifts": has_same_date_multiple_shifts,
		"has_date_range_multiple_shifts": has_date_range_multiple_shifts,
		"common_shifts": common_shifts,
		"common_shifts_details": common_shifts_details,
		"applicable_shifts": applicable_shifts,
		"applicable_shifts_details": applicable_shifts_details,
		"multiple_shifts_message": multiple_shifts_message,
		"same_date_shifts_message": same_date_shifts_message,
	}


@frappe.whitelist()
def detect_shifts_and_validate(
	employee: str, from_date: str, to_date: str | None = None, company: str | None = None
) -> dict:
	"""
	Client-side whitelisted API method to dynamically evaluate shift detection
	and company-wise rules whenever dates or employee change.
	"""
	if not employee or not from_date:
		return {}

	if not to_date:
		to_date = from_date

	if not company:
		company = frappe.db.get_value("Employee", employee, "company")

	config = get_company_attendance_regularization_config(company)
	inclusive_days = get_inclusive_date_range_days(from_date, to_date)
	analysis = get_date_wise_shift_analysis(employee, from_date, to_date)

	response = {
		"config": config,
		"inclusive_days": inclusive_days,
		"is_single_day": analysis["is_single_day"],
		"has_unassigned_dates": analysis["has_unassigned_dates"],
		"unassigned_dates_message": analysis["unassigned_dates_message"],
		"has_same_date_multiple_shifts": analysis["has_same_date_multiple_shifts"],
		"has_multiple_shifts": analysis["has_date_range_multiple_shifts"],
		"multiple_shifts_message": analysis["multiple_shifts_message"],
		"common_shifts": analysis["common_shifts"],
		"common_shifts_details": analysis["common_shifts_details"],
		"same_date_shifts": analysis["applicable_shifts"],
		"same_date_shifts_details": analysis["applicable_shifts_details"],
		"same_date_shifts_message": analysis["same_date_shifts_message"],
		"distinct_shifts": analysis["all_shifts"],
		"single_shift": analysis["common_shifts"][0]
		if (len(analysis["common_shifts"]) == 1 and not analysis["has_same_date_multiple_shifts"])
		else None,
		"no_shift_found": len(analysis["all_shifts"]) == 0,
		"date_wise": analysis["date_wise"],
	}

	return response


def validate_attendance_request_doc(doc) -> None:
	"""Validates an Attendance Request document against company configuration and multiple shifts."""
	if doc.docstatus == 1:
		return

	if not doc.company and doc.employee:
		doc.company = frappe.db.get_value("Employee", doc.employee, "company")

	if not doc.company or not doc.from_date or not doc.to_date:
		return

	config = get_company_attendance_regularization_config(doc.company)

	# 1. Single-day restriction (only if enabled on company)
	if config.get("enable_single_day"):
		if getdate(doc.from_date) != getdate(doc.to_date):
			frappe.throw(
				_(
					"Attendance Regularization is restricted to a single day. From Date and To Date must be the same."
				),
				title=_("Single-Day Attendance Regularization"),
			)
	# 2. Maximum allowed days (only if configured > 0)
	elif config.get("max_days", 0) > 0:
		inclusive_days = get_inclusive_date_range_days(doc.from_date, doc.to_date)
		if inclusive_days > config["max_days"]:
			max_days = config["max_days"]
			msg = (
				_(
					"The selected date range exceeds the maximum allowed limit of {0} days. Please select {0} (or less days)."
				).format(max_days)
				if max_days > 1
				else _(
					"The selected date range exceeds the maximum allowed limit of 1 day. Please select 1 day."
				)
			)
			frappe.throw(
				msg,
				title=_("Maximum Allowed Days Exceeded"),
			)

	# 3. Date-by-date Shift Detection & Validation
	analysis = get_date_wise_shift_analysis(doc.employee, doc.from_date, doc.to_date)

	# 3A. Unassigned dates (no shift assigned on one or more dates)
	if analysis["has_unassigned_dates"]:
		frappe.throw(
			analysis["unassigned_dates_message"],
			title=_("No Shift Assigned"),
			allow_dangerous_html=True,
		)

	# 3B. Multi-day range with different shifts across dates (no single common shift)
	if analysis["has_date_range_multiple_shifts"]:
		doc.shift = None
		frappe.throw(
			analysis["multiple_shifts_message"],
			title=_("Multiple Shifts Found in the Selected Date Range"),
			allow_dangerous_html=True,
		)

	# 3C. Valid shift resolution across the range
	common_shifts = analysis["common_shifts"]
	if common_shifts:
		if not doc.shift:
			if len(common_shifts) == 1 and not analysis["has_same_date_multiple_shifts"]:
				doc.shift = common_shifts[0]
			else:
				# Shift selection is mandatory
				frappe.throw(
					analysis["same_date_shifts_message"],
					title=_("Shift Selection Required"),
					allow_dangerous_html=True,
				)
		elif doc.shift not in common_shifts:
			invalid_dates = [d["date_str"] for d in analysis["date_wise"] if doc.shift not in d["shifts"]]
			frappe.throw(
				_("Selected shift {0} is not assigned for date(s): {1}.").format(
					frappe.bold(doc.shift), ", ".join(invalid_dates)
				),
				title=_("Invalid Shift"),
			)


def validate_attendance_request(doc, method=None):
	if getattr(doc, "_custom_attendance_validated", False) or doc.docstatus == 1:
		return

	validate_attendance_request_doc(doc)
	doc._custom_attendance_validated = True
