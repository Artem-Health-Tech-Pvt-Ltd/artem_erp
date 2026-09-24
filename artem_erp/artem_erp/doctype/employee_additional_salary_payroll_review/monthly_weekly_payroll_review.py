# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import (
	add_months,
	cint,
	flt,
	get_first_day,
	get_last_day,
	getdate,
	today,
)

from artem_erp.override.additional_salary import (
	calculate_concluding_recurring_additional_salary_amount,
	get_employee_joining_date,
	get_recurring_additional_salary_due_date,
	is_recurring_additional_salary_due,
)


def get_target_payroll_month(date=None):
	"""
	Returns (start_date, end_date) for the 1st and last day of the target month.
	"""
	ref_date = getdate(date) if date else getdate(today())
	return get_first_day(ref_date), get_last_day(ref_date)


def get_recurring_additional_salary_payout_date(doc, start_date, end_date):
	"""
	Returns the exact due date for a recurring Additional Salary within [start_date, end_date].
	"""
	start_date = getdate(start_date)
	end_date = getdate(end_date)

	from_date = doc.get("from_date")
	base_start = from_date or doc.get("custom_date_of_joining")
	if not base_start and doc.get("employee"):
		base_start = get_employee_joining_date(doc.get("employee"))

	if not base_start:
		return start_date

	to_date = doc.get("to_date")
	duration = doc.get("custom_duration_of_additional_salary")

	due_date = get_recurring_additional_salary_due_date(
		start_date=start_date,
		end_date=end_date,
		base_start=base_start,
		duration=duration,
		to_date=to_date,
	)
	if due_date:
		return due_date
	if to_date and start_date <= getdate(to_date) <= end_date:
		return getdate(to_date)
	return start_date


def get_applicable_additional_salaries_for_month(company, start_date, end_date):
	"""
	Returns all submitted, active Additional Salaries due in [start_date, end_date] for the company.
	"""
	start_date = getdate(start_date)
	end_date = getdate(end_date)

	additional_sal = frappe.qb.DocType("Additional Salary")
	records = (
		frappe.qb.from_(additional_sal)
		.select(
			additional_sal.name,
			additional_sal.employee,
			additional_sal.employee_name,
			additional_sal.company,
			additional_sal.salary_component,
			additional_sal.amount,
			additional_sal.is_recurring,
			additional_sal.payroll_date,
			additional_sal.from_date,
			additional_sal.to_date,
			additional_sal.custom_date_of_joining,
			additional_sal.custom_duration_of_additional_salary,
		)
		.where(
			(additional_sal.company == company)
			& (additional_sal.docstatus == 1)
			& (additional_sal.disabled == 0)
		)
	).run(as_dict=True)

	due_records = []
	for rec in records:
		if not rec.is_recurring:
			if rec.payroll_date and start_date <= getdate(rec.payroll_date) <= end_date:
				rec["payout_date"] = rec.payroll_date
				due_records.append(rec)
		else:
			if is_recurring_additional_salary_due(rec, start_date, end_date):
				rec["payout_date"] = get_recurring_additional_salary_payout_date(rec, start_date, end_date)
				due_records.append(rec)
			elif rec.to_date and start_date <= getdate(rec.to_date) <= end_date:
				rec["payout_date"] = getdate(rec.to_date)
				rec["amount"] = calculate_concluding_recurring_additional_salary_amount(rec, start_date, end_date)
				due_records.append(rec)

	return due_records


