# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters: dict | None = None):
	"""Return columns, data, message, chart, report_summary for Expense Claim Details Report."""
	filters = filters or {}
	columns = get_columns()
	data, report_summary = get_data(filters)

	return columns, data, None, None, report_summary


def execute_snapshot_report(filters: dict | None = None):
	"""Return columns and data for snapshot report if enabled."""
	return execute(filters)


def get_columns() -> list[dict]:
	"""Return columns for detailed claim listing."""
	return [
		{
			"label": _("Claim No."),
			"fieldname": "claim_no",
			"fieldtype": "Link",
			"options": "Expense Claim",
			"width": 140,
		},
		{
			"label": _("Claim Date"),
			"fieldname": "claim_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Employee ID"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{
			"label": _("Employee Name"),
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("Expense Date"),
			"fieldname": "expense_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Description"),
			"fieldname": "description",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Claimed Amount"),
			"fieldname": "claimed_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"label": _("Approved Amount"),
			"fieldname": "approved_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"label": _("Rejected Amount"),
			"fieldname": "rejected_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"label": _("Status"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": _("Approval Status"),
			"fieldname": "approval_status",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Approver"),
			"fieldname": "approver",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Approval Date"),
			"fieldname": "approval_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Remarks"),
			"fieldname": "remarks",
			"fieldtype": "Data",
			"width": 200,
		},
	]


def get_data(filters: dict) -> tuple[list[dict], list[dict]]:
	"""Fetch detailed expense claims and build report summary using Frappe ORM."""
	# 1. Fetch filtered Expense Claims
	ec_filters = {"docstatus": ["!=", 2]}

	if filters.get("company"):
		ec_filters["company"] = filters.get("company")

	if filters.get("employee"):
		ec_filters["employee"] = filters.get("employee")

	if filters.get("department"):
		ec_filters["department"] = filters.get("department")

	status_filter = filters.get("claim_status") or filters.get("status")
	if status_filter and status_filter != "All":
		ec_filters["status"] = status_filter

	approval_status = filters.get("approval_status")
	if approval_status and approval_status != "All":
		ec_filters["approval_status"] = approval_status

	expense_claims = frappe.get_all(
		"Expense Claim",
		filters=ec_filters,
		fields=[
			"name",
			"posting_date",
			"employee",
			"employee_name",
			"company",
			"currency",
			"status",
			"approval_status",
			"expense_approver",
			"modified",
			"remark",
		],
		ignore_permissions=True,
	)

	ec_map = {ec.name: ec for ec in expense_claims}
	valid_ec_names = list(ec_map.keys())

	# Determine default currency
	currency = None
	if filters.get("company"):
		currency = frappe.get_cached_value("Company", filters.get("company"), "default_currency")
	if not currency:
		currency = frappe.db.get_default("currency") or "INR"

	claim_type = filters.get("expense_claim_type_id") or filters.get("expense_claim_type")

	if not valid_ec_names:
		report_summary = [
			{
				"value": claim_type or _("All"),
				"label": _("Expense Claim Type"),
				"datatype": "Data",
				"indicator": "Blue",
			},
			{
				"value": 0,
				"label": _("Total Claims"),
				"datatype": "Int",
				"indicator": "Purple",
			},
			{
				"value": 0.0,
				"label": _("Total Claimed Amount"),
				"datatype": "Currency",
				"currency": currency,
				"indicator": "Orange",
			},
			{
				"value": 0.0,
				"label": _("Total Approved Amount"),
				"datatype": "Currency",
				"currency": currency,
				"indicator": "Green",
			},
			{
				"value": 0.0,
				"label": _("Total Rejected Amount"),
				"datatype": "Currency",
				"currency": currency,
				"indicator": "Red",
			},
		]
		return [], report_summary

	# 2. Fetch Expense Claim Detail child rows
	ecd_filters = {
		"parenttype": "Expense Claim",
		"parent": ["in", valid_ec_names],
	}
	if claim_type and claim_type != "All":
		ecd_filters["expense_type"] = claim_type

	details = frappe.get_all(
		"Expense Claim Detail",
		filters=ecd_filters,
		fields=[
			"name",
			"parent",
			"expense_type",
			"expense_date",
			"description",
			"amount",
			"sanctioned_amount",
			"idx",
		],
		order_by="idx asc",
		ignore_permissions=True,
	)

	# 3. Fetch latest workflow action details (approver, time, remark)
	workflow_log_map = {}
	logs = frappe.get_all(
		"Workflow Action Log",
		filters={
			"parent": ["in", valid_ec_names],
			"parenttype": "Expense Claim",
		},
		fields=["parent", "action_by", "action_by_name", "action", "time", "remark", "idx"],
		order_by="idx asc",
		ignore_permissions=True,
	)
	for log in logs:
		workflow_log_map[log.parent] = log

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	data = []
	total_claimed = 0.0
	total_approved = 0.0
	total_rejected = 0.0
	unique_claims = set()

	for d in details:
		ec = ec_map.get(d.parent)
		if not ec:
			continue

		exp_date = d.expense_date or ec.posting_date
		if from_date and str(exp_date) < str(from_date):
			continue
		if to_date and str(exp_date) > str(to_date):
			continue

		claimed_amt = flt(d.amount)
		approved_amt = flt(d.sanctioned_amount)
		rejected_amt = max(0.0, claimed_amt - approved_amt)

		total_claimed += claimed_amt
		total_approved += approved_amt
		total_rejected += rejected_amt
		unique_claims.add(ec.name)

		wfl = workflow_log_map.get(ec.name)

		approver = (
			(wfl.get("action_by_name") or wfl.get("action_by"))
			if wfl
			else (ec.expense_approver or "")
		)

		approval_date = None
		if wfl and wfl.get("time"):
			approval_date = getdate(wfl.get("time"))
		elif ec.approval_status == "Approved" and ec.modified:
			approval_date = getdate(ec.modified)

		remarks = (
			(wfl.get("remark") if wfl and wfl.get("remark") else None)
			or ec.remark
			or d.description
			or ""
		)

		data.append({
			"claim_no": ec.name,
			"claim_date": ec.posting_date,
			"employee": ec.employee,
			"employee_name": ec.employee_name,
			"expense_date": exp_date,
			"description": d.description or "",
			"claimed_amount": claimed_amt,
			"approved_amount": approved_amt,
			"rejected_amount": rejected_amt,
			"status": ec.status or "",
			"approval_status": ec.approval_status or "",
			"approver": approver,
			"approval_date": approval_date,
			"remarks": remarks,
			"currency": ec.currency or currency,
		})

	# Sort data by expense_date desc, claim_no desc
	data.sort(key=lambda row: (str(row.get("expense_date") or ""), str(row.get("claim_no") or "")), reverse=True)

	# Report Summary Header Cards
	report_summary = [
		{
			"value": claim_type or _("All"),
			"label": _("Expense Claim Type"),
			"datatype": "Data",
			"indicator": "Blue",
		},
		{
			"value": len(unique_claims),
			"label": _("Total Claims"),
			"datatype": "Int",
			"indicator": "Purple",
		},
		{
			"value": total_claimed,
			"label": _("Total Claimed Amount"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Orange",
		},
		{
			"value": total_approved,
			"label": _("Total Approved Amount"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green",
		},
		{
			"value": total_rejected,
			"label": _("Total Rejected Amount"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Red",
		},
	]

	return data, report_summary

