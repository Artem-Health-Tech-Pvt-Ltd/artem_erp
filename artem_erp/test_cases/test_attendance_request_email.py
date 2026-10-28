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
	def test_is_attendance_request_notification_already_sent(self):
		test_name = "HR-ARQ-26-10-00024"
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
		# Fetch an employee with reporting manager
		emp = frappe.get_doc("Employee", "CON-002")
		dummy_doc = frappe._dict(
			{
				"name": "HR-ARQ-TEST",
				"employee": emp.name,
				"employee_name": emp.employee_name,
			}
		)

		# 1. Pending Approval -> Recipient is Reporting Manager
		mgr_email, mgr_name = get_request_recipient(dummy_doc, "Pending Approval")
		self.assertIsNotNone(mgr_email)
		self.assertIn("@", mgr_email)
		self.assertEqual(mgr_name, "Aarohi Patel")

		# 2. Approved -> Recipient is Employee
		emp_email, emp_name = get_request_recipient(dummy_doc, "Approved")
		self.assertIsNotNone(emp_email)
		self.assertIn("@", emp_email)
		self.assertEqual(emp_name, emp.employee_name)

	def test_build_template_context(self):
		dummy_doc = frappe._dict(
			{
				"name": "HR-ARQ-26-10-00024",
				"employee": "CON-002",
				"employee_name": "Hardik barot",
				"from_date": "2026-10-28",
				"to_date": "2026-10-28",
				"half_day": 0,
				"reason": "Work From Home",
				"explanation": "not able to travel",
			}
		)
		ctx = build_template_context(dummy_doc, "Pending Approval", "Aarohi Patel")

		self.assertEqual(ctx["recipient_name"], "Aarohi Patel")
		self.assertEqual(ctx["employee_name"], "Hardik barot")
		self.assertEqual(ctx["request_type"], "Work From Home")
		self.assertEqual(ctx["attendance_date"], format_date("2026-10-28"))
		self.assertEqual(ctx["half_day"], "No")
		self.assertEqual(ctx["reason"], "not able to travel")
		self.assertEqual(ctx["status"], "Pending Approval")
		self.assertEqual(ctx["approver_name"], "-")
		self.assertIn("HR-ARQ-26-10-00024", ctx["request_url"])
		self.assertIn("<a href=", ctx["request_url"])

	def test_send_attendance_request_notification_lifecycle(self):
		# Test with existing Attendance Request HR-ARQ-26-10-00024
		req_doc = frappe.get_doc("Attendance Request", "HR-ARQ-26-10-00024")

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

	def test_error_logging_when_config_or_data_missing(self):
		# ETPL2013 has no reporting manager
		emp_no_mgr = frappe.get_doc("Employee", "ETPL2013")
		dummy_req = frappe._dict(
			{
				"name": "HR-ARQ-TEST-NOMGR",
				"employee": emp_no_mgr.name,
				"employee_name": emp_no_mgr.employee_name,
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
		self.assertEqual(error_log.method, f"No Reporting Manager Found for Employee {emp_no_mgr.name}")
		if error_log:
			frappe.db.delete("Error Log", {"name": error_log.name})