def get_pending_additional_salaries_to_carry_forward(review_doc):
	"""
	Identify pending Additional Salary records to carry forward into Previous Pending:
	1. Pending records from the most recent prior review (On Hold, Partially Paid with remaining amount, or un-finalized).
	2. Submitted past Additional Salaries that never appeared in any prior review.
	"""
	company = review_doc.company
	payroll_from_date = getdate(review_doc.payroll_from_date)

	pending_items = []
	processed_ads_keys = set()

	# 1. Query prior reviews for the same company in reverse chronological order
	prior_review_names = frappe.get_all(
		"Employee Additional Salary Payroll Review",
		filters={
			"company": company,
			"payroll_to_date": ["<", payroll_from_date],
			"docstatus": ["!=", 2],
		},
		order_by="payroll_to_date desc",
		pluck="name",
	)

	for pr_name in prior_review_names:
		prior_review = frappe.get_doc("Employee Additional Salary Payroll Review", pr_name)
		all_prior_rows = (
			(prior_review.additional_salary_payment_details or [])
			+ (prior_review.previous_pending_additional_salary or [])
		)

		for row in all_prior_rows:
			if not row.additional_salary or (row.employee, row.additional_salary) in processed_ads_keys:
				continue

			total_amt = flt(row.total_amount)
			paid_amt = flt(row.paid_amount)
			paid_pct = flt(row.paid_percentage)
			remaining_amt = flt(row.remaining_amount)
			pay_action = row.pay_action or "On Hold"

			is_pending = False
			if pay_action == "On Hold":
				is_pending = True
				if remaining_amt <= 0 and total_amt > 0 and paid_amt == 0:
					remaining_amt = total_amt
			elif pay_action == "Partially Paid" and (remaining_amt > 0 or (total_amt - paid_amt) > 0):
				is_pending = True
				if remaining_amt <= 0:
					remaining_amt = max(0.0, total_amt - paid_amt)
			elif pay_action not in ("Pay", "Never Pay", "Paid Outside ERP Payroll"):
				# Un-finalized row
				is_pending = True
				if remaining_amt <= 0 and total_amt > 0 and paid_amt == 0:
					remaining_amt = total_amt

			if is_pending:
				pending_items.append({
					"additional_salary": row.additional_salary,
					"employee": row.employee,
					"employee_name": row.employee_name,
					"bonus_type": row.bonus_type,
					"previous_pay_action": pay_action,
					"previous_additional_salary_total_amount": total_amt,
					"previous_additional_salary_paid_percentage": paid_pct,
					"previous_additional_salary_paid_amount": paid_amt,
					"previous_additional_salary_remaining_amount": remaining_amt,
					"total_amount": remaining_amt,
					"remaining_amount": remaining_amt,
					"paid_percentage": 0.0,
					"paid_amount": 0.0,
					"payout_date": row.payout_date,
					"pay_action": pay_action,
					"comment": row.comment,
				})

			# Mark as processed so older reviews don't override or duplicate
			processed_ads_keys.add((row.employee, row.additional_salary))

	return pending_items


def sync_additional_salaries_for_review(review_doc):
	"""
	Synchronizes current-month and previous-pending Additional Salary records into review_doc.
	Ensures idempotency and never overwrites HR-modified child rows or fields.
	"""
	company = review_doc.company
	start_date = getdate(review_doc.payroll_from_date)
	end_date = getdate(review_doc.payroll_to_date)

	# 1. Collect all existing (employee, additional_salary) keys across both tables
	existing_current_keys = {
		(row.employee, row.additional_salary)
		for row in (review_doc.additional_salary_payment_details or [])
		if row.additional_salary
	}
	existing_pending_keys = {
		(row.employee, row.additional_salary)
		for row in (review_doc.previous_pending_additional_salary or [])
		if row.additional_salary
	}
	all_existing_keys = existing_current_keys | existing_pending_keys

	added_current_count = 0
	added_pending_count = 0

	# 2. Synchronize Current Month Additional Salaries
	current_due_records = get_applicable_additional_salaries_for_month(company, start_date, end_date)
	for rec in current_due_records:
		key = (rec.employee, rec.name)
		if key in all_existing_keys:
			# Never duplicate or overwrite HR-modified values
			continue

		employee_name = rec.employee_name
		if not employee_name and rec.employee:
			employee_name = frappe.db.get_value("Employee", rec.employee, "employee_name")

		review_doc.append(
			"additional_salary_payment_details",
			{
				"additional_salary": rec.name,
				"employee": rec.employee,
				"employee_name": employee_name,
				"bonus_type": rec.salary_component,
				"total_amount": flt(rec.amount),
				"payout_date": rec.get("payout_date") or start_date,
				"remaining_amount": flt(rec.amount),
				"is_reviewed": 0,
			},
		)
		all_existing_keys.add(key)
		added_current_count += 1

	# 3. Synchronize Previous Pending Additional Salaries
	pending_records = get_pending_additional_salaries_to_carry_forward(review_doc)
	for pend in pending_records:
		key = (pend["employee"], pend["additional_salary"])
		if key in all_existing_keys:
			continue

		rem_amt = flt(pend.get("remaining_amount", 0.0))
		prev_total = flt(pend.get("previous_additional_salary_total_amount") or pend.get("total_amount", 0.0))
		prev_pct = flt(pend.get("previous_additional_salary_paid_percentage") or pend.get("paid_percentage", 0.0))
		prev_paid = flt(pend.get("previous_additional_salary_paid_amount") or pend.get("paid_amount", 0.0))
		prev_rem = flt(pend.get("previous_additional_salary_remaining_amount") or rem_amt)

		review_doc.append(
			"previous_pending_additional_salary",
			{
				"additional_salary": pend["additional_salary"],
				"employee": pend["employee"],
				"employee_name": pend["employee_name"],
				"bonus_type": pend["bonus_type"],
				"previous_pay_action": pend.get("previous_pay_action") or pend.get("pay_action") or "",
				"previous_additional_salary_total_amount": prev_total,
				"previous_additional_salary_paid_percentage": prev_pct,
				"previous_additional_salary_paid_amount": prev_paid,
				"previous_additional_salary_remaining_amount": prev_rem,
				"total_amount": rem_amt,
				"remaining_amount": rem_amt,
				"paid_percentage": 0.0,
				"paid_amount": 0.0,
				"payout_date": pend.get("payout_date") or start_date,
				"pay_action": pend.get("pay_action") or "On Hold",
				"comment": pend.get("comment") or "",
				"is_reviewed": 0,
			},
		)
		all_existing_keys.add(key)
		added_pending_count += 1

	if added_current_count == 0 and added_pending_count == 0:
		has_existing = bool(
			(review_doc.additional_salary_payment_details or [])
			or (review_doc.previous_pending_additional_salary or [])
		)
		if has_existing:
			msg = _("No new Additional Salary records found to synchronize.")
		else:
			msg = _("No Additional Salary records found.")
		indicator = "orange"
	else:
		msg = _(
			"Synchronization completed: {0} current month and {1} previous pending record(s) added."
		).format(added_current_count, added_pending_count)
		indicator = "green"

	return {
		"message": msg,
		"indicator": indicator,
		"added_current": added_current_count,
		"added_pending": added_pending_count,
	}


