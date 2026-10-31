# Copyright (c) 2026, Artem Healthtech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from artem_erp.auto_email.monthly_attendance_lock_email import (
	create_attendance_lock_notification_logs,
	get_company_team_recipients,
	is_attendance_lock_reminder_already_sent,
	send_monthly_attendance_lock_reminder,
)
from artem_erp.auto_email.utils import get_artem_settings


class TestMonthlyAttendanceLockEmail(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.class_cleanup_records = []
		cls.test_email_group = "_Test Monthly Lock Email Group"
		cls.test_user_email = "test.lock.user@artemhealthtech.com"
		cls.test_member_email = "test.lock.member@artemhealthtech.com"
		cls.template_name = "Attendance Regularization & Monthly Attendance Lock Reminder"

		# Outgoing email account
		if frappe.db.exists("Email Account", "Artem HealthTech"):
			frappe.db.set_value("Email Account", "Artem HealthTech", "default_outgoing", 1)
			frappe.db.set_value("Email Account", "Artem HealthTech", "enable_outgoing", 1)
		elif frappe.db.exists("Email Account", "Jobs"):
			frappe.db.set_value("Email Account", "Jobs", "default_outgoing", 1)
			frappe.db.set_value("Email Account", "Jobs", "enable_outgoing", 1)
		elif not frappe.db.exists("Email Account", {"default_outgoing": 1}):
			accounts = frappe.get_all("Email Account", limit=1)
			if accounts:
				frappe.db.set_value("Email Account", accounts[0].name, "default_outgoing", 1)
				frappe.db.set_value("Email Account", accounts[0].name, "enable_outgoing", 1)

		# Ensure reminder Email Template fixture exists
		if not frappe.db.exists("Email Template", cls.template_name):
			tpl = frappe.get_doc(
				{
					"doctype": "Email Template",
					"name": cls.template_name,
					"subject": "Monthly Attendance Lock Reminder - {{ month_name }} {{ year }}",
					"response": "<p>Dear Team, please regularize your attendance for {{ month_name }} {{ year }}.</p>",
				}
			).insert(ignore_permissions=True)
			cls.class_cleanup_records.append(("Email Template", tpl.name))

		# Ensure test User fixture exists for notification logs
		if not frappe.db.exists("User", cls.test_user_email):
			usr = frappe.get_doc(
				{
					"doctype": "User",
					"email": cls.test_user_email,
					"first_name": "Test",
					"last_name": "Lock User",
					"enabled": 1,
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
			cls.class_cleanup_records.append(("User", usr.name))

		# Ensure test Email Group fixture exists
		if not frappe.db.exists("Email Group", cls.test_email_group):
			eg = frappe.get_doc(
				{
					"doctype": "Email Group",
					"title": cls.test_email_group,
				}
			).insert(ignore_permissions=True)
			cls.class_cleanup_records.append(("Email Group", eg.name))

		# Ensure test Email Group Member fixtures exist
		for m_email in [cls.test_member_email, cls.test_user_email]:
			if not frappe.db.exists(
				"Email Group Member", {"email_group": cls.test_email_group, "email": m_email}
			):
				egm = frappe.get_doc(
					{
						"doctype": "Email Group Member",
						"email_group": cls.test_email_group,
						"email": m_email,
						"unsubscribed": 0,
					}
				).insert(ignore_permissions=True)
				cls.class_cleanup_records.append(("Email Group Member", egm.name))

		# Configure Artem Setting
		cls.orig_reminder_day = frappe.db.get_single_value("Artem Setting", "attendance_lock_reminder_day")
		cls.orig_template = frappe.db.get_single_value(
			"Artem Setting", "attendance_lock_notification_template"
		)

		setting = frappe.get_single("Artem Setting")
		setting.attendance_lock_reminder_day = 24
		setting.attendance_lock_notification_template = cls.template_name
		existing_groups = [
			row.email_group
			for row in setting.get("company_team_emails", [])
			if getattr(row, "email_group", None)
		]
		if cls.test_email_group not in existing_groups:
			setting.append("company_team_emails", {"email_group": cls.test_email_group})
			cls.added_group_to_setting = True
		else:
			cls.added_group_to_setting = False
		setting.save(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep

	@classmethod
	def tearDownClass(cls):
		# Revert Artem Setting
		try:
			setting = frappe.get_single("Artem Setting")
			setting.attendance_lock_reminder_day = cls.orig_reminder_day or 24
			setting.attendance_lock_notification_template = cls.orig_template or ""
			if getattr(cls, "added_group_to_setting", False):
				setting.company_team_emails = [
					row
					for row in setting.get("company_team_emails", [])
					if getattr(row, "email_group", None) != cls.test_email_group
				]
			setting.save(ignore_permissions=True)
		except Exception:
			pass

		# Clean up fixtures in reverse order
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
		frappe.db.set_single_value("Artem Setting", "attendance_lock_reminder_day", 24)
		frappe.db.set_single_value(
			"Artem Setting", "attendance_lock_notification_template", self.template_name
		)

		# Clean up any test communications / notification logs for test months
		for date_range in [
			["2026-05-01", "2026-05-31"],
			["2026-06-01", "2026-06-30"],
			["2026-10-01", "2026-10-31"],
		]:
			comms = frappe.get_all(
				"Communication",
				filters={
					"reference_doctype": "Email Template",
					"reference_name": self.template_name,
					"communication_date": ["between", date_range],
				},
				pluck="name",
			)
			for c in comms:
				frappe.db.delete("Communication", {"name": c})

		frappe.db.commit()  # nosemgrep

	def tearDown(self):
		for doctype, name in self.cleanup_records:
			try:
				if frappe.db.exists(doctype, name):
					frappe.db.delete(doctype, {"name": name})
			except Exception:
				pass
		frappe.db.commit()  # nosemgrep
		super().tearDown()

	def test_get_company_team_recipients(self):
		settings = get_artem_settings()
		self.assertIsNotNone(settings)

		recipients = get_company_team_recipients(settings)
		self.assertIsInstance(recipients, list)
		self.assertGreater(len(recipients), 0)
		self.assertIn(self.test_member_email, [r.lower() for r in recipients])
		for email in recipients:
			self.assertIn("@", email)

	def test_skip_when_not_configured_day(self):
		# Default reminder day is 24. Run for 23rd of month without force -> should skip
		res = send_monthly_attendance_lock_reminder(target_date="2026-10-23", force=False)
		self.assertEqual(res.get("status"), "skipped")
		self.assertIn("not the configured reminder day", res.get("message"))

	def test_dynamic_reminder_day_configuration(self):
		# Test setting a custom reminder day (e.g. 29)
		orig_day = frappe.db.get_single_value("Artem Setting", "attendance_lock_reminder_day")
		try:
			frappe.db.set_single_value("Artem Setting", "attendance_lock_reminder_day", 29)
			frappe.db.commit()  # nosemgrep

			# Running on 24th should now skip
			res_24 = send_monthly_attendance_lock_reminder(target_date="2026-10-24", force=False)
			self.assertEqual(res_24.get("status"), "skipped")
			self.assertIn("not the configured reminder day (29)", res_24.get("message"))

			# Running on 29th should match the configured day
			res_29 = send_monthly_attendance_lock_reminder(target_date="2026-05-29", force=False)
			self.assertEqual(res_29.get("status"), "success")
			if res_29.get("communication"):
				self.cleanup_records.append(("Communication", res_29.get("communication")))
		finally:
			frappe.db.set_single_value("Artem Setting", "attendance_lock_reminder_day", orig_day)
			frappe.db.commit()  # nosemgrep

	def test_validate_attendance_lock_reminder_day(self):
		# Invalid day (0 or 32) should raise ValidationError
		doc = frappe.get_single("Artem Setting")
		doc.attendance_lock_reminder_day = 32
		self.assertRaises(frappe.ValidationError, doc.save)

		doc.attendance_lock_reminder_day = 0
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_send_monthly_attendance_lock_reminder_success_and_duplicate(self):
		test_target_date = "2026-06-24"
		settings = get_artem_settings()
		template_name = getattr(settings, "attendance_lock_notification_template", None)
		self.assertTrue(template_name)

		# Clean up any preexisting communication/notification log for test month
		existing_comm = frappe.get_all(
			"Communication",
			filters={
				"reference_doctype": "Email Template",
				"reference_name": template_name,
				"communication_date": ["between", ["2026-06-01", "2026-06-30"]],
			},
			pluck="name",
		)
		for c in existing_comm:
			frappe.db.delete("Communication", {"name": c})

		# 1. Send reminder for test date (24th)
		res1 = send_monthly_attendance_lock_reminder(target_date=test_target_date, force=False)
		self.assertEqual(res1.get("status"), "success")
		self.assertGreater(res1.get("recipients_count", 0), 0)
		self.assertGreater(res1.get("notification_logs_count", 0), 0)

		comm_name = res1.get("communication")
		if comm_name:
			self.cleanup_records.append(("Communication", comm_name))

		# Verify Communication record
		comm_doc = frappe.get_doc("Communication", comm_name)
		self.assertEqual(comm_doc.reference_doctype, "Email Template")
		self.assertEqual(comm_doc.reference_name, template_name)
		self.assertIn("Reminder", comm_doc.subject)
		self.assertFalse(comm_doc.cc)

		# Verify Notification Log was created
		logs = frappe.get_all(
			"Notification Log",
			filters={
				"document_type": "Email Template",
				"document_name": template_name,
				"type": "Alert",
			},
			fields=["name", "for_user", "subject"],
			order_by="creation desc",
			limit=10,
		)
		self.assertGreater(len(logs), 0)
		for l in logs[: res1.get("notification_logs_count", 0)]:
			self.cleanup_records.append(("Notification Log", l.name))

		# 2. Second invocation on same month without force should skip due to duplicate check
		res2 = send_monthly_attendance_lock_reminder(target_date=test_target_date, force=False)
		self.assertEqual(res2.get("status"), "skipped")
		self.assertIn("already sent", res2.get("message"))

		# 3. Invocation with force=True should bypass duplicate check
		res3 = send_monthly_attendance_lock_reminder(target_date=test_target_date, force=True)
		self.assertEqual(res3.get("status"), "success")
		if res3.get("communication"):
			self.cleanup_records.append(("Communication", res3.get("communication")))

	def test_create_attendance_lock_notification_logs(self):
		test_users = [self.test_user_email]
		logs = create_attendance_lock_notification_logs(
			subject="Test Lock Reminder",
			message="<p>Test body</p>",
			recipients=test_users,
		)
		self.assertEqual(len(logs), 1)
		self.cleanup_records.append(("Notification Log", logs[0]))

		doc = frappe.get_doc("Notification Log", logs[0])
		self.assertEqual(doc.for_user, self.test_user_email)
		self.assertEqual(doc.type, "Alert")
		self.assertEqual(doc.subject, "Test Lock Reminder")

	def test_missing_template_configuration_logs_error(self):
		orig_val = frappe.db.get_single_value("Artem Setting", "attendance_lock_notification_template")
		try:
			frappe.db.set_single_value("Artem Setting", "attendance_lock_notification_template", "")
			frappe.db.commit()  # nosemgrep

			res = send_monthly_attendance_lock_reminder(target_date="2026-10-24", force=True)
			self.assertEqual(res.get("status"), "error")

			# Verify Error Log exists
			err_log = frappe.get_all(
				"Error Log",
				filters={"method": ["like", "%Template Configuration Missing%"]},
				limit=1,
			)
			self.assertGreater(len(err_log), 0)
			self.cleanup_records.append(("Error Log", err_log[0].name))
		finally:
			frappe.db.set_single_value("Artem Setting", "attendance_lock_notification_template", orig_val)
			frappe.db.commit()  # nosemgrep

	def test_nonexistent_email_template_logs_error(self):
		orig_val = frappe.db.get_single_value("Artem Setting", "attendance_lock_notification_template")
		try:
			frappe.db.set_single_value(
				"Artem Setting",
				"attendance_lock_notification_template",
				"Nonexistent Fake Template Name 123",
			)
			frappe.db.commit()  # nosemgrep

			res = send_monthly_attendance_lock_reminder(target_date="2026-10-24", force=True)
			self.assertEqual(res.get("status"), "error")

			err_log = frappe.get_all(
				"Error Log",
				filters={"method": ["like", "%Email Template Not Found%"]},
				limit=1,
			)
			self.assertGreater(len(err_log), 0)
			self.cleanup_records.append(("Error Log", err_log[0].name))
		finally:
			frappe.db.set_single_value("Artem Setting", "attendance_lock_notification_template", orig_val)
			frappe.db.commit()  # nosemgrep

	def test_missing_reminder_day_configuration_logs_error(self):
		orig_val = frappe.db.get_single_value("Artem Setting", "attendance_lock_reminder_day")
		try:
			frappe.db.set_single_value("Artem Setting", "attendance_lock_reminder_day", "")
			frappe.db.commit()  # nosemgrep

			res = send_monthly_attendance_lock_reminder(target_date="2026-10-24", force=True)
			self.assertEqual(res.get("status"), "error")
			self.assertIn("not configured", res.get("message"))

			err_log = frappe.get_all(
				"Error Log",
				filters={"method": ["like", "%Reminder Day Not Configured%"]},
				limit=1,
			)
			self.assertGreater(len(err_log), 0)
			self.cleanup_records.append(("Error Log", err_log[0].name))
		finally:
			frappe.db.set_single_value("Artem Setting", "attendance_lock_reminder_day", orig_val)
			frappe.db.commit()  # nosemgrep
