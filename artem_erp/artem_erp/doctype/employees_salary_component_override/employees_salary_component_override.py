# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_link_to_form, getdate
from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
	COMPONENT_EVAL_GLOBALS,
	_safe_eval,
	sanitize_expression,
)


class EmployeesSalaryComponentOverride(Document):
	def _validate_links(self):
		if self.docstatus == 1:
			self.flags.ignore_links = True
			return
		super()._validate_links()

	def validate(self):
		if self.docstatus == 1 and getattr(self, "_action", None) != "submit":
			self.flags.ignore_links = True
			if cint(self.is_active):
				self.validate_single_active_override()
			return

		self.set_assignment_and_structure()
		self.validate_employee_and_company()
		self.validate_override_details()
		self.validate_single_active_override()

	def before_update_after_submit(self):
		self.flags.ignore_links = True
		if cint(self.is_active):
			self.validate_single_active_override()

	def set_assignment_and_structure(self):
		if not self.employee:
			return

		if not self.salary_structure_assignment or not self.salary_structure:
			details = get_active_assignment_details(self.employee, self.effective_from_date)
			if details:
				if not self.salary_structure_assignment:
					self.salary_structure_assignment = details.get("salary_structure_assignment")
				if not self.salary_structure:
					self.salary_structure = details.get("salary_structure")
				if not self.company:
					self.company = details.get("company")

		if not self.salary_structure_assignment:
			frappe.throw(
				_("No submitted Salary Structure Assignment found for Employee {0}.").format(
					frappe.bold(self.employee)
				)
			)

	def validate_employee_and_company(self):
		if self.employee and self.company:
			emp_company = frappe.db.get_value("Employee", self.employee, "company")
			if emp_company and emp_company != self.company:
				frappe.throw(
					_("Employee {0} belongs to company {1}, but selected company is {2}.").format(
						frappe.bold(self.employee), frappe.bold(emp_company), frappe.bold(self.company)
					)
				)

	def validate_override_details(self):
		# Clean out any blank rows before validating
		if self.get("override_details"):
			valid_rows = [row for row in self.override_details if row.salary_component]
			if len(valid_rows) != len(self.override_details):
				self.set("override_details", valid_rows)

		if not self.get("override_details"):
			frappe.throw(_("Please add at least one salary component to override."))

		eligible_components = get_eligible_components(
			self.salary_structure,
			salary_structure_assignment=self.salary_structure_assignment,
			employee=self.employee,
		)
		eligible_map = {d["salary_component"]: d for d in eligible_components}

		seen_components = set()
		for row in self.override_details:
			if not row.salary_component:
				frappe.throw(_("Row #{0}: Salary Component is mandatory.").format(row.idx))

			if row.salary_component in seen_components:
				frappe.throw(
					_(
						"Salary Component {0} is added multiple times. Each component can only be overridden once."
					).format(frappe.bold(row.salary_component))
				)
			seen_components.add(row.salary_component)

			# Validate positive override amount (Rule 5)
			if flt(row.override_amount) <= 0:
				frappe.throw(
					_("Override Amount for component {0} must be strictly greater than zero.").format(
						frappe.bold(row.salary_component)
					)
				)

			# Verify component is eligible in this Salary Structure
			if self.salary_structure and row.salary_component not in eligible_map:
				frappe.throw(
					_(
						"Salary Component {0} is not eligible for override in Salary Structure {1}. "
						"Only components with 'Allow Override' enabled can be overridden."
					).format(frappe.bold(row.salary_component), frappe.bold(self.salary_structure))
				)

			# Auto-fill structure amount, abbr, component_type, and difference
			info = eligible_map.get(row.salary_component) or {}
			if not row.abbr:
				row.abbr = info.get("abbr")
			if not row.component_type:
				row.component_type = info.get("component_type")

			row.structure_amount = flt(info.get("structure_amount", row.structure_amount))
			row.difference_amount = flt(row.override_amount) - flt(row.structure_amount)

	def validate_single_active_override(self):
		if not cint(self.is_active) or self.docstatus != 1:
			return

		filters = {
			"employee": self.employee,
			"salary_structure": self.salary_structure,
			"docstatus": 1,
			"is_active": 1,
			"name": ["!=", self.name],
		}

		existing_active = frappe.db.get_value("Employees Salary Component Override", filters, "name")
		if existing_active:
			frappe.throw(
				_(
					"Employee {0} already has an active component override ({1}) for Salary Structure {2}. "
					"Please deactivate the existing override before activating this one."
				).format(
					frappe.bold(self.employee),
					frappe.bold(existing_active),
					frappe.bold(self.salary_structure),
				)
			)

	def on_submit(self):
		self.validate_single_active_override()
		if not cint(self.is_active):
			frappe.throw(_("Activate the salary component override before submitting it."))
		self.process_override_submission()

	def process_override_submission(self):
		if not self.salary_structure_assignment:
			frappe.throw(_("Salary Structure Assignment is mandatory to submit component overrides."))

		if not frappe.db.exists("Salary Structure Assignment", self.salary_structure_assignment):
			frappe.throw(
				_("Linked Salary Structure Assignment {0} does not exist.").format(
					frappe.bold(self.salary_structure_assignment)
				)
			)

		old_ssa = frappe.get_doc("Salary Structure Assignment", self.salary_structure_assignment)
		if (
			old_ssa.docstatus != 1
			or old_ssa.employee != self.employee
			or old_ssa.company != self.company
			or old_ssa.salary_structure != self.salary_structure
		):
			frappe.throw(
				_(
					"The Salary Structure Assignment must be submitted and match the employee, company, and salary structure."
				)
			)

		# 1. Calculate the Base Amount = (CTC / 12) - EPFC - EESIC
		ctc = flt(old_ssa.ctc)
		if ctc <= 0:
			frappe.throw(
				_("Salary Structure Assignment {0} must have a positive CTC before applying component overrides.").format(
					frappe.bold(old_ssa.name)
				)
			)

		base_amount, epfc, eesic = self.calculate_overridden_base_amount(old_ssa, ctc)

		# 2. Cancel the Existing Salary Structure Assignment
		if old_ssa.docstatus == 1:
			old_ssa.ignore_linked_doctypes = ["Employees Salary Component Override"]
			old_ssa.flags.ignore_permissions = True
			old_ssa.cancel()

		# 3. Create an Amended Salary Structure Assignment
		new_ssa = frappe.copy_doc(old_ssa)
		new_ssa.docstatus = 0
		new_ssa.amended_from = old_ssa.name
		new_ssa.base = base_amount
		new_ssa.custom_is_override_salary_structure_component = 1
		new_ssa.custom_employees_salary_component_override = self.name
		new_ssa.flags.ignore_permissions = True
		new_ssa.insert()
		new_ssa.submit()

		# Add cancellation reason comment in the cancelled Salary Structure Assignment
		try:
			comment_lines = [
				_(
					"Cancelled automatically upon submission of Employees Salary Component Override {0}."
				).format(get_link_to_form("Employees Salary Component Override", self.name)),
				_(
					"Amended assignment {0} created with recalculated Base Amount ₹{1:,.2f} (EPFC: ₹{2:,.2f}, EESIC: ₹{3:,.2f})."
				).format(
					get_link_to_form("Salary Structure Assignment", new_ssa.name),
					base_amount,
					epfc,
					eesic,
				),
			]
			if getattr(self, "remarks", None):
				comment_lines.append(_("Reason / Remarks: {0}").format(self.remarks))

			old_ssa.add_comment("Comment", "<br>".join(comment_lines))
		except Exception:
			frappe.log_error(
				title="Failed to add cancellation comment to old SSA",
				message=frappe.get_traceback(),
			)

		# 4. Update the Employee Salary Component Override Document
		self.overridden_salary_structure_assignment = new_ssa.name
		self.db_set("overridden_salary_structure_assignment", new_ssa.name)

		frappe.msgprint(
			_(
				"Cancelled Salary Structure Assignment {0} and created amended assignment {1} with recalculated Base Amount ₹{2:,.2f} (EPFC: ₹{3:,.2f}, EESIC: ₹{4:,.2f})."
			).format(
				get_link_to_form("Salary Structure Assignment", old_ssa.name),
				get_link_to_form("Salary Structure Assignment", new_ssa.name),
				base_amount,
				epfc,
				eesic,
			),
			title=_("Assignment Amended"),
			indicator="green",
		)

	def calculate_overridden_base_amount(self, old_ssa, ctc):
		"""
		Recalculates monthly base amount using:
		Base Amount = (CTC / 12) - EPFC - EESIC
		Employer PF Contributions (EPFC) and Employer ESI (EESIC) are calculated
		using the formulas defined in the linked Salary Structure, considering
		overridden component amounts.
		"""
		ss_name = old_ssa.salary_structure or self.salary_structure
		ss = frappe.get_cached_doc("Salary Structure", ss_name)

		# Build formula evaluation context from SSA
		data = (
			old_ssa._get_component_eval_context() if hasattr(old_ssa, "_get_component_eval_context") else {}
		)
		data["ctc"] = flt(ctc)

		# Map overrides
		overrides = {}
		overrides_abbr = {}
		for row in self.get("override_details") or []:
			if row.salary_component:
				overrides[row.salary_component] = flt(row.override_amount)
			if row.abbr:
				overrides_abbr[row.abbr] = flt(row.override_amount)

		# Inject overrides into context
		for comp, val in overrides.items():
			data[comp] = val
		for abbr, val in overrides_abbr.items():
			data[abbr] = val

		# Evaluate earnings (handling formulas that depend on overrides, e.g. HRA, AB)
		for e in ss.get("earnings") or []:
			if e.salary_component in overrides:
				val = overrides[e.salary_component]
			elif e.abbr and e.abbr in overrides_abbr:
				val = overrides_abbr[e.abbr]
			elif e.amount_based_on_formula and e.formula:
				cond = sanitize_expression(e.condition)
				if cond and not _safe_eval(cond, COMPONENT_EVAL_GLOBALS.copy(), data):
					continue
				formula = sanitize_expression(e.formula)
				val = flt(_safe_eval(formula, COMPONENT_EVAL_GLOBALS.copy(), data))
			else:
				val = flt(e.amount)

			if e.abbr:
				data[e.abbr] = val
			data[e.salary_component] = val

		data["gross_pay"] = sum(
			flt(data.get(e.abbr, 0.0))
			for e in (ss.get("earnings") or [])
			if not e.statistical_component and not e.do_not_include_in_total and e.abbr
		)

		# Evaluate employer contributions
		epfc = 0.0
		eesic = 0.0
		for ec in ss.get("employer_contributions") or []:
			cond = sanitize_expression(ec.condition)
			if cond and not _safe_eval(cond, COMPONENT_EVAL_GLOBALS.copy(), data):
				continue

			formula = sanitize_expression(ec.formula)
			if ec.salary_component in overrides:
				val = overrides[ec.salary_component]
			elif ec.abbr and ec.abbr in overrides_abbr:
				val = overrides_abbr[ec.abbr]
			elif ec.amount_based_on_formula and formula:
				val = flt(_safe_eval(formula, COMPONENT_EVAL_GLOBALS.copy(), data))
			else:
				val = flt(ec.amount)

			if ec.abbr:
				data[ec.abbr] = val
			data[ec.salary_component] = val

			abbr_upper = (ec.abbr or "").upper().strip()
			comp_upper = (ec.salary_component or "").upper().strip()
			if (
				abbr_upper == "EPFC"
				or "EMPLOYER PF" in comp_upper
				or ("PF" in comp_upper and "EMPLOYER" in comp_upper)
			):
				epfc = val
			elif (
				abbr_upper in ("EESIC", "ESI-ER")
				or "EMPLOYER ESI" in comp_upper
				or ("ESI" in comp_upper and "EMPLOYER" in comp_upper)
			):
				eesic = val

		if not epfc and "EPFC" in data:
			epfc = flt(data["EPFC"])
		if not eesic and "EESIC" in data:
			eesic = flt(data["EESIC"])

		monthly_ctc = flt(ctc) / 12.0
		base_amount = flt(monthly_ctc - epfc - eesic, 2)
		return base_amount, epfc, eesic

	def before_cancel(self):
		self.ignore_linked_doctypes = ["Salary Structure Assignment", "Salary Slip"]
		self.flags.ignore_links = True

	def on_cancel(self):
		self.ignore_linked_doctypes = ["Salary Structure Assignment", "Salary Slip"]
		self.flags.ignore_links = True

		# 1. Cancel linked Salary Slips
		self.cancel_linked_salary_slips()

		# 2. If the overridden assignment was submitted, cancel it
		if getattr(self, "overridden_salary_structure_assignment", None):
			if frappe.db.exists("Salary Structure Assignment", self.overridden_salary_structure_assignment):
				overridden_status = frappe.db.get_value(
					"Salary Structure Assignment", self.overridden_salary_structure_assignment, "docstatus"
				)
				if overridden_status == 1:
					overridden_doc = frappe.get_doc(
						"Salary Structure Assignment", self.overridden_salary_structure_assignment
					)
					overridden_doc.flags.ignore_permissions = True
					overridden_doc.cancel()
					try:
						overridden_doc.add_comment(
							"Comment",
							_(
								"Cancelled automatically upon cancellation of Employees Salary Component Override {0}."
							).format(get_link_to_form("Employees Salary Component Override", self.name)),
						)
					except Exception:
						pass

		self.unlink_from_salary_structure_assignments()
		self.unlink_from_salary_slips()

	def cancel_linked_salary_slips(self):
		linked_slips = frappe.get_all(
			"Salary Slip",
			filters={
				"custom_salary_component_override": self.name,
				"docstatus": ["<", 2],
			},
			fields=["name", "docstatus"],
		)
		cancelled_slips = []
		for slip in linked_slips:
			slip_doc = frappe.get_doc("Salary Slip", slip.name)
			slip_doc.flags.ignore_permissions = True
			if slip.docstatus == 1:
				slip_doc.cancel()
				try:
					slip_doc.add_comment(
						"Comment",
						_(
							"Cancelled automatically upon cancellation of Employees Salary Component Override {0}."
						).format(get_link_to_form("Employees Salary Component Override", self.name)),
					)
				except Exception:
					pass
				cancelled_slips.append(slip.name)
			elif slip.docstatus == 0:
				slip_doc.discard()
				try:
					slip_doc.add_comment(
						"Comment",
						_(
							"Discarded automatically upon cancellation of Employees Salary Component Override {0}."
						).format(get_link_to_form("Employees Salary Component Override", self.name)),
					)
				except Exception:
					pass
				cancelled_slips.append(slip.name)

		if cancelled_slips:
			frappe.msgprint(
				_("Cancelled linked Salary Slip(s): {0}").format(
					", ".join(get_link_to_form("Salary Slip", s) for s in cancelled_slips)
				),
				title=_("Salary Slips Cancelled"),
				indicator="orange",
			)

	def on_trash(self):
		self.unlink_from_salary_structure_assignments()
		self.unlink_from_salary_slips()

	def unlink_from_salary_slips(self):
		linked_slips = frappe.get_all(
			"Salary Slip",
			filters={"custom_salary_component_override": self.name},
			pluck="name",
		)
		for slip_name in linked_slips:
			frappe.db.set_value(
				"Salary Slip",
				slip_name,
				{
					"custom_salary_component_override": None,
					"custom_component_override_applied": 0,
				},
				update_modified=False,
			)

	def unlink_from_salary_structure_assignments(self):
		# 1. Clear any SSA referencing this override document
		linked_ssas = frappe.get_all(
			"Salary Structure Assignment",
			filters={"custom_employees_salary_component_override": self.name},
			pluck="name",
		)
		target_ssas = set(linked_ssas)
		if getattr(self, "salary_structure_assignment", None):
			target_ssas.add(self.salary_structure_assignment)
		if getattr(self, "overridden_salary_structure_assignment", None):
			target_ssas.add(self.overridden_salary_structure_assignment)

		for ssa_name in target_ssas:
			if ssa_name and frappe.db.exists("Salary Structure Assignment", ssa_name):
				frappe.db.set_value(
					"Salary Structure Assignment",
					ssa_name,
					{
						"custom_is_override_salary_structure_component": 0,
						"custom_employees_salary_component_override": None,
					},
					update_modified=False,
				)

		# 2. Clear links on self so self does not prevent deleting referenced SSAs
		frappe.db.set_value(
			"Employees Salary Component Override",
			self.name,
			{
				"salary_structure_assignment": None,
				"overridden_salary_structure_assignment": None,
			},
			update_modified=False,
		)

	def on_update_after_submit(self):
		self.sync_active_status_with_salary_structure_assignment()

	def on_update(self):
		# If user changes is_active on submitted document
		if self.docstatus == 1:
			self.sync_active_status_with_salary_structure_assignment()

	def sync_active_status_with_salary_structure_assignment(self):
		active_assignment = self.overridden_salary_structure_assignment or self.salary_structure_assignment
		if self.overridden_salary_structure_assignment:
			overridden_status = frappe.db.get_value(
				"Salary Structure Assignment", self.overridden_salary_structure_assignment, "docstatus"
			)
			if overridden_status == 1:
				active_assignment = self.overridden_salary_structure_assignment

		if cint(self.is_active):
			self.validate_single_active_override()
			if active_assignment and frappe.db.exists("Salary Structure Assignment", active_assignment):
				frappe.db.set_value(
					"Salary Structure Assignment",
					active_assignment,
					{
						"custom_is_override_salary_structure_component": 1,
						"custom_employees_salary_component_override": self.name,
					},
					update_modified=False,
				)
		else:
			# Option 1: Remove reference from linked Salary Structure Assignment
			target_ssas = set()
			if self.overridden_salary_structure_assignment:
				target_ssas.add(self.overridden_salary_structure_assignment)
			if self.salary_structure_assignment:
				target_ssas.add(self.salary_structure_assignment)

			linked_ssas = frappe.get_all(
				"Salary Structure Assignment",
				filters={"custom_employees_salary_component_override": self.name},
				pluck="name",
			)
			target_ssas.update(linked_ssas)

			for ssa_name in target_ssas:
				if ssa_name and frappe.db.exists("Salary Structure Assignment", ssa_name):
					frappe.db.set_value(
						"Salary Structure Assignment",
						ssa_name,
						{
							"custom_is_override_salary_structure_component": 0,
							"custom_employees_salary_component_override": None,
						},
						update_modified=False,
					)


