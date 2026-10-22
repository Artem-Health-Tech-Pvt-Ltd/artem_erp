import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate
from hrms.hr.doctype.leave_application.leave_application import (
	LeaveApplication,
	get_holidays,
	get_leave_balance_on,
	get_number_of_leave_days,
	is_lwp,
)
from hrms.hr.utils import get_holiday_dates_for_employee


class CustomLeaveApplication(LeaveApplication):
	def validate_balance_leaves(self):
		if self.custom_is_sandwich_leave:
			self.total_leave_days = flt(date_diff(self.to_date, self.from_date) + 1)
			if not is_lwp(self.leave_type):
				precision = cint(frappe.db.get_single_value("System Settings", "float_precision")) or 2
				leave_balance = get_leave_balance_on(
					self.employee,
					self.leave_type,
					self.from_date,
					self.to_date,
					consider_all_leaves_in_the_allocation_period=True,
					for_consumption=True,
				)
				if leave_balance:
					self.leave_balance = flt(leave_balance.get("leave_balance"), precision)
				else:
					self.leave_balance = 0.0

				if (
					self.status != "Rejected"
					and leave_balance
					and self.total_leave_days > flt(leave_balance.get("leave_balance_for_consumption", 0), precision)
				):
					self.show_insufficient_balance_message(
						flt(leave_balance.get("leave_balance_for_consumption", 0), precision)
					)
			else:
				self.leave_balance = 0.0
			return

		precision = cint(frappe.db.get_single_value("System Settings", "float_precision")) or 2

		if self.from_date and self.to_date:
			self.total_leave_days = get_number_of_leave_days(
				self.employee,
				self.leave_type,
				self.from_date,
				self.to_date,
				self.half_day,
				self.half_day_date,
			)

			if self.custom_apply_sandwich_exemption and self.leave_type:
				if frappe.db.get_value("Leave Type", self.leave_type, "include_holiday"):
					holidays = flt(get_holidays(self.employee, self.from_date, self.to_date))
					if holidays > 0:
						self.total_leave_days = max(0.0, flt(self.total_leave_days) - holidays)

			if self.total_leave_days <= 0:
				frappe.throw(
					_(
						"The day(s) on which you are applying for leave are holidays. You need not apply for leave."
					)
				)

			if not is_lwp(self.leave_type):
				leave_balance = get_leave_balance_on(
					self.employee,
					self.leave_type,
					self.from_date,
					self.to_date,
					consider_all_leaves_in_the_allocation_period=True,
					for_consumption=True,
				)
				leave_balance_for_consumption = flt(
					leave_balance.get("leave_balance_for_consumption"), precision
				)
				if self.status != "Rejected" and (
					leave_balance_for_consumption < self.total_leave_days or not leave_balance_for_consumption
				):
					self.show_insufficient_balance_message(leave_balance_for_consumption)

	def update_attendance(self):
		if self.status != "Approved":
			return

		include_holiday = cint(frappe.db.get_value("Leave Type", self.leave_type, "include_holiday"))
		if include_holiday and self.custom_apply_sandwich_exemption:
			holiday_dates = get_holiday_dates_for_employee(self.employee, self.from_date, self.to_date)
			curr = getdate(self.from_date)
			end = getdate(self.to_date)
			while curr <= end:
				date = curr.strftime("%Y-%m-%d")
				attendance_name = frappe.db.exists(
					"Attendance",
					dict(
						employee=self.employee,
						attendance_date=date,
						docstatus=("!=", 2),
					),
				)
				if date in holiday_dates:
					if attendance_name:
						attendance = frappe.get_doc("Attendance", attendance_name)
						attendance.flags.ignore_permissions = True
						if attendance.docstatus == 1:
							attendance.cancel()
						frappe.delete_doc("Attendance", attendance_name, force=1)
					curr = add_days(curr, 1)
					continue

				self.create_or_update_attendance(attendance_name, date)
				curr = add_days(curr, 1)
			return

		super().update_attendance()
