# Copyright (c) 2026, Artem Healthtech and Contributors
# See license.txt

import os
import unittest

import frappe
from frappe.utils import add_days, add_months, get_first_day, get_last_day, getdate, today

from artem_erp.artem_erp.doctype.employee_additional_salary_payroll_review.monthly_weekly_payroll_review import (
	create_monthly_payroll_reviews,
	get_previous_pending_additional_salary_details,
	get_target_payroll_month,
	sync_additional_salaries_for_review,
	sync_weekly_payroll_reviews,
)


def cancel_and_delete(doctype, name):
	if name and frappe.db.exists(doctype, name):
		doc = frappe.get_doc(doctype, name)
		if doc.docstatus == 1:
			doc.cancel()
		doc.delete(force=True)


class TestEmployeeAdditionalSalaryPayrollReview(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		if os.path.exists("/workspace/development/frappe-bench/sites"):
			os.chdir("/workspace/development/frappe-bench/sites")
		frappe.init(site="release.artemhrms")
		frappe.connect()

	@classmethod
	def tearDownClass(cls):
		frappe.destroy()

	def setUp(self):
		super().setUp()
		ssa = frappe.db.get_value(
			"Salary Structure Assignment",
			{"docstatus": 1},
			["employee", "company"],
			as_dict=True,
		)
		if ssa:
			self.employee = ssa.employee
			self.company = ssa.company
		else:
			self.company = frappe.db.get_value("Company", {"is_group": 0}, "name")
			self.employee = frappe.db.get_value("Employee", {"company": self.company}, "name")

		comp_name = "Test Review Comp"
		if not frappe.db.exists("Salary Component", comp_name):
			comp = frappe.new_doc("Salary Component")
			comp.salary_component = comp_name
			comp.salary_component_abbr = "TRCOMP"
			comp.type = "Earning"
			comp.insert()
		self.salary_component = comp_name

	def tearDown(self):
		frappe.db.rollback()

	def test_autoname_and_dates_validation(self):
		"""
		Checks name generation and payroll to_date validation.
		"""
		doc = frappe.new_doc("Employee Additional Salary Payroll Review")
		doc.company = self.company
		doc.payroll_from_date = "2026-11-01"
		doc.payroll_to_date = "2026-11-30"
		doc.status = "Draft"
		doc.autoname()

		abbr = frappe.db.get_value("Company", self.company, "abbr")
		self.assertEqual(doc.name, f"{abbr}-Nov-2026")

		# to_date < from_date throws ValidationError
		doc.payroll_to_date = "2026-10-31"
		self.assertRaises(frappe.ValidationError, doc.validate)

	def test_is_reviewed_completion_and_submission_validation(self):
		"""
		If any child row has is_reviewed = 0:
		- Cannot set Status to Completed
		- Cannot submit
		Can only be Completed/Submitted when all rows have is_reviewed = 1.
		"""
		doc = frappe.new_doc("Employee Additional Salary Payroll Review")
		doc.company = self.company
		doc.payroll_from_date = "2026-10-01"
		doc.payroll_to_date = "2026-10-31"
		doc.status = "Draft"

		doc.append(
			"additional_salary_payment_details",
			{
				"employee": self.employee,
				"bonus_type": self.salary_component,
				"total_amount": 15000,
				"is_reviewed": 0,
			},
		)

		doc.append(
			"previous_pending_additional_salary",
			{
				"employee": self.employee,
				"bonus_type": self.salary_component,
				"total_amount": 5000,
				"is_reviewed": 1,
			},
		)

		# 1. Setting Status to Completed when a row is unreviewed throws ValidationError
		doc.status = "Completed"
		self.assertRaises(frappe.ValidationError, doc.validate)

		# 2. Submitting when a row is unreviewed throws ValidationError
		doc.status = "Draft"
		doc.docstatus = 1
		self.assertRaises(frappe.ValidationError, doc.validate)

		# 3. Marking all rows as reviewed allows Completed and Submit
		doc.additional_salary_payment_details[0].is_reviewed = 1
		doc.status = "Completed"
		doc.validate()  # Passes without error
		self.assertEqual(doc.status, "Completed")

	def test_monthly_cron_creation_and_idempotence(self):
		"""
		Monthly cron creates review for the company for current month.
		Running it again does not duplicate the review or child rows.
		Monthly cron ONLY creates review for the company IF an employee has an Additional Salary.
		If no employee has Additional Salary in that month, no review is generated.
		"""
		ahpl_company = "Artem HealthTech Private Limited"
		ahpl_emp = "AHPL0178"
		test_date = "2027-02-01"
		start_date, end_date = get_target_payroll_month(test_date)
		abbr = frappe.db.get_value("Company", ahpl_company, "abbr") or "AHPL"
		expected_name = f"{abbr}-Feb-2027"

		# Clean up any existing review for this test period
		frappe.db.delete(
			"Employee Additional Salary Payroll Review",
			{
				"company": ahpl_company,
				"payroll_from_date": start_date,
				"payroll_to_date": end_date,
			},
		)
		cancel_and_delete("Employee Additional Salary Payroll Review", expected_name)

		# 1. When NO additional salary exists for this month: review should NOT be created
		create_monthly_payroll_reviews(test_date)
		self.assertFalse(frappe.db.exists("Employee Additional Salary Payroll Review", expected_name))

		# 2. When an Additional Salary DOES exist for this month: review SHOULD be created
		as_doc = frappe.new_doc("Additional Salary")
		as_doc.company = ahpl_company
		as_doc.employee = ahpl_emp
		as_doc.salary_component = self.salary_component
		as_doc.amount = 20000
		as_doc.payroll_date = "2027-02-15"
		as_doc.is_recurring = 0
		as_doc.insert()
		as_doc.submit()

		try:
			create_monthly_payroll_reviews(test_date)
			self.assertTrue(frappe.db.exists("Employee Additional Salary Payroll Review", expected_name))

			# 3. Idempotent: running again does not duplicate the review
			create_monthly_payroll_reviews(test_date)
			review_count = frappe.db.count(
				"Employee Additional Salary Payroll Review",
				{
					"company": ahpl_company,
					"payroll_from_date": start_date,
					"payroll_to_date": end_date,
					"docstatus": ["!=", 2],
				},
			)
			self.assertEqual(review_count, 1)

		finally:
			cancel_and_delete("Employee Additional Salary Payroll Review", expected_name)
			if as_doc:
				cancel_and_delete("Additional Salary", as_doc.name)

	def test_weekly_cron_syncs_new_additional_salaries(self):
		"""
		Weekly cron synchronizes newly added Additional Salary into existing current-month review.
		"""
		test_date = "2026-10-01"
		start_date, end_date = get_target_payroll_month(test_date)

		# Ensure a review document exists in Draft
		abbr = frappe.db.get_value("Company", self.company, "abbr")
		review_name = f"{abbr}-Oct-2026"
		frappe.db.delete("Employee Additional Salary Payroll Review", review_name)

		review_doc = frappe.new_doc("Employee Additional Salary Payroll Review")
		review_doc.company = self.company
		review_doc.payroll_from_date = start_date
		review_doc.payroll_to_date = end_date
		review_doc.status = "Draft"
		review_doc.insert()

		# Create a new non-recurring Additional Salary for October 2026
		as_doc = frappe.new_doc("Additional Salary")
		as_doc.company = self.company
		as_doc.employee = self.employee
		as_doc.salary_component = self.salary_component
		as_doc.amount = 25000
		as_doc.payroll_date = "2026-10-15"
		as_doc.is_recurring = 0
		as_doc.insert()
		as_doc.submit()

		try:
			# Run weekly cron
			sync_weekly_payroll_reviews(test_date)

			review_doc.reload()
			ads_names = [r.additional_salary for r in review_doc.additional_salary_payment_details]
			self.assertIn(as_doc.name, ads_names)

			# Verify attributes
			row = next(
				r for r in review_doc.additional_salary_payment_details if r.additional_salary == as_doc.name
			)
			self.assertEqual(row.total_amount, 25000)
			self.assertEqual(row.is_reviewed, 0)
			self.assertEqual(str(row.payout_date), "2026-10-15")

			# Run weekly cron again: must NOT duplicate child row
			sync_weekly_payroll_reviews(test_date)
			review_doc.reload()
			matching_rows = [
				r for r in review_doc.additional_salary_payment_details if r.additional_salary == as_doc.name
			]
			self.assertEqual(len(matching_rows), 1)

		finally:
			cancel_and_delete("Employee Additional Salary Payroll Review", review_name)
			as_doc.cancel()
			frappe.delete_doc("Additional Salary", as_doc.name, force=True)

	def test_recurring_additional_salary_inclusion(self):
		"""
		Recurring Additional Salary is included when its recurrence due date falls within payroll dates.
		"""
		test_date = "2026-11-01"
		start_date, end_date = get_target_payroll_month(test_date)

		# Quarterly starting 13-Aug-2026 -> First payment is 13-Nov-2026 (falls in Nov 2026)
		as_doc = frappe.new_doc("Additional Salary")
		as_doc.company = self.company
		as_doc.employee = self.employee
		as_doc.salary_component = self.salary_component
		as_doc.amount = 40000
		as_doc.is_recurring = 1
		as_doc.custom_duration_of_additional_salary = "Quarterly"
		as_doc.from_date = "2026-08-13"
		as_doc.insert()
		as_doc.submit()

		try:
			review_doc = frappe.new_doc("Employee Additional Salary Payroll Review")
			review_doc.company = self.company
			review_doc.payroll_from_date = start_date
			review_doc.payroll_to_date = end_date
			review_doc.status = "Draft"

			sync_additional_salaries_for_review(review_doc)

			ads_names = [r.additional_salary for r in review_doc.additional_salary_payment_details]
			self.assertIn(as_doc.name, ads_names)

			row = next(
				r for r in review_doc.additional_salary_payment_details if r.additional_salary == as_doc.name
			)
			self.assertEqual(row.total_amount, 40000)
			self.assertEqual(str(row.payout_date), "2026-11-13")

		finally:
			as_doc.cancel()
			frappe.delete_doc("Additional Salary", as_doc.name, force=True)

	def test_preservation_of_hr_modified_values(self):
		"""
		Sync never overwrites HR-modified values (pay_action, paid_amount, is_reviewed, comment).
		"""
		review_doc = frappe.new_doc("Employee Additional Salary Payroll Review")
		review_doc.company = self.company
		review_doc.payroll_from_date = "2026-10-01"
		review_doc.payroll_to_date = "2026-10-31"
		review_doc.status = "Draft"

		as_name = "TEST-ADS-HR-MOD"
		review_doc.append(
			"additional_salary_payment_details",
			{
				"additional_salary": as_name,
				"employee": self.employee,
				"bonus_type": self.salary_component,
				"total_amount": 50000,
				"pay_action": "On Hold",
				"paid_amount": 0,
				"remaining_amount": 50000,
				"comment": "HR put on hold pending appraisal",
				"is_reviewed": 1,
			},
		)

		# Run sync
		sync_additional_salaries_for_review(review_doc)

		# Ensure row was NOT modified
		row = review_doc.additional_salary_payment_details[0]
		self.assertEqual(row.pay_action, "On Hold")
		self.assertEqual(row.comment, "HR put on hold pending appraisal")
		self.assertEqual(row.is_reviewed, 1)
		self.assertEqual(row.paid_amount, 0)
		self.assertEqual(row.remaining_amount, 50000)

	def test_pending_carry_forward_lifecycle(self):
		"""
		Month 1: Item is put On Hold by HR -> submitted.
		Month 2: Item is carried forward into previous_pending_additional_salary.
		Month 2: Item is left On Hold -> submitted.
		Month 3: Item continues to carry forward into previous_pending_additional_salary.
		Month 3: Item is marked Pay -> submitted.
		Month 4: Item is finalized and NOT carried forward.
		"""
		abbr = frappe.db.get_value("Company", self.company, "abbr")

		# Clean up any leftover reviews for Oct, Nov, Dec 2026 and Jan 2027
		for m in ["Oct-2026", "Nov-2026", "Dec-2026", "Jan-2027"]:
			cancel_and_delete("Employee Additional Salary Payroll Review", f"{abbr}-{m}")

		# Create test Additional Salary
		as_doc = frappe.new_doc("Additional Salary")
		as_doc.company = self.company
		as_doc.employee = self.employee
		as_doc.salary_component = self.salary_component
		as_doc.amount = 35000
		as_doc.payroll_date = "2026-10-10"
		as_doc.is_recurring = 0
		as_doc.insert()
		as_doc.submit()

		r1 = r2 = r3 = r4 = None
		try:
			# === MONTH 1 (Oct 2026) ===
			r1 = frappe.new_doc("Employee Additional Salary Payroll Review")
			r1.company = self.company
			r1.payroll_from_date = "2026-10-01"
			r1.payroll_to_date = "2026-10-31"
			r1.status = "Draft"
			sync_additional_salaries_for_review(r1)
			r1.insert()

			# Mark all rows in r1 as reviewed
			for row in r1.additional_salary_payment_details or []:
				if row.additional_salary != as_doc.name:
					row.pay_action = "On Hold"
				row.is_reviewed = 1
			for row in r1.previous_pending_additional_salary or []:
				row.pay_action = "On Hold"
				row.is_reviewed = 1

			# HR marks as On Hold
			r1_row = next(
				r for r in r1.additional_salary_payment_details if r.additional_salary == as_doc.name
			)
			r1_row.pay_action = "On Hold"
			r1.submit()

			# === MONTH 2 (Nov 2026) ===
			r2 = frappe.new_doc("Employee Additional Salary Payroll Review")
			r2.company = self.company
			r2.payroll_from_date = "2026-11-01"
			r2.payroll_to_date = "2026-11-30"
			r2.status = "Draft"
			sync_additional_salaries_for_review(r2)
			r2.insert()

			# Should be in previous_pending_additional_salary!
			pending_ads_r2 = [r.additional_salary for r in r2.previous_pending_additional_salary]
			self.assertIn(as_doc.name, pending_ads_r2)

			r2_row = next(
				r for r in r2.previous_pending_additional_salary if r.additional_salary == as_doc.name
			)
			self.assertEqual(r2_row.total_amount, 35000)
			self.assertEqual(r2_row.pay_action, "On Hold")
			self.assertEqual(r2_row.previous_pay_action, "On Hold")
			self.assertEqual(r2_row.is_reviewed, 0)  # Needs HR review for Nov

			# HR reviews all rows in r2 and leaves as_doc On Hold again
			for row in r2.additional_salary_payment_details or []:
				if row.additional_salary != as_doc.name:
					row.pay_action = "On Hold"
				row.is_reviewed = 1
			for row in r2.previous_pending_additional_salary or []:
				if row.additional_salary != as_doc.name:
					row.pay_action = "On Hold"
				row.is_reviewed = 1
			r2.submit()

			# === MONTH 3 (Dec 2026) ===
			r3 = frappe.new_doc("Employee Additional Salary Payroll Review")
			r3.company = self.company
			r3.payroll_from_date = "2026-12-01"
			r3.payroll_to_date = "2026-12-31"
			r3.status = "Draft"
			sync_additional_salaries_for_review(r3)
			r3.insert()

			# Still carried forward into previous_pending_additional_salary!
			pending_ads_r3 = [r.additional_salary for r in r3.previous_pending_additional_salary]
			self.assertIn(as_doc.name, pending_ads_r3)

			# Now HR finalizes it: marks as Pay
			for row in r3.additional_salary_payment_details or []:
				if row.additional_salary != as_doc.name:
					row.pay_action = "On Hold"
				row.is_reviewed = 1
			for row in r3.previous_pending_additional_salary or []:
				if row.additional_salary != as_doc.name:
					row.pay_action = "On Hold"
				row.is_reviewed = 1
			r3_row = next(
				r for r in r3.previous_pending_additional_salary if r.additional_salary == as_doc.name
			)
			r3_row.pay_action = "Pay"
			r3_row.paid_amount = 35000
			r3_row.remaining_amount = 0
			r3.submit()

			# === MONTH 4 (Jan 2027) ===
			r4 = frappe.new_doc("Employee Additional Salary Payroll Review")
			r4.company = self.company
			r4.payroll_from_date = "2027-01-01"
			r4.payroll_to_date = "2027-01-31"
			r4.status = "Draft"
			sync_additional_salaries_for_review(r4)
			r4.insert()

			# Record was finalized in Dec 2026, so NOT carried forward to Jan 2027!
			pending_ads_r4 = [r.additional_salary for r in r4.previous_pending_additional_salary]
			self.assertNotIn(as_doc.name, pending_ads_r4)

		finally:
			for r in [r4, r3, r2, r1]:
				if r:
					cancel_and_delete("Employee Additional Salary Payroll Review", r.name)
			if as_doc:
				cancel_and_delete("Additional Salary", as_doc.name)

	def test_partially_paid_carry_forward(self):
		"""
		Partially paid row carries forward the remaining amount into previous_pending_additional_salary.
		"""
		abbr = frappe.db.get_value("Company", self.company, "abbr")
		for m in ["Oct-2026", "Nov-2026"]:
			cancel_and_delete("Employee Additional Salary Payroll Review", f"{abbr}-{m}")

		as_doc = frappe.new_doc("Additional Salary")
		as_doc.company = self.company
		as_doc.employee = self.employee
		as_doc.salary_component = self.salary_component
		as_doc.amount = 50000
		as_doc.payroll_date = "2026-10-15"
		as_doc.is_recurring = 0
		as_doc.insert()
		as_doc.submit()

		r1 = None
		r2 = None
		try:
			# Month 1: Partially Paid with 20k paid, 30k remaining
			r1 = frappe.new_doc("Employee Additional Salary Payroll Review")
			r1.company = self.company
			r1.payroll_from_date = "2026-10-01"
			r1.payroll_to_date = "2026-10-31"
			r1.status = "Draft"
			sync_additional_salaries_for_review(r1)
			r1.insert()

			for row in r1.additional_salary_payment_details or []:
				if row.additional_salary != as_doc.name:
					row.pay_action = "On Hold"
				row.is_reviewed = 1
			for row in r1.previous_pending_additional_salary or []:
				row.pay_action = "On Hold"
				row.is_reviewed = 1

			r1_row = next(
				r for r in r1.additional_salary_payment_details if r.additional_salary == as_doc.name
			)
			r1_row.pay_action = "Partially Paid"
			r1_row.paid_amount = 20000
			r1_row.remaining_amount = 30000
			r1_row.paid_percentage = 40
			r1.submit()

			# Verify details API returns previous_pay_action
			details = get_previous_pending_additional_salary_details(
				company=self.company,
				payroll_from_date="2026-11-01",
				additional_salary=as_doc.name,
			)
			self.assertEqual(details.get("previous_pay_action"), "Partially Paid")
			self.assertEqual(details.get("total_amount"), 50000)
			self.assertEqual(details.get("paid_amount"), 20000)
			self.assertEqual(details.get("remaining_amount"), 30000)

			# Month 2: Carried forward with remaining_amount = 30,000 (remaining portion)
			r2 = frappe.new_doc("Employee Additional Salary Payroll Review")
			r2.company = self.company
			r2.payroll_from_date = "2026-11-01"
			r2.payroll_to_date = "2026-11-30"
			r2.status = "Draft"
			sync_additional_salaries_for_review(r2)
			r2.insert()

			pending_ads_r2 = [r.additional_salary for r in r2.previous_pending_additional_salary]
			self.assertIn(as_doc.name, pending_ads_r2)

			r2_row = next(
				r for r in r2.previous_pending_additional_salary if r.additional_salary == as_doc.name
			)
			self.assertEqual(r2_row.previous_pay_action, "Partially Paid")
			self.assertEqual(r2_row.pay_action, "Partially Paid")
			self.assertEqual(r2_row.previous_additional_salary_total_amount, 50000)
			self.assertEqual(r2_row.previous_additional_salary_paid_amount, 20000)
			self.assertEqual(r2_row.previous_additional_salary_paid_percentage, 40)
			self.assertEqual(r2_row.previous_additional_salary_remaining_amount, 30000)
			self.assertEqual(r2_row.total_amount, 30000)
			self.assertEqual(r2_row.remaining_amount, 30000)
			self.assertEqual(r2_row.paid_amount, 0)
			self.assertEqual(r2_row.paid_percentage, 0)

		finally:
			for r in [r2, r1]:
				if r:
					cancel_and_delete("Employee Additional Salary Payroll Review", r.name)
			if as_doc:
				cancel_and_delete("Additional Salary", as_doc.name)

	def test_paid_amount_mandatory_validation(self):
		"""
		Submitting review requires paid_amount > 0 when pay_action is 'Pay' or 'Partially Paid'.
		"""
		review = frappe.new_doc("Employee Additional Salary Payroll Review")
		review.company = self.company
		review.payroll_from_date = "2027-02-01"
		review.payroll_to_date = "2027-02-28"
		review.status = "Draft"

		# Add row with pay_action = "Pay" but paid_amount = 0
		review.append(
			"additional_salary_payment_details",
			{
				"employee": self.employee,
				"bonus_type": self.salary_component,
				"total_amount": 5000,
				"paid_amount": 0,
				"remaining_amount": 5000,
				"pay_action": "Pay",
				"is_reviewed": 1,
				"payout_date": "2027-02-01",
			},
		)
		review.insert()

		try:
			# Trying to submit must throw ValidationError
			with self.assertRaises(frappe.ValidationError):
				review.submit()

			# Set pay_action = "Partially Paid" and paid_amount = 0
			review.reload()
			review.additional_salary_payment_details[0].pay_action = "Partially Paid"
			review.additional_salary_payment_details[0].paid_amount = 0
			with self.assertRaises(frappe.ValidationError):
				review.submit()

			# Now set valid paid_amount: submission succeeds
			review.reload()
			review.additional_salary_payment_details[0].paid_amount = 2500
			review.additional_salary_payment_details[0].remaining_amount = 2500
			review.additional_salary_payment_details[0].paid_percentage = 50
			review.submit()
			self.assertEqual(review.docstatus, 1)

		finally:
			cancel_and_delete("Employee Additional Salary Payroll Review", review.name)

	def test_paid_amount_must_be_less_than_or_equal_to_total_amount(self):
		"""
		Validates that paid_amount must be less than or equal to total_amount if paid_amount > 0.
		"""
		review = frappe.new_doc("Employee Additional Salary Payroll Review")
		review.company = self.company
		review.payroll_from_date = "2027-03-01"
		review.payroll_to_date = "2027-03-31"
		review.status = "Draft"

		# Exceed in Current Month table: total 5000, paid 6000
		review.append(
			"additional_salary_payment_details",
			{
				"employee": self.employee,
				"bonus_type": self.salary_component,
				"total_amount": 5000,
				"paid_amount": 6000,
				"remaining_amount": 0,
				"pay_action": "Partially Paid",
				"is_reviewed": 0,
				"payout_date": "2027-03-01",
			},
		)

		try:
			with self.assertRaises(frappe.ValidationError):
				review.insert()

			# Fix current month row, but exceed in previous pending table: total 4000, paid 4500
			review.additional_salary_payment_details[0].paid_amount = 3000
			review.additional_salary_payment_details[0].remaining_amount = 2000
			review.append(
				"previous_pending_additional_salary",
				{
					"employee": self.employee,
					"bonus_type": self.salary_component,
					"total_amount": 4000,
					"paid_amount": 4500,
					"remaining_amount": 0,
					"pay_action": "Partially Paid",
					"is_reviewed": 0,
					"payout_date": "2027-03-01",
				},
			)

			with self.assertRaises(frappe.ValidationError):
				review.insert()

			# Fix previous pending table: total 4000, paid 4000 (equal is allowed)
			review.previous_pending_additional_salary[0].paid_amount = 4000
			review.insert()
			self.assertTrue(bool(review.name))

		finally:
			cancel_and_delete("Employee Additional Salary Payroll Review", review.name)

	def test_sync_message_when_no_records_found(self):
		"""
		Sync returns 'No Additional Salary records found.' when no records exist,
		and 'No new Additional Salary records found to synchronize.' when existing rows are already present.
		"""
		# May 2025 has no additional salary records in DB
		review = frappe.new_doc("Employee Additional Salary Payroll Review")
		review.company = self.company
		review.payroll_from_date = "2025-05-01"
		review.payroll_to_date = "2025-05-31"
		review.status = "Draft"

		res = sync_additional_salaries_for_review(review)
		self.assertEqual(res["added_current"], 0)
		self.assertEqual(res["added_pending"], 0)
		self.assertEqual(res["indicator"], "orange")
		self.assertEqual(res["message"], "No Additional Salary records found.")

		# Add an in-memory row and run sync again: must indicate no NEW records found
		review.append(
			"additional_salary_payment_details",
			{
				"employee": self.employee,
				"bonus_type": self.salary_component,
				"total_amount": 5000,
				"paid_amount": 5000,
				"remaining_amount": 0,
				"pay_action": "Pay",
				"is_reviewed": 1,
				"payout_date": "2025-05-01",
			},
		)
		res2 = sync_additional_salaries_for_review(review)
		self.assertEqual(res2["added_current"], 0)
		self.assertEqual(res2["added_pending"], 0)
		self.assertEqual(res2["indicator"], "orange")
		self.assertEqual(res2["message"], "No new Additional Salary records found to synchronize.")

	def test_transition_from_old_to_new_additional_salary(self):
		"""
		User Requirement:
		Old recurring Additional Salary:
		- From Date: 22-03-2026, To Date: 10-10-2026, Duration: Quarterly, Amount: 30,000.
		New Additional Salary:
		- From Date / Payroll Date: 01-11-2026, Amount: 50,000.

		Expected:
		- October 2026 Review: Old salary is included (payout_date = 10-10-2026, prorated amount = 5,934.07).
		  New salary is NOT included.
		- November 2026 Review: Old salary is NOT included (no payments after to_date).
		  New salary IS included (Amount = 50,000).
		"""
		as_old = None
		as_new = None

		try:
			# 1. Create Old Recurring Additional Salary (Quarterly, 30,000)
			as_old = frappe.new_doc("Additional Salary")
			as_old.company = self.company
			as_old.employee = self.employee
			as_old.salary_component = self.salary_component
			as_old.is_recurring = 1
			as_old.custom_duration_of_additional_salary = "Quarterly"
			as_old.from_date = "2026-03-22"
			as_old.to_date = "2026-10-10"
			as_old.amount = 30000
			as_old.insert()
			as_old.submit()

			# 2. Create New Additional Salary (Effective from 01-11-2026, 50,000)
			as_new = frappe.new_doc("Additional Salary")
			as_new.company = self.company
			as_new.employee = self.employee
			as_new.salary_component = self.salary_component
			as_new.is_recurring = 0
			as_new.payroll_date = "2026-11-01"
			as_new.amount = 50000
			as_new.insert()
			as_new.submit()

			# 3. Synchronize October 2026 Review
			oct_review = frappe.new_doc("Employee Additional Salary Payroll Review")
			oct_review.company = self.company
			oct_review.payroll_from_date = "2026-10-01"
			oct_review.payroll_to_date = "2026-10-31"
			oct_review.status = "Draft"

			sync_additional_salaries_for_review(oct_review)

			oct_old_rows = [
				r
				for r in (oct_review.additional_salary_payment_details or [])
				if r.employee == self.employee and r.additional_salary == as_old.name
			]
			self.assertEqual(len(oct_old_rows), 1)

			oct_row = oct_old_rows[0]
			self.assertEqual(oct_row.additional_salary, as_old.name)
			self.assertEqual(oct_row.total_amount, 5917.81)
			self.assertEqual(oct_row.remaining_amount, 5917.81)
			self.assertEqual(str(oct_row.payout_date), "2026-10-10")

			# New salary must NOT be in October review
			oct_as_names = [r.additional_salary for r in (oct_review.additional_salary_payment_details or [])]
			self.assertNotIn(as_new.name, oct_as_names)

			# 4. Synchronize November 2026 Review
			nov_review = frappe.new_doc("Employee Additional Salary Payroll Review")
			nov_review.company = self.company
			nov_review.payroll_from_date = "2026-11-01"
			nov_review.payroll_to_date = "2026-11-30"
			nov_review.status = "Draft"

			sync_additional_salaries_for_review(nov_review)

			nov_new_rows = [
				r
				for r in (nov_review.additional_salary_payment_details or [])
				if r.employee == self.employee and r.additional_salary == as_new.name
			]
			self.assertEqual(len(nov_new_rows), 1)

			nov_row = nov_new_rows[0]
			# Old salary must NOT be in November review
			nov_as_names = [r.additional_salary for r in (nov_review.additional_salary_payment_details or [])]
			self.assertNotIn(as_old.name, nov_as_names)

			# Only new salary is included
			self.assertEqual(nov_row.additional_salary, as_new.name)
			self.assertEqual(nov_row.total_amount, 50000)

		finally:
			if as_new:
				cancel_and_delete("Additional Salary", as_new.name)
			if as_old:
				cancel_and_delete("Additional Salary", as_old.name)
