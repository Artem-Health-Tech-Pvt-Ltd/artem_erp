from typing import Any

import frappe
from frappe import _
from frappe.utils import flt


def validate(doc, method=None):
	sync_withheld_salary_slip_rows(doc)
	fetch_partial_salary_withholdings(doc)


@frappe.whitelist()
def custom_get_account_and_amount(ref_doctype: str, ref_document: str, company: str) -> list | None:
	if not ref_doctype or not ref_document:
		return None

	frappe.has_permission(ref_doctype, "read", ref_document, throw=True)

	if ref_doctype == "Salary Slip":
		slip = frappe.db.get_value(
			"Salary Slip",
			ref_document,
			[
				"payroll_entry",
				"net_pay",
				"salary_withholding",
				"custom_salary_withholding",
				"salary_withholding_cycle",
				"custom_salary_withholding_cycle",
				"custom_is_partially_withheld",
				"custom_withheld_amount",
				"status",
			],
			as_dict=True,
		)
		if not slip:
			return None

		wh_name = slip.get("salary_withholding") or slip.get("custom_salary_withholding")
		cycle_name = slip.get("salary_withholding_cycle") or slip.get("custom_salary_withholding_cycle")

		is_partial = bool(
			slip.get("custom_is_partially_withheld") or flt(slip.get("custom_withheld_amount")) > 0
		)
		held_amount = flt(slip.get("custom_withheld_amount"))

		if not is_partial and cycle_name:
			cycle_held = frappe.db.get_value("Salary Withholding Cycle", cycle_name, "custom_held_amount")
			if flt(cycle_held) > 0:
				is_partial = True
				held_amount = flt(cycle_held)

		if not is_partial:
			cycle_data = frappe.db.get_value(
				"Salary Withholding Cycle",
				{"custom_salary_slip": ref_document},
				["parent", "custom_held_amount"],
				as_dict=True,
			)
			if cycle_data and flt(cycle_data.custom_held_amount) > 0:
				is_partial = True
				held_amount = flt(cycle_data.custom_held_amount)
				if not wh_name:
					wh_name = cycle_data.parent

		if is_partial and wh_name:
			holdback_account = _get_holdback_account(wh_name, company)
			if held_amount > 0 and holdback_account:
				return [holdback_account, held_amount]

		payable_account = (
			frappe.db.get_value("Payroll Entry", slip.payroll_entry, "payroll_payable_account")
			if slip.payroll_entry
			else None
		)
		return [payable_account, slip.net_pay]

	from hrms.hr.doctype.full_and_final_statement.full_and_final_statement import (
		get_account_and_amount as std_get_account_and_amount,
	)

	return std_get_account_and_amount(ref_doctype, ref_document, company)


def sync_withheld_salary_slip_rows(doc):
	"""
	Ensures any Salary Slip added to Payables that has a withheld salary portion
	uses the correct held amount and holdback account, has paid_via_salary_slip = 0,
	and component = 'Salary Withholding Release'.
	"""
	modified = False
	for row in doc.get("payables", []):
		if row.reference_document_type == "Salary Slip" and row.reference_document:
			slip = frappe.db.get_value(
				"Salary Slip",
				row.reference_document,
				[
					"custom_is_partially_withheld",
					"custom_withheld_amount",
					"custom_salary_withholding",
					"salary_withholding",
					"custom_salary_withholding_cycle",
					"salary_withholding_cycle",
					"net_pay",
				],
				as_dict=True,
			)
			if not slip:
				continue

			wh_name = slip.get("custom_salary_withholding") or slip.get("salary_withholding")
			cycle_name = slip.get("custom_salary_withholding_cycle") or slip.get("salary_withholding_cycle")
			is_partial = bool(
				slip.get("custom_is_partially_withheld") or flt(slip.get("custom_withheld_amount")) > 0
			)
			held_amount = flt(slip.get("custom_withheld_amount"))

			if not is_partial and cycle_name:
				cycle_held = frappe.db.get_value("Salary Withholding Cycle", cycle_name, "custom_held_amount")
				if flt(cycle_held) > 0:
					is_partial = True
					held_amount = flt(cycle_held)

			if not is_partial:
				cycle_data = frappe.db.get_value(
					"Salary Withholding Cycle",
					{"custom_salary_slip": row.reference_document},
					["parent", "custom_held_amount"],
					as_dict=True,
				)
				if cycle_data and flt(cycle_data.custom_held_amount) > 0:
					is_partial = True
					held_amount = flt(cycle_data.custom_held_amount)
					if not wh_name:
						wh_name = cycle_data.parent

			if is_partial and held_amount > 0:
				if row.component in ("Salary Slip", None, ""):
					row.component = "Salary Withholding Release"
					modified = True
				if flt(row.amount) != flt(held_amount):
					row.amount = held_amount
					modified = True
				if row.paid_via_salary_slip != 0:
					row.paid_via_salary_slip = 0
					modified = True
				if wh_name:
					holdback_acc = _get_holdback_account(wh_name, getattr(doc, "company", None))
					if holdback_acc and row.account != holdback_acc:
						row.account = holdback_acc
						modified = True

	if modified:
		if hasattr(doc, "set_totals"):
			doc.set_totals()
		else:
			total_payable = sum(flt(r.amount) for r in doc.payables)
			doc.total_payable_amount = flt(total_payable, doc.precision("total_payable_amount") or 2)


