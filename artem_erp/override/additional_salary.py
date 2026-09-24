import frappe
from frappe import _, bold
from frappe.utils import add_months, comma_and, date_diff, flt, formatdate, get_link_to_form, getdate

from hrms.payroll.doctype.additional_salary.additional_salary import AdditionalSalary


def get_employee_joining_date(employee):
	if not employee:
		return None
	if frappe.get_meta("Employee").has_field("date_of_joining"):
		return (
			frappe.db.get_value("Employee", employee, "date_of_joining")
		)
	return frappe.db.get_value("Employee", employee, "date_of_joining")


class CustomAdditionalSalary(AdditionalSalary):
	def validate(self):
		super().validate()
  

	def validate_previous_additional_salary_to_date(self):
		if not self.employee or not self.salary_component or self.docstatus == 2:
			return

		salary = frappe.qb.DocType("Additional Salary")
		query = (
			frappe.qb.from_(salary)
			.select(salary.name)
			.where(
				(salary.employee == self.employee)
				& (salary.salary_component == self.salary_component)
				& (salary.is_recurring == 1)
				& (
					salary.to_date.isnull()
					| (salary.to_date == "")
					| (salary.to_date == "0000-00-00")
				)
				& (salary.docstatus != 2)
				& (salary.disabled == 0)
			)
			.limit(1)
		)

		if self.name:
			query = query.where(salary.name != self.name)

		previous_active = query.run(as_dict=True)

		if previous_active:
			frappe.throw(
				_(
					"Previous Additional Salary To Date is not set. Please set the To Date of the previous Additional Salary before creating a new Additional Salary for this employee."
				)
			)

	def before_update_after_submit(self):
		super().before_update_after_submit()
		self.validate_dates()
		self.validate_previous_additional_salary_to_date()

	def before_validate(self):
		super().before_validate()
		if self.employee and not self.custom_date_of_joining:
			self.custom_date_of_joining = get_employee_joining_date(self.employee)
		if self.employee and (not self.custom_annual_gross_earning or not self.custom_ctc):
			ssa = frappe.db.get_value(
				"Salary Structure Assignment",
				{"employee": self.employee, "docstatus": 1},
				["annual_gross_earning", "ctc"],
				order_by="from_date desc",
				as_dict=True,
			)
			if ssa:
				if not self.custom_annual_gross_earning:
					self.custom_annual_gross_earning = ssa.annual_gross_earning
				if not self.custom_ctc:
					self.custom_ctc = ssa.ctc

	def get_start_date(self):
		"""
		Priority 1: From Date
		Priority 2: Custom Date Of Joining (doc or Employee) / Date Of Joining
		"""
		if self.from_date:
			return getdate(self.from_date)

		joining_date = self.custom_date_of_joining
		if not joining_date and self.employee:
			joining_date = get_employee_joining_date(self.employee)

		if joining_date:
			return getdate(joining_date)

		return None

	def get_first_payment_date(self):
		"""
		The general formula is:
		First Payment Date = Start Date + Duration Interval
		"""
		start_date = self.get_start_date()
		if not start_date:
			return None

		if self.is_recurring and self.custom_duration_of_additional_salary in ("Quarterly", "Half Yearly", "Yearly"):
			duration_map = {"Quarterly": 3, "Half Yearly": 6, "Yearly": 12}
			interval = duration_map[self.custom_duration_of_additional_salary]
			return add_months(start_date, interval)

		return start_date

	def validate_dates(self):
		if self.from_date and self.to_date and getdate(self.to_date) <= getdate(self.from_date):
			frappe.throw(_("To Date must be greater than From Date."))

		if not self.is_recurring:
			super().validate_dates()
			return


		# Recurring Additional Salary Validation
		if not self.custom_duration_of_additional_salary:
			frappe.throw(_("Duration Of Additional Salary is mandatory for recurring type additional salaries."))

		if self.custom_duration_of_additional_salary not in ("Quarterly", "Half Yearly", "Yearly"):
			frappe.throw(_("Duration Of Additional Salary must be one of: Quarterly, Half Yearly, Yearly."))

		start_date = self.get_start_date()
		if not start_date:
			frappe.throw(_("Please provide From Date or ensure Employee Date of Joining is set."))

		if not self.amount or flt(self.amount) <= 0:
			frappe.throw(_("Amount should be greater than zero."))

		first_payment_date = self.get_first_payment_date()

		employee_details = frappe.db.get_value(
			"Employee", self.employee, ["date_of_joining", "relieving_date"], as_dict=True
		) or {}
		date_of_joining = employee_details.get("date_of_joining")
		relieving_date = employee_details.get("relieving_date")

		if self.from_date and self.to_date:
			self.validate_from_to_dates("from_date", "to_date")

		if self.to_date and first_payment_date and getdate(self.to_date) < getdate(first_payment_date):
			frappe.throw(
				_("To date can not be less than first payment date ({0}).").format(
					formatdate(first_payment_date)
				)
			)

		if relieving_date:
			if self.to_date and getdate(self.to_date) > getdate(relieving_date):
				frappe.throw(_("To date can not be greater than employee's relieving date."))
			if self.from_date and getdate(self.from_date) > getdate(relieving_date):
				frappe.throw(_("From date can not be greater than employee's relieving date."))
			if first_payment_date and getdate(first_payment_date) > getdate(relieving_date):
				frappe.throw(
					_("First payment date ({0}) can not be greater than employee's relieving date.").format(
						formatdate(first_payment_date)
					)
				)

	def validate_salary_structure(self):
		effective_from_date = self.payroll_date or self.from_date
		if self.is_recurring and not effective_from_date:
			effective_from_date = self.get_first_payment_date()

		salary_structure = frappe.db.get_value(
			"Salary Structure Assignment",
			{
				"employee": self.employee,
				"docstatus": 1,
				"from_date": ["<=", effective_from_date],
			},
			"salary_structure",
			order_by="from_date desc",
		)

		if not salary_structure:
			salary_structure = frappe.db.get_value(
				"Salary Structure Assignment",
				{
					"employee": self.employee,
					"docstatus": 1,
				},
				"salary_structure",
				order_by="from_date desc",
			)

		if not salary_structure:
			frappe.throw(
				_("There is no Salary Structure assigned to {0}. First assign a Salary Structure.").format(
					self.employee
				)
			)

		if self.overwrite_salary_structure_amount:
			is_structure_component = frappe.db.get_value(
				"Salary Detail",
				{
					"parenttype": "Salary Structure",
					"parent": salary_structure,
					"salary_component": self.salary_component,
				},
			)

			if not is_structure_component:
				self.overwrite_salary_structure_amount = 0
				frappe.msgprint(
					_(
						"Overwrite Salary Structure Amount is disabled as the Salary Component: {0} not part of the Salary Structure: {1}"
					).format(self.salary_component, salary_structure)
				)

	def validate_recurring_additional_salary_overlap(self):
		if not self.is_recurring:
			super().validate_recurring_additional_salary_overlap()
			return

		curr_start = self.get_first_payment_date()
		curr_end = getdate(self.to_date) if self.to_date else None

		existing_records = frappe.get_all(
			"Additional Salary",
			filters={
				"employee": self.employee,
				"name": ["!=", self.name],
				"docstatus": 1,
				"is_recurring": 1,
				"salary_component": self.salary_component,
				"disabled": 0,
			},
			fields=["name", "from_date", "to_date", "custom_date_of_joining"],
		)

		overlapping_salaries = []
		emp_doj = frappe.db.get_value("Employee", self.employee, "date_of_joining")

		for rec in existing_records:
			rec_start = rec.from_date or rec.custom_date_of_joining or emp_doj
			if rec_start:
				rec_start = getdate(rec_start)
			rec_end = getdate(rec.to_date) if rec.to_date else None

			if not curr_start or not rec_start:
				continue

			# Check date range overlap
			starts_before_curr_ends = not curr_end or rec_start <= curr_end
			ends_after_curr_starts = not rec_end or rec_end >= curr_start

			if starts_before_curr_ends and ends_after_curr_starts:
				overlapping_salaries.append(rec.name)

		if overlapping_salaries:
			frappe.throw(
				_(
					"Additional Salary: {0} already exist for Salary Component: {1}."
				).format(
					bold(comma_and(overlapping_salaries)),
					bold(self.salary_component),
				)
			)

	def get_amount(self, sal_start_date, sal_end_date):
		if self.is_recurring and self.custom_duration_of_additional_salary:
			if self.to_date and getdate(sal_start_date) <= getdate(self.to_date) <= getdate(sal_end_date):
				if not is_recurring_additional_salary_due(self, sal_start_date, sal_end_date):
					return calculate_concluding_recurring_additional_salary_amount(self, sal_start_date, sal_end_date)
			return self.amount
		return super().get_amount(sal_start_date, sal_end_date)