def create_monthly_payroll_reviews(date=None):
	"""
	Monthly Cron: 0 9 1 * *
	Runs on the 1st day of every month at 9:00 AM to create the current month's review for each company.
	Only generates a review IF there is at least one applicable Additional Salary record (current month or pending).
	"""
	start_date, end_date = get_target_payroll_month(date)
	companies = frappe.get_all("Company", filters={"is_group": 0}, pluck="name")

	created_reviews = []
	for company in companies:
		company_abbr = frappe.db.get_value("Company", company, "abbr")
		expected_name = f"{company_abbr}-{getdate(start_date).strftime('%b-%Y')}"

		review_doc = None
		if frappe.db.exists("Employee Additional Salary Payroll Review", expected_name):
			review_doc = frappe.get_doc("Employee Additional Salary Payroll Review", expected_name)
		else:
			existing = frappe.get_all(
				"Employee Additional Salary Payroll Review",
				filters={
					"company": company,
					"payroll_from_date": start_date,
					"payroll_to_date": end_date,
					"docstatus": ["!=", 2],
				},
				limit=1,
			)
			if existing:
				review_doc = frappe.get_doc("Employee Additional Salary Payroll Review", existing[0].name)

		if not review_doc:
			# Only generate/insert review IF at least one employee gets additional salary in current month
			review_doc = frappe.new_doc("Employee Additional Salary Payroll Review")
			review_doc.company = company
			review_doc.payroll_from_date = start_date
			review_doc.payroll_to_date = end_date
			review_doc.status = "Draft"
			review_doc.is_system_generated = 1
			sync_additional_salaries_for_review(review_doc)

			has_current_month_salaries = bool(review_doc.additional_salary_payment_details)
			if has_current_month_salaries:
				review_doc.insert(ignore_permissions=True)
				created_reviews.append(review_doc.name)
		else:
			# Idempotent: if already exists and is editable (Draft / In Review), sync missing records
			if review_doc.docstatus == 0:
				res = sync_additional_salaries_for_review(review_doc)
				if not review_doc.additional_salary_payment_details and review_doc.is_system_generated:
					# Clean up empty system-generated review if no current month additional salaries exist
					review_doc.delete(ignore_permissions=True)
				elif res["added_current"] > 0 or res["added_pending"] > 0:
					review_doc.save(ignore_permissions=True)

	return created_reviews


