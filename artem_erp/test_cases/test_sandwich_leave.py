# Copyright (c) 2026, Artem Healthtech and Contributors
# See license.txt

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, getdate

from artem_erp.doc_events.sandwich_leave import (
	check_sandwich_condition,
	get_sandwich_exemptions_consumed,
	get_sandwich_settings,
)


class TestSandwichLeave(IntegrationTestCase):
	"""
	Comprehensive integration test suite for Artem ERP Sandwich Leave functionality.
	Tests cover:
	1. Detection of two-application sandwich conditions across weekends/holidays.
	2. Detection of single-application multi-day leaves with Include Holidays enabled.
	3. Exclusion rules: Half-Day, Partial Day, Optional Holidays, and working days in gaps.
	4. Validation rules: blocking unconfirmed saves, allowing confirmed saves, enforcing exemption quotas.
	5. Exemption adjustments: reducing total_leave_days and skipping sandwich generation.
	6. Workflow lifecycle: blocking non-sequential approvals, auto-generating sandwich records on approval.
	7. Synchronization: attendance marking for working days vs holidays, and cascading cancellations.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setting = frappe.get_doc("Artem Setting")
		cls.original_apply_rule = setting.apply_sandwich_leave_rule_on_leave
		cls.original_max_exemptions = setting.maximum_employee_exemptions

		frappe.db.set_single_value("Artem Setting", "apply_sandwich_leave_rule_on_leave", 1)
		frappe.db.set_single_value("Artem Setting", "maximum_employee_exemptions", 2)
		frappe.clear_document_cache("Artem Setting")
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_single_value(
			"Artem Setting", "apply_sandwich_leave_rule_on_leave", cls.original_apply_rule
		)
		frappe.db.set_single_value(
			"Artem Setting", "maximum_employee_exemptions", cls.original_max_exemptions
		)
		frappe.clear_document_cache("Artem Setting")
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		self.employee = "CON-002"
		self.approver = "Administrator"
		self.created_docs = []
		frappe.set_user("Administrator")

		# Default test configuration: rule enabled, 2 exemptions allowed
		frappe.db.set_single_value("Artem Setting", "apply_sandwich_leave_rule_on_leave", 1)
		frappe.db.set_single_value("Artem Setting", "maximum_employee_exemptions", 2)
		frappe.clear_document_cache("Artem Setting")

	def tearDown(self):
		# Clean up any test documents created during testing in reverse order
		for doctype, name in reversed(self.created_docs):
			try:
				if frappe.db.exists(doctype, name):
					doc = frappe.get_doc(doctype, name)
					if doc.docstatus == 1:
						has_wf = frappe.get_all(
							"Workflow", filters={"document_type": doctype, "is_active": 1}
						)
						if has_wf:
							apply_workflow(doc, "Cancel")
						else:
							doc.cancel()
					frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
			except Exception:
				pass

		frappe.db.rollback()
		frappe.db.set_single_value("Artem Setting", "apply_sandwich_leave_rule_on_leave", 1)
		frappe.db.set_single_value("Artem Setting", "maximum_employee_exemptions", 2)
		frappe.clear_document_cache("Artem Setting")
		frappe.db.commit()  # nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		super().tearDown()

	def _create_leave_application(
		self,
		leave_type: str,
		from_date: str,
		to_date: str,
		description: str = "Test Leave",
		half_day: int = 0,
		half_day_date: str | None = None,
		is_partial_day: int = 0,
		partial_day_type: str | None = None,
		duration_minutes: int = 0,
		confirmed: int = 0,
		exemption: int = 0,
	):
		"""Helper to construct and insert a Leave Application test record."""
		doc = frappe.new_doc("Leave Application")
		doc.employee = self.employee
		doc.leave_approver = self.approver
		doc.leave_type = leave_type
		doc.from_date = from_date
		doc.to_date = to_date
		doc.description = description
		doc.half_day = half_day
		doc.half_day_date = half_day_date
		doc.custom_is_partial_day_leave = is_partial_day
		doc.custom_partial_day_type = partial_day_type
		doc.custom_partial_day_duration = duration_minutes
		doc.custom_sandwich_rule_confirmed = confirmed
		doc.custom_apply_sandwich_exemption = exemption
		doc.insert(ignore_permissions=True)
		doc.flags.pop("in_print", None)
		doc.flags.pop("print_settings", None)

		self.created_docs.append(("Leave Application", doc.name))
		return doc

	def _approve_doc(self, doc):
		"""Helper to transition document to Approved state."""
		doc.flags.pop("in_print", None)
		doc.flags.pop("print_settings", None)
		has_wf = frappe.get_all("Workflow", filters={"document_type": doc.doctype, "is_active": 1})
		if has_wf:
			apply_workflow(doc, "Approve")
			doc.reload()
			doc.flags.pop("in_print", None)
		else:
			doc.status = "Approved"
			doc.submit()
			doc.flags.pop("in_print", None)

	def _cancel_doc(self, doc):
		"""Helper to transition document to Cancelled state."""
		doc.flags.pop("in_print", None)
		doc.flags.pop("print_settings", None)
		has_wf = frappe.get_all("Workflow", filters={"document_type": doc.doctype, "is_active": 1})
		if has_wf:
			apply_workflow(doc, "Cancel")
			doc.reload()
			doc.flags.pop("in_print", None)
		else:
			doc.cancel()
			doc.flags.pop("in_print", None)

	# -------------------------------------------------------------------------
	# Group 1: Configuration & Sandwich Condition Detection
	# -------------------------------------------------------------------------

	def test_01_sandwich_disabled_when_setting_is_off(self):
		"""When apply_sandwich_leave_rule_on_leave is disabled, sandwich conditions are ignored."""
		frappe.db.set_single_value("Artem Setting", "apply_sandwich_leave_rule_on_leave", 0)
		frappe.clear_document_cache("Artem Setting")

		# Create preceding leave on Friday
		l1 = self._create_leave_application("Casual Leave", "2026-11-06", "2026-11-06", "Friday Leave")
		self._approve_doc(l1)

		# Check Monday condition
		res = check_sandwich_condition(
			employee=self.employee,
			from_date="2026-11-09",
			to_date="2026-11-09",
			leave_type="Casual Leave",
		)
		self.assertFalse(res.get("sandwich_detected"))

	def test_02_normal_leave_no_sandwich(self):
		"""A standalone single-day leave on a working day has no sandwich condition."""
		res = check_sandwich_condition(
			employee=self.employee,
			from_date="2026-11-06",
			to_date="2026-11-06",
			leave_type="Casual Leave",
		)
		self.assertFalse(res.get("sandwich_detected"))

	def test_03_two_application_sandwich_detected(self):
		"""Leave on Friday + Weekend (Sat, Sun) + Leave on Monday triggers Sandwich Leave condition."""
		# Preceding Leave: Friday 2026-11-06
		l1 = self._create_leave_application("Casual Leave", "2026-11-06", "2026-11-06", "Friday Leave")
		self._approve_doc(l1)

		# Current Leave evaluated for Monday 2026-11-09
		res = check_sandwich_condition(
			employee=self.employee,
			from_date="2026-11-09",
			to_date="2026-11-09",
			leave_type="Casual Leave",
		)
		self.assertTrue(res.get("sandwich_detected"))
		self.assertFalse(res.get("is_single_application_holiday"))
		self.assertEqual(res.get("prior_leave"), l1.name)
		self.assertEqual(res.get("intervening_dates"), ["2026-11-07", "2026-11-08"])
		self.assertEqual(res.get("intervening_days_count"), 2)

	def test_04_gap_with_working_day_not_sandwich(self):
		"""If the gap between two leaves contains at least one working day, sandwich rule does not apply."""
		# Leave on Thursday 2026-11-05 (Friday 2026-11-06 is a working day)
		l1 = self._create_leave_application("Casual Leave", "2026-11-05", "2026-11-05", "Thursday Leave")
		self._approve_doc(l1)

		# Current Leave on Monday 2026-11-09
		res = check_sandwich_condition(
			employee=self.employee,
			from_date="2026-11-09",
			to_date="2026-11-09",
			leave_type="Casual Leave",
		)
		self.assertFalse(res.get("sandwich_detected"))

	def test_05_half_day_exclusion(self):
		"""Half-Day leaves are excluded and break the sandwich leave calculation."""
		# Scenario A: Preceding leave is Half-Day
		l1 = self._create_leave_application(
			"Casual Leave",
			"2026-11-06",
			"2026-11-06",
			"Half-Day Friday",
			half_day=1,
			half_day_date="2026-11-06",
		)
		self._approve_doc(l1)

		res_a = check_sandwich_condition(
			employee=self.employee,
			from_date="2026-11-09",
			to_date="2026-11-09",
			leave_type="Casual Leave",
		)
		self.assertFalse(res_a.get("sandwich_detected"))

		# Scenario B: Current leave is Half-Day (preceding leave is full day)
		l2 = self._create_leave_application("Casual Leave", "2026-11-13", "2026-11-13", "Full-Day Friday")
		self._approve_doc(l2)

		res_b = check_sandwich_condition(
			employee=self.employee,
			from_date="2026-11-16",
			to_date="2026-11-16",
			leave_type="Casual Leave",
			half_day=1,
		)
		self.assertFalse(res_b.get("sandwich_detected"))

	def test_06_partial_day_exclusion(self):
		"""Partial Day leaves (hourly) do not trigger sandwich leaves."""
		# Preceding leave is Partial Day
		l1 = self._create_leave_application(
			"Partial Day",
			"2026-11-06",
			"2026-11-06",
			"Partial Day Friday",
			is_partial_day=1,
			partial_day_type="Late Arrival",
			duration_minutes=60,
		)
		self._approve_doc(l1)

		res = check_sandwich_condition(
			employee=self.employee,
			from_date="2026-11-09",
			to_date="2026-11-09",
			leave_type="Casual Leave",
		)
		self.assertFalse(res.get("sandwich_detected"))

	def test_07_optional_holiday_exclusion(self):
		"""If prior or current leave is an Optional Holiday Leave Type, intervening weekly offs are exempt."""
		# Prior leave is Optional Holiday (2026-12-25 is Christmas Day in Optional Holiday list)
		l1 = self._create_leave_application(
			"Optional Holiday", "2026-12-25", "2026-12-25", "Optional Holiday Friday"
		)
		self._approve_doc(l1)

		res = check_sandwich_condition(
			employee=self.employee,
			from_date="2026-12-28",
			to_date="2026-12-28",
			leave_type="Casual Leave",
		)
		self.assertFalse(res.get("sandwich_detected"))

	def test_08_single_application_include_holiday_sandwich_detection(self):
		"""A multi-day leave spanning non-working days under an Include Holidays leave type triggers Sandwich Leave."""
		res = check_sandwich_condition(
			employee=self.employee,
			from_date="2026-11-06",
			to_date="2026-11-09",
			leave_type="Casual Leave",
		)
		self.assertTrue(res.get("sandwich_detected"))
		self.assertTrue(res.get("is_single_application_holiday"))
		self.assertEqual(res.get("intervening_dates"), ["2026-11-07", "2026-11-08"])
		self.assertEqual(res.get("intervening_days_count"), 2)

	# -------------------------------------------------------------------------
	# Group 2: Form Validations & Employee Actions (Confirmation vs Exemption)
	# -------------------------------------------------------------------------

	def test_09_unconfirmed_sandwich_leave_blocks_save(self):
		"""Saving a leave application that triggers sandwich leave without confirming or exempting raises ValidationError."""
		# Prior Leave: Friday 2026-11-06
		l1 = self._create_leave_application("Casual Leave", "2026-11-06", "2026-11-06", "Friday Leave")
		self._approve_doc(l1)

		# Attempting to save Monday without confirmed=1 or exemption=1
		l2 = frappe.new_doc("Leave Application")
		l2.employee = self.employee
		l2.leave_approver = self.approver
		l2.leave_type = "Casual Leave"
		l2.from_date = "2026-11-09"
		l2.to_date = "2026-11-09"
		l2.description = "Monday Unconfirmed"
		l2.custom_sandwich_rule_confirmed = 0
		l2.custom_apply_sandwich_exemption = 0

		self.assertRaises(frappe.ValidationError, l2.insert)

	def test_10_confirmed_sandwich_leave_saves_successfully(self):
		"""Saving with custom_sandwich_rule_confirmed=1 succeeds and sets custom_sandwich_detected."""
		l1 = self._create_leave_application("Casual Leave", "2026-11-06", "2026-11-06", "Friday Leave")
		self._approve_doc(l1)

		l2 = self._create_leave_application(
			"Casual Leave", "2026-11-09", "2026-11-09", "Monday Confirmed", confirmed=1
		)
		self.assertEqual(l2.custom_sandwich_detected, 1)
		self.assertEqual(l2.custom_sandwich_rule_confirmed, 1)

	def test_11_apply_exemption_saves_and_consumes_quota(self):
		"""Applying an exemption allows saving and counts toward consumed exemptions."""
		l1 = self._create_leave_application("Casual Leave", "2026-11-06", "2026-11-06", "Friday Leave")
		self._approve_doc(l1)

		# Save Monday with exemption
		l2 = self._create_leave_application(
			"Casual Leave", "2026-11-09", "2026-11-09", "Monday Exempt", exemption=1
		)
		self.assertEqual(l2.custom_apply_sandwich_exemption, 1)

		consumed = get_sandwich_exemptions_consumed(self.employee, "2026-01-01", "2026-12-31")
		self.assertEqual(consumed, 1)

	def test_12_exemption_quota_limit_enforced(self):
		"""Exceeding maximum allowed exemptions throws ValidationError."""
		# Set maximum exemptions to 1
		frappe.db.set_single_value("Artem Setting", "maximum_employee_exemptions", 1)
		frappe.clear_document_cache("Artem Setting")

		# Use the 1 allowed exemption
		l1 = self._create_leave_application("Casual Leave", "2026-11-06", "2026-11-06", "Friday Leave")
		self._approve_doc(l1)

		l2 = self._create_leave_application(
			"Casual Leave", "2026-11-09", "2026-11-09", "Monday Exempt", exemption=1
		)
		self._approve_doc(l2)

		# Attempting to use a 2nd exemption should fail
		l3 = self._create_leave_application("Casual Leave", "2026-11-13", "2026-11-13", "Next Friday Leave")
		self._approve_doc(l3)

		l4 = frappe.new_doc("Leave Application")
		l4.employee = self.employee
		l4.leave_approver = self.approver
		l4.leave_type = "Casual Leave"
		l4.from_date = "2026-11-16"
		l4.to_date = "2026-11-16"
		l4.description = "Next Monday Over Quota"
		l4.custom_apply_sandwich_exemption = 1

		self.assertRaises(frappe.ValidationError, l4.insert)

	def test_13_single_application_exemption_adjusts_total_leave_days(self):
		"""For a multi-day Include Holidays leave, applying exemption excludes holidays from total_leave_days."""
		# Without exemption: Friday to Monday (4 calendar days) = 4.0 days
		doc_no_exemption = self._create_leave_application(
			"Casual Leave", "2026-11-06", "2026-11-09", "Without Exemption", confirmed=1
		)
		self.assertEqual(flt(doc_no_exemption.total_leave_days), 4.0)

		# With exemption: Friday to Monday (4 calendar days - 2 weekend holidays) = 2.0 days
		# Using distinct dates to avoid overlap with doc_no_exemption
		doc_with_exemption = self._create_leave_application(
			"Casual Leave", "2026-11-13", "2026-11-16", "With Exemption", exemption=1
		)
		self.assertEqual(flt(doc_with_exemption.total_leave_days), 2.0)

	# -------------------------------------------------------------------------
	# Group 3: Sequential Approvals
	# -------------------------------------------------------------------------

	def test_14_sequential_approval_blocks_subsequent_leave(self):
		"""Approving a subsequent leave is blocked if the earlier relevant leave application is pending."""
		# Leave 1 (Friday) is created and left in Pending status
		self._create_leave_application("Casual Leave", "2026-11-06", "2026-11-06", "Friday Pending")

		# Leave 2 (Monday) is created
		l2 = self._create_leave_application(
			"Casual Leave", "2026-11-09", "2026-11-09", "Monday Leave", confirmed=1
		)

		# Attempting to approve Leave 2 should throw earlier application pending error
		self.assertRaises(frappe.ValidationError, self._approve_doc, l2)

	def test_15_approval_allowed_after_earlier_leave_approved(self):
		"""Once the earlier leave application is approved, the subsequent leave can be approved."""
		l1 = self._create_leave_application("Casual Leave", "2026-11-06", "2026-11-06", "Friday Pending")
		self._approve_doc(l1)

		l2 = self._create_leave_application(
			"Casual Leave", "2026-11-09", "2026-11-09", "Monday Leave", confirmed=1
		)
		self._approve_doc(l2)

		self.assertEqual(l2.status, "Approved")
		self.assertEqual(l2.docstatus, 1)

	# -------------------------------------------------------------------------
	# Group 4: Automatic Sandwich Leave Generation & Deductions
	# -------------------------------------------------------------------------

	def test_16_auto_generation_of_sandwich_leave_records(self):
		"""Upon approval of parent leave, system auto-generates approved sandwich leave records for the weekend."""
		l1 = self._create_leave_application("Casual Leave", "2026-11-06", "2026-11-06", "Friday Leave")
		self._approve_doc(l1)

		l2 = self._create_leave_application(
			"Casual Leave", "2026-11-09", "2026-11-09", "Monday Leave", confirmed=1
		)
		self._approve_doc(l2)

		# Check generated sandwich leaves
		sandwiches = frappe.get_all(
			"Leave Application",
			filters={"custom_parent_leave_application": l2.name},
			fields=[
				"name",
				"from_date",
				"to_date",
				"total_leave_days",
				"custom_is_sandwich_leave",
				"custom_system_generated",
				"custom_prior_leave_application",
				"leave_balance",
				"docstatus",
			],
		)
		self.assertTrue(len(sandwiches) > 0)
		sl = sandwiches[0]
		self.assertEqual(sl.custom_is_sandwich_leave, 1)
		self.assertEqual(sl.custom_system_generated, 1)
		self.assertEqual(sl.custom_prior_leave_application, l1.name)
		self.assertEqual(str(sl.from_date), "2026-11-07")
		self.assertEqual(str(sl.to_date), "2026-11-08")
		self.assertEqual(flt(sl.total_leave_days), 2.0)
		self.assertEqual(sl.docstatus, 1)
		self.assertGreater(flt(sl.leave_balance), 0.0)

	def test_17_exemption_skips_sandwich_generation(self):
		"""When employee applies an exemption, no sandwich leave records are generated upon approval."""
		l1 = self._create_leave_application("Casual Leave", "2026-11-06", "2026-11-06", "Friday Leave")
		self._approve_doc(l1)

		l2 = self._create_leave_application(
			"Casual Leave", "2026-11-09", "2026-11-09", "Monday Exempt", exemption=1
		)
		self._approve_doc(l2)

		sandwiches = frappe.get_all(
			"Leave Application",
			filters={"custom_parent_leave_application": l2.name},
		)
		self.assertEqual(len(sandwiches), 0)

	def test_18_single_application_include_holiday_skips_extra_records(self):
		"""In single-application Include Holidays leaves, no separate sandwich leave records are generated."""
		doc = self._create_leave_application(
			"Casual Leave", "2026-11-06", "2026-11-09", "Multi-day Leave", confirmed=1
		)
		self._approve_doc(doc)

		sandwiches = frappe.get_all(
			"Leave Application",
			filters={"custom_parent_leave_application": doc.name},
		)
		self.assertEqual(len(sandwiches), 0)

	# -------------------------------------------------------------------------
	# Group 5: Attendance Synchronization & Cascading Cancellation
	# -------------------------------------------------------------------------

	def test_19_attendance_synchronization_with_and_without_exemption(self):
		"""Single application with exemption marks only working days as On Leave, whereas without exemption marks all days."""
		# Case A: With Exemption
		doc_exempt = self._create_leave_application(
			"Casual Leave", "2026-11-06", "2026-11-09", "Exempt Leave", exemption=1
		)
		self._approve_doc(doc_exempt)

		attendances_exempt = {
			str(a.attendance_date): a.status
			for a in frappe.get_all(
				"Attendance",
				filters={
					"employee": self.employee,
					"attendance_date": ["between", ["2026-11-06", "2026-11-09"]],
				},
				fields=["attendance_date", "status"],
			)
		}
		# Friday (06) and Monday (09) marked On Leave
		self.assertEqual(attendances_exempt.get("2026-11-06"), "On Leave")
		self.assertEqual(attendances_exempt.get("2026-11-09"), "On Leave")
		# Saturday (07) and Sunday (08) remain holidays (not marked On Leave)
		self.assertNotIn("2026-11-07", attendances_exempt)
		self.assertNotIn("2026-11-08", attendances_exempt)

		self._cancel_doc(doc_exempt)

		# Case B: Without Exemption (all 4 days marked On Leave)
		doc_confirmed = self._create_leave_application(
			"Casual Leave", "2026-11-06", "2026-11-09", "Confirmed Leave", confirmed=1
		)
		self._approve_doc(doc_confirmed)

		attendances_confirmed = {
			str(a.attendance_date): a.status
			for a in frappe.get_all(
				"Attendance",
				filters={
					"employee": self.employee,
					"attendance_date": ["between", ["2026-11-06", "2026-11-09"]],
				},
				fields=["attendance_date", "status"],
			)
		}
		self.assertEqual(attendances_confirmed.get("2026-11-06"), "On Leave")
		self.assertEqual(attendances_confirmed.get("2026-11-07"), "On Leave")
		self.assertEqual(attendances_confirmed.get("2026-11-08"), "On Leave")
		self.assertEqual(attendances_confirmed.get("2026-11-09"), "On Leave")

	def test_20_cancellation_of_parent_leave_cancels_sandwich_leave(self):
		"""Cancelling a parent leave automatically cancels all linked auto-generated sandwich leaves."""
		l1 = self._create_leave_application("Casual Leave", "2026-11-06", "2026-11-06", "Friday Leave")
		self._approve_doc(l1)

		l2 = self._create_leave_application(
			"Casual Leave", "2026-11-09", "2026-11-09", "Monday Leave", confirmed=1
		)
		self._approve_doc(l2)

		# Verify sandwich leave exists and is approved
		sandwiches = frappe.get_all(
			"Leave Application",
			filters={"custom_parent_leave_application": l2.name},
			fields=["name", "docstatus"],
		)
		self.assertEqual(len(sandwiches), 1)
		self.assertEqual(sandwiches[0].docstatus, 1)

		# Cancel parent leave l2
		self._cancel_doc(l2)

		# Verify sandwich leave was cancelled automatically
		sl_doc = frappe.get_doc("Leave Application", sandwiches[0].name)
		self.assertEqual(sl_doc.docstatus, 2)
		self.assertEqual(sl_doc.workflow_state, "Cancelled")
