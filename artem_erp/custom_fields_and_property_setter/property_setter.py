def get_property_setters():
	return [
		# Shift Assignment
		{
			"doctype": "Shift Assignment",
			"doctype_or_field": "DocField",
			"fieldname": "shift_location",
			"property": "hidden",
			"property_type": "Check",
			"value": 1,
		},
		#  Additional Salary
		{
			"doctype": "Additional Salary",
			"doctype_or_field": "DocField",
			"fieldname": "to_date",
			"property": "mandatory_depends_on",
			"property_type": "Data",
			"value": "",
		},
		{
			"doctype": "Additional Salary",
			"doctype_or_field": "DocField",
			"fieldname": "from_date",
			"property": "mandatory_depends_on",
			"property_type": "Data",
			"value": "",
		},
		{
			"doctype": "Additional Salary",
			"doctype_or_field": "DocField",
			"fieldname": "to_date",
			"property": "allow_on_submit",
			"property_type": "Check",
			"value": 1,
		},
		{
			"doctype": "Additional Salary",
			"doctype_or_field": "DocField",
			"fieldname": "amount",
			"property": "allow_on_submit",
			"property_type": "Check",
			"value": 1,
		},
	]
