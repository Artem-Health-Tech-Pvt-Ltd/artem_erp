# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import format_date

from artem_erp.auto_email.attendance_request_email import (
	build_template_context,
	get_request_recipient,
	is_attendance_request_notification_already_sent,
	send_attendance_request_notification,
)


class TestAttendanceRequestEmail(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.cleanup_records = []

		# 1. Ensure outgoing Email Account is enabled
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

		# 2. Ensure Email Template exists
		template_name = "Attendance Request Notification"
		if not frappe.db.exists("Email Template", template_name):
			tpl = frappe.get_doc(
				{
					"doctype": "Email Template",
					"name": template_name,
					"subject": "Attendance Request – {{ employee_name }} – {{ status }}",  # noqa: RUF001
					"response": "<p>Dear {{ recipient_name }}, Attendance request for {{ employee_name }}: {{ status }}</p>",
				}
			)
			tpl.insert(ignore_permissions=True)
			cls.cleanup_records.append(("Email Template", template_name))

		# 3. Configure Artem Setting
		frappe.db.set_single_value(
			"Artem Setting",
			"attendance_request_notification_email_template",
			template_name,
		)

		company = (
			frappe.defaults.get_user_default("company")
			or frappe.db.get_value("Company", {}, "name")
			or "Pearl Group"
		)
		holiday_list = frappe.db.get_value("Holiday List", {}, "name")

		# 4. Create Manager Employee fixture
		cls.mgr_email = "test.mgr.ar@artemhealthtech.com"
		mgr = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "_Test",
				"last_name": "Manager AR",
				"employee_name": "_Test Manager AR",
				"gender": "Female",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"status": "Active",
				"company": company,
				"holiday_list": holiday_list,
				"prefered_email": cls.mgr_email,
				"company_email": cls.mgr_email,
				"person_to_be_contacted": "Emergency Contact",
				"emergency_phone_number": "9999999999",
				"relation": "Other",
				"salary_mode": "Bank",
			}
		)
		mgr.insert(ignore_permissions=True, ignore_mandatory=True)
		cls.mgr = mgr
		cls.cleanup_records.append(("Employee", mgr.name))

		# 5. Create Subordinate Employee fixture
		cls.emp_email = "test.emp.ar@artemhealthtech.com"
		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "_Test",
				"last_name": "Employee AR",
				"employee_name": "_Test Employee AR",
				"gender": "Male",
				"date_of_birth": "1995-01-01",
				"date_of_joining": "2022-01-01",
				"status": "Active",
				"company": company,
				"holiday_list": holiday_list,
				"reports_to": mgr.name,
				"prefered_email": cls.emp_email,
				"company_email": cls.emp_email,
				"person_to_be_contacted": "Emergency Contact",
				"emergency_phone_number": "9999999999",
				"relation": "Other",
				"salary_mode": "Bank",
			}
		)
		emp.insert(ignore_permissions=True, ignore_mandatory=True)
		cls.emp = emp
		cls.cleanup_records.append(("Employee", emp.name))

		# 6. Create Employee with No Manager fixture (for error logging test)
		emp_no_mgr = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "_Test",
				"last_name": "NoManager AR",
				"employee_name": "_Test NoManager AR",
				"gender": "Other",
				"date_of_birth": "1996-01-01",
				"date_of_joining": "2023-01-01",
				"status": "Active",
				"company": company,
				"holiday_list": holiday_list,
				"prefered_email": "test.nomgr@artemhealthtech.com",
				"company_email": "test.nomgr@artemhealthtech.com",
				"person_to_be_contacted": "Emergency Contact",
				"emergency_phone_number": "9999999999",
				"relation": "Other",
				"salary_mode": "Bank",
			}
		)
		emp_no_mgr.insert(ignore_permissions=True, ignore_mandatory=True)
		cls.emp_no_mgr = emp_no_mgr
		cls.cleanup_records.append(("Employee", emp_no_mgr.name))

		# 7. Create Attendance Request fixture
		req_doc = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": emp.name,
				"company": company,
				"from_date": "2026-10-28",
				"to_date": "2026-10-28",
				"include_holidays": 1,
				"reason": "Work From Home",
				"explanation": "Testing attendance request notification lifecycle",
			}
		)
		req_doc.insert(ignore_permissions=True, ignore_mandatory=True)
		cls.req_doc = req_doc
		cls.cleanup_records.append(("Attendance Request", req_doc.name))

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

	def setUp(self):
		super().setUp()
		frappe.db.delete(
			"Communication",
			{
				"reference_doctype": "Attendance Request",
				"reference_name": self.req_doc.name,
			},
		)
		frappe.db.delete(
			"Email Queue",
			{
				"reference_doctype": "Attendance Request",
				"reference_name": self.req_doc.name,
			},
		)

	def test_is_attendance_request_notification_already_sent(self):
		test_name = self.req_doc.name
		# Create a dummy Communication
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Automated Message",
				"communication_medium": "Email",
				"sent_or_received": "Sent",
				"reference_doctype": "Attendance Request",
				"reference_name": test_name,
				"subject": "Attendance Request – Test Employee – Pending Approval",  # noqa: RUF001
				"content": "Test content",
				"recipients": "test@example.com",
			}
		)
		comm.insert(ignore_permissions=True, ignore_links=True)

		try:
			self.assertTrue(is_attendance_request_notification_already_sent(test_name, "Pending Approval"))
			self.assertFalse(is_attendance_request_notification_already_sent(test_name, "Approved"))
			self.assertFalse(
				is_attendance_request_notification_already_sent("NON-EXISTENT", "Pending Approval")
			)
		finally:
			frappe.db.delete("Communication", {"name": comm.name})

	def test_get_request_recipient(self):
		dummy_doc = frappe._dict(
			{
				"name": self.req_doc.name,
				"employee": self.emp.name,
				"employee_name": self.emp.employee_name,
			}
		)

		# 1. Pending Approval -> Recipient is Reporting Manager
		mgr_email, mgr_name = get_request_recipient(dummy_doc, "Pending Approval")
		self.assertEqual(mgr_email, self.mgr_email)
		self.assertEqual(mgr_name, self.mgr.employee_name)

		# 2. Approved -> Recipient is Employee
		emp_email, emp_name = get_request_recipient(dummy_doc, "Approved")
		self.assertEqual(emp_email, self.emp_email)
		self.assertEqual(emp_name, self.emp.employee_name)

	def test_build_template_context(self):
		ctx = build_template_context(self.req_doc, "Pending Approval", self.mgr.employee_name)

		self.assertEqual(ctx["recipient_name"], self.mgr.employee_name)
		self.assertEqual(ctx["employee_name"], self.emp.employee_name)
		self.assertEqual(ctx["request_type"], "Work From Home")
		self.assertEqual(ctx["attendance_date"], format_date("2026-10-28"))
		self.assertEqual(ctx["half_day"], "No")
		self.assertEqual(ctx["reason"], "Testing attendance request notification lifecycle")
		self.assertEqual(ctx["status"], "Pending Approval")
		self.assertEqual(ctx["approver_name"], "-")
		self.assertIn(self.req_doc.name, ctx["request_url"])
		self.assertIn("<a href=", ctx["request_url"])

	def test_send_attendance_request_notification_lifecycle(self):
		req_doc = self.req_doc

		# Clear any existing communications for test isolation
		frappe.db.delete(
			"Communication",
			{
				"reference_doctype": "Attendance Request",
				"reference_name": req_doc.name,
			},
		)

		try:
			# 1. Send Pending Approval (Created)
			sent = send_attendance_request_notification(req_doc, "Pending Approval")
			self.assertTrue(sent)

			# 2. Duplicate check - second call should return False
			duplicate_sent = send_attendance_request_notification(req_doc, "Pending Approval")
			self.assertFalse(duplicate_sent)

			# 3. Send Approved
			sent_approved = send_attendance_request_notification(req_doc, "Approved")
			self.assertTrue(sent_approved)

			# 4. Duplicate check on Approved
			self.assertFalse(send_attendance_request_notification(req_doc, "Approved"))

			# 5. Send Rejected
			sent_rejected = send_attendance_request_notification(req_doc, "Rejected")
			self.assertTrue(sent_rejected)

			# 6. Duplicate check on Rejected
			self.assertFalse(send_attendance_request_notification(req_doc, "Rejected"))
		finally:
			frappe.db.delete(
				"Communication",
				{
					"reference_doctype": "Attendance Request",
					"reference_name": req_doc.name,
				},
			)
			frappe.db.delete(
				"Email Queue",
				{
					"reference_doctype": "Attendance Request",
					"reference_name": req_doc.name,
				},
			)

	def test_error_logging_when_config_or_data_missing(self):
		dummy_req = frappe._dict(
			{
				"name": "HR-ARQ-TEST-NOMGR",
				"employee": self.emp_no_mgr.name,
				"employee_name": self.emp_no_mgr.employee_name,
				"from_date": "2026-10-28",
				"to_date": "2026-10-28",
				"reason": "Work From Home",
			}
		)

		sent = send_attendance_request_notification(dummy_req, "Pending Approval")
		self.assertFalse(sent)

		# Verify Error Log was generated with specific clear title
		error_log = frappe.db.get_value(
			"Error Log",
			{"reference_name": dummy_req.name},
			["name", "method"],
			as_dict=True,
		)
		self.assertIsNotNone(error_log)
		self.assertEqual(error_log.method, f"No Reporting Manager Found for Employee {self.emp_no_mgr.name}")
		if error_log:
			frappe.db.delete("Error Log", {"name": error_log.name})
