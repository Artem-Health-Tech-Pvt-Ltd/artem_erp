import frappe
from frappe import _


def get_data(data=None):
	return {
		"fieldname": "reference_name",
		"internal_links": {
			"Employee Advance": ["advances", "employee_advance"],
			"Expense": ["expenses", "custom_expense"],
		},
		"transactions": [
			{"label": _("Payment"), "items": ["Payment Entry", "Journal Entry"]},
			{"label": _("Reference"), "items": ["Employee Advance", "Expense"]},
		],
	}
