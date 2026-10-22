# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import datetime
import json

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.model.workflow import apply_workflow
from frappe.utils import (
	add_days,
	cint,
	date_diff,
	flt,
	formatdate,
	getdate,
)
from hrms.hr.doctype.leave_application.leave_application import (
	get_leave_balance_on,
	is_lwp,
)
from hrms.hr.utils import (
	get_holidays_for_employee,
	get_leave_period,
)


def get_sandwich_settings() -> dict:
	"""
	Fetch sandwich leave configuration from Artem Setting, with fallbacks.
	Reads priority-wise deduction Leave Types from the sandwich_leave_deduction_type child table.
	"""
	doc = frappe.get_cached_doc("Artem Setting")
	apply_rule = bool(cint(doc.apply_sandwich_leave_rule_on_leave))
	max_exemptions = cint(doc.maximum_employee_exemptions)

	deduction_types = []
	for row in doc.get("sandwich_leave_deduction_type") or []:
		if row.leave_type and row.leave_type not in deduction_types:
			deduction_types.append(row.leave_type)

	# Fallback if child table has no rows configured
	if not deduction_types:
		for pat in ["Casual Leave", "%Casual%"]:
			lt = frappe.db.get_value("Leave Type", {"name": ["like", pat], "is_lwp": 0}, "name")
			if lt and lt not in deduction_types:
				deduction_types.append(lt)
				break
		for pat in ["%Privilege%", "%Earned%", "%Paid%"]:
			lt = frappe.db.get_value("Leave Type", {"name": ["like", pat], "is_lwp": 0}, "name")
			if lt and lt not in deduction_types:
				deduction_types.append(lt)
				break
		unpaid_lt = (
			frappe.db.get_value("Leave Type", {"name": "Unpaid Leave"}, "name")
			or frappe.db.get_value("Leave Type", {"name": "Leave Without Pay"}, "name")
			or frappe.db.get_value("Leave Type", {"is_lwp": 1}, "name")
		)
		if unpaid_lt and unpaid_lt not in deduction_types:
			deduction_types.append(unpaid_lt)

	return {
		"apply_sandwich_leave_rule_on_leave": apply_rule,
		"maximum_employee_exemptions": max_exemptions,
		"deduction_types": deduction_types,
	}


def get_leave_year_for_employee(employee: str, date) -> tuple:
	"""
	Return (year_start, year_end) for the employee covering `date`.
	Checks Leave Period, then Fiscal Year, then calendar year.
	"""
	date = getdate(date)
	company = frappe.db.get_value("Employee", employee, "company") or frappe.defaults.get_user_default(
		"Company"
	)

	if company:
		leave_periods = get_leave_period(date, date, company)
		if leave_periods:
			return getdate(leave_periods[0].from_date), getdate(leave_periods[0].to_date)

		fy = get_fiscal_year(date=date, company=company, as_dict=True)
		if fy:
			return getdate(fy.year_start_date), getdate(fy.year_end_date)

	# Fallback to calendar year
	return getdate(f"{date.year}-01-01"), getdate(f"{date.year}-12-31")


def get_sandwich_exemptions_consumed(
	employee: str, year_start, year_end, exclude_name: str | None = None
) -> int:
	"""
	Count how many sandwich leave exemptions have been used by the employee
	in the given leave year. Excludes cancelled and rejected applications.
	"""
	filters = {
		"employee": employee,
		"custom_apply_sandwich_exemption": 1,
		"from_date": [">=", year_start],
		"to_date": ["<=", year_end],
		"docstatus": ["!=", 2],
		"status": ["!=", "Rejected"],
	}
	if exclude_name:
		filters["name"] = ["!=", exclude_name]

	return cint(frappe.db.count("Leave Application", filters=filters))


