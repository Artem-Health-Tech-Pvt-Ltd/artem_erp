import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)


CUSTOM_FIELDS = {
	"Leave Application": [
		{
			"fieldname": "custom_sandwich_section",
			"fieldtype": "Section Break",
			"label": "Sandwich Leave Details",
			"insert_after": "department",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_system_generated",
			"fieldtype": "Check",
			"label": "System Generated",
			"insert_after": "custom_sandwich_section",
			"read_only": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_is_sandwich_leave",
			"fieldtype": "Check",
			"label": "Is Sandwich Leave",
			"insert_after": "custom_system_generated",
			"read_only": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_parent_leave_application",
			"label": "Parent Leave Application",
			"fieldtype": "Link",
			"options": "Leave Application",
			"insert_after": "custom_is_sandwich_leave",
			"read_only": 1,
			"depends_on": "eval:doc.custom_is_sandwich_leave == 1",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_prior_leave_application",
			"label": "Prior Leave Application",
			"fieldtype": "Link",
			"options": "Leave Application",
			"insert_after": "custom_parent_leave_application",
			"read_only": 1,
			"depends_on": "eval:doc.custom_is_sandwich_leave == 1",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_sandwich_col_break",
			"fieldtype": "Column Break",
			"insert_after": "custom_prior_leave_application",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_sandwich_detected",
			"fieldtype": "Check",
			"label": "Sandwich Leave Detected",
			"insert_after": "custom_sandwich_col_break",
			"read_only": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_sandwich_rule_confirmed",
			"fieldtype": "Check",
			"label": "Sandwich Leave Confirmed",
			"insert_after": "custom_sandwich_detected",
			"read_only": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_apply_sandwich_exemption",
			"fieldtype": "Check",
			"label": "Sandwich Leave Exemption Applied",
			"insert_after": "custom_sandwich_rule_confirmed",
			"read_only": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_sandwich_details",
			"fieldtype": "Small Text",
			"label": "Sandwich Details",
			"insert_after": "custom_apply_sandwich_exemption",
			"read_only": 1,
			"hidden": 1,
			"system_generated": 0,
		},
	]
}
