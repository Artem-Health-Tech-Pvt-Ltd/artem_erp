import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)


CUSTOM_FIELDS = {
	"Additional Salary": [
		{
			"fieldname": "custom_date_of_joining",
			"label": "Date Of Joining",
			"fieldtype": "Date",
			"insert_after": "department",
			"fetch_from": "employee.date_of_joining",
			"read_only": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_annual_gross_earning",
			"label": "Annual Gross Earning",
			"fieldtype": "Currency",
			"insert_after": "custom_date_of_joining",
			"read_only": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_ctc",
			"label": "Total Cost To Company (CTC)",
			"fieldtype": "Currency",
			"insert_after": "custom_annual_gross_earning",
			"read_only": 1,
			"system_generated": 0,
		},
		{
			"fieldname": "custom_duration_of_additional_salary",
			"label": "Duration Of Additional Salary",
			"fieldtype": "Select",
			"options": "\nQuarterly\nHalf Yearly\nYearly",
			"insert_after": "is_recurring",
			"depends_on": "eval:doc.is_recurring",
			"mandatory_depends_on": "eval:doc.is_recurring",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_additional_salary_payment_history_section_break",
			"fieldtype": "Section Break",
			"insert_after": "ref_docname",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_additional_salary_payment_history",
			"label": "Additional Salary Payment History",
			"fieldtype": "Table",
			"options": "Additional Salary Payment History",
			"insert_after": "custom_additional_salary_payment_history_section_break",
			"read_only": 1,
			"allow_on_submit": 1,
			"system_generated": 0,
		},
	],
}