def get_relevant_prior_leave(employee: str, from_date, current_name: str | None = None) -> dict | None:
	"""
	Find the closest preceding non-rejected, non-cancelled regular leave application.
	"""
	from_date = getdate(from_date)
	filters = {
		"employee": employee,
		"docstatus": ["!=", 2],
		"status": ["!=", "Rejected"],
		"custom_is_sandwich_leave": 0,
		"to_date": ["<", from_date],
	}
	if current_name:
		filters["name"] = ["!=", current_name]

	prior_leaves = frappe.get_all(
		"Leave Application",
		filters=filters,
		fields=[
			"name",
			"from_date",
			"to_date",
			"leave_type",
			"docstatus",
			"status",
			"total_leave_days",
			"half_day",
			"custom_is_partial_day_leave",
		],
		order_by="to_date desc, from_date desc",
		limit=1,
	)
	return prior_leaves[0] if prior_leaves else None


def get_all_holiday_dates_for_employee(employee: str, start_date, end_date) -> set:
	"""
	Return a set of date objects representing all holidays and weekly offs
	for the given employee between start_date and end_date.
	"""
	holidays = get_holidays_for_employee(employee, start_date, end_date, raise_exception=False) or []
	return {getdate(h.get("holiday_date")) for h in holidays if h.get("holiday_date")}


