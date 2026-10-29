# Copyright (c) 2026, Artem Healthtech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from artem_erp.auto_email.monthly_attendance_lock_email import (
	create_attendance_lock_notification_logs,
	get_company_team_recipients,
	get_hr_manager_cc_recipients,
	is_attendance_lock_reminder_already_sent,
	send_monthly_attendance_lock_reminder,
)
from artem_erp.auto_email.utils import get_artem_settings


class TestMonthlyAttendanceLockEmail(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.cleanup_records = []
		frappe.db.set_single_value("Artem Setting", "attendance_lock_reminder_day", 24)
		if frappe.db.exists("Email Account", "Artem HealthTech"):
			frappe.db.set_value("Email Account", "Artem HealthTech", "default_outgoing", 1)
			frappe.db.set_value("Email Account", "Artem HealthTech", "enable_outgoing", 1)
			frappe.db.commit() # nosemgrep

	def tearDown(self):
		for doctype, name in self.cleanup_records:
			try:
				if frappe.db.exists(doctype, name):
					frappe.db.delete(doctype, {"name": name})
			except Exception:
				pass
		frappe.db.commit() # nosemgrep
		super().tearDown()

	def test_get_company_team_recipients(self):
		settings = get_artem_settings()
		self.assertIsNotNone(settings)

		recipients = get_company_team_recipients(settings)
		self.assertIsInstance(recipients, list)
		self.assertGreater(len(recipients), 0)
		for email in recipients:
			self.assertIn("@", email)

	def test_get_hr_manager_cc_recipients(self):
		cc_recipients, hr_users = get_hr_manager_cc_recipients()
		self.assertIsInstance(cc_recipients, list)
		self.assertIsInstance(hr_users, list)
		self.assertGreater(len(cc_recipients), 0)
		self.assertGreater(len(hr_users), 0)

		# Ensure exclusion works
		excluded_email = cc_recipients[0]
		filtered_cc, _ = get_hr_manager_cc_recipients(exclude_emails=[excluded_email])
		self.assertNotIn(excluded_email, filtered_cc)

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
			frappe.db.commit() # nosemgrep

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
			frappe.db.commit() # nosemgrep

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
		for l in logs[:res1.get("notification_logs_count", 0)]:
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
		test_users = ["anjupatoliya314@gmail.com"]
		logs = create_attendance_lock_notification_logs(
			subject="Test Lock Reminder",
			message="<p>Test body</p>",
			hr_users=test_users,
		)
		self.assertEqual(len(logs), 1)
		self.cleanup_records.append(("Notification Log", logs[0]))

		doc = frappe.get_doc("Notification Log", logs[0])
		self.assertEqual(doc.for_user, "anjupatoliya314@gmail.com")
		self.assertEqual(doc.type, "Alert")
		self.assertEqual(doc.subject, "Test Lock Reminder")

	def test_missing_template_configuration_logs_error(self):
		orig_val = frappe.db.get_single_value("Artem Setting", "attendance_lock_notification_template")
		try:
			frappe.db.set_single_value("Artem Setting", "attendance_lock_notification_template", "")
			frappe.db.commit() # nosemgrep

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
			frappe.db.commit() # nosemgrep

	def test_nonexistent_email_template_logs_error(self):
		orig_val = frappe.db.get_single_value("Artem Setting", "attendance_lock_notification_template")
		try:
			frappe.db.set_single_value(
				"Artem Setting",
				"attendance_lock_notification_template",
				"Nonexistent Fake Template Name 123",
			)
			frappe.db.commit() # nosemgrep

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
			frappe.db.commit() # nosemgrep

	def test_missing_reminder_day_configuration_logs_error(self):
		orig_val = frappe.db.get_single_value("Artem Setting", "attendance_lock_reminder_day")
		try:
			frappe.db.set_single_value("Artem Setting", "attendance_lock_reminder_day", "")
			frappe.db.commit() # nosemgrep

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
			frappe.db.commit() # nosemgrep
