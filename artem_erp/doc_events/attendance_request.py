import frappe


def remove_penalty_from_attendance(doc, method=None):
	"""Disable the penalty checkbox for linked Attendance records."""

	if not doc.employee or not doc.from_date or not doc.to_date:
		return

	attendance_records = frappe.get_all(
		"Attendance",
		filters={
			"employee": doc.employee,
			"attendance_date": ["between", [doc.from_date, doc.to_date]],
			"docstatus": 1,
		},
		pluck="name",
	)

	for attendance_name in attendance_records:
		frappe.db.set_value(
			"Attendance",
			attendance_name,
			"custom_penalty",
			0,
			update_modified=False,
		)