@frappe.whitelist()
def check_sandwich_condition(
	employee: str | None = None,
	from_date: str | datetime.date | None = None,
	to_date: str | datetime.date | None = None,
	leave_type: str | None = None,
	name: str | None = None,
	doc_name: str | None = None,
	**kwargs,
) -> dict:
	"""
	Whitelisted method to evaluate if a sandwich leave condition exists.
	Returns detailed metadata including intervening dates, prior leave reference,
	and exemption allowance information.
	Accepts string dates from HTTP requests or datetime.date from internal Python calls.
	"""
	target_name = name or doc_name

	# Determine if flags were explicitly provided by the caller
	has_half_day_arg = "half_day" in kwargs
	half_day = cint(kwargs.get("half_day")) if has_half_day_arg else None

	has_partial_arg = ("is_partial_day" in kwargs) or ("custom_is_partial_day_leave" in kwargs)
	if has_partial_arg:
		is_partial_day = cint(kwargs.get("is_partial_day")) or cint(kwargs.get("custom_is_partial_day_leave"))
	else:
		is_partial_day = None

	if target_name and frappe.db.exists("Leave Application", target_name):
		target_doc = frappe.get_doc("Leave Application", target_name)
		if not employee:
			employee = target_doc.employee
		if not from_date:
			from_date = target_doc.from_date
		if not to_date:
			to_date = target_doc.to_date
		if not leave_type:
			leave_type = target_doc.leave_type
		if half_day is None:
			half_day = cint(target_doc.half_day)
		if is_partial_day is None:
			is_partial_day = cint(target_doc.custom_is_partial_day_leave)

	half_day = cint(half_day)
	is_partial_day = cint(is_partial_day)

	if not is_partial_day and leave_type:
		is_partial_day = cint(frappe.db.get_value("Leave Type", leave_type, "custom_is_partial_day"))

	# Partial Leave and Half-Day Leave are excluded from sandwich leave calculation
	if half_day or is_partial_day:
		return {
			"sandwich_detected": False,
			"exempt_reason": "Partial Leave and Half-Day Leave are excluded from Sandwich Leave.",
		}

	if not employee or not from_date or not leave_type:
		return {"sandwich_detected": False}

	settings = get_sandwich_settings()
	if not settings.get("apply_sandwich_leave_rule_on_leave"):
		return {"sandwich_detected": False}

	from_date = getdate(from_date)
	prior_leave = get_relevant_prior_leave(employee, from_date, current_name=target_name)

	# 1. Check Prior Leave Sandwich Condition
	is_prior_sandwich = False
	remaining_sandwich_dates = []

	if prior_leave:
		prior_half_day = cint(prior_leave.get("half_day"))
		prior_is_partial = cint(prior_leave.get("custom_is_partial_day_leave"))
		if not prior_is_partial and prior_leave.get("leave_type"):
			prior_is_partial = cint(
				frappe.db.get_value("Leave Type", prior_leave.get("leave_type"), "custom_is_partial_day")
			)

		if not (prior_half_day or prior_is_partial):
			is_prior_optional = bool(
				frappe.db.get_value("Leave Type", prior_leave.leave_type, "is_optional_leave")
			)
			is_current_optional = bool(frappe.db.get_value("Leave Type", leave_type, "is_optional_leave"))
			if not (is_prior_optional or is_current_optional):
				prior_to_date = getdate(prior_leave.to_date)
				intervening_dates = []
				curr = add_days(prior_to_date, 1)
				while curr < from_date:
					intervening_dates.append(curr)
					curr = add_days(curr, 1)

				if intervening_dates:
					employee_holidays = get_all_holiday_dates_for_employee(
						employee, intervening_dates[0], intervening_dates[-1]
					)
					if all(d in employee_holidays for d in intervening_dates):
						existing = frappe.get_all(
							"Leave Application",
							filters={
								"employee": employee,
								"docstatus": ["!=", 2],
								"status": ["!=", "Rejected"],
								"from_date": ["<=", intervening_dates[-1]],
								"to_date": [">=", intervening_dates[0]],
							},
							fields=["from_date", "to_date", "name"],
						)
						covered_dates = set()
						for ex in existing:
							d = getdate(ex.from_date)
							while d <= getdate(ex.to_date):
								covered_dates.add(d)
								d = add_days(d, 1)

						remaining_sandwich_dates = [d for d in intervening_dates if d not in covered_dates]
						if remaining_sandwich_dates:
							is_prior_sandwich = True

	if is_prior_sandwich:
		# Calculate exemption allowance
		year_start, year_end = get_leave_year_for_employee(employee, from_date)
		max_exemptions = settings.get("maximum_employee_exemptions") or 0
		consumed_exemptions = get_sandwich_exemptions_consumed(
			employee, year_start, year_end, exclude_name=target_name
		)
		remaining_exemptions = max(0, max_exemptions - consumed_exemptions)

		return {
			"sandwich_detected": True,
			"is_single_application_holiday": False,
			"prior_leave": prior_leave.name,
			"prior_leave_status": prior_leave.status,
			"prior_leave_docstatus": prior_leave.docstatus,
			"prior_leave_type": prior_leave.leave_type,
			"prior_from_date": str(prior_leave.from_date),
			"prior_to_date": str(prior_leave.to_date),
			"intervening_dates": [str(d) for d in remaining_sandwich_dates],
			"intervening_days_count": len(remaining_sandwich_dates),
			"exemptions_allowed": max_exemptions,
			"exemptions_consumed": consumed_exemptions,
			"exemptions_remaining": remaining_exemptions,
			"leave_year_start": str(year_start),
			"leave_year_end": str(year_end),
		}

	# 2. Check Single Application Include Holidays Sandwich Condition
	to_date = getdate(to_date or from_date)
	include_holiday = cint(frappe.db.get_value("Leave Type", leave_type, "include_holiday"))
	if include_holiday:
		holidays = get_all_holiday_dates_for_employee(employee, from_date, to_date)
		total_span = date_diff(to_date, from_date) + 1
		if holidays and 0 < len(holidays) < total_span:
			year_start, year_end = get_leave_year_for_employee(employee, from_date)
			max_exemptions = settings.get("maximum_employee_exemptions") or 0
			consumed_exemptions = get_sandwich_exemptions_consumed(
				employee, year_start, year_end, exclude_name=target_name
			)
			remaining_exemptions = max(0, max_exemptions - consumed_exemptions)

			return {
				"sandwich_detected": True,
				"is_single_application_holiday": True,
				"leave_type": leave_type,
				"from_date": str(from_date),
				"to_date": str(to_date),
				"intervening_dates": [str(d) for d in sorted(holidays)],
				"intervening_days_count": len(holidays),
				"exemptions_allowed": max_exemptions,
				"exemptions_consumed": consumed_exemptions,
				"exemptions_remaining": remaining_exemptions,
				"leave_year_start": str(year_start),
				"leave_year_end": str(year_end),
			}

	return {"sandwich_detected": False}


