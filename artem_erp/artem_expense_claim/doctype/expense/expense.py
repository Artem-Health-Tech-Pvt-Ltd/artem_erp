# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class Expense(Document):
	def validate(self):
		self.check_if_claimed()
		self.set_limit_and_check_overlimit()

	def check_if_claimed(self):
		if not self.is_new():
			is_claimed = frappe.db.get_value("Expense", self.name, "is_claim_raise")
			if is_claimed:
				frappe.throw(
					_("This expense is already linked to an Expense Claim and cannot be edited."),
					title=_("Action Not Allowed")
				)

	def set_limit_and_check_overlimit(self):
		limit_type = None
		limit_amount = 0.0

		if self.city and self.expense_category:
			grade = self.employee_grade
			if not grade and self.employee:
				grade = frappe.db.get_value("Employee", self.employee, "grade")
				if grade:
					self.employee_grade = grade

			limit_info = get_expense_limit_details(
				expense_category=self.expense_category,
				city=self.city,
				employee_grade=grade,
			)
			limit_type = limit_info.get("limit_type")
			limit_amount = flt(limit_info.get("limit_amount"))

			if is_per_km(limit_type):
				self.per_km_rate = limit_amount
				self.total_amount = flt(self.total_distance_in_km) * flt(self.per_km_rate)
				self.limit_amount = 0.0
				self.is_overlimit__expense = 0
			else:
				self.limit_amount = limit_amount
				self.validate_overlimit()
		else:
			self.validate_overlimit()

	def validate_overlimit(self):
		total_amount = flt(self.total_amount)
		limit_amount = flt(self.limit_amount)

		if limit_amount > 0:
			daily_usage = get_daily_used_expense_amount(
				employee=self.employee,
				expense_category=self.expense_category,
				expense_date=self.expense_date,
				exclude_expense=self.name,
			)
			available_limit = max(0.0, limit_amount - daily_usage)

			if total_amount > available_limit:
				over_limit_amount = total_amount - available_limit
				allowed_over_limit = get_allowed_over_limit_amount(
					employee=self.employee,
					expense_category=self.expense_category,
					expense_date=self.expense_date,
				)

				if allowed_over_limit is not None and over_limit_amount <= flt(allowed_over_limit):
					self.is_overlimit__expense = 1
				else:
					self.is_overlimit__expense = 1
					frappe.throw(
						_("The entered expense amount exceeds the allowed limit. Please contact the HR Team or your Reporting Manager for approval."),
						title=_("Over-Limit Expense")
					)
			else:
				self.is_overlimit__expense = 0
		else:
			self.is_overlimit__expense = 0


def get_daily_used_expense_amount(
	employee: str | None,
	expense_category: str | None,
	expense_date: str | None,
	exclude_expense: str | None = None,
) -> float:
	"""
	Calculate the sum of total_amount already entered for the same employee,
	same expense_category, and same expense_date.
	"""
	if not employee or not expense_category or not expense_date:
		return 0.0

	filters = {
		"employee": employee,
		"expense_category": expense_category,
		"expense_date": expense_date,
	}
	if exclude_expense:
		filters["name"] = ["!=", exclude_expense]

	rows = frappe.db.get_all(
		"Expense",
		filters=filters,
		fields=["total_amount"],
	)

	return sum(flt(d.total_amount) for d in rows)


def get_allowed_over_limit_amount(employee, expense_category, expense_date=None):
	"""
	Check if the employee has a valid over-limit authorization in custom_expense_overlimit_authorization
	where:
	  - parent = employee
	  - expense_category = expense_category
	  - valid_till_date >= expense_date (or today if expense_date is not set)
	Returns the allowed_over_limit_amount if found, else None.
	"""
	if not employee or not expense_category:
		return None

	date_to_check = expense_date or today()

	auth_rows = frappe.db.get_all(
		"Expense Over-limit Authorization",
		filters={
			"parent": employee,
			"parenttype": "Employee",
			"parentfield": "custom_expense_overlimit_authorization",
			"expense_category": expense_category,
			"valid_till_date": [">=", date_to_check],
		},
		fields=["allowed_over_limit_amount"],
		order_by="valid_till_date desc, creation desc",
		limit=1,
	)

	if auth_rows:
		return flt(auth_rows[0].allowed_over_limit_amount)

	return None


def is_per_km(limit_type):
	if not limit_type:
		return False
	return str(limit_type).strip().lower().replace(" ", "").replace("-", "") in ["perkm", "km"]


