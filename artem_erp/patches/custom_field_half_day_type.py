import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)


CUSTOM_FIELDS = {
	"Attendance Request": [
		{
			"fieldname": "custom_half_day_type",
			"label": "Half Day Type",
			"fieldtype": "Select",
			"insert_after": "half_day_date",
			"options": "First Half\nSecond Half",
			"depends_on": "eval:doc.half_day",
			"mandatory_depends_on": "eval:doc.half_day",
			"system_generated": 0,
		}
	],
	"Leave Application": [
		{
			"fieldname": "custom_half_day_type",
			"label": "Half Day Type",
			"fieldtype": "Select",
			"insert_after": "total_leave_days",
			"options": "First Half\nSecond Half",
			"depends_on": "eval:doc.half_day",
			"mandatory_depends_on": "eval:doc.half_day",
			"system_generated": 0,
		}
	],
}