def get_recurring_additional_salary_due_date(start_date, end_date, base_start, duration, to_date=None):
	"""
	Calculates and returns the first recurring Additional Salary due date
	that falls within the payroll period [start_date, end_date].

	Business Rules:
	1. base_start is strictly the cycle starting point (e.g. from_date or joining date).
	   It is NEVER treated as a payment date itself for Quarterly, Half Yearly, or Yearly.
	2. The first payment occurs only after one full interval has elapsed:
	   first_due_date = add_months(base_start, interval)
	3. Subsequent recurring payments occur at:
	   due_date = add_months(base_start, k * interval) for k = 1, 2, 3, ...
	   Anchoring to base_start with (k * interval) preserves month-end days (29th, 30th, 31st)
	   across varying month lengths without day-drifting.
	4. If an optional to_date is provided and the due date exceeds to_date, it is not due.
	5. Returns None if no recurring due date falls within [start_date, end_date].
	"""
	if not start_date or not end_date or not base_start:
		return None

	start_date = getdate(start_date)
	end_date = getdate(end_date)
	base_start = getdate(base_start)
	to_date = getdate(to_date) if to_date else None

	duration_map = {
		"Quarterly": 3,
		"Half Yearly": 6,
		"Yearly": 12,
	}

	if duration in duration_map:
		interval = duration_map[duration]
		# First due date starts after 1 interval (k = 1).
		# base_start is only the cycle starting point and is NOT a payment date.
		k = 1
	else:
		# Standard monthly recurrence (starts at k = 0, including base_start month)
		interval = 1
		k = 0

	while True:
		# Calculate each recurrence date strictly from base_start using add_months()
		due_date = add_months(base_start, k * interval)

		# Due dates are strictly chronological.
		# If the current due date is past end_date, no later due date can fall in this period.
		if due_date > end_date:
			return None

		# Check if due_date falls within [start_date, end_date]
		if due_date >= start_date:
			if to_date and due_date > to_date:
				return None
			return due_date

		k += 1


