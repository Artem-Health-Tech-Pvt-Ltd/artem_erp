import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)


CUSTOM_FIELDS = {
	"User": [
		{
			"fieldname": "custom_device_login_authorization_section",
			"label": "Device Login Authorization",
			"fieldtype": "Section Break",
			"insert_after": "last_known_versions",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_enable_device_login_restriction",
			"label": "Enable Device Login Restriction",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "custom_device_login_authorization_section",
			"description": "Enables or disables device-based login restrictions for the user.",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_authorized_device_token",
			"label": "Authorized Device Token",
			"fieldtype": "Data",
			"insert_after": "custom_enable_device_login_restriction",
			"read_only": 1,
			"description": "Stores the UUID token of the currently authorized browser or device.",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_device_authorization_status",
			"label": "Device Authorization Status",
			"fieldtype": "Select",
			"options": "\nPending Onboarding\nAuthorized\nBlocked",
			"insert_after": "custom_authorized_device_token",
			"read_only": 1,
			"description": "Displays the user's current device authorization status.",
			"system_generated": 0,
		},
	],
}
