import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)


CUSTOM_FIELDS = {
	"Attendance": [
		{
			"fieldname": "custom_penalty",
			"label": "Penalty",
			"fieldtype": "Check",
			"insert_after": "early_exit",
			"read_only": 1,
			"allow_on_submit": 1,
			"system_generated": 0,
		},
	]
}
