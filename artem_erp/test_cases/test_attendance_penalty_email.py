# Copyright (c) 2026, Artem Healthtech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from artem_erp.auto_email.attendance_penalty_email import (
	get_missing_punches_label,
	get_penalty_leave_type,
	get_required_working_hours,
	is_penalty_notification_already_sent,
	send_attendance_penalty_email,
)


class TestAttendancePenaltyEmail(IntegrationTestCase):
	def test_get_required_working_hours(self):
		att1 = frappe._dict({"custom_adjusted_required_hours": 6.5})
		self.assertEqual(get_required_working_hours(att1), "6.5 hrs")

		att2 = frappe._dict({"standard_working_hours": 9.0})
		self.assertEqual(get_required_working_hours(att2), "9.0 hrs")

		att3 = frappe._dict({"shift": "Ahmedabad HO"})
		self.assertEqual(get_required_working_hours(att3), "9.5 hrs")

		att4 = frappe._dict({"shift": "Mumbai"})
		self.assertEqual(get_required_working_hours(att4), "9.0 hrs")

		att5 = frappe._dict({"employee": "CON-002"})
		self.assertEqual(get_required_working_hours(att5), "9.5 hrs")

	def test_get_missing_punches_label(self):
		att_both_missing = frappe._dict({"in_time": None, "out_time": None, "working_hours": 0})
		self.assertIn("Yes", get_missing_punches_label(att_both_missing))

		att_in_missing = frappe._dict(
			{"in_time": None, "out_time": "2026-10-28 18:00:00", "working_hours": 0}
		)
		self.assertIn("Punch-In", get_missing_punches_label(att_in_missing))

		att_out_missing = frappe._dict(
			{"in_time": "2026-10-28 09:30:00", "out_time": None, "working_hours": 0}
		)
		self.assertIn("Punch-Out", get_missing_punches_label(att_out_missing))

		att_complete = frappe._dict(
			{"in_time": "2026-10-28 09:30:00", "out_time": "2026-10-28 18:00:00", "working_hours": 8.5}
		)
		self.assertEqual(get_missing_punches_label(att_complete), "No")

	def test_get_penalty_leave_type(self):
		att1 = frappe._dict({"leave_type": "Casual Leave"})
		self.assertEqual(get_penalty_leave_type(att1), "Casual Leave")

		att2 = frappe._dict({"status": "Absent"})
		self.assertEqual(get_penalty_leave_type(att2, penalty_status="Half Day"), "Half Day")

	def test_send_attendance_penalty_email_and_duplicate_prevention(self):
		# Create test attendance
		test_date = "2026-05-15"
		test_emp = "ETPL-CON-0001"

		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": test_emp,
				"attendance_date": test_date,
				"status": "Absent",
				"custom_penalty": 1,
				"working_hours": 0,
			}
		)
		att.insert(ignore_permissions=True)

		try:
			# First send: should succeed
			res1 = send_attendance_penalty_email(
				att,
				reason="Attendance penalty applied: No Punch records; 0 working hours; marked as Absent.",
				penalty_status="Absent",
			)
			self.assertTrue(res1)

			# Verify Communication was created
			comm = frappe.db.get_value(
				"Communication",
				{"reference_doctype": "Attendance", "reference_name": att.name},
				["name", "subject", "recipients"],
				as_dict=True,
			)
			self.assertIsNotNone(comm)
			self.assertIn("Attendance Penalty", comm.subject)
			self.assertIn("anjali.patoliya@artemhealthtech.com", comm.recipients)

			# Second send: should detect duplicate and skip
			res2 = send_attendance_penalty_email(
				att,
				reason="Attendance penalty applied: duplicate attempt.",
				penalty_status="Absent",
			)
			self.assertFalse(res2)

			# Verify duplicate check directly
			self.assertTrue(is_penalty_notification_already_sent(att.name))

		finally:
			# Cleanup test attendance and communication
			frappe.db.delete("Communication", {"reference_doctype": "Attendance", "reference_name": att.name})
			frappe.db.delete("Email Queue", {"reference_doctype": "Attendance", "reference_name": att.name})
			frappe.db.delete("Attendance", {"name": att.name})
