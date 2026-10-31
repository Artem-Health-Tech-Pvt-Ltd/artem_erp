# Copyright (c) 2026, Artem Healthtech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from artem_erp.auto_email.birthday_and_work_anniversary import (
	get_birthday_employees,
	get_work_anniversary_employees,
	send_birthday_wishes,
	send_work_anniversary_wishes,
)
from artem_erp.auto_email.utils import (
	get_employee_recipient_email,
	get_ordinal,
	parse_cc_recipients,
)


class TestBirthdayAnniversary(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.cleanup_records = []

		# Outgoing email account
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

		# Ensure birthday and anniversary templates exist
		for t_name in ["Employee Birthday", "Employee Work Anniversary"]:
			if not frappe.db.exists("Email Template", t_name):
				tpl = frappe.get_doc(
					{
						"doctype": "Email Template",
						"name": t_name,
						"subject": f"Happy {t_name}, {{{{ employee_name }}}}!",
						"response": f"<p>Happy {t_name}, {{{{ employee_name }}}}!</p>",
					}
				).insert(ignore_permissions=True)
				cls.cleanup_records.append(("Email Template", tpl.name))

		frappe.db.set_single_value("Artem Setting", "employee_birthday_email_template", "Employee Birthday")
		frappe.db.set_single_value(
			"Artem Setting", "employee_work_anniversary_email_template", "Employee Work Anniversary"
		)
		frappe.db.set_single_value("Artem Setting", "company_team_emails", "team@artemhealthtech.com")

		# Create a test-owned employee fixture
		company = (
			frappe.defaults.get_user_default("company")
			or frappe.db.get_value("Company", {}, "name")
			or "Pearl Group"
		)
		holiday_list = frappe.db.get_value("Holiday List", {}, "name")
		cls.test_email = "test.birthday@artemhealthtech.com"
		cls.test_dob = "2000-05-30"
		cls.test_doj = "2020-08-12"

		# Clean up any leftover test employee from prior interrupted runs
		for old_emp in frappe.get_all("Employee", filters={"company_email": cls.test_email}, pluck="name"):
			frappe.db.delete("Communication", {"reference_name": old_emp})
			frappe.db.delete("Employee", {"name": old_emp})
		frappe.db.commit()  # nosemgrep

		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "_Test",
				"last_name": "Birthday Employee",
				"employee_name": "_Test Birthday Employee",
				"gender": "Female",
				"date_of_birth": cls.test_dob,
				"date_of_joining": cls.test_doj,
				"status": "Active",
				"company": company,
				"holiday_list": holiday_list,
				"prefered_email": cls.test_email,
				"company_email": cls.test_email,
				"person_to_be_contacted": "Emergency Contact",
				"emergency_phone_number": "9999999999",
				"relation": "Other",
				"salary_mode": "Bank",
			}
		)
		emp.insert(ignore_permissions=True, ignore_mandatory=True)
		cls.test_emp_id = emp.name
		cls.cleanup_records.append(("Employee", emp.name))

	@classmethod
	def tearDownClass(cls):
		if hasattr(cls, "test_emp_id"):
			frappe.db.delete("Communication", {"reference_name": cls.test_emp_id})
			frappe.db.delete("Email Queue", {"reference_name": cls.test_emp_id})
		for doctype, name in reversed(cls.cleanup_records):
			try:
				if frappe.db.exists(doctype, name):
					frappe.db.delete(doctype, {"name": name})
			except Exception:
				pass
		frappe.db.commit()  # nosemgrep
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		frappe.db.set_value("Employee", self.test_emp_id, "date_of_birth", self.test_dob)
		frappe.db.set_value("Employee", self.test_emp_id, "date_of_joining", self.test_doj)
		frappe.db.set_value("Employee", self.test_emp_id, "prefered_email", self.test_email)
		frappe.db.delete("Communication", {"reference_name": self.test_emp_id})
		frappe.db.delete("Email Queue", {"reference_name": self.test_emp_id})

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
		# Target date matches test employee's DOB (May 30)
		employees = get_birthday_employees("2026-05-30")
		employee_ids = [e["name"] for e in employees]
		self.assertIn(self.test_emp_id, employee_ids)

	def test_work_anniversary_query_matching(self):
		# Target date matches test employee's joining anniversary (Aug 12)
		employees = get_work_anniversary_employees("2026-08-12")
		employee_ids = [e["name"] for e in employees]
		self.assertIn(self.test_emp_id, employee_ids)

		# Current year joining should NOT be included as an anniversary (0 completed years)
		employees_joining_year = get_work_anniversary_employees(self.test_doj)
		employee_ids_joining_year = [e["name"] for e in employees_joining_year]
		self.assertNotIn(self.test_emp_id, employee_ids_joining_year)

	def test_work_anniversary_email_sent_only_to_employee_without_cc(self):
		target_date = "2026-08-12"
		frappe.db.delete("Communication", {"reference_name": self.test_emp_id})
		frappe.db.delete("Email Queue", {"reference_name": self.test_emp_id})

		res = send_work_anniversary_wishes(target_date)
		self.assertGreaterEqual(res["sent"], 1)

		comm = frappe.db.get_value(
			"Communication",
			{"reference_name": self.test_emp_id, "email_template": "Employee Work Anniversary"},
			["name", "recipients", "cc"],
			as_dict=True,
		)
		self.assertIsNotNone(comm)
		# Sent ONLY to the celebrating employee
		self.assertIn(self.test_email, comm.recipients)
		self.assertNotIn("team@artemhealthtech.com", comm.recipients)
		# Ensure NO CC recipients are set
		self.assertEqual(comm.cc or "", "")

	def test_duplicate_prevention_and_error_logging(self):
		target_date = "2026-05-30"
		# Missing email logs error
		frappe.db.set_value("Employee", self.test_emp_id, "company_email", "")
		frappe.db.set_value("Employee", self.test_emp_id, "personal_email", "")
		frappe.db.set_value("Employee", self.test_emp_id, "prefered_email", "")
		frappe.db.set_value("Employee", self.test_emp_id, "user_id", "")

		res = send_birthday_wishes(target_date)
		self.assertGreaterEqual(res["errors"], 1)

		# Now configure valid email
		frappe.db.set_value("Employee", self.test_emp_id, "prefered_email", self.test_email)

		# First send
		res1 = send_birthday_wishes(target_date)
		self.assertEqual(res1["sent"], 1)

		# Second send on the same date should be skipped to prevent duplicates
		res2 = send_birthday_wishes(target_date)
		self.assertEqual(res2["skipped"], 1)
		self.assertEqual(res2["sent"], 0)

	def test_separate_birthday_and_anniversary_sends(self):
		target_date = "2026-05-30"
		try:
			# Set joining date to match birthday date
			frappe.db.set_value("Employee", self.test_emp_id, "date_of_joining", "2020-05-30")
			frappe.db.set_value("Employee", self.test_emp_id, "prefered_email", self.test_email)

			# Clear communications for test employee
			frappe.db.delete("Communication", {"reference_name": self.test_emp_id})
			frappe.db.delete("Email Queue", {"reference_name": self.test_emp_id})

			from artem_erp.auto_email import send_birthday_and_anniversary_wishes

			result = send_birthday_and_anniversary_wishes(target_date)
			# Both birthday and anniversary must send separately
			self.assertEqual(result["birthday"]["sent"], 1)
			self.assertEqual(result["anniversary"]["sent"], 1)

			comms = frappe.get_all(
				"Communication",
				filters={"reference_name": self.test_emp_id},
				fields=["subject", "email_template", "recipients", "cc"],
			)
			self.assertEqual(len(comms), 2)
			templates_used = [c.email_template for c in comms]
			self.assertIn("Employee Birthday", templates_used)
			self.assertIn("Employee Work Anniversary", templates_used)

			bday_comm = next(c for c in comms if c.email_template == "Employee Birthday")
			anniv_comm = next(c for c in comms if c.email_template == "Employee Work Anniversary")

			# Birthday email includes company team in CC
			self.assertTrue(bool(bday_comm.cc))

			# Work anniversary email is sent ONLY to celebrating employee (no CC)
			self.assertEqual(anniv_comm.cc or "", "")
			self.assertIn(self.test_email, anniv_comm.recipients)
			self.assertNotIn("team@artemhealthtech.com", anniv_comm.recipients)
		finally:
			frappe.db.delete("Communication", {"reference_name": self.test_emp_id})
			frappe.db.delete("Email Queue", {"reference_name": self.test_emp_id})