@frappe.whitelist()
def get_partial_withholding_rows(employee: str, company: str | None = None):
	"""
	Returns a list of dicts for unreleased percentage-based Salary Withholding Cycles
	ready to be appended to the Payables table on the client side or server side.
	"""
	if not employee:
		return []

	Cycle = frappe.qb.DocType("Salary Withholding Cycle")
	Withholding = frappe.qb.DocType("Salary Withholding")

	cycles = (
		frappe.qb.from_(Cycle)
		.inner_join(Withholding)
		.on(Cycle.parent == Withholding.name)
		.select(
			Cycle.name.as_("cycle_name"),
			Cycle.parent.as_("withholding_parent"),
			Cycle.from_date,
			Cycle.to_date,
			Cycle.custom_held_amount,
			Cycle.custom_salary_slip,
		)
		.where(
			(Withholding.employee == employee)
			& (Withholding.docstatus == 1)
			& (Cycle.is_salary_released == 0)
			& (Cycle.custom_held_amount > 0)
		)
		.orderby(Cycle.from_date)
	).run(as_dict=True)

	rows = []
	for cycle in cycles:
		holdback_account = _get_holdback_account(cycle.withholding_parent, company)
		ref_doc = cycle.custom_salary_slip or cycle.cycle_name
		rows.append(
			{
				"status": "Unsettled",
				"component": "Salary Withholding Release",
				"reference_document_type": "Salary Slip"
				if cycle.custom_salary_slip
				else "Salary Withholding",
				"reference_document": ref_doc,
				"account": holdback_account,
				"amount": flt(cycle.custom_held_amount),
				"paid_via_salary_slip": 0,  # CRUCIAL: 0 allows create_journal_entry() to debit this account
				"remark": _("Release of withheld salary for period {0} to {1}").format(
					cycle.from_date, cycle.to_date
				),
			}
		)

	return rows


@frappe.whitelist()
def fetch_partial_salary_withholdings(doc: Any, method: str | None = None):
	"""
	Automatically finds unreleased percentage-based Salary Withholding Cycles
	for the exiting employee and appends them to the Full and Final Statement
	Payables table with paid_via_salary_slip = 0 so they are settled in the F&F Journal Entry.
	"""
	if isinstance(doc, str):
		doc = frappe.get_doc(frappe.parse_json(doc))

	if not getattr(doc, "employee", None):
		return []

	rows = get_partial_withholding_rows(doc.employee, getattr(doc, "company", None))
	existing_refs = set(d.reference_document for d in doc.get("payables", []) if d.reference_document)

	modified = False
	added_rows = []
	for row in rows:
		if row["reference_document"] in existing_refs:
			continue

		doc.append("payables", row)
		existing_refs.add(row["reference_document"])
		added_rows.append(row)
		modified = True

	if modified:
		if hasattr(doc, "set_totals"):
			doc.set_totals()
		else:
			total_payable = sum(flt(r.amount) for r in doc.payables)
			doc.total_payable_amount = flt(total_payable, doc.precision("total_payable_amount") or 2)
			total_receivable = sum(flt(r.amount) for r in (doc.receivables or [])) + flt(
				getattr(doc, "total_asset_recovery_cost", 0)
			)
			doc.total_receivable_amount = flt(total_receivable, doc.precision("total_receivable_amount") or 2)

	return added_rows


def on_submit(doc, method=None):
	"""
	Links the submitted Full and Final Statement to the relevant Salary Withholding Cycles
	and updates Payroll Employee Detail is_salary_withheld to 0 so the Payroll Entry
	does not show 'Release Withheld Salaries'.
	"""
	for row in doc.get("payables", []):
		if row.component == "Salary Withholding Release" and row.reference_document:
			_set_fnf_reference_on_cycle(row.reference_document, doc.name)

	_update_payroll_entries_withholding_status(doc, is_released=1)