def validate_sandwich_leave_on_save(doc):
	"""
	Called in Leave Application validate() hook.
	Records sandwich detection and verifies exemption allowance limits.
	"""
	if doc.custom_is_sandwich_leave or doc.custom_system_generated:
		return

	if doc.half_day or doc.custom_is_partial_day_leave:
		doc.custom_sandwich_detected = 0
		doc.custom_sandwich_rule_confirmed = 0
		doc.custom_apply_sandwich_exemption = 0
		doc.custom_prior_leave_application = None
		doc.custom_sandwich_details = None
		return

	settings = get_sandwich_settings()
	if not settings.get("apply_sandwich_leave_rule_on_leave"):
		doc.custom_sandwich_detected = 0
		doc.custom_sandwich_rule_confirmed = 0
		doc.custom_apply_sandwich_exemption = 0
		return

	res = check_sandwich_condition(
		employee=doc.employee,
		from_date=doc.from_date,
		to_date=doc.to_date,
		leave_type=doc.leave_type,
		name=doc.name,
		half_day=doc.half_day,
		is_partial_day=doc.custom_is_partial_day_leave,
	)

	if res.get("sandwich_detected"):
		doc.custom_sandwich_detected = 1
		doc.custom_prior_leave_application = (
			res.get("prior_leave") if not res.get("is_single_application_holiday") else None
		)
		doc.custom_sandwich_details = json.dumps(
			{
				"is_single_application_holiday": bool(res.get("is_single_application_holiday")),
				"prior_leave": res.get("prior_leave"),
				"intervening_dates": res.get("intervening_dates"),
				"days_count": res.get("intervening_days_count"),
			}
		)

		# Validate exemption quota if employee chose to apply exemption
		if doc.custom_apply_sandwich_exemption:
			if res.get("exemptions_remaining", 0) <= 0:
				frappe.throw(
					_(
						"Cannot apply Sandwich Leave Exemption. You have reached the maximum allowed limit of {0} exemption(s) for the leave year ({1} to {2})."
					).format(
						res.get("exemptions_allowed", 0),
						formatdate(res.get("leave_year_start")),
						formatdate(res.get("leave_year_end")),
					),
					title=_("Sandwich Leave Exemption Limit Exceeded"),
				)
		elif not doc.custom_sandwich_rule_confirmed:
			if res.get("is_single_application_holiday"):
				if res.get("exemptions_remaining", 0) <= 0:
					return

				dates_str = ", ".join(formatdate(d) for d in res.get("intervening_dates", []))
				days_count = res.get("intervening_days_count")
				rem = res.get("exemptions_remaining", 0)
				allowed = res.get("exemptions_allowed", 0)
				frappe.throw(
					_(
						"Sandwich Leave condition detected:<br>"
						"The selected Leave Type ({0}) includes intervening non-working days ({1} day(s): <b>{2}</b>) between {3} and {4} as leave.<br>"
						"Under Sandwich Leave policy, these intervening days will be counted as leave unless an exemption is applied.<br>"
						"<span style='color: #28a745;'>You have <b>{5}</b> of <b>{6}</b> sandwich leave exemption(s) remaining for this leave year.</span><br><br>"
						"To confirm and proceed, please check <b>Sandwich Leave Confirmed</b> under the <b>Sandwich Leave Details</b> section of this form.<br>"
						"(Alternatively, check <b>Apply Sandwich Exemption</b> if you wish to use an exemption)."
					).format(
						doc.leave_type,
						days_count,
						dates_str,
						formatdate(doc.from_date),
						formatdate(doc.to_date),
						rem,
						allowed,
					),
					title=_("Sandwich Leave Confirmation Required"),
				)
			else:
				from frappe.utils import get_link_to_form

				prior_link = get_link_to_form("Leave Application", res.get("prior_leave"))
				dates_str = ", ".join(formatdate(d) for d in res.get("intervening_dates", []))
				days_count = res.get("intervening_days_count")
				rem = res.get("exemptions_remaining", 0)
				allowed = res.get("exemptions_allowed", 0)

				exemption_note = ""
				if allowed > 0:
					if rem > 0:
						exemption_note = _(
							"<br><span style='color: #28a745;'>You have <b>{0}</b> of <b>{1}</b> sandwich leave exemption(s) remaining for this leave year.</span>"
						).format(rem, allowed)
					else:
						exemption_note = _(
							"<br><span style='color: #dc3545;'>All <b>{0}</b> sandwich leave exemptions have been consumed for this leave year.</span>"
						).format(allowed)

				frappe.throw(
					_(
						"Sandwich Leave condition detected:<br>"
						"Intervening non-working days ({0} day(s): <b>{1}</b>) fall between earlier leave application {2} and this application.<br>"
						"Under Sandwich Leave policy, these intervening days will be automatically deducted as leave upon manager approval.{3}<br><br>"
						"To confirm and proceed, please check <b>Sandwich Leave Confirmed</b> under the <b>Sandwich Leave Details</b> section of this form.<br>"
						"(Alternatively, check <b>Apply Sandwich Exemption</b> if you wish to use an exemption)."
					).format(days_count, dates_str, prior_link, exemption_note),
					title=_("Sandwich Leave Confirmation Required"),
				)
	else:
		doc.custom_sandwich_detected = 0
		doc.custom_sandwich_rule_confirmed = 0
		doc.custom_apply_sandwich_exemption = 0
		doc.custom_prior_leave_application = None
		doc.custom_sandwich_details = None


