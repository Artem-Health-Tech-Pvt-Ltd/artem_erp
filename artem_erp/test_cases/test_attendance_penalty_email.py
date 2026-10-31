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
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.cleanup_records = []

		# Ensure default outgoing email account is enabled
		if frappe.db.exists("Email Account", "Jobs"):
			frappe.db.set_value("Email Account", "Jobs", "default_outgoing", 1)
			frappe.db.set_value("Email Account", "Jobs", "enable_outgoing", 1)
		elif frappe.db.exists("Email Account", {"default_outgoing": 1}):
			pass
		else:
			accounts = frappe.get_all("Email Account", limit=1)
			if accounts:
				frappe.db.set_value("Email Account", accounts[0].name, "default_outgoing", 1)
				frappe.db.set_value("Email Account", accounts[0].name, "enable_outgoing", 1)

		# Ensure Email Template exists
		template_name = "Employee Attendance Penalty Notification"
		if not frappe.db.exists("Email Template", template_name):
			tpl = frappe.get_doc(
				{
					"doctype": "Email Template",
					"name": template_name,
					"subject": "Apply Attendance Penalty On {{ date }}",
					"response": "<p>Dear {{ employee_name }}, attendance penalty applied.</p>",
				}
			)
			tpl.insert(ignore_permissions=True)
			cls.cleanup_records.append(("Email Template", template_name))

		# Configure Artem Setting with the penalty template
		frappe.db.set_single_value(
			"Artem Setting",
			"employee_attendance_penalty_notification_email_template",
			template_name,
		)

		# Create a test-owned employee with a valid recipient email
		company = (
			frappe.defaults.get_user_default("company")
			or frappe.db.get_value("Company", {}, "name")
			or "Pearl Group"
		)
		cls.test_email = "test.penalty@artemhealthtech.com"

		# Clean up any leftover test employee from prior interrupted runs
		for old_emp in frappe.get_all("Employee", filters={"company_email": cls.test_email}, pluck="name"):
			frappe.db.delete("Attendance", {"employee": old_emp})
			frappe.db.delete("Communication", {"reference_name": old_emp})
			frappe.db.delete("Employee", {"name": old_emp})
		frappe.db.commit()  # nosemgrep

		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "_Test",
				"last_name": "Penalty Employee",
				"employee_name": "_Test Penalty Employee",
				"gender": "Female",
				"date_of_birth": "1995-01-01",
				"date_of_joining": "2022-01-01",
				"status": "Active",
				"company": company,
				"prefered_email": cls.test_email,
				"company_email": cls.test_email,
				"person_to_be_contacted": "Emergency Contact",
				"emergency_phone_number": "9999999999",
				"relation": "Other",
				"salary_mode": "Bank",
			}
		)
		emp.insert(ignore_permissions=True, ignore_mandatory=True)
		cls.test_emp = emp.name
		cls.cleanup_records.append(("Employee", cls.test_emp))

	@classmethod
	def tearDownClass(cls):
		for doctype, name in reversed(cls.cleanup_records):
			try:
				if frappe.db.exists(doctype, name):
					frappe.db.delete(doctype, {"name": name})
			except Exception:
				pass
		frappe.db.commit()  # nosemgrep
		super().tearDownClass()

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

		# Verify date-aware Shift Assignment takes precedence over default_shift
		frappe.db.set_value("Employee", self.test_emp, "default_shift", "Ahmedabad HO")
		if frappe.db.exists("Shift Type", "Mumbai"):
			sa = frappe.get_doc(
				{
					"doctype": "Shift Assignment",
					"employee": self.test_emp,
					"shift_type": "Mumbai",
					"start_date": "2026-05-10",
					"end_date": "2026-05-20",
					"status": "Active",
					"docstatus": 1,
				}
			)
			sa.insert(ignore_permissions=True)
			self.cleanup_records.append(("Shift Assignment", sa.name))

			# Inside Shift Assignment date range -> returns Mumbai (9.0 hrs)
			att_during_sa = frappe._dict({"employee": self.test_emp, "attendance_date": "2026-05-15"})
			self.assertEqual(get_required_working_hours(att_during_sa), "9.0 hrs")

			# Outside Shift Assignment date range -> falls back to default_shift Ahmedabad HO (9.5 hrs)
			att_outside_sa = frappe._dict({"employee": self.test_emp, "attendance_date": "2026-06-01"})
			self.assertEqual(get_required_working_hours(att_outside_sa), "9.5 hrs")

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
		# Create test attendance using test-owned employee fixture
		test_date = "2026-05-15"

		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.test_emp,
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
			self.assertIn(self.test_email, comm.recipients)

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