@frappe.whitelist()
def get_active_assignment_details(
	employee: str | None = None,
	effective_date: str | None = None,
) -> dict:
	if not employee:
		return {}

	effective_date = getdate(effective_date) if effective_date else getdate()

	ssa_list = frappe.get_all(
		"Salary Structure Assignment",
		filters={
			"employee": employee,
			"docstatus": 1,
			"from_date": ["<=", effective_date],
		},
		fields=["name", "salary_structure", "company", "from_date", "base", "variable"],
		order_by="from_date desc",
		limit=1,
	)

	if not ssa_list:
		# Fallback to any latest submitted assignment
		ssa_list = frappe.get_all(
			"Salary Structure Assignment",
			filters={
				"employee": employee,
				"docstatus": 1,
			},
			fields=["name", "salary_structure", "company", "from_date", "base", "variable"],
			order_by="from_date desc",
			limit=1,
		)

	if not ssa_list:
		return {}

	ssa = ssa_list[0]
	return {
		"salary_structure_assignment": ssa.name,
		"salary_structure": ssa.salary_structure,
		"company": ssa.company,
		"from_date": ssa.from_date,
	}


@frappe.whitelist()
def get_eligible_components(
	salary_structure: str | None = None,
	salary_structure_assignment: str | None = None,
	employee: str | None = None,
) -> list[dict]:
	if not salary_structure:
		return []

	if not salary_structure_assignment and employee:
		details = get_active_assignment_details(employee)
		if details:
			salary_structure_assignment = details.get("salary_structure_assignment")

	evaluated_map = {}
	if salary_structure_assignment:
		try:
			ssa_doc = frappe.get_doc("Salary Structure Assignment", salary_structure_assignment)
			ssa_doc.flags.ignore_overrides = True
			evaluated = ssa_doc.get_evaluated_components()
			for comp_type_key in ("earnings", "deductions", "employer_contributions"):
				for row in evaluated.get(comp_type_key) or []:
					comp_name = row.get("salary_component")
					if comp_name:
						evaluated_map[comp_name] = flt(row.get("default_amount", row.get("amount")))
		except Exception as e:
			frappe.log_error(
				title="Salary Component Override",
				message=f"Error evaluating components for SSA {salary_structure_assignment}: {e}",
			)

	ss = frappe.get_cached_doc("Salary Structure", salary_structure)
	eligible = []
	seen = set()

	def check_and_add(row, comp_type):
		comp_name = row.salary_component
		if comp_name in seen:
			return

		allow_override = cint(row.get("custom_allow_override"))
		if not allow_override:
			allow_override = cint(
				frappe.get_cached_value("Salary Component", comp_name, "custom_allow_override")
			)

		if allow_override:
			abbr = row.get("abbr") or frappe.get_cached_value(
				"Salary Component", comp_name, "salary_component_abbr"
			)
			structure_amt = (
				evaluated_map[comp_name]
				if comp_name in evaluated_map
				else flt(row.get("amount") or row.get("max_benefit_amount", 0))
			)
			eligible.append(
				{
					"salary_component": comp_name,
					"abbr": abbr,
					"component_type": comp_type,
					"structure_amount": flt(structure_amt),
				}
			)
			seen.add(comp_name)

	for d in ss.get("earnings") or []:
		check_and_add(d, "Earning")

	for d in ss.get("deductions") or []:
		check_and_add(d, "Deduction")

	for d in ss.get("employer_contributions") or []:
		check_and_add(d, "Employer Contribution")

	for d in ss.get("employee_benefits") or []:
		check_and_add(d, "Earning")

	return eligible


@frappe.whitelist()
def get_eligible_components_query(
	doctype: str | None = None,
	txt: str | None = None,
	searchfield: str | None = None,
	start: int = 0,
	page_len: int = 20,
	filters: dict | None = None,
) -> list[tuple[str, str]]:
	salary_structure = filters.get("salary_structure") if filters else None
	if not salary_structure:
		return []

	eligible = get_eligible_components(
		salary_structure=salary_structure,
		salary_structure_assignment=filters.get("salary_structure_assignment") if filters else None,
		employee=filters.get("employee") if filters else None,
	)
	results = []
	for c in eligible:
		name = c["salary_component"]
		abbr = c["abbr"]
		if not txt or txt.lower() in name.lower() or (abbr and txt.lower() in abbr.lower()):
			results.append((name, abbr or ""))

	return results
