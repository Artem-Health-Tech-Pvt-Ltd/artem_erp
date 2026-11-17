# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import json
from datetime import datetime, time

import frappe
from frappe import _
from frappe.utils import format_time, getdate, today

STATUS_OFFICE_CHECKIN = "Office Check-in"
STATUS_ON_DUTY = "On Duty"
STATUS_WFH = "Work From Home (WFH)"
STATUS_ON_LEAVE = "On Leave"
STATUS_NO_CHECKIN = "No Check-in"


def execute(filters: dict | None = None):
	"""Return columns, data, message, chart, and report_summary for the report."""
	filters = frappe._dict(filters or {})

	if filters.get("date") and getdate(filters.get("date")) > getdate(today()):
		frappe.throw(_("Cannot select a future date."))

	columns = get_columns()
	data, report_summary, message = get_data_and_summary(filters)

	return columns, data, message, None, report_summary


def execute_snapshot_report(filters: dict | None = None):
	return execute(filters)


def get_columns() -> list[dict]:
	"""Return columns for the report."""
	return [
		{
			"label": _("Employee ID"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 140,
		},
		{
			"label": _("Employee Name"),
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 160,
		},
		{
			"label": _("Department"),
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": 160,
		},
		{
			"label": _("Shift"),
			"fieldname": "shift",
			"fieldtype": "Link",
			"options": "Shift Type",
			"width": 140,
		},
		{
			"label": _("Work Status"),
			"fieldname": "work_status",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Check-in Time"),
			"fieldname": "checkin_time",
			"fieldtype": "Time",
			"width": 130,
		},
		{
			"label": _("Leave Type"),
			"fieldname": "leave_type",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("OD/WFH explanation"),
			"fieldname": "explanation",
			"fieldtype": "Data",
			"width": 200,
		},
	]


def parse_list_filter(val) -> list[str]:
	"""Normalize string, JSON list, or list into a list of strings."""
	if not val:
		return []
	if isinstance(val, list):
		return [str(v).strip() for v in val if v]
	if isinstance(val, str):
		val = val.strip()
		if not val:
			return []
		if val.startswith("[") and val.endswith("]"):
			try:
				parsed = json.loads(val)
				if isinstance(parsed, list):
					return [str(v).strip() for v in parsed if v]
			except Exception:
				pass
		return [v.strip() for v in val.split(",") if v.strip()]
	return [str(val).strip()]


def get_leave_type_display(la, selected_date) -> str | None:
	"""Format leave type with first half, second half, or partial day details when applicable."""
	if not la:
		return None

	leave_type = la.leave_type or ""

	# Check if half day on selected_date
	is_half_day = False
	if la.get("half_day"):
		if la.from_date == la.to_date:
			is_half_day = True
		elif la.half_day_date and getdate(la.half_day_date) == selected_date:
			is_half_day = True

	if is_half_day:
		half_type = (la.get("custom_half_day_type") or "").strip()
		if half_type:
			return f"{leave_type} ({half_type})"
		return f"{leave_type} (Half Day)"

	# Check for partial day leave on selected_date
	if la.get("custom_is_partial_day_leave"):
		partial_type = (la.get("custom_partial_day_type") or "").strip()
		if partial_type:
			return f"{leave_type} ({partial_type})"
		return f"{leave_type} (Partial Day)"

	return leave_type


def get_data_and_summary(filters: dict):
	"""Evaluate employee daily work status and calculate summary cards and holiday messages."""
	if filters.get("date") and getdate(filters.get("date")) > getdate(today()):
		frappe.throw(_("Cannot select a future date."))

	selected_date = getdate(filters.get("date") or today())
	selected_companies = parse_list_filter(filters.get("company"))
	selected_departments = parse_list_filter(filters.get("department"))
	selected_shifts = parse_list_filter(filters.get("shift"))
	selected_employee = (filters.get("employee") or "").strip()
	selected_work_statuses = parse_list_filter(filters.get("work_status"))

	selected_work_statuses_normalized = set()
	for s in selected_work_statuses:
		s_clean = s.strip().lower()
		if "home" in s_clean or "wfh" in s_clean:
			selected_work_statuses_normalized.add(STATUS_WFH.lower())
			selected_work_statuses_normalized.add("work from home")
		else:
			selected_work_statuses_normalized.add(s_clean)

	# 1. Fetch eligible employees (include Active and Left for historical dates)
	emp_filters = [["status", "in", ["Active", "Left"]]]
	if selected_employee:
		emp_filters.append(["name", "=", selected_employee])
	if selected_companies:
		emp_filters.append(["company", "in", selected_companies])
	if selected_departments:
		emp_filters.append(["department", "in", selected_departments])

	all_employees = frappe.get_list(
		"Employee",
		filters=emp_filters,
		fields=[
			"name",
			"employee_name",
			"company",
			"department",
			"default_shift",
			"holiday_list",
			"date_of_joining",
			"relieving_date",
		],
		limit=None,
		order_by="employee_name asc, name asc",
	)

	# Filter out employees who hadn't joined yet or had already left by selected_date
	eligible_employees = []
	for emp in all_employees:
		if emp.date_of_joining and getdate(emp.date_of_joining) > selected_date:
			continue
		if emp.relieving_date and getdate(emp.relieving_date) < selected_date:
			continue
		eligible_employees.append(emp)

	if not eligible_employees:
		report_summary = get_report_summary(0, 0, 0, 0, 0)
		return [], report_summary, None

	emp_ids = [emp.name for emp in eligible_employees]

	# 2. Determine assigned shift for each employee on selected_date
	shift_assignments = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": ["in", emp_ids],
			"docstatus": 1,
			"status": "Active",
			"start_date": ["<=", selected_date],
		},
		fields=["employee", "shift_type", "start_date", "end_date"],
		order_by="start_date desc, creation desc",
	)

	emp_shift_map = {}
	for sa in shift_assignments:
		if sa.employee not in emp_shift_map:
			if not sa.end_date or getdate(sa.end_date) >= selected_date:
				emp_shift_map[sa.employee] = sa.shift_type

	for emp in eligible_employees:
		if emp.name not in emp_shift_map:
			emp_shift_map[emp.name] = emp.default_shift or ""

	# Filter by selected shifts if filter is present
	if selected_shifts:
		eligible_employees = [
			emp for emp in eligible_employees if emp_shift_map.get(emp.name) in selected_shifts
		]
		if not eligible_employees:
			report_summary = get_report_summary(0, 0, 0, 0, 0)
			return [], report_summary, None
		emp_ids = [emp.name for emp in eligible_employees]

	# 3. Fetch Employee Checkin records for selected_date
	start_datetime = f"{selected_date} 00:00:00"
	end_datetime = f"{selected_date} 23:59:59"

	checkins = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": ["in", emp_ids],
			"time": ["between", [start_datetime, end_datetime]],
		},
		fields=["employee", "log_type", "time"],
		order_by="time asc",
	)

	emp_checkins = {}
	for c in checkins:
		emp_checkins.setdefault(c.employee, []).append(c)

	emp_first_checkin = {}
	for emp_id, c_list in emp_checkins.items():
		in_logs = [c for c in c_list if (c.log_type or "").upper() == "IN"]
		if in_logs:
			emp_first_checkin[emp_id] = in_logs[0].time
		else:
			emp_first_checkin[emp_id] = c_list[0].time

	# 4. Fetch Attendance Requests covering selected_date (Draft or Approved)
	attendance_requests = frappe.get_all(
		"Attendance Request",
		filters={
			"employee": ["in", emp_ids],
			"docstatus": ["in", [0, 1]],
			"from_date": ["<=", selected_date],
			"to_date": [">=", selected_date],
		},
		fields=["name", "employee", "reason", "explanation", "docstatus", "creation"],
		order_by="creation desc",
	)

	emp_od_request = {}
	emp_wfh_request = {}
	for ar in attendance_requests:
		reason = (ar.reason or "").strip().lower()
		if reason == "on duty":
			if ar.employee not in emp_od_request:
				emp_od_request[ar.employee] = ar
		elif reason == "work from home":
			if ar.employee not in emp_wfh_request:
				emp_wfh_request[ar.employee] = ar

	# 5. Fetch Leave Applications covering selected_date (Draft or Approved)
	leave_applications = frappe.get_all(
		"Leave Application",
		filters={
			"employee": ["in", emp_ids],
			"docstatus": ["in", [0, 1]],
			"status": ["in", ["Open", "Approved"]],
			"from_date": ["<=", selected_date],
			"to_date": [">=", selected_date],
		},
		fields=[
			"name",
			"employee",
			"leave_type",
			"status",
			"docstatus",
			"half_day",
			"half_day_date",
			"custom_half_day_type",
			"custom_is_partial_day_leave",
			"custom_partial_day_type",
			"from_date",
			"to_date",
			"creation",
		],
		order_by="creation desc",
	)

	emp_leave_map = {}
	for la in leave_applications:
		if la.employee not in emp_leave_map:
			emp_leave_map[la.employee] = la

	# 6. Evaluate Attendance Status and Priority for each employee
	# Priority Order:
	# 1. Office Check-in
	# 2. On Duty
	# 3. Work From Home (WFH)
	# 4. On Leave
	# 5. No Check-in
	data = []
	filtered_employees = []
	for emp in eligible_employees:
		emp_id = emp.name
		shift = emp_shift_map.get(emp_id, "")

		la = emp_leave_map.get(emp_id)
		leave_type_display = get_leave_type_display(la, selected_date) if la else None

		if emp_id in emp_first_checkin:
			status = STATUS_OFFICE_CHECKIN
			raw_checkin = emp_first_checkin[emp_id]
			checkin_time = format_time(raw_checkin) if raw_checkin else None
			leave_type = leave_type_display
			explanation = None
		elif emp_id in emp_od_request:
			status = STATUS_ON_DUTY
			checkin_time = None
			leave_type = leave_type_display
			explanation = emp_od_request[emp_id].explanation or ""
		elif emp_id in emp_wfh_request:
			status = STATUS_WFH
			checkin_time = None
			leave_type = leave_type_display
			explanation = emp_wfh_request[emp_id].explanation or ""
		elif emp_id in emp_leave_map:
			status = STATUS_ON_LEAVE
			checkin_time = None
			leave_type = leave_type_display
			explanation = None
		else:
			status = STATUS_NO_CHECKIN
			checkin_time = None
			leave_type = None
			explanation = None

		# Apply Work Status filter if selected
		if selected_work_statuses_normalized and status.lower() not in selected_work_statuses_normalized:
			continue

		filtered_employees.append(emp)
		data.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"company": emp.company,
				"department": emp.department,
				"shift": shift,
				"work_status": status,
				"checkin_time": checkin_time,
				"leave_type": leave_type,
				"explanation": explanation,
			}
		)

	# 7. Summary Cards Calculation
	count_office_checkin = sum(1 for row in data if row["work_status"] == STATUS_OFFICE_CHECKIN)
	count_on_leave = sum(1 for row in data if row["work_status"] == STATUS_ON_LEAVE)
	count_on_duty = sum(1 for row in data if row["work_status"] == STATUS_ON_DUTY)
	count_wfh = sum(1 for row in data if row["work_status"] == STATUS_WFH)
	count_no_checkin = sum(1 for row in data if row["work_status"] == STATUS_NO_CHECKIN)

	report_summary = get_report_summary(
		count_office_checkin, count_on_leave, count_on_duty, count_wfh, count_no_checkin
	)

	# 8. Weekly Off and Holiday Validation (evaluated for displayed employees)
	eval_employees = filtered_employees if selected_work_statuses_normalized else eligible_employees
	message = get_holiday_and_weekly_off_message(eval_employees, emp_shift_map, selected_date)

	return data, report_summary, message


