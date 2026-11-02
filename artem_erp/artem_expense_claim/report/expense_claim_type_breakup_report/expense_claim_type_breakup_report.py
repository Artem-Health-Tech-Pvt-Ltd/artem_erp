# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters: dict | None = None):
	"""Return columns and data for the Expense Claim Type Breakup Report."""
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)

	return columns, data


def execute_snapshot_report(filters: dict | None = None):
	"""Return columns and data for snapshot report if enabled."""
	return execute(filters)


def get_columns() -> list[dict]:
	"""Return columns for the report."""
	return [
		{
			"label": _("Expense Claim Type"),
			"fieldname": "expense_claim_type",
			"fieldtype": "Link",
			"options": "Expense Claim Type",
			"width": 160,
		},
		{
			"label": _("Description"),
			"fieldname": "description",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("No. of Claims"),
			"fieldname": "no_of_claims",
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"label": _("Total Claimed Amount"),
			"fieldname": "total_claimed_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"label": _("Total Approved Amount"),
			"fieldname": "total_approved_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"label": _("Total Rejected Amount"),
			"fieldname": "total_rejected_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{
			"label": _("Status"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": _("Action"),
			"fieldname": "action",
			"fieldtype": "Data",
			"width": 180,
		},
	]


def get_data(filters: dict) -> list[dict]:
	"""Fetch expense claim type summary breakup using Frappe ORM."""
	# 1. Fetch Expense Claim Types
	type_filters = {}
	if filters.get("expense_claim_type"):
		type_filters["name"] = filters.get("expense_claim_type")

	fields = ["name", "expense_type", "description"]
	has_disabled_field = frappe.db.has_column("Expense Claim Type", "disabled")
	if has_disabled_field:
		fields.append("disabled")

	claim_types = frappe.get_all(
		"Expense Claim Type",
		filters=type_filters,
		fields=fields,
		order_by="name asc",
		ignore_permissions=True,
	)

	# 2. Build filters for Expense Claim
	ec_filters = {"docstatus": ["!=", 2]}
	if filters.get("company"):
		ec_filters["company"] = filters.get("company")
	if filters.get("employee"):
		ec_filters["employee"] = filters.get("employee")
	if filters.get("department"):
		ec_filters["department"] = filters.get("department")
	if filters.get("approval_status"):
		ec_filters["approval_status"] = filters.get("approval_status")

	expense_claims = frappe.get_all(
		"Expense Claim",
		filters=ec_filters,
		fields=["name", "employee", "posting_date", "company", "department", "approval_status", "status"],
		ignore_permissions=True,
	)
	ec_map = {ec.name: ec for ec in expense_claims}
	valid_ec_names = list(ec_map.keys())

	# 3. Fetch Expense Claim Detail child rows
	agg_map = {}
	if valid_ec_names:
		ecd_filters = {
			"parenttype": "Expense Claim",
			"parent": ["in", valid_ec_names],
		}
		if filters.get("expense_claim_type"):
			ecd_filters["expense_type"] = filters.get("expense_claim_type")

		details = frappe.get_all(
			"Expense Claim Detail",
			filters=ecd_filters,
			fields=["name", "parent", "expense_type", "expense_date", "amount", "sanctioned_amount", "description"],
			ignore_permissions=True,
		)

		from_date = filters.get("from_date")
		to_date = filters.get("to_date")

		for d in details:
			parent_claim = ec_map.get(d.parent)
			if not parent_claim:
				continue

			exp_date = d.expense_date or parent_claim.posting_date
			if from_date and str(exp_date) < str(from_date):
				continue
			if to_date and str(exp_date) > str(to_date):
				continue

			exp_type = d.expense_type
			if exp_type not in agg_map:
				agg_map[exp_type] = {
					"claims": set(),
					"total_claimed": 0.0,
					"total_approved": 0.0,
				}

			agg_map[exp_type]["claims"].add(d.parent)
			agg_map[exp_type]["total_claimed"] += flt(d.amount)
			agg_map[exp_type]["total_approved"] += flt(d.sanctioned_amount)

	# Determine default currency
	currency = None
	if filters.get("company"):
		currency = frappe.get_cached_value("Company", filters.get("company"), "default_currency")
	if not currency:
		currency = frappe.db.get_default("currency") or "INR"

	data = []
	for ct in claim_types:
		ct_name = ct.name
		agg = agg_map.get(ct_name)

		no_of_claims = len(agg["claims"]) if agg else 0
		total_claimed = flt(agg["total_claimed"] if agg else 0.0)
		total_approved = flt(agg["total_approved"] if agg else 0.0)
		total_rejected = max(0.0, total_claimed - total_approved)

		is_disabled = bool(ct.get("disabled")) if has_disabled_field else False
		status = "Disabled" if is_disabled else "Active"

		data.append({
			"expense_claim_type": ct_name,
			"expense_claim_type_id": ct_name,
			"description": ct.get("description") or "",
			"no_of_claims": no_of_claims,
			"total_claimed_amount": total_claimed,
			"total_approved_amount": total_approved,
			"total_rejected_amount": total_rejected,
			"status": status,
			"action": _("View Expense Claims"),
			"currency": currency,
		})

	return data