@frappe.whitelist()
def check_earlier_pending_before_approval(
	employee: str | None = None,
	from_date: str | datetime.date | None = None,
	to_date: str | datetime.date | None = None,
	leave_type: str | None = None,
	name: str | None = None,
	doc_name: str | None = None,
	**kwargs,
) -> dict:
	"""
	Whitelisted method called before workflow action or approval
	to check if an earlier relevant leave application is still pending.
	"""
	target_name = name or doc_name
	if target_name and (not employee or not from_date or not leave_type):
		if frappe.db.exists("Leave Application", target_name):
			doc = frappe.get_doc("Leave Application", target_name)
			employee = employee or doc.employee
			from_date = from_date or str(doc.from_date)
			to_date = to_date or str(doc.to_date)
			leave_type = leave_type or doc.leave_type

	if not employee or not from_date or not leave_type:
		return {"has_pending_prior": False}

	settings = get_sandwich_settings()
	if not settings.get("apply_sandwich_leave_rule_on_leave"):
		return {"has_pending_prior": False}

	prior_leave = get_relevant_prior_leave(employee, from_date, current_name=target_name)
	if not prior_leave:
		return {"has_pending_prior": False}

	cond = check_sandwich_condition(
		employee=employee,
		from_date=from_date,
		to_date=to_date,
		leave_type=leave_type,
		name=target_name,
	)
	if not cond or not cond.get("sandwich_detected") or cond.get("is_single_application_holiday"):
		return {"has_pending_prior": False}

	if prior_leave.docstatus != 1 or prior_leave.status != "Approved":
		return {
			"has_pending_prior": True,
			"prior_leave": prior_leave.name,
			"prior_from_date": formatdate(prior_leave.from_date),
			"prior_to_date": formatdate(prior_leave.to_date),
			"prior_status": prior_leave.status,
		}

	return {"has_pending_prior": False}


