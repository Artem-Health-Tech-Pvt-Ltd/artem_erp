# Copyright (c) 2026, Artem Healthtech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from artem_erp.auto_email.team_availability_email import (
	build_availability_details_html,
	is_department_notification_sent_today,
	send_daily_team_availability_notifications,
)
from artem_erp.auto_email.utils import (
	format_date_range,
	get_employee_recipient_email,
	get_initials,
	get_leave_emoji,
)


class TestTeamAvailability(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.class_cleanup_records = []

		company = frappe.defaults.get_user_default("company") or frappe.db.get_value("Company", {}, "name")
		if not company:
			comp_doc = frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": "_Test Company",
					"default_currency": "INR",
					"country": "India",
				}
			).insert(ignore_permissions=True)
			cls.class_cleanup_records.append(("Company", comp_doc.name))
			company = comp_doc.name

		cls.company = company
		cls.dept_name = "_Test Availability Dept"
		existing_dept = frappe.db.get_value(
			"Department",
			{"department_name": cls.dept_name, "company": cls.company},
			"name",
		)
		if not existing_dept:
			dept_doc = frappe.get_doc(
				{
					"doctype": "Department",
					"department_name": cls.dept_name,
					"company": cls.company,
				}
			).insert(ignore_permissions=True)
			cls.test_dept = dept_doc.name
			cls.class_cleanup_records.append(("Department", dept_doc.name))
		else:
			cls.test_dept = existing_dept

	@classmethod
	def tearDownClass(cls):
		for doctype, name in reversed(cls.class_cleanup_records):
			try:
				if frappe.db.exists(doctype, name):
					frappe.db.delete(doctype, {"name": name})
			except Exception:
				pass
		frappe.db.commit()  # nosemgrep
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		self.cleanup_records = []

	def tearDown(self):
		for doctype, name in self.cleanup_records:
			try:
				if frappe.db.exists(doctype, name):
					frappe.db.delete(doctype, {"name": name})
			except Exception:
				pass
		frappe.db.commit()  # nosemgrep
		super().tearDown()

	def test_get_employee_recipient_email(self):
		emp1 = {
			"prefered_email": "team.lead@example.com",
			"company_email": "fallback@example.com",
		}
		self.assertEqual(get_employee_recipient_email(emp1), "team.lead@example.com")

		emp2 = {
			"prefered_email": "",
			"company_email": "company@example.com",
		}
		self.assertEqual(get_employee_recipient_email(emp2), "company@example.com")

		emp3 = {
			"prefered_email": "not-an-email",
			"company_email": "",
		}
		self.assertIsNone(get_employee_recipient_email(emp3))

	def test_get_initials(self):
		self.assertEqual(get_initials("Patoliya Anjali"), "PA")
		self.assertEqual(get_initials("Twisha Bhaveshkumar"), "TB")
		self.assertEqual(get_initials("Kishan"), "KI")
		self.assertEqual(get_initials(""), "EM")

	def test_format_date_range(self):
		self.assertEqual(format_date_range("2026-10-16", "2026-10-16"), "16 Oct, 2026 - 16 Oct, 2026")
		self.assertEqual(format_date_range("2026-10-13", "2026-10-16"), "13 Oct, 2026 - 16 Oct, 2026")
		self.assertEqual(format_date_range("2026-10-13", None), "13 Oct, 2026")
		self.assertEqual(format_date_range(None, None), "")

	def test_get_leave_emoji(self):
		self.assertEqual(get_leave_emoji("Sick Leave"), "🤒")
		self.assertEqual(get_leave_emoji("Casual Leave"), "🌴")
		self.assertEqual(get_leave_emoji("Birthday Leave"), "🎂")
		self.assertEqual(get_leave_emoji(None), "🏖️")

	def test_build_availability_details_html(self):
		on_leave = [
			{
				"employee": "EMP-001",
				"employee_name": "Patoliya Anjali",
				"date_range": "13 Oct, 2026 - 16 Oct, 2026",
				"leave_type": "Sick Leave",
			}
		]
		wfh = [
			{
				"employee": "EMP-002",
				"employee_name": "Twisha Bhaveshkumar",
				"date_range": "16 Oct, 2026 - 16 Oct, 2026",
			}
		]
		html = build_availability_details_html(on_leave, wfh)
		self.assertIn("🤒 On Leave", html)
		self.assertIn("Patoliya Anjali", html)
		self.assertIn("Sick Leave", html)
		self.assertIn("🤒", html)
		self.assertIn("PA", html)
		self.assertIn("Working Remotely", html)
		self.assertIn("Twisha Bhaveshkumar", html)
		self.assertIn("TB", html)

	def test_duplicate_check_and_send_notifications(self):
		test_date = "2026-10-16"
		res = send_daily_team_availability_notifications(date=test_date)
		self.assertIsInstance(res, dict)
		self.assertIn("departments_sent", res)
		self.assertIn("departments_skipped_duplicate", res)
		self.assertIn("departments_no_availability", res)

		# Clean up any communications and email queues created during test send
		comms = frappe.get_all(
			"Communication",
			filters={
				"reference_doctype": "Department",
				"communication_date": test_date,
			},
			pluck="name",
		)
		for c in comms:
			self.cleanup_records.append(("Communication", c))

		eqs = frappe.get_all(
			"Email Queue",
			filters={
				"reference_doctype": "Department",
				"status": ["in", ["Not Sent", "Sending"]],
			},
			pluck="name",
		)
		for eq in eqs:
			self.cleanup_records.append(("Email Queue", eq))

	def test_duplicate_error_log_generation(self):
		dept = self.test_dept
		test_date = "2026-10-28"

		# Ensure communication exists for dept on test_date
		if not frappe.db.exists(
			"Communication",
			{"reference_doctype": "Department", "reference_name": dept, "communication_date": test_date},
		):
			comm = frappe.get_doc(
				{
					"doctype": "Communication",
					"communication_type": "Automated Message",
					"communication_medium": "Email",
					"sent_or_received": "Sent",
					"reference_doctype": "Department",
					"reference_name": dept,
					"subject": f"Team Availability Update - {test_date}",
					"content": "Test content",
					"communication_date": test_date,
				}
			)
			comm.insert(ignore_permissions=True)
			self.cleanup_records.append(("Communication", comm.name))

		# Clear previous duplicate error logs for dept to test cleanly
		frappe.db.delete("Error Log", {"method": ["like", f"%{dept}%"]})
		frappe.db.commit()  # nosemgrep

		is_sent = is_department_notification_sent_today(dept, test_date)
		self.assertTrue(is_sent)

		# Verify error log was created
		logs = frappe.get_all(
			"Error Log",
			filters={"reference_doctype": "Department", "reference_name": dept},
			fields=["name", "method", "error"],
		)
		self.assertTrue(len(logs) > 0)
		for log in logs:
			self.cleanup_records.append(("Error Log", log.name))
		self.assertIn("Already Sent", logs[0].method)
