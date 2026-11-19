# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class ArtemSetting(Document):
	def validate(self):
		self.validate_attendance_lock_reminder_day()

	def validate_attendance_lock_reminder_day(self):
		if self.attendance_lock_reminder_day is not None and self.attendance_lock_reminder_day != "":
			day = cint(self.attendance_lock_reminder_day)
			if day < 1 or day > 31:
				frappe.throw(_("Attendance Lock Reminder Day must be between 1 and 31."))