def validate_earlier_pending_applications(doc):
	"""
	Stage 2: Manager Approves the Leave Application.
	When attempting to approve, check if an earlier relevant leave application is still pending.
	If pending, block approval until the earlier application is resolved.
	"""
	if doc.custom_is_sandwich_leave or doc.custom_system_generated:
		return

	if doc.half_day or doc.custom_is_partial_day_leave:
		return

	settings = get_sandwich_settings()
	if not settings.get("apply_sandwich_leave_rule_on_leave"):
		return

	prior_leave = get_relevant_prior_leave(doc.employee, doc.from_date, current_name=doc.name)
	if not prior_leave:
		return

	# Re-evaluate if sandwich condition connects prior_leave with current application
	cond = check_sandwich_condition(
		employee=doc.employee,
		from_date=doc.from_date,
		to_date=doc.to_date,
		leave_type=doc.leave_type,
		name=doc.name,
		half_day=doc.half_day,
		is_partial_day=doc.custom_is_partial_day_leave,
	)
	if not cond or not cond.get("sandwich_detected") or cond.get("is_single_application_holiday"):
		return

	# If prior application is pending approval
	if prior_leave.docstatus != 1 or prior_leave.status != "Approved":
		from frappe.utils import get_link_to_form

		prior_link = get_link_to_form("Leave Application", prior_leave.name)
		frappe.throw(
			_(
				"Cannot approve Leave Application {0}. The earlier relevant leave application {1} (from {2} to {3}) is still pending approval. Earlier pending leave applications must be approved or Rejected before approving this application."
			).format(
				frappe.bold(doc.name or "this application"),
				prior_link,
				formatdate(prior_leave.from_date),
				formatdate(prior_leave.to_date),
			),
			title=_("Earlier Leave Application Pending"),
			primary_action={
				"label": _("Go to {0}").format(prior_leave.name),
				"client_action": "frappe.set_route",
				"args": ["Form", "Leave Application", prior_leave.name],
			},
		)


def get_effective_available_balance(
	employee: str,
	leave_type: str | None,
	date,
	current_docname: str | None = None,
) -> float:
	"""
	Calculate Effective Available Balance = Current Available Balance - Reserved Pending Leaves.
	Does not count the current application twice.
	"""
	if not leave_type:
		return 0.0

	if is_lwp(leave_type):
		return float("inf")

	balance_dict = get_leave_balance_on(
		employee,
		leave_type,
		date,
		consider_all_leaves_in_the_allocation_period=True,
		for_consumption=True,
	)
	current_balance = flt(
		balance_dict.get("leave_balance_for_consumption", 0.0)
		if isinstance(balance_dict, dict)
		else balance_dict
	)

	# Sum pending leave applications for this employee & leave type
	pending_query = """
		SELECT COALESCE(SUM(total_leave_days), 0)
		FROM `tabLeave Application`
		WHERE employee = %s
		  AND leave_type = %s
		  AND docstatus = 0
		  AND status NOT IN ('Rejected', 'Cancelled')
		  AND name != %s
	"""
	pending_result = frappe.db.sql(pending_query, (employee, leave_type, current_docname or ""))
	pending_days = flt(pending_result[0][0]) if pending_result else 0.0

	return max(0.0, current_balance - pending_days)


