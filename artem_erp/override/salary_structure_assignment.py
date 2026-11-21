# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt
from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
	COMPONENT_EVAL_GLOBALS,
	SALARY_COMPONENT_FLAGS,
	SalaryStructureAssignment,
	_safe_eval,
	sanitize_expression,
	throw_error_message,
)


class CustomSalaryStructureAssignment(SalaryStructureAssignment):
	def get_active_salary_component_overrides(self):
		if getattr(self.flags, "ignore_overrides", False):
			return {}

		if hasattr(self, "_active_component_overrides_cache"):
			return self._active_component_overrides_cache

		self._active_component_overrides_cache = {}
		if not self.employee:
			return self._active_component_overrides_cache

		override_name = getattr(self, "custom_employees_salary_component_override", None)
		if override_name:
			is_active, docstatus = frappe.db.get_value(
				"Employees Salary Component Override",
				override_name,
				["is_active", "docstatus"],
			) or (0, 0)
			if not (cint(is_active) and cint(docstatus) == 1):
				override_name = None

		if not override_name and (
			cint(getattr(self, "custom_is_override_salary_structure_component", 0)) or self.docstatus == 1
		):
			override_name = frappe.db.get_value(
				"Employees Salary Component Override",
				{
					"employee": self.employee,
					"docstatus": 1,
					"is_active": 1,
					"overridden_salary_structure_assignment": self.name,
				},
				"name",
			)
			if not override_name:
				override_name = frappe.db.get_value(
					"Employees Salary Component Override",
					{
						"employee": self.employee,
						"docstatus": 1,
						"is_active": 1,
						"salary_structure": self.salary_structure,
					},
					"name",
					order_by="creation desc",
				)

		if override_name:
			details = frappe.get_all(
				"Salary Component Override Detail",
				filters={"parent": override_name},
				fields=["salary_component", "abbr", "override_amount"],
			)
			for row in details:
				self._active_component_overrides_cache[row.salary_component] = flt(row.override_amount)

		return self._active_component_overrides_cache

	def _evaluate_component_table(self, rows, data: frappe._dict) -> list:
		"""Evaluate one component table against the shared data (mutating it
		with each component's full-cycle amount), injecting any active employee component overrides."""
		overrides = self.get_active_salary_component_overrides()
		evaluated_components = []
		for struct_row in rows:
			condition = sanitize_expression(struct_row.condition)
			formula = sanitize_expression(struct_row.formula)
			amount = flt(struct_row.amount)

			try:
				if condition and not _safe_eval(condition, COMPONENT_EVAL_GLOBALS.copy(), data):
					continue

				if struct_row.salary_component in overrides:
					override_amt = flt(
						overrides[struct_row.salary_component],
						struct_row.precision("amount"),
					)
					default_amount = override_amt
					amount = override_amt
				elif struct_row.amount_based_on_formula and formula:
					default_amount = flt(
						_safe_eval(formula, COMPONENT_EVAL_GLOBALS.copy(), data),
						struct_row.precision("amount"),
					)
				else:
					default_amount = amount
			except NameError as ne:
				throw_error_message(
					struct_row,
					ne,
					title=_("Name error"),
					description=_("This error can be due to missing or deleted field."),
				)
			except SyntaxError as se:
				throw_error_message(
					struct_row,
					se,
					title=_("Syntax error"),
					description=_("This error can be due to invalid syntax."),
				)
			except Exception as exc:
				throw_error_message(
					struct_row,
					exc,
					title=_("Error in formula or condition"),
					description=_("This error can be due to invalid formula or condition."),
				)
				raise

			data[struct_row.abbr] = default_amount

			evaluated_component_row = frappe._dict(
				default_amount=default_amount,
				amount=amount,
				condition=condition,
				formula=formula,
				precision=struct_row.precision("amount"),
			)
			for field in SALARY_COMPONENT_FLAGS:
				evaluated_component_row[field] = struct_row.get(field)
			evaluated_components.append(evaluated_component_row)

		return evaluated_components

	def before_cancel(self):
		if hasattr(super(), "before_cancel"):
			super().before_cancel()
		self.ignore_linked_doctypes = ["Employees Salary Component Override"]
		self.flags.ignore_links = True

	def on_cancel(self):
		if hasattr(super(), "on_cancel"):
			super().on_cancel()
		self.unlink_from_salary_component_overrides()

	def on_trash(self):
		if hasattr(super(), "on_trash"):
			super().on_trash()
		self.unlink_from_salary_component_overrides()

	def unlink_from_salary_component_overrides(self):
		# 1. Clear reference from this SSA
		if getattr(self, "custom_employees_salary_component_override", None):
			frappe.db.set_value(
				"Salary Structure Assignment",
				self.name,
				{
					"custom_is_override_salary_structure_component": 0,
					"custom_employees_salary_component_override": None,
				},
				update_modified=False,
			)

		# 2. Clear references from Employees Salary Component Override documents
		for field in ("salary_structure_assignment", "overridden_salary_structure_assignment"):
			linked_overrides = frappe.get_all(
				"Employees Salary Component Override",
				filters={
					field: self.name,
				},
				pluck="name",
			)
			for ov_name in linked_overrides:
				frappe.db.set_value(
					"Employees Salary Component Override",
					ov_name,
					{field: None},
					update_modified=False,
				)
