# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import unittest
from datetime import timedelta

import frappe
from frappe.utils import add_days, getdate

from artem_erp.doc_events.attendance_request import (
	build_date_wise_multiple_shifts_html_message,
	build_multiple_shifts_html_message,
	build_same_date_multiple_shifts_html_message,
	build_unassigned_dates_html_message,
	detect_shifts_and_validate,
	get_company_attendance_regularization_config,
	get_date_wise_shift_analysis,
	get_effective_shift_for_date,
	get_inclusive_date_range_days,
	get_shift_time_label,
	get_shift_working_hours,
	get_shifts_for_date,
	get_shifts_for_date_range,
	group_consecutive_date_wise_shifts,
	group_consecutive_shifts,
	validate_attendance_request_doc,
)


class TestCompanyAttendanceRegularization(unittest.TestCase):
	def setUp(self):
		frappe.db.rollback()

	def tearDown(self):
		frappe.db.rollback()

	def test_get_inclusive_date_range_days(self):
		self.assertEqual(get_inclusive_date_range_days("2026-11-01", "2026-11-01"), 1)
		self.assertEqual(get_inclusive_date_range_days("2026-11-01", "2026-11-03"), 3)
		self.assertEqual(get_inclusive_date_range_days("2026-11-01", "2026-11-05"), 5)

	def test_group_consecutive_shifts(self):
		date_shifts = [
			{"date": getdate("2026-11-15"), "shift": "General Shift"},
			{"date": getdate("2026-11-16"), "shift": "General Shift"},
			{"date": getdate("2026-11-17"), "shift": "General Shift"},
			{"date": getdate("2026-11-18"), "shift": "Evening Shift"},
			{"date": getdate("2026-11-19"), "shift": "Evening Shift"},
		]
		groups = group_consecutive_shifts(date_shifts)
		self.assertEqual(len(groups), 2)
		self.assertEqual(groups[0]["shift"], "General Shift")
		self.assertEqual(str(groups[0]["start_date"]), "2026-11-15")
		self.assertEqual(str(groups[0]["end_date"]), "2026-11-17")
		self.assertEqual(groups[1]["shift"], "Evening Shift")
		self.assertEqual(str(groups[1]["start_date"]), "2026-11-18")
		self.assertEqual(str(groups[1]["end_date"]), "2026-11-19")

	def test_group_consecutive_shifts_with_one_day_override(self):
		# Scenario 5 segmenting: General (03-04), Evening (05), General (06-07)
		date_shifts = [
			{"date": getdate("2026-11-03"), "shift": "General Shift"},
			{"date": getdate("2026-11-04"), "shift": "General Shift"},
			{"date": getdate("2026-11-05"), "shift": "Evening Shift"},
			{"date": getdate("2026-11-06"), "shift": "General Shift"},
			{"date": getdate("2026-11-07"), "shift": "General Shift"},
		]
		groups = group_consecutive_shifts(date_shifts)
		self.assertEqual(len(groups), 3)
		self.assertEqual(groups[0]["shift"], "General Shift")
		self.assertEqual(str(groups[0]["start_date"]), "2026-11-03")
		self.assertEqual(str(groups[0]["end_date"]), "2026-11-04")
		self.assertEqual(groups[1]["shift"], "Evening Shift")
		self.assertEqual(str(groups[1]["start_date"]), "2026-11-05")
		self.assertEqual(str(groups[1]["end_date"]), "2026-11-05")
		self.assertEqual(groups[2]["shift"], "General Shift")
		self.assertEqual(str(groups[2]["start_date"]), "2026-11-06")
		self.assertEqual(str(groups[2]["end_date"]), "2026-11-07")

	def test_build_multiple_shifts_html_message(self):
		shift_groups = [
			{
				"shift": "General Shift",
				"start_date": getdate("2026-11-15"),
				"end_date": getdate("2026-11-20"),
				"working_hours": "09:30 - 19:00",
			},
			{
				"shift": "Evening Shift",
				"start_date": getdate("2026-11-21"),
				"end_date": getdate("2026-11-25"),
				"working_hours": "10:00 - 18:30",
			},
		]
		html = build_multiple_shifts_html_message(shift_groups)
		self.assertIn("Multiple Shifts Found in the Selected Date Range", html)
		self.assertIn("General Shift", html)
		self.assertIn("Evening Shift", html)
		self.assertIn("15-11-2026 to 20-11-2026", html)
		self.assertIn("21-11-2026 to 25-11-2026", html)
		self.assertIn("09:30 - 19:00", html)
		self.assertIn("10:00 - 18:30", html)

	def test_get_shift_time_label(self):
		from unittest.mock import patch

		with patch(
			"frappe.db.get_value",
			return_value={
				"start_time": timedelta(seconds=9 * 3600 + 30 * 60),
				"end_time": timedelta(seconds=18 * 3600 + 30 * 60),
			},
		):
			label = get_shift_time_label("General Shift")
			self.assertEqual(label, "From Time: 09:30 to To Time: 18:30")

	def test_build_same_date_multiple_shifts_html_message(self):
		from unittest.mock import patch

		def mock_get_value(doctype, name, fields, as_dict=False):
			if name == "Morning Shift":
				return {"start_time": timedelta(seconds=8 * 3600), "end_time": timedelta(seconds=13 * 3600)}
			elif name == "Evening Shift":
				return {"start_time": timedelta(seconds=16 * 3600), "end_time": timedelta(seconds=20 * 3600)}
			return {}

		with patch("frappe.db.get_value", side_effect=mock_get_value):
			html = build_same_date_multiple_shifts_html_message(
				"2026-11-03", ["Morning Shift", "Evening Shift"]
			)
			self.assertIn("Shift Selection Required", html)
			self.assertIn("Morning Shift", html)
			self.assertIn("From Time: 08:00 to To Time: 13:00", html)
			self.assertIn("Evening Shift", html)
			self.assertIn("From Time: 16:00 to To Time: 20:00", html)
			self.assertIn("03-11-2026", html)
			self.assertIn("Please select one of the applicable shifts from the Shift field.", html)

	def test_same_date_multiple_shifts_validation_logic(self):
		from unittest.mock import patch

		def mock_get_shifts_for_date(employee, dt):
			if getdate(dt) == getdate("2026-11-03"):
				return ["Morning Shift", "Evening Shift"]
			return []

		doc = frappe._dict(
			doctype="Attendance Request",
			employee="EMP-TEST",
			company="Test Company",
			from_date="2026-11-03",
			to_date="2026-11-03",
			shift=None,
			docstatus=0,
		)

		with (
			patch(
				"artem_erp.doc_events.attendance_request.get_company_attendance_regularization_config",
				return_value={"enable_single_day": 0, "max_days": 0},
			),
			patch(
				"artem_erp.doc_events.attendance_request.get_shifts_for_date",
				side_effect=mock_get_shifts_for_date,
			),
		):
			# 1. When shift is not selected, must throw ValidationError (Shift Selection Required)
			with self.assertRaises(frappe.ValidationError):
				validate_attendance_request_doc(doc)

			# 2. When employee selects "Morning Shift", validation must pass
			doc.shift = "Morning Shift"
			validate_attendance_request_doc(doc)  # Should not raise

			# 3. When employee selects "Evening Shift", validation must pass
			doc.shift = "Evening Shift"
			validate_attendance_request_doc(doc)  # Should not raise

			# 4. When employee selects an unassigned shift "Night Shift", must raise ValidationError
			doc.shift = "Night Shift"
			with self.assertRaises(frappe.ValidationError):
				validate_attendance_request_doc(doc)

		# 5. When company has enable_single_day=1, selecting a valid assigned shift must pass
		with (
			patch(
				"artem_erp.doc_events.attendance_request.get_company_attendance_regularization_config",
				return_value={"enable_single_day": 1, "max_days": 1},
			),
			patch(
				"artem_erp.doc_events.attendance_request.get_shifts_for_date",
				side_effect=mock_get_shifts_for_date,
			),
		):
			doc.shift = "Morning Shift"
			validate_attendance_request_doc(doc)  # Should not raise

	def test_date_range_multiple_shifts_scenario(self):
		"""
		Tests scenario:
		From Date: 03-11-2026, To Date: 04-11-2026
		03-11: Morning Shift & Evening Shift
		04-11: Night Shift (different shift)
		Must identify different shifts date by date, require separate requests,
		and NEVER display that no shift is assigned because shifts are assigned!
		"""
		from unittest.mock import patch

		def mock_get_shifts(employee, dt):
			if getdate(dt) == getdate("2026-11-03"):
				return ["Morning Shift", "Evening Shift"]
			elif getdate(dt) == getdate("2026-11-04"):
				return ["Night Shift"]
			return []

		with patch(
			"artem_erp.doc_events.attendance_request.get_shifts_for_date", side_effect=mock_get_shifts
		):
			analysis = get_date_wise_shift_analysis("EMP-TEST", "2026-11-03", "2026-11-04")
			self.assertFalse(analysis["has_unassigned_dates"])
			self.assertTrue(analysis["has_date_range_multiple_shifts"])
			self.assertEqual(analysis["common_shifts"], [])

			html = analysis["multiple_shifts_message"]
			self.assertIn("03-11-2026", html)
			self.assertIn("Morning Shift", html)
			self.assertIn("Evening Shift", html)
			self.assertIn("04-11-2026", html)
			self.assertIn("Night Shift", html)
			self.assertNotIn("No Shift Assigned", html)

			# Attempting to validate should raise ValidationError
			doc = frappe._dict(
				doctype="Attendance Request",
				employee="EMP-TEST",
				company="Test Company",
				from_date="2026-11-03",
				to_date="2026-11-04",
				shift=None,
				docstatus=0,
			)
			with patch(
				"artem_erp.doc_events.attendance_request.get_company_attendance_regularization_config",
				return_value={"enable_single_day": 0, "max_days": 0},
			):
				with self.assertRaises(frappe.ValidationError):
					validate_attendance_request_doc(doc)

	def test_unassigned_dates_identifies_specific_date(self):
		"""
		Tests scenario:
		03-11 has Morning Shift
		04-11 has NO shift
		Must specifically identify 04-11-2026 as unassigned, and NOT 03-11-2026!
		"""
		from unittest.mock import patch

		def mock_get_shifts(employee, dt):
			if getdate(dt) == getdate("2026-11-03"):
				return ["Morning Shift"]
			return []

		with patch(
			"artem_erp.doc_events.attendance_request.get_shifts_for_date", side_effect=mock_get_shifts
		):
			analysis = get_date_wise_shift_analysis("EMP-TEST", "2026-11-03", "2026-11-04")
			self.assertTrue(analysis["has_unassigned_dates"])
			self.assertEqual(len(analysis["dates_with_no_shift"]), 1)
			self.assertEqual(str(analysis["dates_with_no_shift"][0]["date"]), "2026-11-04")

			html = analysis["unassigned_dates_message"]
			self.assertIn("04-11-2026", html)
			self.assertNotIn("03-11-2026", html)

	def test_date_range_grouping_consecutive_dates_for_same_shift(self):
		"""
		Tests that consecutive dates having the same shift are grouped into a single
		date range row (e.g. 04-11-2026 to 10-11-2026 for Ahmedabad HO)
		instead of separate date rows.
		"""
		from unittest.mock import patch

		def mock_get_shifts(employee, dt):
			if getdate(dt) == getdate("2026-11-03"):
				return ["Test", "9:30-11:30"]
			elif getdate("2026-11-04") <= getdate(dt) <= getdate("2026-11-10"):
				return ["Ahmedabad HO"]
			return []

		with patch(
			"artem_erp.doc_events.attendance_request.get_shifts_for_date", side_effect=mock_get_shifts
		):
			analysis = get_date_wise_shift_analysis("EMP-TEST", "2026-11-03", "2026-11-10")
			groups = group_consecutive_date_wise_shifts(analysis["date_wise"])
			self.assertEqual(len(groups), 2)
			self.assertEqual(groups[0]["date_range_str"], "03-11-2026")
			self.assertEqual(groups[0]["shifts"], ["Test", "9:30-11:30"])
			self.assertEqual(groups[1]["date_range_str"], "04-11-2026 to 10-11-2026")
			self.assertEqual(groups[1]["shifts"], ["Ahmedabad HO"])

			html = analysis["multiple_shifts_message"]
			self.assertIn("04-11-2026 to 10-11-2026", html)
			self.assertIn("Ahmedabad HO", html)
