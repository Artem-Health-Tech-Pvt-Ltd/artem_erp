import frappe
from frappe import _
from frappe.utils import flt


def validate(doc, method=None):
	validate_percentage_withholding_fields(doc)
	calculate_total_accumulated_amount(doc)


def validate_percentage_withholding_fields(doc):
	if getattr(doc, "custom_withholding_mode", None) == "Percentage":
		percentage = flt(doc.custom_withholding_percentage)
		if percentage <= 0 or percentage > 100:
			frappe.throw(
				_("Withholding Percentage must be greater than 0% and at most 100%."),
				title=_("Invalid Withholding Percentage"),
			)

		if not getattr(doc, "custom_withholding_component", None):
			if not frappe.db.exists("Salary Component", "Salary Withholding"):
				frappe.throw(
					_(
						"Salary Component 'Salary Withholding' does not exist. Please create it first or select a different component."
					),
					title=_("Missing Salary Component"),
				)
			else:
				doc.custom_withholding_component = "Salary Withholding"

		# Ensure component exists
		ensure_salary_withholding_component_exists(doc.custom_withholding_component)

		# Auto-fetch holdback account from Salary Component Account if empty
		if doc.company and not getattr(doc, "custom_holdback_account", None):
			component_acc = frappe.db.get_value(
				"Salary Component Account",
				{"parent": doc.custom_withholding_component, "company": doc.company},
				"account",
			)
			if component_acc:
				doc.custom_holdback_account = component_acc


def before_cancel(doc, method=None):
	doc.flags.ignore_links = True
	doc.ignore_linked_doctypes = (
		"Salary Slip",
		"Salary Withholding Cycle",
		"Full and Final Statement",
		"Full and Final Outstanding Statement",
		"Payroll Entry",
	)


def on_submit(doc, method=None):
	sync_payroll_entries_for_withholding(doc)


def on_update(doc, method=None):
	if doc.docstatus == 1:
		sync_payroll_entries_for_withholding(doc)


def on_cancel(doc, method=None):
	doc.flags.ignore_links = True
	sync_payroll_entries_for_withholding(doc, is_cancelled=True)


def sync_payroll_entries_for_withholding(doc, is_cancelled=False):
	"""
	Automatically updates is_salary_withheld on any existing Payroll Entry records
	that overlap with the cycles in this Salary Withholding document.
	"""
	if isinstance(doc, str):
		doc = frappe.get_doc("Salary Withholding", doc)

	if not doc.employee:
		return

	for cycle in doc.get("cycles") or []:
		from_date = cycle.from_date
		to_date = cycle.to_date
		if not from_date or not to_date:
			continue

		is_withheld = 0 if (is_cancelled or cycle.is_salary_released or doc.docstatus != 1) else 1

		payroll_entries = frappe.db.sql(
			"""
			SELECT name FROM `tabPayroll Entry`
			WHERE start_date <= %s AND end_date >= %s
			""",
			(to_date, from_date),
			pluck=True,
		)

		if payroll_entries:
			frappe.db.sql(
				"""
				UPDATE `tabPayroll Employee Detail`
				SET is_salary_withheld = %s
				WHERE employee = %s AND parent IN %s
				""",
				(is_withheld, doc.employee, tuple(payroll_entries)),
			)


def calculate_total_accumulated_amount(doc):
	total_held = sum(flt(cycle.get("custom_held_amount", 0)) for cycle in (doc.get("cycles") or []))
	doc.custom_total_accumulated_amount = flt(
		total_held, doc.precision("custom_total_accumulated_amount") or 2
	)


def ensure_salary_withholding_component_exists(component_name="Salary Withholding"):
	if not frappe.db.exists("Salary Component", component_name):
		try:
			comp = frappe.new_doc("Salary Component")
			comp.salary_component = component_name
			comp.salary_component_abbr = "SWH"
			comp.type = "Deduction"
			comp.description = _("Withheld salary retention for employee notice period / separation.")
			comp.is_tax_applicable = 0
			comp.do_not_include_in_total = 0
			comp.flags.ignore_permissions = True
			comp.flags.ignore_mandatory = True
			comp.save()
		except Exception:
			pass