def is_recurring_additional_salary_due(doc, start_date, end_date):
	"""
	Check whether a recurring Additional Salary has a payment due in [start_date, end_date].
	"""
	start_date = getdate(start_date)
	end_date = getdate(end_date)

	from_date = doc.get("from_date")
	base_start_date = from_date
	if not base_start_date:
		base_start_date = doc.get("custom_date_of_joining")
	if not base_start_date and doc.get("employee"):
		base_start_date = get_employee_joining_date(doc.get("employee"))

	if not base_start_date:
		return False

	to_date = doc.get("to_date")
	duration = doc.get("custom_duration_of_additional_salary")

	due_date = get_recurring_additional_salary_due_date(
		start_date=start_date,
		end_date=end_date,
		base_start=base_start_date,
		duration=duration,
		to_date=to_date,
	)
	return bool(due_date)


def calculate_concluding_recurring_additional_salary_amount(doc, start_date, end_date):
	"""
	Calculates the cycle-prorated amount for a recurring Additional Salary
	whose to_date concludes within the payroll month [start_date, end_date]
	before the next scheduled recurrence due date.

	Calculation:
	1. Locate the cycle:
	   - prev_date: the payout date of the most recent cycle before to_date (or base_start if within 1st interval).
	   - next_date: the next scheduled payout date after to_date.
	2. Total days in cycle = date_diff(next_date, prev_date)
	3. Active days in cycle = date_diff(to_date, prev_date)
	4. Prorated amount = round((amount / total_days) * active_days, 2)

	Example:
	Quarterly salary with amount = 30,000.
	base_start = 22-03-2026, to_date = 10-10-2026.
	Payments were made on 22-06-2026, 22-09-2026.
	Next payment would have been 22-12-2026.
	prev_date = 22-09-2026, next_date = 22-12-2026 (91 days).
	Active days = 22-09-2026 to 10-10-2026 = 18 days.
	per_day_amount = 30,000 / 365
	eligible_amount = (30,000 / 365) * 18 * 4 = 5,917.81.
	"""
	if isinstance(doc, dict):
		d = doc
	else:
		d = doc.as_dict() if hasattr(doc, "as_dict") else doc

	from_date = d.get("from_date")
	base_start = from_date or d.get("custom_date_of_joining")
	if not base_start and d.get("employee"):
		base_start = get_employee_joining_date(d.get("employee"))

	if not base_start or not d.get("to_date"):
		return flt(d.get("amount", 0.0))

	base_start = getdate(base_start)
	to_date = getdate(d.get("to_date"))
	amount = flt(d.get("amount", 0.0))
	duration = d.get("custom_duration_of_additional_salary")

	duration_map = {
		"Quarterly": 3,
		"Half Yearly": 6,
		"Yearly": 12,
	}

	interval = duration_map.get(duration, 1)

	# For custom durations (Quarterly, Half Yearly, Yearly), the first payout is at k=1.
	# For standard monthly recurrence, interval is 1 and starts at k=1 from base_start.
	k = 1
	prev_date = base_start
	next_date = add_months(base_start, interval)

	while next_date < to_date:
		prev_date = next_date
		k += 1
		next_date = add_months(base_start, k * interval)

	active_days = date_diff(to_date, prev_date)
	if active_days <= 0:
		return 0.0

	multiplier_map = {
		"Quarterly": 4,
		"Half Yearly": 2,
		"Yearly": 1,
	}
	cycle_multiplier = multiplier_map.get(duration, 1)

	per_day_amount = amount / 365
	eligible_amount = per_day_amount * active_days * cycle_multiplier
	return flt(eligible_amount, 2)