def sync_weekly_payroll_reviews(date=None):
	"""
	Weekly Cron: 0 9 * * 1
	Runs every Monday at 9:00 AM to synchronize newly created Additional Salary records
	into the existing current-month review, or creates the review if new Additional Salaries
	have been added since the monthly run.
	"""
	start_date, end_date = get_target_payroll_month(date)
	companies = frappe.get_all("Company", filters={"is_group": 0}, pluck="name")

	updated_reviews = []
	for company in companies:
		existing = frappe.get_all(
			"Employee Additional Salary Payroll Review",
			filters={
				"company": company,
				"payroll_from_date": start_date,
				"payroll_to_date": end_date,
				"docstatus": ["!=", 2],
			},
			order_by="creation desc",
			limit=1,
		)

		if existing:
			review_doc = frappe.get_doc("Employee Additional Salary Payroll Review", existing[0].name)
			res = sync_additional_salaries_for_review(review_doc)
			if not review_doc.additional_salary_payment_details and review_doc.is_system_generated:
				review_doc.delete(ignore_permissions=True)
			elif res["added_current"] > 0 or res["added_pending"] > 0:
				review_doc.save(ignore_permissions=True)
				updated_reviews.append(review_doc.name)
		else:
			# If no active review exists for current month, try creating (will only create if records exist)
			created = create_monthly_payroll_reviews(date)
			if created:
				updated_reviews.extend(created)

	return updated_reviews


@frappe.whitelist()
def check_payroll_review_status(
	company: str | None = None,
	start_date: str | None = None,
	end_date: str | None = None,
):
	"""
	Checks if an Employee Additional Salary Payroll Review exists for the company
	and given payroll date range.
	Returns dict with exists, name, docstatus, and status.
	"""
	if not (company and start_date and end_date):
		return {"exists": False}

	start_date = getdate(start_date)
	end_date = getdate(end_date)

	# Check for draft review first
	draft_reviews = frappe.get_all(
		"Employee Additional Salary Payroll Review",
		filters={
			"company": company,
			"payroll_from_date": ["<=", end_date],
			"payroll_to_date": [">=", start_date],
			"docstatus": 0,
		},
		fields=["name", "docstatus", "status"],
		order_by="creation desc",
		limit=1,
	)
	if draft_reviews:
		r = draft_reviews[0]
		return {
			"exists": True,
			"name": r.name,
			"docstatus": r.docstatus,
			"status": r.status,
		}

	# Then check for submitted review
	submitted_reviews = frappe.get_all(
		"Employee Additional Salary Payroll Review",
		filters={
			"company": company,
			"payroll_from_date": ["<=", end_date],
			"payroll_to_date": [">=", start_date],
			"docstatus": 1,
		},
		fields=["name", "docstatus", "status"],
		order_by="creation desc",
		limit=1,
	)
	if submitted_reviews:
		r = submitted_reviews[0]
		return {
			"exists": True,
			"name": r.name,
			"docstatus": r.docstatus,
			"status": r.status,
		}

	return {"exists": False}


@frappe.whitelist()
def get_previous_pending_additional_salary_details(
	company: str | None = None,
	payroll_from_date: str | None = None,
	additional_salary: str | None = None,
):
	"""
	Returns details of the most recent prior review row for this additional salary,
	including previous_pay_action, remaining_amount, paid_amount, paid_percentage, total_amount, etc.
	"""
	if not (company and payroll_from_date and additional_salary):
		return {}

	payroll_from_date = getdate(payroll_from_date)

	prior_reviews = frappe.get_all(
		"Employee Additional Salary Payroll Review",
		filters={
			"company": company,
			"payroll_to_date": ["<", payroll_from_date],
			"docstatus": ["!=", 2],
		},
		order_by="payroll_to_date desc",
		pluck="name",
	)

	for pr_name in prior_reviews:
		pr_doc = frappe.get_doc("Employee Additional Salary Payroll Review", pr_name)
		all_rows = (pr_doc.additional_salary_payment_details or []) + (pr_doc.previous_pending_additional_salary or [])
		for row in all_rows:
			if row.additional_salary == additional_salary:
				rem = flt(row.remaining_amount)
				tot = flt(row.total_amount)
				paid = flt(row.paid_amount)
				pct = flt(row.paid_percentage)
				action = row.pay_action or "On Hold"
				if rem <= 0 and tot > 0 and paid == 0:
					rem = tot
				elif rem <= 0 and tot > paid:
					rem = tot - paid

				return {
					"previous_pay_action": action,
					"pay_action": action,
					"total_amount": tot,
					"paid_percentage": pct,
					"paid_amount": paid,
					"remaining_amount": rem,
				}

	# If not found in any prior review, check Additional Salary itself
	ads = frappe.db.get_value("Additional Salary", additional_salary, ["amount", "salary_component"], as_dict=True)
	if ads:
		amt = flt(ads.amount)
		return {
			"previous_pay_action": "",
			"pay_action": "On Hold",
			"total_amount": amt,
			"paid_percentage": 0.0,
			"paid_amount": 0.0,
			"remaining_amount": amt,
		}

	return {}