def get_report_summary(
	office_checkin: int, on_leave: int, on_duty: int, wfh: int, no_checkin: int
) -> list[dict]:
	"""Return summary cards configuration for the 5 defined statuses."""
	return [
		{
			"value": office_checkin,
			"label": _("Office Check-in"),
			"datatype": "Int",
			"indicator": "Green",
		},
		{
			"value": on_leave,
			"label": _("On Leave"),
			"datatype": "Int",
			"indicator": "Orange",
		},
		{
			"value": on_duty,
			"label": _("On Duty"),
			"datatype": "Int",
			"indicator": "Blue",
		},
		{
			"value": wfh,
			"label": _("Work From Home"),
			"datatype": "Int",
			"indicator": "Purple",
		},
		{
			"value": no_checkin,
			"label": _("No Check-in"),
			"datatype": "Int",
			"indicator": "Red",
		},
	]


def get_holiday_and_weekly_off_message(
	eligible_employees: list, emp_shift_map: dict, selected_date
) -> str | None:
	"""Check if selected_date is a weekly off or holiday for the evaluated employees."""
	if not eligible_employees:
		return None

	emp_ids = [emp.name for emp in eligible_employees]
	companies = list({emp.company for emp in eligible_employees if emp.company})

	# Fetch Holiday List Assignments for employees and companies
	assigned_to_list = emp_ids + companies
	hla_records = frappe.get_all(
		"Holiday List Assignment",
		filters={
			"assigned_to": ["in", assigned_to_list],
			"docstatus": 1,
			"from_date": ["<=", selected_date],
		},
		fields=["assigned_to", "holiday_list", "from_date"],
		order_by="from_date desc",
	)

	emp_hla = {}
	company_hla = {}
	for hla in hla_records:
		if hla.assigned_to in companies and hla.assigned_to not in company_hla:
			company_hla[hla.assigned_to] = hla.holiday_list
		elif hla.assigned_to in emp_ids and hla.assigned_to not in emp_hla:
			emp_hla[hla.assigned_to] = hla.holiday_list

	# Shift Type holiday lists
	all_shifts = list(
		{emp_shift_map.get(emp.name) for emp in eligible_employees if emp_shift_map.get(emp.name)}
	)
	shift_hl_map = {}
	if all_shifts:
		shift_records = frappe.get_all(
			"Shift Type",
			filters={"name": ["in", all_shifts]},
			fields=["name", "holiday_list"],
		)
		shift_hl_map = {s.name: s.holiday_list for s in shift_records if s.holiday_list}

	# Company default holiday lists
	company_hl_map = {}
	if companies:
		comp_records = frappe.get_all(
			"Company",
			filters={"name": ["in", companies]},
			fields=["name", "default_holiday_list"],
		)
		company_hl_map = {c.name: c.default_holiday_list for c in comp_records if c.default_holiday_list}

	# Resolve effective holiday list for each employee
	emp_effective_hl = {}
	for emp in eligible_employees:
		emp_id = emp.name
		shift = emp_shift_map.get(emp_id)
		hl = (
			emp_hla.get(emp_id)
			or emp.holiday_list
			or shift_hl_map.get(shift)
			or company_hla.get(emp.company)
			or company_hl_map.get(emp.company)
		)
		if hl:
			emp_effective_hl[emp_id] = hl

	unique_hls = list(set(emp_effective_hl.values()))
	if not unique_hls:
		return None

	# Query Holiday table for selected_date
	holidays = frappe.get_all(
		"Holiday",
		filters={
			"parent": ["in", unique_hls],
			"holiday_date": selected_date,
		},
		fields=["parent", "weekly_off"],
	)

	hl_weekly_off_set = set()
	hl_holiday_set = set()
	for h in holidays:
		if h.weekly_off:
			hl_weekly_off_set.add(h.parent)
		else:
			hl_holiday_set.add(h.parent)

	# Also check weekly_off day name in Holiday List
	day_name = selected_date.strftime("%A").lower()
	hl_docs = frappe.get_all(
		"Holiday List",
		filters={"name": ["in", unique_hls]},
		fields=["name", "weekly_off"],
	)
	for hl_doc in hl_docs:
		if hl_doc.weekly_off and hl_doc.weekly_off.strip().lower() == day_name:
			hl_weekly_off_set.add(hl_doc.name)

	# Track weekly off and holiday by employee's assigned shift
	shift_weekly_off = set()
	shift_holiday = set()

	for emp in eligible_employees:
		shift = emp_shift_map.get(emp.name) or ""
		hl = emp_effective_hl.get(emp.name)
		if hl:
			if hl in hl_weekly_off_set:
				shift_weekly_off.add(shift)
			if hl in hl_holiday_set:
				shift_holiday.add(shift)

	if not shift_weekly_off and not shift_holiday:
		return None

	def get_shift_desc(shift_set: set) -> tuple[str, bool]:
		named = [s for s in shift_set if s]
		if not named:
			return "", False
		if len(named) == 1:
			return named[0], True
		return ", ".join(sorted(named)), False

	msg_text = None
	if shift_weekly_off and shift_holiday:
		if shift_weekly_off == shift_holiday:
			shifts_str, is_single = get_shift_desc(shift_weekly_off)
			if not shifts_str:
				msg_text = _("The selected date falls on a weekly off and a holiday.")
			else:
				label = (
					_("shift: {0}").format(shifts_str) if is_single else _("shifts: {0}").format(shifts_str)
				)
				msg_text = _("The selected date falls on a weekly off and a holiday for {0}.").format(label)
		else:
			wo_str, wo_single = get_shift_desc(shift_weekly_off)
			hol_str, hol_single = get_shift_desc(shift_holiday)
			wo_label = _("shift: {0}").format(wo_str) if wo_single else _("shifts: {0}").format(wo_str)
			hol_label = _("shift: {0}").format(hol_str) if hol_single else _("shifts: {0}").format(hol_str)
			msg_text = _("The selected date falls on a weekly off for {0} and is a holiday for {1}.").format(
				wo_label, hol_label
			)
	elif shift_weekly_off:
		shifts_str, is_single = get_shift_desc(shift_weekly_off)
		if not shifts_str:
			msg_text = _("The selected date falls on a weekly off.")
		else:
			label = _("shift: {0}").format(shifts_str) if is_single else _("shifts: {0}").format(shifts_str)
			msg_text = _("The selected date falls on a weekly off for {0}.").format(label)
	elif shift_holiday:
		shifts_str, is_single = get_shift_desc(shift_holiday)
		if not shifts_str:
			msg_text = _("The selected date is a holiday.")
		else:
			label = _("shift: {0}").format(shifts_str) if is_single else _("shifts: {0}").format(shifts_str)
			msg_text = _("The selected date is a holiday for {0}.").format(label)

	if msg_text:
		return f"""<div class="daily-status-notice-banner" style="
			display: flex;
			align-items: center;
			background: #fffbeb;
			border: 1px solid #fcd34d;
			border-left: 5px solid #f59e0b;
			border-radius: 8px;
			padding: 12px 18px;
			margin: 12px 0 16px 0;
			color: #92400e;
			box-shadow: 0 2px 6px rgba(245, 158, 11, 0.12);
		">
			<span style="
				display: inline-flex;
				align-items: center;
				justify-content: center;
				background-color: #f59e0b;
				color: #ffffff;
				width: 26px;
				height: 26px;
				border-radius: 50%;
				font-size: 15px;
				font-weight: 700;
				margin-right: 14px;
				flex-shrink: 0;
			">&#9888;</span>
			<span style="
				font-size: 14px;
				font-weight: 600;
				color: #92400e;
				letter-spacing: 0.2px;
			">
				{msg_text}
			</span>
		</div>"""

	return None
