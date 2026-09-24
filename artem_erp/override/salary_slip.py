import math

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_link_to_form, getdate
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip, get_salary_component_data

from artem_erp.override.additional_salary import (
	get_custom_additional_salaries,
	get_employee_joining_date,
	is_recurring_additional_salary_due,
)


def get_additional_salaries_from_reviews(review_names, employee, start_date, end_date, component_type):
	comp_type = "Earning" if component_type == "earnings" else "Deduction"
	additional_salaries = []
	seen_salaries = set()
	components_to_overwrite = []

	for r_name in review_names:
		review_doc = frappe.get_doc("Employee Additional Salary Payroll Review", r_name)
		all_rows = (review_doc.additional_salary_payment_details or []) + (
			review_doc.previous_pending_additional_salary or []
		)

		for row in all_rows:
			if not row.additional_salary or row.employee != employee:
				continue

			# Only allow Pay, Paid, or Partially Paid
			if row.pay_action not in ("Pay", "Paid", "Partially Paid"):
				continue

			paid_amount = flt(row.paid_amount)
			if paid_amount <= 0:
				continue

			# Check component type matches (Earning vs Deduction)
			component_type_in_db = frappe.get_cached_value("Salary Component", row.bonus_type, "type")
			if component_type_in_db != comp_type:
				continue

			# Ensure not applied twice in this slip
			if row.additional_salary in seen_salaries:
				continue

			# Ensure not already applied in another submitted Salary Slip for this period
			already_paid = frappe.db.sql(
				"""
				SELECT sd.name
				FROM `tabSalary Detail` sd
				JOIN `tabSalary Slip` ss ON ss.name = sd.parent
				WHERE ss.docstatus = 1
				  AND ss.employee = %s
				  AND sd.additional_salary = %s
				  AND ss.start_date <= %s
				  AND ss.end_date >= %s
				LIMIT 1
				""",
				(employee, row.additional_salary, end_date, start_date),
			)
			if already_paid:
				continue

			seen_salaries.add(row.additional_salary)

			# Fetch Additional Salary document properties
			as_info = (
				frappe.db.get_value(
					"Additional Salary",
					row.additional_salary,
					[
						"overwrite_salary_structure_amount",
						"is_recurring",
						"ref_doctype",
						"ref_docname",
						"deduct_full_tax_on_selected_payroll_date",
					],
					as_dict=True,
				)
				or frappe._dict()
			)

			item = frappe._dict(
				{
					"name": row.additional_salary,
					"component": row.bonus_type,
					"amount": paid_amount,
					"overwrite": as_info.get("overwrite_salary_structure_amount") or 0,
					"is_recurring": as_info.get("is_recurring") or 0,
					"ref_doctype": as_info.get("ref_doctype"),
					"ref_docname": as_info.get("ref_docname"),
					"deduct_full_tax_on_selected_payroll_date": as_info.get(
						"deduct_full_tax_on_selected_payroll_date"
					)
					or 0,
				}
			)

			if item.overwrite:
				if item.component in components_to_overwrite:
					frappe.throw(
						_(
							"Multiple Additional Salaries with overwrite property exist for Salary Component {0} between {1} and {2}."
						).format(frappe.bold(item.component), start_date, end_date),
						title=_("Error"),
					)
				components_to_overwrite.append(item.component)

			additional_salaries.append(item)

	return additional_salaries


