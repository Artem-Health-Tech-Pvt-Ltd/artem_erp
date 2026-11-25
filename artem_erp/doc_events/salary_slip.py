import frappe
from frappe import _
from frappe.utils import flt, rounded
from hrms.payroll.doctype.payroll_entry.payroll_entry import get_salary_withholdings

from artem_erp.override.salary_slip import update_additional_salary_payment_history


def validate(doc, method=None):
	process_percentage_salary_withholding(doc)


def on_submit(doc, method=None):
	update_additional_salary_payment_history(doc, cancel=False)
	update_salary_withholding_cycle_record(doc, cancel=False)
	if doc.get("custom_is_partially_withheld"):
		frappe.db.set_value("Salary Slip", doc.name, "status", "Submitted")


def before_cancel(doc, method=None):
	doc.flags.ignore_links = True
	doc.ignore_linked_doctypes = (
		"Salary Withholding",
		"Salary Withholding Cycle",
		"Full and Final Statement",
		"Full and Final Outstanding Statement",
	)

	# 1. Automatically cancel linked Full and Final Statement (FNF) if one exists
	_cancel_linked_fnf_for_salary_slip(doc)

	# 2. Remove the cancelled Salary Slip from Salary Withholding document's cycles
	_unlink_salary_slip_from_withholding(doc)


def on_cancel(doc, method=None):
	doc.flags.ignore_links = True
	update_additional_salary_payment_history(doc, cancel=True)
	_unlink_salary_slip_from_withholding(doc)


def _cancel_linked_fnf_for_salary_slip(doc):
	"""
	Automatically cancels any submitted Full and Final Statement (FNF) referencing
	this Salary Slip, without requiring manual user cancellation.
	"""
	if frappe.flags.get("in_salary_slip_cancel"):
		return

	# frappe.flags.in_salary_slip_cancel = True
	# try:
	fnf_names = set()
	# 1. From Full and Final Outstanding Statement child table
	linked_fnf_rows = frappe.db.get_all(
		"Full and Final Outstanding Statement",
		filters={
			"reference_document_type": "Salary Slip",
			"reference_document": doc.name,
		},
		fields=["parent"],
	)
	for row in linked_fnf_rows:
		if frappe.db.get_value("Full and Final Statement", row.parent, "docstatus") == 1:
			fnf_names.add(row.parent)
	# 2. From Salary Withholding Cycle
	cycle_fnf = frappe.db.get_all(
		"Salary Withholding Cycle",
		filters={"custom_salary_slip": doc.name},
		pluck="custom_fnf_reference",
	)
	for fnf in cycle_fnf:
		if fnf and frappe.db.get_value("Full and Final Statement", fnf, "docstatus") == 1:
			fnf_names.add(fnf)
	for fnf_name in fnf_names:
		_cancel_linked_fnf_journal_entries(fnf_name)
		fnf_doc = frappe.get_doc("Full and Final Statement", fnf_name)
		if fnf_doc.docstatus == 1:
			fnf_doc.flags.ignore_links = True
			fnf_doc.ignore_linked_doctypes = (
				"Salary Withholding",
				"Salary Withholding Cycle",
				"Salary Slip",
				"GL Entry",
				"Journal Entry",
				"Full and Final Outstanding Statement",
			)
			fnf_doc.cancel()
	# finally:
	# 	frappe.flags.in_salary_slip_cancel = False


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