def before_cancel(doc, method=None):
	doc.flags.ignore_links = True
	doc.ignore_linked_doctypes = (
		"Salary Withholding",
		"Salary Withholding Cycle",
		"Salary Slip",
		"GL Entry",
		"Journal Entry",
		"Full and Final Outstanding Statement",
	)

	# 1. Cancel linked Journal Entries if any exist
	_cancel_linked_fnf_journal_entries(doc.name)

	# 2. Remove cancelled FNF reference from Salary Withholding Cycle(s)
	_unlink_fnf_from_withholding_cycles(doc)

	# 3. Preserve Salary Slips (do not cancel them), but revert payroll entry is_salary_withheld status
	_update_payroll_entries_withholding_status(doc, is_released=0)


def on_cancel(doc, method=None):
	doc.flags.ignore_links = True
	"""
	Clears the F&F reference and ensures cycles remain unreleased if F&F is cancelled.
	"""
	for row in doc.get("payables", []):
		if row.component == "Salary Withholding Release" and row.reference_document:
			_set_fnf_reference_on_cycle(row.reference_document, None, is_released=0)

	_unlink_fnf_from_withholding_cycles(doc)
	_update_payroll_entries_withholding_status(doc, is_released=0)


def _unlink_fnf_from_withholding_cycles(doc):
	"""
	Removes the cancelled FNF reference from Salary Withholding Cycle child table
	and resets release status without deleting Salary Withholding or Salary Slips.
	"""
	cycles = frappe.db.get_all(
		"Salary Withholding Cycle",
		filters={"custom_fnf_reference": doc.name},
		fields=["name", "parent"],
	)
	parents_to_update = set()

	for c in cycles:
		frappe.db.set_value(
			"Salary Withholding Cycle",
			c.name,
			{
				"custom_fnf_reference": None,
				"is_salary_released": 0,
				"journal_entry": None,
			},
		)
		if c.parent:
			parents_to_update.add(c.parent)

	for parent_name in parents_to_update:
		if frappe.db.exists("Salary Withholding", parent_name):
			parent_doc = frappe.get_doc("Salary Withholding", parent_name)
			parent_doc.set_status(update=True)


