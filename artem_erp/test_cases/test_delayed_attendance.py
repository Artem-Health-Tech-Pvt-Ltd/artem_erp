# Copyright (c) 2026, Artem Healthtech and Contributors
# See license.txt

from datetime import datetime, timedelta

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate, nowdate

from artem_erp.scheduler_events.delayed_attendance import (
	calculate_attendance_for_logs,
	process_delayed_employee_checkins,
	resolve_unassigned_checkin_shifts,
)


class TestDelayedAttendance(IntegrationTestCase):
	"""
	Dynamic integration test suite for delayed employee checkin processing.
	Handles dynamic site environments and checkins with or without log_type
	(e.g. biometric devices that do not specify IN/OUT).
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.class_records = []

		# Save original geolocation setting and disable during tests to allow flexible testing
		cls.orig_allow_geolocation = frappe.db.get_single_value("HR Settings", "allow_geolocation_tracking")
		frappe.db.set_single_value("HR Settings", "allow_geolocation_tracking", 0)

		# 1. Dynamically resolve or create Company
		cls.company = cls.get_or_create_test_company()

		# 2. Dynamically resolve or create Shift Type
		cls.shift_name = cls.get_or_create_test_shift_type()

		# 3. Dynamically resolve or create Employee
		cls.employee = cls.get_or_create_test_employee()

		# Set test dates
		cls.test_date_1 = "2026-06-15"
		cls.test_date_2 = "2026-06-16"
		cls.test_date_3 = "2026-06-17"
		cls.test_date_4 = "2026-06-18"
		cls.test_date_5 = "2026-06-19"

	@classmethod
	def get_or_create_test_company(cls) -> str:
		company = frappe.defaults.get_user_default("company") or frappe.db.get_value("Company", {}, "name")
		if company:
			return company

		test_comp_name = "_Test Dynamic Company"
		if frappe.db.exists("Company", test_comp_name):
			return test_comp_name

		comp = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": test_comp_name,
				"default_currency": "INR",
				"country": "India",
			}
		).insert(ignore_permissions=True)
		cls.class_records.append(("Company", comp.name))
		return comp.name

	@classmethod
	def get_or_create_test_shift_type(cls) -> str:
		shift_name = "_Test Delayed Shift"
		shift_values = {
			"enable_auto_attendance": 1,
			"mark_auto_attendance_on_holidays": 1,
			"determine_check_in_and_check_out": "Alternating entries as IN and OUT during the same shift",
			"working_hours_calculation_based_on": "First Check-in and Last Check-out",
			"working_hours_threshold_for_half_day": 6.0,
			"working_hours_threshold_for_absent": 4.0,
		}
		if frappe.db.exists("Shift Type", shift_name):
			frappe.db.set_value(
				"Shift Type",
				shift_name,
				shift_values,
				update_modified=False,
			)
			frappe.clear_document_cache("Shift Type", shift_name)
			return shift_name

		shift = frappe.get_doc(
			{
				"doctype": "Shift Type",
				"name": shift_name,
				"start_time": "09:00:00",
				"end_time": "18:00:00",
				**shift_values,
			}
		).insert(ignore_permissions=True)
		frappe.clear_document_cache("Shift Type", shift_name)
		cls.class_records.append(("Shift Type", shift.name))
		return shift.name

	@classmethod
	def get_or_create_test_employee(cls) -> str:
		emp_email = "test.delayed.dynamic@example.com"
		existing_emp = frappe.db.get_value("Employee", {"company_email": emp_email}, "name")
		if existing_emp:
			frappe.db.set_value("Employee", existing_emp, "status", "Active", update_modified=False)
			frappe.db.set_value(
				"Employee", existing_emp, "default_shift", cls.shift_name, update_modified=False
			)
			return existing_emp

		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "_Test",
				"last_name": "Delayed Emp",
				"employee_name": "_Test Delayed Emp",
				"company_email": emp_email,
				"prefered_email": emp_email,
				"gender": "Female",
				"date_of_birth": "1995-01-01",
				"date_of_joining": "2020-01-01",
				"company": cls.company,
				"status": "Active",
				"default_shift": cls.shift_name,
				"person_to_be_contacted": "Emergency Contact",
				"emergency_phone_number": "9999999999",
				"relation": "Other",
				"salary_mode": "Bank",
			}
		)
		emp.flags.ignore_mandatory = True
		emp.insert(ignore_permissions=True, ignore_mandatory=True)
		cls.class_records.append(("Employee", emp.name))
		return emp.name

	@classmethod
	def tearDownClass(cls):
		if hasattr(cls, "orig_allow_geolocation") and cls.orig_allow_geolocation is not None:
			frappe.db.set_single_value(
				"HR Settings", "allow_geolocation_tracking", cls.orig_allow_geolocation
			)
		for doctype, name in reversed(cls.class_records):
			try:
				if frappe.db.exists(doctype, name):
					frappe.db.delete(doctype, {"name": name})
			except Exception:
				pass
		frappe.db.commit()  # nosemgrep
		super().tearDownClass()

	def create_checkin(self, **kwargs):
		"""
		Helper to create Employee Checkin record with valid coordinates and device_id.
		"""
		checkin_dict = {
			"doctype": "Employee Checkin",
			"employee": self.employee,
			"latitude": 23.0225,
			"longitude": 72.5714,
			"device_id": "TEST_DEVICE",
		}
		checkin_dict.update(kwargs)
		doc = frappe.get_doc(checkin_dict)
		doc.insert(ignore_permissions=True)
		self.cleanup_records.append(("Employee Checkin", doc.name))
		return doc

	def setUp(self):
		super().setUp()
		self.cleanup_records = []
		self.clean_test_dates(
			[
				self.test_date_1,
				self.test_date_2,
				self.test_date_3,
				self.test_date_4,
				self.test_date_5,
			]
		)

	def tearDown(self):
		for doctype, name in reversed(self.cleanup_records):
			try:
				if frappe.db.exists(doctype, name):
					frappe.db.delete(doctype, {"name": name})
			except Exception:
				pass
		self.clean_test_dates(
			[
				self.test_date_1,
				self.test_date_2,
				self.test_date_3,
				self.test_date_4,
				self.test_date_5,
			]
		)
		frappe.db.commit()  # nosemgrep
		super().tearDown()

	def clean_test_dates(self, dates: list):
		"""Deletes any leftover test checkins and attendances for the given test dates."""
		for d in dates:
			frappe.db.delete("Attendance", {"employee": self.employee, "attendance_date": d})
			frappe.db.delete("Employee Checkin", {"employee": self.employee, "time": ["like", f"{d}%"]})
		frappe.db.commit()  # nosemgrep

	def test_delayed_checkin_without_log_type_updates_attendance(self):
		"""
		Scenario: Biometric devices often upload punch records WITHOUT log_type (None/empty).
		Existing Attendance is Absent. Delayed checkins have no log_type set.
		The scheduler should still process them using First Checkin & Last Checkout rules,
		update the Attendance to Present, and link both checkins.
		"""
		test_date = self.test_date_1

		# 1. Existing Attendance created as Absent
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": test_date,
				"status": "Absent",
				"shift": self.shift_name,
				"working_hours": 0.0,
			}
		).insert(ignore_permissions=True)
		att.submit()
		self.cleanup_records.append(("Attendance", att.name))

		# 2. Delayed biometric punches without log_type (log_type omitted / None)
		ck_first = self.create_checkin(
			time=f"{test_date} 09:05:00",
			shift=self.shift_name,
			shift_start=f"{test_date} 09:00:00",
			shift_end=f"{test_date} 18:00:00",
			skip_auto_attendance=1,
		)

		ck_last = self.create_checkin(
			time=f"{test_date} 18:05:00",
			shift=self.shift_name,
			shift_start=f"{test_date} 09:00:00",
			shift_end=f"{test_date} 18:00:00",
			skip_auto_attendance=1,
		)

		# 3. Run delayed attendance scheduler
		result = process_delayed_employee_checkins()
		self.assertTrue(result["success"])
		self.assertIn(att.name, result["updated_attendances"])

		# 4. Verify Attendance is updated to Present with correct working hours
		updated_att = frappe.get_doc("Attendance", att.name)
		self.assertEqual(updated_att.status, "Present")
		self.assertGreater(updated_att.working_hours, 8.0)

		# Ensure no duplicate Attendance records were created
		att_count = frappe.db.count(
			"Attendance",
			{"employee": self.employee, "attendance_date": test_date, "docstatus": ["<", 2]},
		)
		self.assertEqual(att_count, 1)

		# 5. Verify skip_auto_attendance was disabled and checkins were linked
		ck_first_reloaded = frappe.get_doc("Employee Checkin", ck_first.name)
		ck_last_reloaded = frappe.get_doc("Employee Checkin", ck_last.name)
		self.assertEqual(ck_first_reloaded.skip_auto_attendance, 0)
		self.assertEqual(ck_last_reloaded.skip_auto_attendance, 0)
		self.assertEqual(ck_first_reloaded.attendance, att.name)
		self.assertEqual(ck_last_reloaded.attendance, att.name)

	def test_delayed_checkin_updates_to_half_day_without_log_type(self):
		"""
		Scenario: Delayed punches without log_type: 09:00 to 14:00 (5 hours).
		The Attendance should update from Absent to Half Day without requiring log_type.
		"""
		test_date = self.test_date_2

		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": test_date,
				"status": "Absent",
				"shift": self.shift_name,
				"working_hours": 0.0,
			}
		).insert(ignore_permissions=True)
		att.submit()
		self.cleanup_records.append(("Attendance", att.name))

		ck_first = self.create_checkin(
			time=f"{test_date} 09:00:00",
			shift=self.shift_name,
			shift_start=f"{test_date} 09:00:00",
			shift_end=f"{test_date} 18:00:00",
			skip_auto_attendance=1,
		)

		ck_last = self.create_checkin(
			time=f"{test_date} 14:00:00",
			shift=self.shift_name,
			shift_start=f"{test_date} 09:00:00",
			shift_end=f"{test_date} 18:00:00",
			skip_auto_attendance=1,
		)

		result = process_delayed_employee_checkins()
		self.assertTrue(result["success"])
		self.assertIn(att.name, result["updated_attendances"])

		updated_att = frappe.get_doc("Attendance", att.name)
		self.assertEqual(updated_att.status, "Half Day")
		self.assertEqual(updated_att.working_hours, 5.0)

		ck_first_reloaded = frappe.get_doc("Employee Checkin", ck_first.name)
		ck_last_reloaded = frappe.get_doc("Employee Checkin", ck_last.name)
		self.assertEqual(ck_first_reloaded.skip_auto_attendance, 0)
		self.assertEqual(ck_last_reloaded.skip_auto_attendance, 0)
		self.assertEqual(ck_first_reloaded.attendance, att.name)
		self.assertEqual(ck_last_reloaded.attendance, att.name)

	def test_existing_checkin_combined_with_delayed_checkout_mixed_log_type(self):
		"""
		Scenario: Employee punched in the morning with log_type = IN.
		Delayed checkout punch uploaded later has NO log_type (None).
		The scheduler should handle mixed log_type checkins smoothly.
		"""
		test_date = self.test_date_3

		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": test_date,
				"status": "Absent",
				"shift": self.shift_name,
				"working_hours": 0.0,
			}
		).insert(ignore_permissions=True)
		att.submit()
		self.cleanup_records.append(("Attendance", att.name))

		# Morning punch has log_type = IN
		ck_in = self.create_checkin(
			time=f"{test_date} 09:00:00",
			log_type="IN",
			shift=self.shift_name,
			shift_start=f"{test_date} 09:00:00",
			shift_end=f"{test_date} 18:00:00",
			skip_auto_attendance=0,
		)
		# Link existing checkin to attendance in DB (avoid triggering validate_time_change on insert)
		frappe.db.set_value("Employee Checkin", ck_in.name, "attendance", att.name, update_modified=False)

		# Delayed evening punch has NO log_type
		ck_out = self.create_checkin(
			time=f"{test_date} 18:00:00",
			shift=self.shift_name,
			shift_start=f"{test_date} 09:00:00",
			shift_end=f"{test_date} 18:00:00",
			skip_auto_attendance=1,
		)

		result = process_delayed_employee_checkins()
		self.assertTrue(result["success"])
		self.assertIn(att.name, result["updated_attendances"])

		updated_att = frappe.get_doc("Attendance", att.name)
		self.assertEqual(updated_att.status, "Present")
		self.assertEqual(updated_att.working_hours, 9.0)

		ck_out_reloaded = frappe.get_doc("Employee Checkin", ck_out.name)
		self.assertEqual(ck_out_reloaded.attendance, att.name)
		self.assertEqual(ck_out_reloaded.skip_auto_attendance, 0)

	def test_resolve_unassigned_checkin_shifts_without_log_type(self):
		"""
		Scenario: Raw checkin without shift and without log_type.
		With active Shift Assignment, shift should be resolved automatically.
		"""
		test_date = self.test_date_4

		sa = frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": self.employee,
				"shift_type": self.shift_name,
				"start_date": test_date,
				"status": "Active",
				"company": self.company,
			}
		).insert(ignore_permissions=True)
		sa.submit()
		self.cleanup_records.append(("Shift Assignment", sa.name))

		# Checkin without shift and without log_type
		ck = self.create_checkin(
			time=f"{test_date} 09:00:00",
			offshift=1,
		)

		# Ensure shift and shift_start are unassigned in DB so resolve_unassigned_checkin_shifts processes it
		frappe.db.set_value(
			"Employee Checkin",
			ck.name,
			{
				"shift": None,
				"shift_start": None,
				"shift_end": None,
				"shift_actual_start": None,
				"shift_actual_end": None,
				"offshift": 1,
			},
			update_modified=False,
		)

		resolve_unassigned_checkin_shifts()

		ck_reloaded = frappe.get_doc("Employee Checkin", ck.name)
		self.assertEqual(ck_reloaded.shift, self.shift_name)
		self.assertEqual(ck_reloaded.offshift, 0)
		self.assertIsNotNone(ck_reloaded.shift_start)

	def test_calculate_attendance_for_logs_helper_without_log_type(self):
		"""
		Verifies calculate_attendance_for_logs correctly processes logs when
		log_type is completely missing (None/empty).
		"""
		test_date = self.test_date_5
		logs = [
			frappe._dict(
				{
					"name": "CK-NO-LOG-1",
					"employee": self.employee,
					"time": f"{test_date} 09:00:00",
					"log_type": None,  # log_type not set
					"shift": self.shift_name,
					"shift_start": f"{test_date} 09:00:00",
					"shift_end": f"{test_date} 18:00:00",
				}
			),
			frappe._dict(
				{
					"name": "CK-NO-LOG-2",
					"employee": self.employee,
					"time": f"{test_date} 18:00:00",
					"log_type": None,  # log_type not set
					"shift": self.shift_name,
					"shift_start": f"{test_date} 09:00:00",
					"shift_end": f"{test_date} 18:00:00",
				}
			),
		]

		res = calculate_attendance_for_logs(self.employee, self.shift_name, test_date, logs)
		self.assertIsNotNone(res)
		self.assertEqual(res["status"], "Present")
		self.assertEqual(res["working_hours"], 9.0)
		self.assertEqual(res["late_entry"], 0)
		self.assertEqual(res["early_exit"], 0)
