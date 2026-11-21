import math

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, get_link_to_form, getdate
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip, _safe_eval, get_salary_component_data

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
		self.set_salary_component_override_status()

	def get_active_salary_component_overrides(self):
		if hasattr(self, "_active_component_overrides_cache"):
			return self._active_component_overrides_cache

		self._active_component_overrides_cache = {}
		if not self.employee:
			return self._active_component_overrides_cache

		override_name = None
		# 1. Check linked SSA directly
		if not hasattr(self, "_salary_structure_assignment"):
			if getattr(self, "salary_structure", None) and getattr(self, "actual_start_date", None):
				try:
					self.set_salary_structure_assignment()
				except Exception:
					pass

		ssa_doc = getattr(self, "_salary_structure_assignment", None)
		ssa_name = (
			ssa_doc.name
			if hasattr(ssa_doc, "name")
			else (ssa_doc.get("name") if isinstance(ssa_doc, dict) else ssa_doc)
		)
		if ssa_name:
			override_name = frappe.db.get_value(
				"Salary Structure Assignment",
				ssa_name,
				"custom_employees_salary_component_override",
			)

		# Validate the linked override is submitted and active
		if override_name:
			is_active, docstatus = frappe.db.get_value(
				"Employees Salary Component Override",
				override_name,
				["is_active", "docstatus"],
			) or (0, 0)
			if not (cint(is_active) and cint(docstatus) == 1):
				override_name = None

		# 2. If not found on SSA, query active submitted override for this employee
		if not override_name:
			filters = {
				"employee": self.employee,
				"docstatus": 1,
				"is_active": 1,
			}
			if self.salary_structure:
				filters["salary_structure"] = self.salary_structure
			if ssa_name:
				filters_overridden = dict(filters)
				filters_overridden["overridden_salary_structure_assignment"] = ssa_name
				override_name = frappe.db.get_value(
					"Employees Salary Component Override",
					filters_overridden,
					"name",
					order_by="creation desc",
				)
				if not override_name:
					filters["salary_structure_assignment"] = ssa_name
					override_name = frappe.db.get_value(
						"Employees Salary Component Override",
						filters,
						"name",
						order_by="creation desc",
					)
			else:
				override_name = frappe.db.get_value(
					"Employees Salary Component Override",
					filters,
					"name",
					order_by="creation desc",
				)

		if override_name:
			details = frappe.get_all(
				"Salary Component Override Detail",
				filters={"parent": override_name},
				fields=["salary_component", "abbr", "component_type", "override_amount"],
			)
			for row in details:
				self._active_component_overrides_cache[row.salary_component] = {
					"override_amount": flt(row.override_amount),
					"abbr": row.abbr,
					"component_type": row.component_type,
					"docname": override_name,
				}

		return self._active_component_overrides_cache

	def set_salary_component_override_status(self):
		overrides = self.get_active_salary_component_overrides()
		if overrides:
			self.custom_component_override_applied = 1
			# Get document name from first component override info
			first_comp = next(iter(overrides.values()))
			self.custom_salary_component_override = first_comp.get("docname")
		else:
			self.custom_component_override_applied = 0
			self.custom_salary_component_override = None

	def eval_condition_and_formula(self, struct_row, data):
		overrides = self.get_active_salary_component_overrides()
		if overrides and struct_row.salary_component in overrides:
			override_info = overrides[struct_row.salary_component]
			override_amount = flt(override_info["override_amount"])

			# Evaluate condition if defined
			condition = struct_row.condition
			if condition and not _safe_eval(condition, self.whitelisted_globals, data):
				return None

			# Update default_amount on struct_row so update_component_row receives it
			struct_row.default_amount = override_amount

			# Prorate if payment-days dependent
			if struct_row.depends_on_payment_days and cint(self.total_working_days):
				amount = override_amount * flt(self.payment_days) / cint(self.total_working_days)
			else:
				amount = override_amount

			amount = flt(amount, struct_row.precision or 2)
			if amount is not None:
				data[struct_row.abbr] = amount
				if hasattr(self, "default_data") and self.default_data is not None:
					self.default_data[struct_row.abbr] = override_amount

			return amount

		return super().eval_condition_and_formula(struct_row, data)

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