@frappe.whitelist()
def check_expense_overlimit(
	employee: str | None = None,
	expense_category: str | None = None,
	expense_date: str | None = None,
	total_amount: float = 0.0,
	limit_amount: float = 0.0,
	expense_name: str | None = None,
):
	"""
	API to check if total_amount is within available daily limit or covered by overlimit authorization.
	"""
	total_amount = flt(total_amount)
	limit_amount = flt(limit_amount)

	used_amount = get_daily_used_expense_amount(
		employee=employee,
		expense_category=expense_category,
		expense_date=expense_date,
		exclude_expense=expense_name,
	)
	available_limit = max(0.0, limit_amount - used_amount)

	if limit_amount <= 0 or total_amount <= available_limit:
		return {
			"is_overlimit": False,
			"allowed": True,
			"used_amount": used_amount,
			"available_limit": available_limit,
			"over_limit_amount": 0.0,
			"allowed_over_limit_amount": 0.0,
		}

	over_limit_amount = total_amount - available_limit
	allowed_over_limit = get_allowed_over_limit_amount(employee, expense_category, expense_date)

	if allowed_over_limit is not None and over_limit_amount <= flt(allowed_over_limit):
		return {
			"is_overlimit": True,
			"allowed": True,
			"used_amount": used_amount,
			"available_limit": available_limit,
			"over_limit_amount": over_limit_amount,
			"allowed_over_limit_amount": flt(allowed_over_limit),
		}

	return {
		"is_overlimit": True,
		"allowed": False,
		"used_amount": used_amount,
		"available_limit": available_limit,
		"over_limit_amount": over_limit_amount,
		"allowed_over_limit_amount": flt(allowed_over_limit) if allowed_over_limit is not None else 0.0,
		"message": _("The entered expense amount exceeds the allowed limit. Please contact the HR Team or your Reporting Manager for approval."),
	}


@frappe.whitelist()
def get_expense_limit(
	expense_category: str | None = None,
	city: str | None = None,
	employee: str | None = None,
	employee_grade: str | None = None,
	expense_date: str | None = None,
	expense_name: str | None = None,
):
	"""
	API endpoint to determine city category, limit type, limit amount, employee grade,
	and calculate daily used amount and available limit amount.
	"""
	if not employee_grade and employee:
		employee_grade = frappe.db.get_value("Employee", employee, "grade")

	city_category = get_city_category_for_city(city) if city else None
	limit_details = get_expense_limit_details(
		expense_category=expense_category,
		city=city,
		employee_grade=employee_grade,
		city_category=city_category,
	)

	limit_amount = flt(limit_details.get("limit_amount"))
	limit_type = limit_details.get("limit_type")
	per_km = is_per_km(limit_type)

	used_amount = 0.0
	available_limit = limit_amount

	if not per_km and limit_amount > 0:
		used_amount = get_daily_used_expense_amount(
			employee=employee,
			expense_category=expense_category,
			expense_date=expense_date,
			exclude_expense=expense_name,
		)
		available_limit = max(0.0, limit_amount - used_amount)

	return {
		"city_category": city_category,
		"employee_grade": employee_grade,
		"limit_type": limit_type,
		"limit_amount": limit_amount,
		"is_per_km": per_km,
		"used_amount": used_amount,
		"available_limit": available_limit,
	}


def get_city_category_for_city(city):
	"""
	Find the City Category for a given City using Frappe Python API.
	First checks if the city exists in any City Category's child table.
	If not found, falls back to the City Category where `is_other_city` is enabled (1).
	"""
	if not city:
		return None

	# Find category where city is present in City Category Table child rows
	parent_category = frappe.db.get_value(
		"City Category Table",
		filters={"city": city, "parenttype": "City Category"},
		fieldname="parent",
	)

	if parent_category:
		return parent_category

	# Fallback to the City Category where is_other_city is enabled
	other_category = frappe.db.get_value("City Category", {"is_other_city": 1}, "name")
	return other_category


def get_expense_limit_details(expense_category, city=None, employee_grade=None, city_category=None):
	"""
	Fetch limit details (limit_type, limit_amount) from custom_expense_limit_details in Expense Claim Type
	matching employee_grade and city_category using Frappe Python API.
	"""
	if not expense_category:
		return {"limit_type": None, "limit_amount": 0.0}

	if not city_category and city:
		city_category = get_city_category_for_city(city)

	if not employee_grade or not city_category:
		return {"limit_type": None, "limit_amount": 0.0}

	row = frappe.db.get_value(
		"Expense Limit Details",
		filters={
			"parent": expense_category,
			"parenttype": "Expense Claim Type",
			"parentfield": "custom_expense_limit_details",
			"employee_grade": employee_grade,
			"city_category": city_category,
		},
		fieldname=["limit_type", "limit_amount"],
		as_dict=True,
	)

	if row:
		return {
			"limit_type": row.get("limit_type"),
			"limit_amount": flt(row.get("limit_amount")),
		}

	return {"limit_type": None, "limit_amount": 0.0}


def get_expense_limit_amount(expense_category, city=None, employee_grade=None, city_category=None):
	details = get_expense_limit_details(expense_category, city, employee_grade, city_category)
	return flt(details.get("limit_amount"))
