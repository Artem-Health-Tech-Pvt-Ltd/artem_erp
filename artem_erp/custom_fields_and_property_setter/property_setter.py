def get_property_setters():
	return [
		{
			"doctype": "Shift Assignment",
			"doctype_or_field": "DocField",
			"fieldname": "shift_location",
			"property": "hidden",
			"property_type": "Check",
			"value": 1,
		},
		# Expense claim details
		{
			"doctype": "Expense Claim Detail",
			"doctype_or_field": "DocField",
			"fieldname": "expense_date",
			"property": "read_only",
			"property_type": "Check",
			"value": 1,
		},
		{
			"doctype": "Expense Claim Detail",
			"doctype_or_field": "DocField",
			"fieldname": "expense_type",
			"property": "fetch_from",
			"value": "custom_expense.expense_category",
		},
		{
			"doctype": "Expense Claim Detail",
			"doctype_or_field": "DocField",
			"fieldname": "expense_date",
			"property": "fetch_from",
			"property_type": "Small Text",
			"value": "custom_expense.expense_date",
		},
		{
			"doctype": "Expense Claim Detail",
			"doctype_or_field": "DocField",
			"fieldname": "description",
			"property": "fetch_from",
			"value": "custom_expense.purpose",
		},
		{
			"doctype": "Expense Claim Detail",
			"doctype_or_field": "DocField",
			"fieldname": "amount",
			"property": "read_only",
			"property_type": "Check",
			"value": 1,
		},
	]
