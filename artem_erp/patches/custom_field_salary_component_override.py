import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)


CUSTOM_FIELDS = {
	"Salary Component": [
		{
			"fieldname": "custom_allow_override",
			"label": "Allow Override",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "depends_on_payment_days",
			"description": "Allows this salary component to be manually overridden in the assigned Salary Structure.",
			"system_generated": 0,
		},
	],
	"Salary Detail": [
		{
			"fieldname": "custom_allow_override",
			"label": "Allow Override",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "deduct_full_tax_on_selected_payroll_date",
			"in_list_view": 1,
			"fetch_from": "salary_component.custom_allow_override",
			"allow_on_submit": 1,
			"description": "Allows this salary component to be manually overridden in the assigned Salary Structure..",
			"system_generated": 0,
		},
	],
	"Employee Benefit Detail": [
		{
			"fieldname": "custom_allow_override",
			"label": "Allow Override",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "amount",
			"in_list_view": 1,
			"fetch_from": "salary_component.custom_allow_override",
			"allow_on_submit": 1,
			"description": "Allows this salary component to be manually overridden in the assigned Salary Structure.",
			"system_generated": 0,
		},
	],
	"Salary Structure Assignment": [
		{
			"fieldname": "custom_is_override_salary_structure_component",
			"label": "Is Override Salary Structure Component",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "salary_structure",
			"read_only": 1,
			"allow_on_submit": 1,
			"description": "Indicates whether salary component override functionality is active for this assignment.",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_employees_salary_component_override",
			"label": "Employees Salary Component Override",
			"fieldtype": "Link",
			"options": "Employees Salary Component Override",
			"insert_after": "custom_is_override_salary_structure_component",
			"read_only": 1,
			"allow_on_submit": 1,
			"description": "Reference link to the submitted Employees Salary Component Override document.",
			"system_generated": 0,
		},
	],
	"Salary Slip": [
		{
			"fieldname": "custom_component_override_applied",
			"label": "Component Override Applied",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "salary_structure",
			"read_only": 1,
			"description": "Indicates whether overridden salary component amounts were applied to this salary slip.",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_salary_component_override",
			"label": "Applied Override Document",
			"fieldtype": "Link",
			"options": "Employees Salary Component Override",
			"insert_after": "custom_component_override_applied",
			"read_only": 1,
			"description": "References the Employees Salary Component Override document applied during calculation.",
			"system_generated": 0,
		},
	],
}