def _unlink_salary_slip_from_withholding(doc):
	"""
	Removes the cancelled Salary Slip from Salary Withholding Cycle(s)
	while ensuring the parent Salary Withholding remains valid,
	its other cycles are unaffected, and it is not deleted.
	"""
	cycle_pairs = set()

	cycle_rows = frappe.db.get_all(
		"Salary Withholding Cycle",
		filters={"custom_salary_slip": doc.name},
		fields=["name", "parent"],
	)
	for r in cycle_rows:
		cycle_pairs.add((r.name, r.parent))

	c_name = doc.salary_withholding_cycle or doc.get("custom_salary_withholding_cycle")
	p_name = doc.salary_withholding or doc.get("custom_salary_withholding")
	if c_name:
		cycle_pairs.add((c_name, p_name))

	parents_to_update = set()

	for cycle_name, parent_name in cycle_pairs:
		if cycle_name and frappe.db.exists("Salary Withholding Cycle", cycle_name):
			frappe.db.set_value(
				"Salary Withholding Cycle",
				cycle_name,
				{
					"custom_salary_slip": None,
					"custom_held_amount": 0.0,
					"custom_disbursed_amount": 0.0,
					"is_salary_released": 0,
					"journal_entry": None,
					"custom_fnf_reference": None,
				},
			)
			parent = parent_name or frappe.db.get_value("Salary Withholding Cycle", cycle_name, "parent")
			if parent:
				parents_to_update.add(parent)

	for parent_name in parents_to_update:
		if frappe.db.exists("Salary Withholding", parent_name):
			total_held = (
				frappe.db.sql(
					"SELECT SUM(custom_held_amount) FROM `tabSalary Withholding Cycle` WHERE parent = %s",
					parent_name,
				)[0][0]
				or 0.0
			)
			frappe.db.set_value(
				"Salary Withholding", parent_name, "custom_total_accumulated_amount", flt(total_held)
			)
			parent_doc = frappe.get_doc("Salary Withholding", parent_name)
			parent_doc.set_status(update=True)

	# Clear link fields on this Salary Slip
	doc.salary_withholding = None
	doc.salary_withholding_cycle = None
	doc.custom_salary_withholding = None
	doc.custom_salary_withholding_cycle = None
	frappe.db.set_value(
		"Salary Slip",
		doc.name,
		{
			"salary_withholding": None,
			"salary_withholding_cycle": None,
			"custom_salary_withholding": None,
			"custom_salary_withholding_cycle": None,
		},
	)


def process_percentage_salary_withholding(doc):
	"""
	Intercepts standard binary salary withholding when Salary Withholding is configured
	in 'Percentage' mode. Applies a deduction component for the withheld percentage
	and prevents Salary Slip status from becoming 'Withheld', allowing the remaining
	disbursed salary to be paid via normal Payroll Entry bank transfer.
	"""

	wh_name = doc.salary_withholding or doc.get("custom_salary_withholding")
	wh_cycle = doc.salary_withholding_cycle or doc.get("custom_salary_withholding_cycle")

	if not wh_name and doc.start_date and doc.end_date and doc.employee:
		withholdings = get_salary_withholdings(doc.start_date, doc.end_date, doc.employee)
		if withholdings:
			wh_name = withholdings[0].salary_withholding
			wh_cycle = withholdings[0].salary_withholding_cycle

	if not wh_name or not frappe.db.exists("Salary Withholding", wh_name):
		# No withholding applicable; reset custom partial flags if previously set
		if doc.get("custom_is_partially_withheld"):
			_reset_partial_withholding_fields(doc)
		return

	wh_doc = frappe.get_cached_doc("Salary Withholding", wh_name)
	if wh_doc.get("custom_withholding_mode") != "Percentage":
		# Standard 100% withholding mode; let standard HRMS handle it
		if doc.get("custom_is_partially_withheld"):
			_reset_partial_withholding_fields(doc)
		return

	percentage = flt(wh_doc.get("custom_withholding_percentage", 0))
	if percentage <= 0:
		return

	# 1. Maintain link references in both standard and custom fields so standard connections work
	doc.custom_salary_withholding = wh_name
	doc.custom_salary_withholding_cycle = wh_cycle
	doc.salary_withholding = wh_name
	doc.salary_withholding_cycle = wh_cycle

	# Ensure slip status is not 'Withheld'
	if doc.docstatus == 0:
		doc.status = "Draft"
	elif doc.docstatus == 1:
		doc.status = "Submitted"

	# 2. Determine base amount and calculate withheld amount
	calc_base = wh_doc.get("custom_calculation_base") or "Gross Pay"
	comp_name = wh_doc.get("custom_withholding_component") or "Salary Withholding"

	if calc_base == "Net Pay":
		other_deductions = sum(
			flt(d.amount)
			for d in (doc.deductions or [])
			if d.salary_component != comp_name and not d.do_not_include_in_total
		)
		total_loan = flt(doc.get("total_loan_repayment", 0))
		net_before_hold = flt(doc.gross_pay) - other_deductions - total_loan
		hold_amount = net_before_hold * (percentage / 100.0)
	else:
		# Gross Pay
		hold_amount = flt(doc.gross_pay) * (percentage / 100.0)

	precision = doc.precision("net_pay") or 2
	hold_amount = flt(hold_amount, precision)

	# 3. Ensure component exists
	if not frappe.db.exists("Salary Component", comp_name):
		frappe.error_log(f"Salary Component '{comp_name}' does not exist. Creating it now.")

	# 4. Remove existing deduction row for this component (if any) to prevent duplication
	doc.deductions = [d for d in (doc.deductions or []) if d.salary_component != comp_name]

	# 5. Add deduction row for withheld portion
	if hold_amount > 0:
		doc.append(
			"deductions",
			{
				"salary_component": comp_name,
				"amount": hold_amount,
				"do_not_include_in_total": 0,
			},
		)

	# 6. Set custom fields
	doc.custom_is_partially_withheld = 1
	doc.custom_withheld_percentage = percentage
	doc.custom_withheld_amount = hold_amount

	# 7. Recalculate totals
	total_loan = flt(doc.get("total_loan_repayment", 0))
	doc.total_deduction = sum(flt(d.amount) for d in doc.deductions if not d.do_not_include_in_total)
	doc.net_pay = flt(doc.gross_pay) - (flt(doc.total_deduction) + total_loan)
	is_rounding_disabled = (
		doc.is_rounding_total_disabled() if hasattr(doc, "is_rounding_total_disabled") else False
	)
	doc.rounded_total = doc.net_pay if is_rounding_disabled else rounded(doc.net_pay)
	if hasattr(doc, "set_net_total_in_words"):
		doc.set_net_total_in_words()