class CustomSalarySlip(SalarySlip):
	def validate(self):
		self.validate_additional_salary_review()
		super().validate()

	def validate_additional_salary_review(self):
		if not (self.company and self.start_date and self.end_date):
			return

		draft_reviews = frappe.get_all(
			"Employee Additional Salary Payroll Review",
			filters={
				"company": self.company,
				"payroll_from_date": ["<=", self.end_date],
				"payroll_to_date": [">=", self.start_date],
				"docstatus": 0,
			},
			fields=["name"],
			limit=1,
		)
		if draft_reviews:
			frappe.throw(
				_(
					"Cannot process Salary Slip for {0}: Employee Additional Salary Payroll Review {1} is still in Draft. Please complete and submit the review first."
				).format(
					self.employee,
					get_link_to_form("Employee Additional Salary Payroll Review", draft_reviews[0].name),
				),
				title=_("Additional Salary Review Required"),
			)

	def add_additional_salary_components(self, component_type):
		# Check if a submitted review exists for this period and company
		submitted_reviews = frappe.get_all(
			"Employee Additional Salary Payroll Review",
			filters={
				"company": self.company,
				"payroll_from_date": ["<=", self.end_date],
				"payroll_to_date": [">=", self.start_date],
				"docstatus": 1,
			},
			order_by="payroll_to_date desc",
			pluck="name",
		)

		if submitted_reviews:
			additional_salaries = get_additional_salaries_from_reviews(
				submitted_reviews, self.employee, self.start_date, self.end_date, component_type
			)
		else:
			# Fallback if no review document exists for this payroll period
			additional_salaries = get_custom_additional_salaries(
				self.employee, self.start_date, self.end_date, component_type
			)

		for additional_salary in additional_salaries:
			component_data = get_salary_component_data(additional_salary.component)
			remove_if_zero_valued = frappe.get_cached_value(
				"Salary Component", additional_salary.component, "remove_if_zero_valued"
			)
			if flt(additional_salary.amount) == 0 and remove_if_zero_valued:
				continue
			self.update_component_row(
				component_data,
				additional_salary.amount,
				component_type,
				additional_salary,
				is_recurring=additional_salary.is_recurring,
			)

			if component_type == "earnings" and hasattr(self, "benefit_ledger_components"):
				if (
					additional_salary.ref_doctype == "Employee Benefit Claim"
					and component_data.is_flexible_benefit
				) or component_data.accrual_component:
					if additional_salary.ref_doctype == "Employee Benefit Claim":
						remarks = f"Payout against Employee Benefit Claim {additional_salary.ref_docname}"
						flexible_benefit = 1
					else:
						remarks = "Accrual Component payout via Additional Salary"
						flexible_benefit = 0

					self.benefit_ledger_components.append(
						{
							"salary_component": additional_salary.component,
							"amount": additional_salary.amount,
							"is_accrual": 0,
							"transaction_type": "Payout",
							"flexible_benefit": flexible_benefit,
							"remarks": remarks,
						}
					)

	def get_future_recurring_additional_amount(self, additional_salary, monthly_additional_amount):
		if not self.payroll_period:
			return 0

		as_doc = frappe.db.get_value(
			"Additional Salary",
			additional_salary,
			[
				"name",
				"is_recurring",
				"custom_duration_of_additional_salary",
				"from_date",
				"to_date",
				"custom_date_of_joining",
				"employee",
			],
			as_dict=True,
		)
		if not as_doc or not as_doc.is_recurring:
			return 0

		duration = as_doc.get("custom_duration_of_additional_salary")
		if duration in ("Quarterly", "Half Yearly", "Yearly"):
			duration_map = {"Quarterly": 3, "Half Yearly": 6, "Yearly": 12}
			interval = duration_map[duration]

			from_date = as_doc.get("from_date")
			first_date = from_date or as_doc.get("custom_date_of_joining")
			if not first_date:
				first_date = get_employee_joining_date(as_doc.employee)
			if not first_date:
				return 0

			first_date = getdate(first_date)
			sub_period_start = add_days(getdate(self.end_date), 1)
			payroll_end = getdate(self.payroll_period.end_date)
			if as_doc.get("to_date"):
				payroll_end = min(payroll_end, getdate(as_doc.to_date))

			if sub_period_start > payroll_end:
				return 0

			future_count = 0
			k = 1
			while True:
				due_date = add_months(first_date, k * interval)
				if due_date > payroll_end:
					break
				if due_date >= sub_period_start:
					future_count += 1
				k += 1

			return flt(monthly_additional_amount * future_count)

		# Standard monthly recurrence fallback with null-safe to_date
		try:
			return super().get_future_recurring_additional_amount(
				additional_salary, monthly_additional_amount
			)
		except Exception:
			to_date = as_doc.get("to_date") or self.payroll_period.end_date
			from_date = getdate(self.start_date)
			if getdate(to_date) > getdate(self.payroll_period.end_date):
				to_date = getdate(self.payroll_period.end_date)
			future_months = max(0, ((to_date.year - from_date.year) * 12) + (to_date.month - from_date.month))
			return flt(monthly_additional_amount * future_months)

	def on_submit(self):
		super().on_submit()
		update_additional_salary_payment_history(self, cancel=False)

	def on_cancel(self):
		super().on_cancel()
		update_additional_salary_payment_history(self, cancel=True)


def update_additional_salary_payment_history(salary_slip, cancel=False):
	processed_additional_salaries = set()
	for row in (salary_slip.get("earnings") or []) + (salary_slip.get("deductions") or []):
		additional_salary_name = getattr(row, "additional_salary", None)
		if not additional_salary_name:
			continue

		if additional_salary_name in processed_additional_salaries:
			continue

		is_recurring = frappe.db.get_value("Additional Salary", additional_salary_name, "is_recurring")
		if not is_recurring:
			continue

		processed_additional_salaries.add(additional_salary_name)

		if cancel:
			frappe.db.delete(
				"Additional Salary Payment History",
				{"parent": additional_salary_name, "salary_slip": salary_slip.name},
			)
		else:
			exists = frappe.db.exists(
				"Additional Salary Payment History",
				{"parent": additional_salary_name, "salary_slip": salary_slip.name},
			)
			if not exists:
				as_doc = frappe.get_doc("Additional Salary", additional_salary_name)
				as_amount = (
					flt(getattr(row, "additional_amount", None))
					or flt(getattr(row, "amount", None))
					or flt(as_doc.amount)
				)

				as_doc.append(
					"custom_additional_salary_payment_history",
					{
						"salary_slip": salary_slip.name,
						"payroll_duration_from_date": salary_slip.start_date,
						"payroll_duration_to_date": salary_slip.end_date,
						"additional_salary_amount": as_amount,
						"total_net_pay": flt(salary_slip.net_pay),
					},
				)
				as_doc.flags.ignore_validate_update_after_submit = True
				as_doc.flags.ignore_validate = True
				as_doc.flags.ignore_mandatory = True
				as_doc.save(ignore_permissions=True)