def generate_sandwich_leave_records(doc):
	"""
	Stage 2: After manager approves (on_submit), generate auto-approved Sandwich Leave records
	distributed across Leave Types based on effective balances.
	"""
	if doc.custom_is_sandwich_leave or doc.custom_system_generated:
		return

	if doc.half_day or doc.custom_is_partial_day_leave:
		return

	settings = get_sandwich_settings()
	if not settings.get("apply_sandwich_leave_rule_on_leave"):
		return

	# If employee validly selected an exemption, skip sandwich generation
	if doc.custom_apply_sandwich_exemption:
		frappe.msgprint(
			_(
				"Sandwich Leave generation skipped for Leave Application {0} due to Employee Exemption."
			).format(doc.name),
			alert=True,
		)
		return

	# Recheck sandwich condition using latest state
	cond = check_sandwich_condition(
		employee=doc.employee,
		from_date=doc.from_date,
		to_date=doc.to_date,
		leave_type=doc.leave_type,
		name=doc.name,
		half_day=doc.half_day,
		is_partial_day=doc.custom_is_partial_day_leave,
	)
	if not cond or not cond.get("sandwich_detected") or cond.get("is_single_application_holiday"):
		return

	prior_leave = get_relevant_prior_leave(doc.employee, doc.from_date, current_name=doc.name)
	if not prior_leave or prior_leave.docstatus != 1 or prior_leave.status != "Approved":
		return

	prior_half_day = cint(prior_leave.get("half_day"))
	prior_is_partial = cint(prior_leave.get("custom_is_partial_day_leave"))
	if not prior_is_partial and prior_leave.get("leave_type"):
		prior_is_partial = cint(
			frappe.db.get_value("Leave Type", prior_leave.get("leave_type"), "custom_is_partial_day")
		)
	if prior_half_day or prior_is_partial:
		return

	intervening_dates = [getdate(d) for d in cond.get("intervening_dates", [])]
	if not intervening_dates:
		return

	deduction_types = settings.get("deduction_types") or []
	if not deduction_types:
		frappe.throw(_("No Leave Types configured in Sandwich Leave Deduction Type."))

	# Determine unpaid / LWP fallback if needed
	unpaid_fallback = None
	for lt in deduction_types:
		if is_lwp(lt):
			unpaid_fallback = lt
			break
	if not unpaid_fallback:
		unpaid_fallback = (
			frappe.db.get_value("Leave Type", {"name": "Unpaid Leave"}, "name")
			or frappe.db.get_value("Leave Type", {"name": "Leave Without Pay"}, "name")
			or frappe.db.get_value("Leave Type", {"is_lwp": 1}, "name")
		)

	# Calculate initial effective available balances as of first sandwich day
	ref_date = intervening_dates[0]
	balances = {}
	for lt in deduction_types:
		if not is_lwp(lt):
			balances[lt] = get_effective_available_balance(
				doc.employee, lt, ref_date, current_docname=doc.name
			)

	allocations = []
	for d in intervening_dates:
		allocated_lt = None
		for lt in deduction_types:
			if is_lwp(lt):
				allocated_lt = lt
				break
			if balances.get(lt, 0.0) >= 1.0:
				allocated_lt = lt
				balances[lt] -= 1.0
				break

		if not allocated_lt:
			allocated_lt = unpaid_fallback

		if not allocated_lt:
			frappe.throw(
				_(
					"No Leave Type with available balance or Unpaid Leave Type found for Sandwich Leave allocation."
				)
			)

		allocations.append((d, allocated_lt))

	# Group contiguous dates having the same allocated Leave Type
	grouped_records = []
	curr_group = None
	for d, lt in allocations:
		if not curr_group:
			curr_group = {"from_date": d, "to_date": d, "leave_type": lt, "days": 1.0}
		elif curr_group["leave_type"] == lt and getdate(d) == add_days(curr_group["to_date"], 1):
			curr_group["to_date"] = d
			curr_group["days"] += 1.0
		else:
			grouped_records.append(curr_group)
			curr_group = {"from_date": d, "to_date": d, "leave_type": lt, "days": 1.0}

	if curr_group:
		grouped_records.append(curr_group)

	# Create and submit automatically approved Sandwich Leave Applications
	generated_names = []
	for grp in grouped_records:
		# Double check no duplicate exists
		existing_sl = frappe.db.exists(
			"Leave Application",
			{
				"employee": doc.employee,
				"from_date": grp["from_date"],
				"to_date": grp["to_date"],
				"docstatus": 1,
				"custom_is_sandwich_leave": 1,
				"custom_parent_leave_application": doc.name,
			},
		)
		if existing_sl:
			continue

		sandwich_doc = frappe.new_doc("Leave Application")
		sandwich_doc.employee = doc.employee
		sandwich_doc.employee_name = doc.employee_name
		sandwich_doc.leave_type = grp["leave_type"]
		sandwich_doc.from_date = grp["from_date"]
		sandwich_doc.to_date = grp["to_date"]
		sandwich_doc.total_leave_days = grp["days"]
		if not is_lwp(grp["leave_type"]):
			lb = get_leave_balance_on(
				doc.employee,
				grp["leave_type"],
				grp["from_date"],
				grp["to_date"],
				consider_all_leaves_in_the_allocation_period=True,
			)
			sandwich_doc.leave_balance = flt(lb)
		else:
			sandwich_doc.leave_balance = 0.0
		sandwich_doc.status = "Open"
		sandwich_doc.docstatus = 0
		sandwich_doc.leave_approver = doc.leave_approver or frappe.db.get_value(
			"Employee", doc.employee, "leave_approver"
		)
		sandwich_doc.company = doc.company
		sandwich_doc.follow_via_email = 0
		sandwich_doc.custom_system_generated = 1
		sandwich_doc.custom_is_sandwich_leave = 1
		sandwich_doc.custom_parent_leave_application = doc.name
		sandwich_doc.custom_prior_leave_application = prior_leave.name
		sandwich_doc.description = _(
			"Auto-generated Sandwich Leave for intervening weekly off/holiday between {0} and {1}."
		).format(prior_leave.name, doc.name)

		sandwich_doc.flags.ignore_permissions = True
		sandwich_doc.flags.is_sandwich_leave = True
		sandwich_doc.insert()

		has_workflow = frappe.get_all(
			"Workflow", filters={"document_type": "Leave Application", "is_active": 1}
		)
		if has_workflow:
			apply_workflow(sandwich_doc, "Approve")
		else:
			sandwich_doc.status = "Approved"
			sandwich_doc.submit()
		generated_names.append(sandwich_doc.name)

	if generated_names:
		frappe.msgprint(
			_("Generated {0} Sandwich Leave record(s): {1}").format(
				len(generated_names), ", ".join(generated_names)
			),
			alert=True,
		)


