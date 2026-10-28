# Copyright (c) 2026, Artem Healthtech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from artem_erp.auto_email.birthday_and_work_anniversary import (
	get_birthday_employees,
	get_work_anniversary_employees,
	send_birthday_wishes,
)
from artem_erp.auto_email.utils import (
	get_employee_recipient_email,
	get_ordinal,
	parse_cc_recipients,
)


class TestBirthdayAnniversary(IntegrationTestCase):
	def tearDown(self):
		frappe.db.set_value("Employee", "12079883", "date_of_joining", "2024-08-12")
		frappe.db.set_value("Employee", "12079883", "date_of_birth", "2004-05-30")

	def test_get_ordinal(self):
		self.assertEqual(get_ordinal(1), "1st")
		self.assertEqual(get_ordinal(2), "2nd")
		self.assertEqual(get_ordinal(3), "3rd")
		self.assertEqual(get_ordinal(4), "4th")
		self.assertEqual(get_ordinal(11), "11th")
		self.assertEqual(get_ordinal(12), "12th")
		self.assertEqual(get_ordinal(13), "13th")
		self.assertEqual(get_ordinal(21), "21st")
		self.assertEqual(get_ordinal(22), "22nd")
		self.assertEqual(get_ordinal(23), "23rd")
		self.assertEqual(get_ordinal(100), "100th")

	def test_parse_cc_recipients(self):
		# Test string
		raw = 'hr@example.com, "Management Team" <mgmt@example.com>; dev@example.com\nadmin@example.com, hr@example.com'
		parsed = parse_cc_recipients(raw)
		self.assertIn("hr@example.com", parsed)
		self.assertIn('"Management Team" <mgmt@example.com>', parsed)
		self.assertIn("dev@example.com", parsed)
		self.assertIn("admin@example.com", parsed)
		# Ensure deduplicated
		self.assertEqual(len([p for p in parsed if "hr@example.com" in p]), 1)

		# Test Table MultiSelect dict rows
		table_rows = [
			{"email_group": "non_existent_group", "email": "row1@example.com"},
			{"email_group": "row2@example.com"},
		]
		parsed_table = parse_cc_recipients(table_rows)
		self.assertIn("row2@example.com", parsed_table)

	def test_get_employee_recipient_email(self):
		# Test prefered_email priority
		emp1 = {
			"prefered_email": "direct@test.com",
			"company_email": "company@test.com",
			"personal_email": "personal@test.com",
		}
		self.assertEqual(get_employee_recipient_email(emp1), "direct@test.com")

		# Test fallback to company_email when prefered_email is missing
		emp2 = {
			"prefered_email": "",
			"company_email": "company@test.com",
		}
		self.assertEqual(get_employee_recipient_email(emp2), "company@test.com")

		# Neither prefered_email nor company_email has valid email
		emp3 = {
			"prefered_email": "invalid-email-format",
			"company_email": "",
		}
		self.assertIsNone(get_employee_recipient_email(emp3))

	def test_birthday_query_matching(self):
		# Rohan's DOB is 30-05-2004
		employees = get_birthday_employees("2026-05-30")
		employee_ids = [e["name"] for e in employees]
		self.assertIn("12079883", employee_ids)

	def test_work_anniversary_query_matching(self):
		# Rohan's joining date is 12-08-2024
		employees = get_work_anniversary_employees("2026-08-12")
		employee_ids = [e["name"] for e in employees]
		self.assertIn("12079883", employee_ids)

		# Current year joining should NOT be included as an anniversary
		employees_joining_year = get_work_anniversary_employees("2024-08-12")
		employee_ids_joining_year = [e["name"] for e in employees_joining_year]
		self.assertNotIn("12079883", employee_ids_joining_year)

	def test_duplicate_prevention_and_error_logging(self):
		target_date = "2026-05-30"
		# Missing email logs error
		frappe.db.set_value("Employee", "12079883", "company_email", "")
		frappe.db.set_value("Employee", "12079883", "personal_email", "")
		frappe.db.set_value("Employee", "12079883", "prefered_email", "")
		frappe.db.set_value("Employee", "12079883", "user_id", "")

		res = send_birthday_wishes(target_date)
		self.assertGreaterEqual(res["errors"], 1)

		# Now configure valid email and CC
		frappe.db.set_value("Email Account", "Jobs", "default_outgoing", 1)
		frappe.db.set_value("Email Account", "Jobs", "enable_outgoing", 1)
		frappe.db.set_value("Employee", "12079883", "prefered_email", "rohan.test@artemhealthtech.com")
		frappe.db.set_single_value("Artem Setting", "company_team_emails", "team@artemhealthtech.com")

		# First send
		res1 = send_birthday_wishes(target_date)
		self.assertEqual(res1["sent"], 1)

		# Second send on the same date should be skipped to prevent duplicates
		res2 = send_birthday_wishes(target_date)
		self.assertEqual(res2["skipped"], 1)
		self.assertEqual(res2["sent"], 0)

	def test_separate_birthday_and_anniversary_sends(self):
		target_date = "2026-05-30"
		frappe.db.set_value("Email Account", "Jobs", "default_outgoing", 1)
		frappe.db.set_value("Email Account", "Jobs", "enable_outgoing", 1)
		frappe.db.set_value("Employee", "12079883", "prefered_email", "rohan.test@artemhealthtech.com")
		try:
			# Set joining date to match birthday date
			frappe.db.set_value("Employee", "12079883", "date_of_joining", "2022-05-30")
			frappe.db.set_single_value("Artem Setting", "company_team_emails", "team@artemhealthtech.com")

			# Clear communications for test employee
			frappe.db.delete("Communication", {"reference_name": "12079883"})
			frappe.db.delete("Email Queue", {"reference_name": "12079883"})

			from artem_erp.auto_email import send_birthday_and_anniversary_wishes

			result = send_birthday_and_anniversary_wishes(target_date)
			# Both birthday and anniversary must send separately
			self.assertEqual(result["birthday"]["sent"], 1)
			self.assertEqual(result["anniversary"]["sent"], 1)

			comms = frappe.get_all(
				"Communication",
				filters={"reference_name": "12079883"},
				fields=["subject", "email_template"],
			)
			self.assertEqual(len(comms), 2)
			templates_used = [c.email_template for c in comms]
			self.assertIn("Employee Birthday", templates_used)
			self.assertIn("Employee Work Anniversary", templates_used)
		finally:
			frappe.db.set_value("Employee", "12079883", "date_of_joining", "2024-08-12")