def _cancel_linked_fnf_journal_entries(fnf_name):
	je_names = frappe.db.get_all(
		"Journal Entry Account",
		filters={"reference_type": "Full and Final Statement", "reference_name": fnf_name, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)
	for je_name in je_names:
		je_doc = frappe.get_doc("Journal Entry", je_name)
		if je_doc.docstatus == 1:
			je_doc.flags.ignore_links = True
			je_doc.cancel()


def on_journal_entry_status_change(doc, method=None):
	"""
	Listens to Journal Entry submission and cancellation.
	- When released from FNF: releases withholding cycles, updates payroll employee withholding flags,
	  and links Journal Entry to Payroll Entries in connections.
	- When released from Payroll Entry (via 'Release Withheld Salaries' Bank Entry): releases withholding cycles,
	  updates payroll employee withholding flags, and settles the corresponding Salary Slip / Withholding
	  rows in Full and Final Statement (FNF) child table (payables).

	NOTE: Accrual Journal Entries (voucher_type == 'Journal Entry') MUST NOT release salaries.
	Salaries are only released via Bank Entry or Cash Entry payments.
	"""
	if doc.voucher_type not in ("Bank Entry", "Cash Entry"):
		return

	is_released = 1 if (method == "on_submit" and doc.docstatus == 1) else 0

	# 1. Handle F&F Journal Entries
	for entry in doc.get("accounts", []):
		if entry.reference_type == "Full and Final Statement" and entry.reference_name:
			fnf_name = entry.reference_name
			jv_link = doc.name if is_released else None

			linked_cycles = frappe.get_all(
				"Salary Withholding Cycle",
				filters={"custom_fnf_reference": fnf_name},
				fields=["name", "parent", "custom_salary_slip", "custom_held_amount"],
			)

			for c in linked_cycles:
				frappe.db.set_value(
					"Salary Withholding Cycle",
					c.name,
					{
						"is_salary_released": is_released,
						"custom_disbursed_amount": flt(c.custom_held_amount) if is_released else 0.0,
						"journal_entry": jv_link,
					},
				)
				parent_doc = frappe.get_doc("Salary Withholding", c.parent)
				parent_doc.set_status(update=True)

			if frappe.db.exists("Full and Final Statement", fnf_name):
				fnf_doc = frappe.get_doc("Full and Final Statement", fnf_name)
				_update_payroll_entries_withholding_status(fnf_doc, is_released=is_released)

				if is_released:
					_link_journal_entry_to_payroll_entries(doc, fnf_doc)

	# 2. Handle Payroll Entry / Withholding Cycle Bank Entries
	# ONLY process cycles explicitly linked to this Bank Entry (e.g. via 'Release Withheld Salaries')
	cycles_linked_to_jv = frappe.get_all(
		"Salary Withholding Cycle",
		filters={"journal_entry": doc.name, "docstatus": 1},
		fields=["name", "parent", "from_date", "to_date", "custom_salary_slip", "custom_held_amount"],
	)

	for cycle in cycles_linked_to_jv:
		parent_wh = frappe.db.get_value(
			"Salary Withholding", cycle.parent, ["name", "employee"], as_dict=True
		)
		if not parent_wh:
			continue

		employee = parent_wh.employee

		# Update cycle release details
		cycle_updates = {
			"is_salary_released": is_released,
			"custom_disbursed_amount": flt(cycle.custom_held_amount) if is_released else 0.0,
		}
		if not is_released and method == "on_cancel":
			cycle_updates["journal_entry"] = None
			if cycle.get("custom_salary_slip"):
				frappe.db.sql(
					"""
					UPDATE `tabSalary Slip`
					SET status = 'Submitted'
					WHERE name = %s AND custom_is_partially_withheld = 1
					""",
					(cycle.get("custom_salary_slip"),),
				)
		elif is_released:
			cycle_updates["journal_entry"] = doc.name

		frappe.db.set_value("Salary Withholding Cycle", cycle.name, cycle_updates)
		parent_doc = frappe.get_doc("Salary Withholding", cycle.parent)
		parent_doc.set_status(update=True)

		# Update is_salary_withheld on Payroll Employee Detail
		_update_employee_payroll_entries_withholding(employee, is_released=is_released, cycle=cycle)

		# Settle in Full and Final Statement
		_settle_cycle_in_full_and_final(cycle, employee, is_released=is_released, jv_name=doc.name)


def _update_employee_payroll_entries_withholding(employee, is_released=1, cycle=None):
	"""
	Sets is_salary_withheld to 0 (or 1 on cancel) for this employee in any Payroll Entry
	overlapping with the cycle dates or linked to the cycle's salary slip.
	"""
	pe_set = set()
	if cycle and cycle.get("custom_salary_slip"):
		pe = frappe.db.get_value("Salary Slip", cycle.get("custom_salary_slip"), "payroll_entry")
		if pe:
			pe_set.add(pe)

	if cycle and cycle.get("from_date") and cycle.get("to_date"):
		matching_pes = frappe.db.sql(
			"""
			SELECT name FROM `tabPayroll Entry`
			WHERE start_date <= %s AND end_date >= %s
			""",
			(cycle.get("to_date"), cycle.get("from_date")),
			pluck=True,
		)
		for pe in matching_pes:
			pe_set.add(pe)

	for pe in pe_set:
		frappe.db.sql(
			"""
			UPDATE `tabPayroll Employee Detail`
			SET is_salary_withheld = %s
			WHERE parent = %s AND employee = %s
			""",
			(0 if is_released else 1, pe, employee),
		)


def _settle_cycle_in_full_and_final(cycle, employee, is_released=1, jv_name=None):
	"""
	When withheld salary is released from Payroll Entry, finds any linked Full and Final Statement (FNF)
	for the employee and automatically marks the corresponding payable row as "Settled"
	(or "Unsettled" if cancelled), so it is not double-paid.
	"""
	fnf_records = frappe.get_all(
		"Full and Final Statement",
		filters={"employee": employee, "docstatus": ["!=", 2]},
		fields=["name", "docstatus", "status"],
	)

	salary_slip = cycle.get("custom_salary_slip")
	cycle_name = cycle.get("name")

	for fnf in fnf_records:
		fnf_doc = frappe.get_doc("Full and Final Statement", fnf.name)
		row_updated = False

		for row in fnf_doc.get("payables", []):
			is_match = False
			if salary_slip and row.reference_document == salary_slip:
				is_match = True
			elif cycle_name and row.reference_document == cycle_name:
				is_match = True
			elif (
				salary_slip
				and row.reference_document_type == "Salary Slip"
				and row.reference_document == salary_slip
			):
				is_match = True

			if is_match:
				new_status = "Settled" if is_released else "Unsettled"
				paid_via_slip = 1 if is_released else 0
				remark = f"Settled via Bank Entry {jv_name}" if (is_released and jv_name) else ""

				frappe.db.set_value(
					"Full and Final Outstanding Statement",
					row.name,
					{
						"status": new_status,
						"paid_via_salary_slip": paid_via_slip,
						"remark": remark,
					},
				)
				row.status = new_status
				row.paid_via_salary_slip = paid_via_slip
				row.remark = remark
				row_updated = True

		if row_updated:
			if fnf_doc.docstatus == 1:
				all_settled = all(p.status == "Settled" for p in fnf_doc.payables) and all(
					r.status == "Settled" for r in fnf_doc.receivables
				)
				if is_released and all_settled:
					frappe.db.set_value("Full and Final Statement", fnf_doc.name, "status", "Paid")
				elif not is_released:
					frappe.db.set_value("Full and Final Statement", fnf_doc.name, "status", "Unpaid")


def _update_payroll_entries_withholding_status(fnf_doc, is_released=1):
	"""
	Updates tabPayroll Employee Detail setting is_salary_withheld to 0 (or 1 on cancel)
	for the employee in all Payroll Entries linked to the released salary slips.
	"""
	if not fnf_doc.get("employee"):
		return

	payroll_entries = set()
	for row in fnf_doc.get("payables", []):
		if row.reference_document_type == "Salary Slip" and row.reference_document:
			pe = frappe.db.get_value("Salary Slip", row.reference_document, "payroll_entry")
			if pe:
				payroll_entries.add(pe)
		elif row.component == "Salary Withholding Release" and row.reference_document:
			slip = frappe.db.get_value(
				"Salary Withholding Cycle", row.reference_document, "custom_salary_slip"
			)
			if slip:
				pe = frappe.db.get_value("Salary Slip", slip, "payroll_entry")
				if pe:
					payroll_entries.add(pe)

	# Also check cycles linked via custom_fnf_reference
	cycles = frappe.get_all(
		"Salary Withholding Cycle",
		filters={"custom_fnf_reference": fnf_doc.name},
		pluck="custom_salary_slip",
	)
	for slip in cycles:
		if slip:
			pe = frappe.db.get_value("Salary Slip", slip, "payroll_entry")
			if pe:
				payroll_entries.add(pe)

	for pe in payroll_entries:
		frappe.db.set_value(
			"Payroll Employee Detail",
			{"parent": pe, "employee": fnf_doc.employee},
			"is_salary_withheld",
			0 if is_released else 1,
		)


def _link_journal_entry_to_payroll_entries(jv_doc, fnf_doc):
	"""
	Ensures debit rows for salary payables in the F&F Journal Entry are linked to
	the respective Payroll Entry so the Bank Entry displays in the Payroll Entry dashboard.
	"""
	for acc in jv_doc.get("accounts", []):
		if flt(acc.debit_in_account_currency) > 0 and not acc.reference_name:
			for p in fnf_doc.get("payables", []):
				if (
					p.reference_document_type == "Salary Slip"
					and flt(p.amount) == flt(acc.debit_in_account_currency)
					and p.account == acc.account
				):
					pe = frappe.db.get_value("Salary Slip", p.reference_document, "payroll_entry")
					if pe:
						frappe.db.set_value(
							"Journal Entry Account",
							acc.name,
							{
								"reference_type": "Payroll Entry",
								"reference_name": pe,
								"party_type": "Employee",
								"party": fnf_doc.employee,
							},
						)
						break


def _get_holdback_account(withholding_parent, company=None):
	wh_doc = frappe.get_cached_doc("Salary Withholding", withholding_parent)
	if wh_doc.get("custom_holdback_account"):
		return wh_doc.custom_holdback_account

	comp_name = wh_doc.get("custom_withholding_component")
	if company:
		comp_acc = frappe.db.get_value(
			"Salary Component Account",
			{"parent": comp_name, "company": company},
			"account",
		)
		if comp_acc:
			return comp_acc

		return frappe.get_cached_value("Company", company, "default_payroll_payable_account")

	return None


def _set_fnf_reference_on_cycle(reference_doc, fnf_name, is_released=None):
	cycle_name = frappe.db.get_value(
		"Salary Withholding Cycle", {"custom_salary_slip": reference_doc}, "name"
	)
	if not cycle_name and frappe.db.exists("Salary Withholding Cycle", reference_doc):
		cycle_name = reference_doc

	if cycle_name:
		values = {"custom_fnf_reference": fnf_name}
		if is_released is not None:
			values["is_salary_released"] = is_released
		frappe.db.set_value("Salary Withholding Cycle", cycle_name, values)
