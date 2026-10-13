# Copyright (c) 2026, Artem HealthTech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form, getdate, has_common, nowdate
from frappe.utils.formatters import fmt_money
from frappe.utils.jinja import render_template
from hrms.payroll.doctype.salary_structure.salary_structure import _make_salary_slip


class SalaryBreakupReport:
	def __init__(self, employee, salary_structure_assignment):
		self.employee = employee
		self.salary_structure_assignment = salary_structure_assignment

		self.salary_structure, self.currency, self.assignment_date, self.income_tax_slab, self.ctc = (
			frappe.get_value(
				"Salary Structure Assignment",
				{"name": salary_structure_assignment, "employee": employee},
				["salary_structure", "currency", "from_date", "income_tax_slab", "ctc"],
			)
		)
		self.base_ctc = flt(self.ctc)
		self.validate_ctc()
		self.salary_slip = _make_salary_slip(
			self.salary_structure,
			employee=self.employee,
			for_preview=1,
			as_print=False,
			posting_date=frappe.flags.posting_date if frappe.flags.in_test else None,
			ignore_permissions=True,
		)
		self.net_pay = self.salary_slip.net_pay
		self.gross_pay = self.salary_slip.gross_pay
		self.payroll_frequency = self.salary_slip.payroll_frequency
		self.cycle_multiplier = {
			"Monthly": 12,
			"Fortnightly": 24,
			"Bimonthly": 6,
			"Weekly": 52,
			"Daily": 365,
		}.get(self.payroll_frequency)
		self.salary_components = []
		self.earning_components = []
		self.deduction_components = []
		self.tax_components = []
		self.employer_contribution_components = []
		self.total_net_earnings = []
		self.total_gross_earnings = []
		self.ctc_row = []

	def validate_ctc(self):
		if not self.ctc:
			frappe.throw(
				_("Please set cost to company(CTC) for employee {0} in the {1}").format(
					frappe.bold(self.employee),
					get_link_to_form(
						"Salary Structure Assignment",
						self.salary_structure_assignment,
						"Salary Structure Assignment",
					),
				),
				title=_("CTC Missing for Employee"),
			)

	def get_data(self):
		self.set_salary_component_details()
		self.set_employer_contribution_details()
		self.calculate_yearly_amounts_and_percent_of_ctc()
		self.indent_salary_components()
		self.separate_salary_components_by_type()
		self.set_abbr_type_and_formula()
		self.set_totals_row_for_component_types()
		self.set_net_and_gross_earning_rows()
		self.set_ctc_row()

		return (
			self.earning_components
			+ self.deduction_components
			+ self.tax_components
			+ self.employer_contribution_components
			+ self.total_net_earnings
			+ self.total_gross_earnings
			+ self.ctc_row
		)

	def get_latest_valid_additional_salary(self, salary_component: str):
		records = frappe.get_all(
			"Additional Salary",
			filters={
				"employee": self.employee,
				"salary_component": salary_component,
				"docstatus": 1,
				"disabled": 0,
			},
			fields=[
				"name",
				"salary_component",
				"amount",
				"custom_duration_of_additional_salary",
				"from_date",
				"to_date",
				"custom_date_of_joining",
				"is_recurring",
				"disabled",
				"creation",
			],
			order_by="from_date desc, creation desc",
		)

		if not records:
			return None

		ref_date = getdate(frappe.flags.posting_date) if frappe.flags.posting_date else getdate(nowdate())

		def is_valid(rec, date):
			if not date:
				return False
			start = rec.from_date or rec.custom_date_of_joining
			if start and getdate(start) > getdate(date):
				return False
			if rec.to_date and getdate(rec.to_date) < getdate(date):
				return False
			return True

		# First check against ref_date (posting_date / today)
		for rec in records:
			if is_valid(rec, ref_date):
				return rec

		# If not valid for today, check against assignment_date
		if self.assignment_date and getdate(self.assignment_date) != ref_date:
			assignment_date = getdate(self.assignment_date)
			for rec in records:
				if is_valid(rec, assignment_date):
					return rec

		return None

	def set_salary_component_details(self):
		salary_component_details = frappe.db.get_all(
			"Salary Detail",
			filters={"parent": self.salary_structure},
			fields=["salary_component", "amount_based_on_formula", "formula", "parentfield", "abbr"],
		)

		self.salary_components = [
			{
				"salary_component": component.salary_component,
				"per_cycle": component.amount,
				"abbr": component.abbr,
				"is_tax_component": component.variable_based_on_taxable_salary,
				"component_type": component.parentfield,
			}
			for component in self.salary_slip.earnings + self.salary_slip.deductions
		]

		for component in self.salary_components:
			component_details = next(
				(
					detail
					for detail in salary_component_details
					if component.get("salary_component") == detail.salary_component
				),
				{},
			)
			component.update(component_details)

		# Handle Additional Salary components defined in Salary Structure
		for detail in salary_component_details:
			rec = self.get_latest_valid_additional_salary(detail.salary_component)
			if not rec:
				continue

			matching_comp = next(
				(c for c in self.salary_components if c.get("salary_component") == detail.salary_component),
				None,
			)
			if matching_comp:
				matching_comp["is_additional_salary"] = True
				matching_comp["additional_salary_doc"] = rec
				matching_comp["per_cycle"] = None
			else:
				self.salary_components.append(
					{
						"salary_component": detail.salary_component,
						"per_cycle": None,
						"abbr": detail.abbr
						or frappe.get_cached_value(
							"Salary Component", detail.salary_component, "salary_component_abbr"
						),
						"is_tax_component": 0,
						"component_type": detail.parentfield or "earnings",
						"amount_based_on_formula": detail.amount_based_on_formula,
						"formula": detail.formula,
						"is_additional_salary": True,
						"additional_salary_doc": rec,
					}
				)

		# Also ensure any additional salary component pulled into salary_slip is marked
		for component in self.salary_components:
			if not component.get("is_additional_salary"):
				rec = self.get_latest_valid_additional_salary(component.get("salary_component"))
				if rec:
					component["is_additional_salary"] = True
					component["additional_salary_doc"] = rec
					component["per_cycle"] = None

	def set_employer_contribution_details(self):
		evaluated_components = getattr(self.salary_slip, "_evaluated_components", None)
		if evaluated_components is None:
			evaluated_components = frappe.get_cached_doc(
				"Salary Structure Assignment", self.salary_structure_assignment
			).get_evaluated_components()

		self.salary_components += [
			{
				"salary_component": component.salary_component,
				"per_cycle": flt(component.default_amount),
				"abbr": component.abbr,
				"amount_based_on_formula": component.amount_based_on_formula,
				"formula": component.formula,
				"component_type": "employer_contributions",
			}
			for component in evaluated_components["employer_contributions"]
			if not component.statistical_component
		]

	def calculate_yearly_amounts_and_percent_of_ctc(self):
		duration_multiplier_map = {
			"quarterly": 4,
			"half yearly": 2,
			"yearly": 1,
		}
		for component in self.salary_components:
			if component.get("is_additional_salary"):
				rec = component.get("additional_salary_doc")
				duration = (rec.get("custom_duration_of_additional_salary") or "").strip().lower()
				multiplier = duration_multiplier_map.get(duration, 1)
				annual_amount = flt(rec.get("amount")) * multiplier
				component["annual"] = flt(annual_amount, 2)
			else:
				annual_amount = flt(component.get("per_cycle", 0)) * self.cycle_multiplier
				component["annual"] = flt(annual_amount, 2)

		additional_salary_total = sum(
			flt(c.get("annual") or 0) for c in self.salary_components if c.get("is_additional_salary")
		)
		self.ctc = flt(self.base_ctc) + additional_salary_total

		for component in self.salary_components:
			component["percent_of_ctc"] = self.calculate_percent_of_ctc(component.get("annual", 0))

	def separate_salary_components_by_type(self):
		self.earning_components = [
			component for component in self.salary_components if component.get("component_type") == "earnings"
		]
		self.deduction_components = [
			component
			for component in self.salary_components
			if component.get("component_type") == "deductions" and not component.get("is_tax_component")
		]
		self.tax_components = [
			component for component in self.salary_components if component.get("is_tax_component")
		]
		self.employer_contribution_components = [
			component
			for component in self.salary_components
			if component.get("component_type") == "employer_contributions"
		]

	def set_abbr_type_and_formula(self):
		for component in (
			self.earning_components + self.deduction_components + self.employer_contribution_components
		):
			component["salary_component"] = f"{component.get('salary_component')} ({component.get('abbr')})"
			if component.get("is_additional_salary"):
				component["type"] = "Fixed"
				rec = component.get("additional_salary_doc")
				component["formula"] = rec.get("amount") if rec else "-"
			else:
				component["type"] = "Formula" if component.get("amount_based_on_formula") else "Fixed"
				component["formula"] = (
					component.get("formula") or "-"
					if component.get("amount_based_on_formula")
					else component.get("per_cycle") or "-"
				)

	def set_totals_row_for_component_types(self):
		def calculate_total(period, components):
			total = 0
			for component in components:
				total += flt(component.get(period) or 0)
			return total

		def set_totals_row(component_type):
			components = {
				"Earnings": self.earning_components,
				"Deductions": self.deduction_components,
				"Tax Deductions": self.tax_components,
				"Employer Contributions": self.employer_contribution_components,
			}.get(component_type)
			totals_row = {
				"salary_component": component_type,
				"type": "",
				"formula": "",
				"bold": True,
				"per_cycle": calculate_total("per_cycle", components),
				"annual": calculate_total("annual", components),
				"percent_of_ctc": self.calculate_percent_of_ctc(calculate_total("annual", components)),
			}
			components.insert(0, totals_row)

		for component_type in ("Earnings", "Deductions", "Tax Deductions", "Employer Contributions"):
			set_totals_row(component_type)

	def set_net_and_gross_earning_rows(self):
		has_additional_salary = any(c.get("is_additional_salary") for c in self.salary_components)
		if has_additional_salary:
			earning_rows = [c for c in self.earning_components if not c.get("bold")]
			deduction_rows = [c for c in self.deduction_components if not c.get("bold")]
			tax_rows = [c for c in self.tax_components if not c.get("bold")]

			self.gross_pay = sum(flt(c.get("per_cycle") or 0) for c in earning_rows)
			total_deductions = sum(flt(c.get("per_cycle") or 0) for c in deduction_rows + tax_rows)
			self.net_pay = self.gross_pay - total_deductions

			total_gross_annual = sum(flt(c.get("annual") or 0) for c in earning_rows)
			total_deductions_annual = sum(flt(c.get("annual") or 0) for c in deduction_rows + tax_rows)
			total_net_annual = total_gross_annual - total_deductions_annual
		else:
			total_gross_annual = self.gross_pay * self.cycle_multiplier
			total_net_annual = self.net_pay * self.cycle_multiplier

		self.total_net_earnings = [
			{
				"salary_component": "Total Net Earnings",
				"type": "",
				"formula": "",
				"per_cycle": self.net_pay,
				"annual": total_net_annual,
				"percent_of_ctc": self.calculate_percent_of_ctc(total_net_annual),
				"bold": True,
			}
		]
		self.total_gross_earnings = [
			{
				"salary_component": "Total Gross Earnings",
				"type": "",
				"formula": "",
				"per_cycle": self.gross_pay,
				"annual": total_gross_annual,
				"percent_of_ctc": self.calculate_percent_of_ctc(total_gross_annual),
				"bold": True,
			}
		]

	def set_ctc_row(self):
		employer_rows = [c for c in self.employer_contribution_components if not c.get("bold")]
		employer_per_cycle = sum(flt(c.get("per_cycle") or 0) for c in employer_rows)
		employer_annual = sum(flt(c.get("annual") or 0) for c in employer_rows)

		gross_row = self.total_gross_earnings[0] if self.total_gross_earnings else {}
		gross_per_cycle = flt(gross_row.get("per_cycle") or 0)
		gross_annual = flt(gross_row.get("annual") or 0)

		ctc_per_cycle = gross_per_cycle + employer_per_cycle
		ctc_annual = gross_annual + employer_annual

		self.ctc_row = [
			{
				"salary_component": "CTC = Gross Salary + (Employer PF + ESI)",
				"type": "",
				"formula": "Gross salary + (Employer PF+ ESI)",
				"per_cycle": ctc_per_cycle,
				"annual": ctc_annual,
				"percent_of_ctc": self.calculate_percent_of_ctc(ctc_annual),
				"bold": True,
			}
		]

	def calculate_percent_of_ctc(self, amount):
		return flt(amount * 100 / self.ctc, 2) if self.ctc else 0.0

	def get_per_cycle_ctc(self):
		return flt(self.base_ctc / self.cycle_multiplier, 2) if self.cycle_multiplier else 0.0

	def indent_salary_components(self):
		for component in self.salary_components:
			component["indent"] = 1

	def format_currency(self, amount):
		return fmt_money(amount, precision=2, currency=self.currency)

	def get_columns(self) -> list[dict]:
		"""Return columns for the report.

		One field definition per column, just like a DocType field definition.
		"""
		return [
			{
				"label": _("Component"),
				"fieldname": "salary_component",
				"fieldtype": "Data",
				"width": 300,
				"fixed": 1,
			},
			{
				"label": _("Type"),
				"fieldname": "type",
				"fieldtype": "Data",
				"width": 150,
				"fixed": 1,
			},
			{
				"label": _("Formula/Amount"),
				"fieldname": "formula",
				"fieldtype": "Data",
				"width": 250,
				"fixed": 1,
			},
			{
				"label": _(self.payroll_frequency),
				"fieldname": "per_cycle",
				"fieldtype": "Currency",
				"width": 250,
				"options": "currency",
				"fixed": 1,
			},
			{
				"label": _("Annual"),
				"fieldname": "annual",
				"fieldtype": "Currency",
				"width": 250,
				"options": "currency",
				"fixed": 1,
			},
			{
				"label": _("Percent of CTC (%)"),
				"fieldname": "percent_of_ctc",
				"fieldtype": "Percent",
				"width": 200,
				"fixed": 1,
			},
			{
				"fieldname": "currency",
				"label": _("Currency"),
				"fieldtype": "Link",
				"options": "Currency",
				"hidden": 1,
				"value": self.currency,
			},
		]

	def get_message(self):
		path = "hrms/payroll/report/employee_ctc_break_up/employee_profile_card.html"
		employee_name, designation, image = frappe.get_value(
			"Employee", self.employee, ["employee_name", "designation", "image"]
		)
		context = dict(
			{
				"employee_name": employee_name,
				"designation": designation,
				"image": image,
				"salary_structure": self.salary_structure,
				"per_cycle": self.payroll_frequency,
				"annual_ctc": self.format_currency(self.ctc),
				"per_cycle_ctc": self.format_currency(self.get_per_cycle_ctc()),
				"per_cycle_gross_pay": self.format_currency(self.gross_pay),
				"per_cycle_net_pay": self.format_currency(self.net_pay),
				"assignment_date": frappe.utils.global_date_format(self.assignment_date, "long"),
				"income_tax_slab": self.income_tax_slab,
			}
		)
		# nosemgrep: frappe-semgrep-rules.rules.security.frappe-ssti
		employee_profile_card = render_template(path, context=context, is_path=True)
		return employee_profile_card