def get_custom_additional_salaries(employee, start_date, end_date, component_type):
	"""
	Replacement for get_additional_salaries with support for duration-based recurring additional salaries.
	"""
	comp_type = "Earning" if component_type == "earnings" else "Deduction"

	additional_sal = frappe.qb.DocType("Additional Salary")
	component_field = additional_sal.salary_component.as_("component")
	overwrite_field = additional_sal.overwrite_salary_structure_amount.as_("overwrite")

	# 1. Fetch non-recurring additional salaries falling within start_date and end_date
	non_recurring_list = (
		frappe.qb.from_(additional_sal)
		.select(
			additional_sal.name,
			component_field,
			additional_sal.type,
			additional_sal.amount,
			additional_sal.is_recurring,
			overwrite_field,
			additional_sal.deduct_full_tax_on_selected_payroll_date,
			additional_sal.ref_doctype,
			additional_sal.ref_docname,
		)
		.where(
			(additional_sal.employee == employee)
			& (additional_sal.docstatus == 1)
			& (additional_sal.type == comp_type)
			& (additional_sal.disabled == 0)
			& (additional_sal.is_recurring == 0)
			& (additional_sal.payroll_date[start_date:end_date])
		)
		.run(as_dict=True)
	)

	# 2. Fetch all active recurring additional salaries for this employee & component type
	recurring_candidates = (
		frappe.qb.from_(additional_sal)
		.select(
			additional_sal.name,
			component_field,
			additional_sal.type,
			additional_sal.amount,
			additional_sal.is_recurring,
			overwrite_field,
			additional_sal.deduct_full_tax_on_selected_payroll_date,
			additional_sal.ref_doctype,
			additional_sal.ref_docname,
			additional_sal.from_date,
			additional_sal.to_date,
			additional_sal.custom_duration_of_additional_salary,
			additional_sal.custom_date_of_joining,
			additional_sal.employee,
		)
		.where(
			(additional_sal.employee == employee)
			& (additional_sal.docstatus == 1)
			& (additional_sal.type == comp_type)
			& (additional_sal.disabled == 0)
			& (additional_sal.is_recurring == 1)
		)
		.run(as_dict=True)
	)

	recurring_list = []
	for d in recurring_candidates:
		# Check if due in this payroll period
		is_due = is_recurring_additional_salary_due(d, start_date, end_date)
		if not is_due and d.to_date and start_date <= getdate(d.to_date) <= end_date:
			is_due = True
			d.amount = calculate_concluding_recurring_additional_salary_amount(d, start_date, end_date)

		if not is_due:
			continue

		# Prevent duplicate payment: check if already paid in a submitted Salary Slip
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
			(employee, d.name, end_date, start_date),
		)
		if already_paid:
			continue

		recurring_list.append(d)

	additional_salaries = []
	components_to_overwrite = []
	seen_salaries = set()

	for d in non_recurring_list + recurring_list:
		if d.name in seen_salaries:
			continue
		seen_salaries.add(d.name)

		if d.overwrite:
			if d.component in components_to_overwrite:
				frappe.throw(
					_(
						"Multiple Additional Salaries with overwrite property exist for Salary Component {0} between {1} and {2}."
					).format(frappe.bold(d.component), start_date, end_date),
					title=_("Error"),
				)

			components_to_overwrite.append(d.component)

		additional_salaries.append(d)

	return additional_salaries