def update_salary_withholding_cycle_record(doc, cancel=False):
	"""
	Updates the corresponding Salary Withholding Cycle with the held amount
	and salary slip link on submit/cancel.
	When a salary slip is submitted, the salary is withheld (pending release);
	hence custom_disbursed_amount is 0.0 and is_salary_released is 0.
	"""
	cycle_name = doc.get("custom_salary_withholding_cycle")
	if not cycle_name or not frappe.db.exists("Salary Withholding Cycle", cycle_name):
		return

	held_amt = 0.0 if cancel else flt(doc.get("custom_withheld_amount", 0))
	slip_name = None if cancel else doc.name

	frappe.db.set_value(
		"Salary Withholding Cycle",
		cycle_name,
		{
			"custom_held_amount": held_amt,
			"custom_disbursed_amount": 0.0,
			"is_salary_released": 0,
			"journal_entry": None,
			"custom_salary_slip": slip_name,
		},
	)

	# Update total accumulated amount on parent Salary Withholding
	parent_wh = doc.get("custom_salary_withholding") or frappe.db.get_value(
		"Salary Withholding Cycle", cycle_name, "parent"
	)
	if parent_wh and frappe.db.exists("Salary Withholding", parent_wh):
		total_held = (
			frappe.db.sql(
				"SELECT SUM(custom_held_amount) FROM `tabSalary Withholding Cycle` WHERE parent = %s",
				parent_wh,
			)[0][0]
			or 0.0
		)
		frappe.db.set_value(
			"Salary Withholding", parent_wh, "custom_total_accumulated_amount", flt(total_held)
		)


def _reset_partial_withholding_fields(doc):
	doc.custom_is_partially_withheld = 0
	doc.custom_withheld_percentage = 0
	doc.custom_withheld_amount = 0
	doc.custom_salary_withholding = None
	doc.custom_salary_withholding_cycle = None