def execute(filters: dict | None = None):
	"""Return columns and data for the report.

	This is the main entry point for the report. It accepts the filters as a
	dictionary and should return columns and data. It is called by the framework
	every time the report is refreshed or a filter is updated.
	"""
	employee = filters.get("employee")
	salary_structure_assignment = filters.get("salary_structure_assignment")

	missing_filter = (
		"Employee"
		if not employee
		else "Salary Structure Assignment"
		if not salary_structure_assignment
		else None
	)
	if missing_filter:
		frappe.throw(
			_("Please set {0} to get CTC report").format(frappe.bold(missing_filter)),
			title=_("Missing value for filters"),
		)

	validate_employee_access(employee)

	salary_breakup_report = SalaryBreakupReport(employee, salary_structure_assignment)

	data = salary_breakup_report.get_data()
	columns = salary_breakup_report.get_columns()
	message = salary_breakup_report.get_message()
	return columns, data, message, None, None


ROLES_ALLOWED_TO_VIEW_ANY_EMPLOYEE = ("System Manager", "HR Manager", "HR User")


def validate_employee_access(employee: str):
	can_view_any_employee = has_common(ROLES_ALLOWED_TO_VIEW_ANY_EMPLOYEE, frappe.get_roles())
	is_own_record = frappe.db.get_value("Employee", employee, "user_id") == frappe.session.user

	if not can_view_any_employee and not is_own_record:
		frappe.throw(
			_("You are not permitted to access the CTC report of another employee."),
			frappe.PermissionError,
			title=_("Not Permitted"),
		)
