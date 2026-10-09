# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from hrms.hr.doctype.attendance_request.attendance_request import AttendanceRequest


class CustomAttendanceRequest(AttendanceRequest):
	def has_leave_record(self, attendance_date: str) -> str | None:
		"""
		Check if employee has an approved Leave Application on attendance_date.
		Excludes Partial Day Leave because Partial Day is a partial working-day allowance,
		not a full-day absence. If Partial Day attendance was marked Half Day / Absent
		due to unfulfilled hours, employee is allowed to apply for Attendance Regularization.
		"""
		filters = {
			"employee": self.employee,
			"docstatus": 1,
			"from_date": ("<=", attendance_date),
			"to_date": (">=", attendance_date),
			"status": "Approved",
			"custom_is_partial_day_leave": 0,
		}
		if self.half_day_date == attendance_date:
			filters["half_day"] = 0

		return frappe.db.exists("Leave Application", filters)