def cancel_sandwich_leave_records(doc):
	"""
	Cancel or reverse generated sandwich leave records when the parent or prior leave
	application is cancelled. Idempotent.
	Ensures docstatus=2, status="Cancelled", and workflow_state="Cancelled" (if active workflow exists).
	"""
	if doc.custom_is_sandwich_leave:
		# Standard cancellation of sandwich leave automatically restores ledger balance
		return

	# Find active workflow details for Leave Application
	workflow_state_field = None
	cancelled_state = "Cancelled"
	workflows = frappe.get_all(
		"Workflow",
		filters={"document_type": "Leave Application", "is_active": 1},
		fields=["name", "workflow_state_field"],
	)
	if workflows:
		workflow_state_field = workflows[0].workflow_state_field or "workflow_state"
		cancelled_states = frappe.get_all(
			"Workflow Document State",
			filters={"parent": workflows[0].name, "doc_status": "2"},
			fields=["state"],
		)
		if cancelled_states:
			cancelled_state = cancelled_states[0].state

	# Find all sandwich leave applications linked to this leave (as parent or prior)
	linked_sls = frappe.get_all(
		"Leave Application",
		filters=[
			["custom_is_sandwich_leave", "=", 1],
		],
		or_filters=[
			["custom_parent_leave_application", "=", doc.name],
			["custom_prior_leave_application", "=", doc.name],
		],
		fields=["name", "docstatus", "status"],
	)

	cancelled_records = []
	for sl in linked_sls:
		try:
			sl_doc = frappe.get_doc("Leave Application", sl.name)
			sl_doc.flags.ignore_permissions = True
			sl_doc.flags.is_sandwich_leave = True

			was_active = sl_doc.docstatus != 2

			if sl_doc.docstatus == 1:
				sl_doc.cancel()
				if was_active:
					cancelled_records.append(sl.name)
			elif sl_doc.docstatus == 0:
				try:
					sl_doc.delete()
					if was_active:
						cancelled_records.append(sl.name)
					continue
				except Exception:
					sl_doc.cancel()
					if was_active:
						cancelled_records.append(sl.name)

			# Ensure status and workflow_state are cleanly synchronized in the database
			updates = {"status": "Cancelled", "docstatus": 2}
			if workflow_state_field:
				updates[workflow_state_field] = cancelled_state
			frappe.db.set_value("Leave Application", sl.name, updates)

			if workflow_state_field and was_active:
				try:
					sl_doc.add_comment("Workflow", _(cancelled_state))
				except Exception:
					pass

		except Exception:
			frappe.log_error(title="Sandwich Leave Cancellation Error", message=frappe.get_traceback())

	if cancelled_records:
		frappe.msgprint(
			_("Associated Sandwich Leave record(s) cancelled: {0}").format(", ".join(cancelled_records)),
			alert=True,
		)
