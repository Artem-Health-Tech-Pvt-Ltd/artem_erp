import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)
	create_default_salary_withholding_component()


def create_default_salary_withholding_component():
	component_name = "Salary Withholding"
	if not frappe.db.exists("Salary Component", component_name):
		doc = frappe.new_doc("Salary Component")
		doc.salary_component = component_name
		doc.salary_component_abbr = "SWH"
		doc.type = "Deduction"
		doc.description = "Withheld salary retention for employee notice period / separation."
		doc.is_tax_applicable = 0
		doc.do_not_include_in_total = 0
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.save()


CUSTOM_FIELDS = {
	"Salary Withholding": [
		{
			"fieldname": "custom_withholding_configuration_section",
			"fieldtype": "Section Break",
			"label": "Withholding Configuration",
			"insert_after": "to_date",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_withholding_mode",
			"label": "Withholding Mode",
			"fieldtype": "Select",
			"options": "Full (100%)\nPercentage",
			"default": "Full (100%)",
			"insert_after": "custom_withholding_configuration_section",
			"in_standard_filter": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_withholding_percentage",
			"label": "Withholding Percentage",
			"fieldtype": "Percent",
			"insert_after": "custom_withholding_mode",
			"depends_on": "eval:doc.custom_withholding_mode=='Percentage'",
			"mandatory_depends_on": "eval:doc.custom_withholding_mode=='Percentage'",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_calculation_base",
			"label": "Calculation Base",
			"fieldtype": "Select",
			"options": "Gross Pay\nNet Pay",
			"default": "Gross Pay",
			"insert_after": "custom_withholding_percentage",
			"depends_on": "eval:doc.custom_withholding_mode=='Percentage'",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_withholding_col_break",
			"fieldtype": "Column Break",
			"insert_after": "custom_calculation_base",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_withholding_component",
			"label": "Withholding Salary Component",
			"fieldtype": "Link",
			"options": "Salary Component",
			"insert_after": "custom_withholding_col_break",
			"depends_on": "eval:doc.custom_withholding_mode=='Percentage'",
			"description": "Salary Component used for the hold salary deduction (default: Salary Withholding)",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_holdback_account",
			"label": "Holdback Liability Account",
			"fieldtype": "Link",
			"options": "Account",
			"insert_after": "custom_withholding_component",
			"depends_on": "eval:doc.custom_withholding_mode=='Percentage'",
			"description": "Liability ledger for withheld amounts (e.g., Salary Withholding Payable)",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_total_accumulated_amount",
			"label": "Total Accumulated Withheld Amount",
			"fieldtype": "Currency",
			"insert_after": "custom_holdback_account",
			"read_only": 1,
			"system_generated": 0,
		},
	],
	"Salary Withholding Cycle": [
		{
			"fieldname": "custom_held_amount",
			"label": "Held Amount",
			"fieldtype": "Currency",
			"insert_after": "is_salary_released",
			"read_only": 1,
			"in_list_view": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_disbursed_amount",
			"label": "Disbursed Amount",
			"fieldtype": "Currency",
			"insert_after": "custom_held_amount",
			"read_only": 1,
			"in_list_view": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_salary_slip",
			"label": "Salary Slip",
			"fieldtype": "Link",
			"options": "Salary Slip",
			"insert_after": "custom_disbursed_amount",
			"read_only": 1,
			"in_list_view": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_fnf_reference",
			"label": "F&F Statement",
			"fieldtype": "Link",
			"options": "Full and Final Statement",
			"insert_after": "custom_salary_slip",
			"read_only": 1,
			"system_generated": 0,
		},
	],
	"Salary Slip": [
		{
			"fieldname": "custom_salary_withholding_section",
			"fieldtype": "Section Break",
			"label": "Salary Withholding",
			"insert_after": "bank_name",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_is_partially_withheld",
			"label": "Is Partially Withheld",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "custom_salary_withholding_section",
			"read_only": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_withheld_percentage",
			"label": "Withheld Percentage",
			"fieldtype": "Percent",
			"insert_after": "custom_is_partially_withheld",
			"read_only": 1,
			"depends_on": "eval:doc.custom_is_partially_withheld",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_withheld_amount",
			"label": "Withheld Amount",
			"fieldtype": "Currency",
			"insert_after": "custom_withheld_percentage",
			"read_only": 1,
			"depends_on": "eval:doc.custom_is_partially_withheld",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_salary_withholding_col_break",
			"fieldtype": "Column Break",
			"insert_after": "custom_withheld_amount",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_salary_withholding",
			"label": "Salary Withholding",
			"fieldtype": "Link",
			"options": "Salary Withholding",
			"insert_after": "custom_salary_withholding_col_break",
			"read_only": 1,
			"depends_on": "eval:doc.custom_is_partially_withheld",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_salary_withholding_cycle",
			"label": "Salary Withholding Cycle",
			"fieldtype": "Link",
			"options": "Salary Withholding Cycle",
			"insert_after": "custom_salary_withholding",
			"read_only": 1,
			"depends_on": "eval:doc.custom_is_partially_withheld",
			"system_generated": 0,
		},
	],
}
