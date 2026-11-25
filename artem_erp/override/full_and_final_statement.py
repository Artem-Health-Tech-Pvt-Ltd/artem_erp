import frappe
from frappe import _
from frappe.utils import flt
from hrms.hr.doctype.full_and_final_statement.full_and_final_statement import FullandFinalStatement


class CustomFullandFinalStatement(FullandFinalStatement):
	@frappe.whitelist()
	def get_outstanding_statements(self):
		super().get_outstanding_statements()
		self.add_partial_withheld_salaries()

	def add_partial_withheld_salaries(self):
		from artem_erp.doc_events.full_and_final_statement import fetch_partial_salary_withholdings

		fetch_partial_salary_withholdings(self)
		self.set_totals()

	def before_cancel(self):
		self.flags.ignore_links = True
		self.ignore_linked_doctypes = (
			"Salary Withholding",
			"Salary Withholding Cycle",
			"Salary Slip",
			"GL Entry",
			"Journal Entry",
			"Full and Final Outstanding Statement",
		)

	@frappe.whitelist()
	def create_journal_entry(self):
		jv = super().create_journal_entry()

		# Link salary payable debit rows to their respective Payroll Entry
		# so the Bank Entry displays in the Payroll Entry's Connections dashboard
		for data in self.payables:
			if flt(data.amount) <= 0 or data.paid_via_salary_slip:
				continue

			payroll_entry = None
			if data.reference_document_type == "Salary Slip" and data.reference_document:
				payroll_entry = frappe.db.get_value("Salary Slip", data.reference_document, "payroll_entry")
			elif data.reference_document_type == "Salary Withholding" and data.reference_document:
				slip_name = frappe.db.get_value(
					"Salary Withholding Cycle",
					{"parent": data.reference_document, "custom_fnf_reference": self.name},
					"custom_salary_slip",
				)
				if slip_name:
					payroll_entry = frappe.db.get_value("Salary Slip", slip_name, "payroll_entry")

			if payroll_entry:
				for acc in jv.accounts:
					if (
						acc.account == data.account
						and flt(acc.debit_in_account_currency) == flt(data.amount)
						and not acc.reference_name
					):
						acc.reference_type = "Payroll Entry"
						acc.reference_name = payroll_entry
						acc.party_type = "Employee"
						acc.party = self.employee
						break

		return jv
