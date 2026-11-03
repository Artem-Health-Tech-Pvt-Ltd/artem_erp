import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)


CUSTOM_FIELDS = {
	"Company": [
		{
			"fieldname": "custom_enable_single_day_attendance_regularization",
			"label": "Enable Single-Day Attendance Regularization",
			"fieldtype": "Check",
			"insert_after": "default_holiday_list",
			"default": "0",
			"description": "Enables single-day Attendance Requests for the company.",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_max_attendance_request_days",
			"label": "Maximum Allowed Attendance Request Days",
			"fieldtype": "Int",
			"insert_after": "custom_enable_single_day_attendance_regularization",
			"default": "0",
			"description": "Defines the maximum number of calendar days an employee can select in a single Attendance Request.",
			"depends_on": "eval:!doc.custom_enable_single_day_attendance_regularization",
			"system_generated": 0,
		},
	],
}
