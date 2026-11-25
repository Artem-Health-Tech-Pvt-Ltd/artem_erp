import erpnext
import frappe
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
from frappe import _
from frappe.utils import flt
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
from hrms.payroll.doctype.salary_withholding.salary_withholding import (
	link_bank_entry_in_salary_withholdings,
)

from artem_erp.doc_events.full_and_final_statement import _get_holdback_account


class CustomPayrollEntry(PayrollEntry):
	@frappe.whitelist()
	def has_bank_entries(self) -> dict[str, bool]:
		je = frappe.qb.DocType("Journal Entry")
		jea = frappe.qb.DocType("Journal Entry Account")

		# Check for draft (docstatus=0) or submitted (docstatus=1) bank entries.
		# Cancelled bank entries (docstatus=2) are ignored so "Make Bank Entry" is shown again.
		bank_entries = (
			frappe.qb.from_(je)
			.inner_join(jea)
			.on(je.name == jea.parent)
			.select(je.name)
			.where(
				((je.voucher_type == "Bank Entry") | (je.voucher_type == "Cash Entry"))
				& (jea.reference_name == self.name)
				& (jea.reference_type == "Payroll Entry")
				& (je.docstatus.isin([0, 1]))
			)
		).run(as_dict=True)

		# Ensure has_bank_entries_for_withheld_salaries dynamically reflects
		# the latest database state of is_salary_withheld on employees
		has_withheld = frappe.db.sql(
			"""
			SELECT 1 FROM `tabPayroll Employee Detail`
			WHERE parent = %s AND is_salary_withheld = 1
			LIMIT 1
			""",
			(self.name,),
		)
		return {
			"has_bank_entries": bool(bank_entries),
			"has_bank_entries_for_withheld_salaries": not bool(has_withheld),
		}

	@frappe.whitelist()
	def make_bank_entry(self, for_withheld_salaries: bool = False):
		if not for_withheld_salaries:
			return super().make_bank_entry(for_withheld_salaries=False)

		self.check_permission("write")
		self.employee_based_payroll_payable_entries = {}
		employee_wise_accounting_enabled = frappe.db.get_single_value(
			"Payroll Settings", "process_payroll_accounting_entry_based_on_employee"
		)

		company_currency = erpnext.get_company_currency(self.company)
		accounting_dimensions = get_accounting_dimensions() or []
		precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency")

		accounts = []
		currencies = []
		total_withheld_amount = 0
		released_percentage_cycles = []

		# 1. Standard 100% Withheld Salary Slips (Standard HRMS behavior)
		standard_salary_details = self.get_salary_slip_details(for_withheld_salaries=True)
		standard_total = 0

		if standard_salary_details:
			for salary_detail in standard_salary_details:
				statistical_component = frappe.db.get_value(
					"Salary Component", salary_detail.salary_component, "statistical_component", cache=True
				)
				if not statistical_component:
					parent_field = salary_detail.parentfield
					if parent_field in ("earnings", "deductions"):
						if employee_wise_accounting_enabled:
							self.set_employee_based_payroll_payable_entries(
								salary_detail.parentfield,
								salary_detail.employee,
								salary_detail.amount,
								salary_detail.salary_structure,
							)
						if parent_field == "earnings":
							standard_total += salary_detail.amount
						elif parent_field == "deductions":
							standard_total -= salary_detail.amount

			total_loan_repayment = self.process_loan_repayments_for_bank_entry(standard_salary_details) or 0
			standard_total -= total_loan_repayment

			if standard_total > 0:
				total_withheld_amount += standard_total
				payroll_payable_account = self.payroll_payable_account

				if self.employee_based_payroll_payable_entries:
					for employee, employee_details in self.employee_based_payroll_payable_entries.items():
						je_payment_amount = (
							(employee_details.get("earnings", 0) or 0)
							- (employee_details.get("deductions", 0) or 0)
							- (employee_details.get("total_loan_repayment", 0) or 0)
						)
						if not je_payment_amount:
							continue

						exchange_rate, amount = self.get_amount_and_exchange_rate_for_journal_entry(
							self.payment_account, je_payment_amount, company_currency, currencies
						)
						cost_centers = self.get_payroll_cost_centers_for_employee(
							employee, employee_details.get("salary_structure")
						)
						for cost_center, percentage in cost_centers.items():
							amount_against_cost_center = flt(amount) * percentage / 100
							accounts.append(
								self.update_accounting_dimensions(
									{
										"account": payroll_payable_account,
										"debit_in_account_currency": flt(
											amount_against_cost_center, precision
										),
										"exchange_rate": flt(exchange_rate),
										"reference_type": self.doctype,
										"reference_name": self.name,
										"party_type": "Employee",
										"party": employee,
										"cost_center": cost_center,
									},
									accounting_dimensions,
								)
							)
				else:
					exchange_rate, amount = self.get_amount_and_exchange_rate_for_journal_entry(
						payroll_payable_account, standard_total, company_currency, currencies
					)
					accounts.append(
						self.update_accounting_dimensions(
							{
								"account": payroll_payable_account,
								"debit_in_account_currency": flt(amount, precision),
								"exchange_rate": flt(exchange_rate),
								"reference_type": self.doctype,
								"reference_name": self.name,
								"cost_center": self.cost_center,
							},
							accounting_dimensions,
						)
					)

		# 2. Percentage Withheld Salaries (Artem Percentage Withholding)
		partial_cycles = self.get_unreleased_partial_withholding_cycles()
		for cycle in partial_cycles:
			held_amt = flt(cycle.get("held_amount"))
			if held_amt <= 0:
				continue

			total_withheld_amount += held_amt
			holdback_account = cycle.get("holdback_account")
			emp = cycle.get("employee")

			exchange_rate, amount = self.get_amount_and_exchange_rate_for_journal_entry(
				holdback_account, held_amt, company_currency, currencies
			)

			cost_center = self.cost_center
			if cycle.get("salary_structure"):
				cost_centers = self.get_payroll_cost_centers_for_employee(emp, cycle.get("salary_structure"))
				if cost_centers:
					cost_center = next(iter(cost_centers))

			accounts.append(
				self.update_accounting_dimensions(
					{
						"account": holdback_account,
						"debit_in_account_currency": flt(amount, precision),
						"exchange_rate": flt(exchange_rate),
						"reference_type": self.doctype,
						"reference_name": self.name,
						"party_type": "Employee",
						"party": emp,
						"cost_center": cost_center,
					},
					accounting_dimensions,
				)
			)
			released_percentage_cycles.append(cycle)

		if total_withheld_amount <= 0:
			frappe.msgprint(_("No withheld salaries found to release."))
			return None

		# 3. Credit entry for Bank / Cash
		exchange_rate, total_amount_in_bank = self.get_amount_and_exchange_rate_for_journal_entry(
			self.payment_account, total_withheld_amount, company_currency, currencies
		)
		accounts.insert(
			0,
			self.update_accounting_dimensions(
				{
					"account": self.payment_account,
					"bank_account": self.bank_account,
					"credit_in_account_currency": flt(total_amount_in_bank, precision),
					"exchange_rate": flt(exchange_rate),
					"cost_center": self.cost_center,
				},
				accounting_dimensions,
			),
		)

		voucher_type = (
			"Cash Entry"
			if frappe.get_cached_value("Account", self.payment_account, "account_type") == "Cash"
			else "Bank Entry"
		)
		bank_entry = self.make_journal_entry(
			accounts,
			currencies,
			voucher_type=voucher_type,
			user_remark=_("Payment of withheld salaries from {0} to {1}").format(
				self.start_date, self.end_date
			),
			employee_wise_accounting_enabled=employee_wise_accounting_enabled,
		)

		# 4. Link Bank Entry in cycles
		if standard_salary_details:
			link_bank_entry_in_salary_withholdings(standard_salary_details, bank_entry.name)

		for cycle in released_percentage_cycles:
			frappe.db.set_value(
				"Salary Withholding Cycle",
				cycle["cycle_name"],
				"journal_entry",
				bank_entry.name,
			)

		return bank_entry

	def get_unreleased_partial_withholding_cycles(self):
		"""
		Finds unreleased withholding cycles (Percentage withholding or partial)
		associated with employees in this Payroll Entry.
		"""
		withheld_emp_ids = [emp.employee for emp in self.employees if emp.is_salary_withheld]
		if not withheld_emp_ids:
			return []

		slips = frappe.get_all(
			"Salary Slip",
			filters={
				"payroll_entry": self.name,
				"docstatus": 1,
				"employee": ["in", withheld_emp_ids],
			},
			fields=["name", "employee", "salary_structure", "salary_withholding_cycle", "status"],
		)

		slip_map = {s.name: s for s in slips}
		cycle_slip_map = {s.salary_withholding_cycle: s for s in slips if s.salary_withholding_cycle}

		cycles = frappe.db.sql(
			"""
			SELECT
				c.name as cycle_name,
				c.parent as withholding_name,
				c.from_date,
				c.to_date,
				c.is_salary_released,
				c.custom_held_amount,
				c.custom_salary_slip,
				w.employee,
				w.company,
				w.custom_withholding_mode,
				w.custom_holdback_account
			FROM `tabSalary Withholding Cycle` c
			JOIN `tabSalary Withholding` w ON c.parent = w.name
			WHERE w.employee IN %s
			  AND w.docstatus = 1
			  AND c.docstatus = 1
			  AND c.is_salary_released = 0
			  AND (
				  c.custom_salary_slip IN %s
				  OR c.name IN %s
				  OR (c.from_date >= %s AND c.to_date <= %s)
			  )
			""",
			(
				tuple(withheld_emp_ids),
				tuple(slip_map.keys()) if slip_map else ("",),
				tuple(cycle_slip_map.keys()) if cycle_slip_map else ("",),
				self.start_date,
				self.end_date,
			),
			as_dict=True,
		)

		seen_cycles = set()
		partial_cycles = []

		for c in cycles:
			if c.cycle_name in seen_cycles:
				continue
			seen_cycles.add(c.cycle_name)

			slip = None
			if c.custom_salary_slip and c.custom_salary_slip in slip_map:
				slip = slip_map[c.custom_salary_slip]
			elif c.cycle_name in cycle_slip_map:
				slip = cycle_slip_map[c.cycle_name]

			# Standard HRMS already processes slips with status == "Withheld"
			if slip and slip.status == "Withheld":
				continue

			holdback_account = c.custom_holdback_account or _get_holdback_account(
				c.withholding_name, self.company
			)
			held_amount = flt(c.custom_held_amount)

			if held_amount > 0 and holdback_account:
				partial_cycles.append(
					{
						"cycle_name": c.cycle_name,
						"withholding_name": c.withholding_name,
						"employee": c.employee,
						"held_amount": held_amount,
						"holdback_account": holdback_account,
						"salary_structure": slip.salary_structure if slip else None,
						"salary_slip": slip.name if slip else c.custom_salary_slip,
					}
				)

		return partial_cycles
