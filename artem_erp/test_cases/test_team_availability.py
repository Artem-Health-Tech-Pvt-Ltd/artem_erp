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
		self.assertEqual(get_initials("Patoliya Anjali"), "AP")
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
		self.assertIn("AP", html)
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

	def test_duplicate_error_log_generation(self):
		dept = "Software Team - ETPL"
		test_date = "2026-10-28"

		# Ensure communication exists for dept today
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
					"subject": "Team Availability Update - 28 Oct, 2026",
					"content": "Test content",
					"communication_date": test_date,
				}
			)
			comm.insert(ignore_permissions=True)

		# Clear previous duplicate error logs for dept to test cleanly
		frappe.db.delete("Error Log", {"method": ["like", f"%{dept}%"]})

		is_sent = is_department_notification_sent_today(dept, test_date)
		self.assertTrue(is_sent)

		# Verify error log was created
		logs = frappe.get_all(
			"Error Log",
			filters={"reference_doctype": "Department", "reference_name": dept},
			fields=["method", "error"],
		)
		self.assertTrue(len(logs) > 0)
		self.assertIn("Already Sent", logs[0].method)
