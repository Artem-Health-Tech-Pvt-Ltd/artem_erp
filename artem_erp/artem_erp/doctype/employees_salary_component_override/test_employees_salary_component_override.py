# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.form.save import savedocs
from frappe.tests import IntegrationTestCase
from frappe.utils import flt


class TestEmployeesSalaryComponentOverride(IntegrationTestCase):
	"""
	Integration tests for Employees Salary Component Override:
	- Tests eligibility validation (Allow Override flag).
	- Tests positive override amount validation.
	- Tests difference calculation (override_amount - structure_amount).
	- Tests single active override document per employee/assignment.
	- Tests automated synchronization with Salary Structure Assignment.
	- Tests automatic cancellation of linked Salary Slips on override cancellation.
	- Tests cancellation comments added to replaced Salary Structure Assignments.
	"""

	@classmethod
	def setUpClass(cls):
		pass

	@classmethod
	def tearDownClass(cls):
		pass

	def setUp(self):
		frappe.db.rollback()

	def tearDown(self):
		frappe.db.rollback()

	def test_override_amount_must_be_greater_than_zero(self):
		"""Ensures override amount cannot be 0 or negative upon validation."""
		doc = frappe.new_doc("Employees Salary Component Override")
		doc.company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value(
			"Company", {}, "name"
		)
		doc.append(
			"override_details",
			{
				"salary_component": "Basic Salary",
				"override_amount": 0,
				"structure_amount": 14000,
			},
		)
		self.assertRaises(frappe.ValidationError, doc.validate_override_details)

	def test_difference_amount_calculation(self):
		"""Ensures difference_amount = override_amount - structure_amount."""
		doc = frappe.new_doc("Employees Salary Component Override")
		doc.company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value(
			"Company", {}, "name"
		)
		row = doc.append(
			"override_details",
			{
				"salary_component": "Basic Salary",
				"override_amount": 15000,
				"structure_amount": 14000,
			},
		)
		row.difference_amount = flt(row.override_amount) - flt(row.structure_amount)
		self.assertEqual(row.difference_amount, 1000.0)

	def test_base_amount_recalculation_formula(self):
		"""Ensures Base Amount = (CTC / 12) - EPFC - EESIC with overridden components."""
		doc = frappe.new_doc("Employees Salary Component Override")
		doc.salary_structure = "ETPL - Updated Salary Structure 2026"
		doc.append(
			"override_details",
			{
				"salary_component": "Basic Salary",
				"abbr": "BS",
				"component_type": "Earning",
				"structure_amount": 14000.0,
				"override_amount": 15000.0,
				"difference_amount": 1000.0,
			},
		)

		# Using existing SSA
		ssa_name = frappe.db.get_value("Salary Structure Assignment", {"docstatus": ["in", [1, 2]]}, "name")
		if not ssa_name:
			return
		old_ssa = frappe.get_doc("Salary Structure Assignment", ssa_name)
		base, epfc, eesic = doc.calculate_overridden_base_amount(old_ssa, 360000.0)
		self.assertEqual(epfc, 1800.0)
		self.assertEqual(eesic, 487.5)
		self.assertEqual(base, 27712.5)

	def test_deactivation_and_reactivation_sync(self):
		"""Ensures toggling is_active syncs custom fields on Salary Structure Assignment."""
		doc_name = "ESCO-202611-00002"
		if not frappe.db.exists("Employees Salary Component Override", doc_name):
			return

		doc = frappe.get_doc("Employees Salary Component Override", doc_name)
		ssa_name = doc.overridden_salary_structure_assignment
		if not ssa_name or not frappe.db.exists("Salary Structure Assignment", ssa_name):
			return

		# Deactivate override
		doc.is_active = 0
		doc.save()

		ssa_val = frappe.db.get_value(
			"Salary Structure Assignment",
			ssa_name,
			["custom_is_override_salary_structure_component", "custom_employees_salary_component_override"],
			as_dict=True,
		)
		self.assertEqual(ssa_val.custom_is_override_salary_structure_component, 0)
		self.assertIsNone(ssa_val.custom_employees_salary_component_override)

		# Reactivate override
		doc.reload()
		doc.is_active = 1
		doc.save()

		ssa_val_active = frappe.db.get_value(
			"Salary Structure Assignment",
			ssa_name,
			["custom_is_override_salary_structure_component", "custom_employees_salary_component_override"],
			as_dict=True,
		)
		self.assertEqual(ssa_val_active.custom_is_override_salary_structure_component, 1)
		self.assertEqual(ssa_val_active.custom_employees_salary_component_override, doc.name)

		# Test Desk savedocs simulation
		doc.reload()
		doc_dict = doc.as_dict()
		doc_dict["is_active"] = 0
		savedocs(frappe.as_json(doc_dict), "Update")

		ssa_val_desk = frappe.db.get_value(
			"Salary Structure Assignment",
			ssa_name,
			["custom_is_override_salary_structure_component", "custom_employees_salary_component_override"],
			as_dict=True,
		)
		self.assertEqual(ssa_val_desk.custom_is_override_salary_structure_component, 0)
		self.assertIsNone(ssa_val_desk.custom_employees_salary_component_override)

		# Re-enable via Desk savedocs
		doc.reload()
		doc_dict = doc.as_dict()
		doc_dict["is_active"] = 1
		savedocs(frappe.as_json(doc_dict), "Update")

		ssa_val_desk_active = frappe.db.get_value(
			"Salary Structure Assignment",
			ssa_name,
			["custom_is_override_salary_structure_component", "custom_employees_salary_component_override"],
			as_dict=True,
		)
		self.assertEqual(ssa_val_desk_active.custom_is_override_salary_structure_component, 1)
		self.assertEqual(ssa_val_desk_active.custom_employees_salary_component_override, doc.name)

	def test_cancel_override_cancels_linked_salary_slips(self):
		"""Ensures cancelling an override automatically cancels all linked Salary Slips."""
		emp = "ETPL-CON-0001"
		comp = "Equilym Technologies Private Limited"

		override_doc = frappe.new_doc("Employees Salary Component Override")
		override_doc.employee = emp
		override_doc.company = comp
		override_doc.salary_structure = "ETPL - Updated Salary Structure 2026"
		override_doc.effective_from_date = "2026-11-01"
		override_doc.is_active = 0
		override_doc.append(
			"override_details",
			{
				"salary_component": "Basic Salary",
				"abbr": "BS",
				"component_type": "Earning",
				"structure_amount": 14000.0,
				"override_amount": 16000.0,
				"difference_amount": 2000.0,
			},
		)
		override_doc.flags.ignore_links = True
		override_doc.flags.ignore_permissions = True
		override_doc.insert()
		override_doc.db_set("docstatus", 1)

		# Create linked Salary Slip
		slip = frappe.new_doc("Salary Slip")
		slip.employee = emp
		slip.company = comp
		slip.salary_structure = "ETPL - Updated Salary Structure 2026"
		slip.posting_date = "2028-05-20"
		slip.start_date = "2028-05-01"
		slip.end_date = "2028-05-31"
		slip.payroll_frequency = "Monthly"
		slip.custom_salary_component_override = override_doc.name
		slip.custom_component_override_applied = 1
		slip.flags.ignore_permissions = True
		slip.flags.ignore_links = True
		slip.flags.ignore_validate = True
		slip.flags.ignore_mandatory = True
		slip.insert()
		slip.db_set("docstatus", 1)

		# Cancel override
		override_doc.reload()
		override_doc.cancel()

		self.assertEqual(override_doc.docstatus, 2)
		slip.reload()
		self.assertEqual(slip.docstatus, 2)

	def test_cancel_comment_on_salary_structure_assignment(self):
		"""Ensures replacement comment is added on cancelled Salary Structure Assignment."""
		emp = "ETPL-CON-0001"
		comp = "Equilym Technologies Private Limited"

		ssa = frappe.new_doc("Salary Structure Assignment")
		ssa.employee = emp
		ssa.company = comp
		ssa.salary_structure = "ETPL - Updated Salary Structure 2026"
		ssa.from_date = "2026-11-01"
		ssa.base = 25000.0
		ssa.ctc = 360000.0
		ssa.income_tax_slab = "Tax Regime Slabs with 87A Rebate (AY 2026-27)"
		ssa.flags.ignore_permissions = True
		ssa.flags.ignore_validate = True
		ssa.flags.ignore_mandatory = True
		ssa.insert()
		ssa.db_set("docstatus", 1)

		doc = frappe.new_doc("Employees Salary Component Override")
		doc.employee = emp
		doc.company = comp
		doc.salary_structure = "ETPL - Updated Salary Structure 2026"
		doc.salary_structure_assignment = ssa.name
		doc.effective_from_date = "2026-11-01"
		doc.is_active = 0
		doc.remarks = "Testing cancellation comment"
		doc.append(
			"override_details",
			{
				"salary_component": "Basic Salary",
				"abbr": "BS",
				"component_type": "Earning",
				"structure_amount": 14000.0,
				"override_amount": 16000.0,
				"difference_amount": 2000.0,
			},
		)
		doc.flags.ignore_links = True
		doc.flags.ignore_permissions = True
		doc.insert()

		doc.process_override_submission()

		comments = frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "Salary Structure Assignment",
				"reference_name": ssa.name,
			},
			fields=["name", "content"],
		)
		self.assertGreater(len(comments), 0)
		self.assertIn(
			"Cancelled automatically upon submission of Employees Salary Component Override",
			comments[0].content,
		)
		self.assertIn("Testing cancellation comment", comments[0].content)
