import frappe
from artem_erp.custom_fields_and_property_setter.property_setter import get_property_setters



def execute():
	for property_setter in get_property_setters():
		frappe.make_property_setter(property_setter, validate_fields_for_doctype=False)


def get_property_setters():
	return [
		# Employee
		{
			"doctype": "Employee",
			"doctype_or_field": "DocField",
			"fieldname": "prefered_contact_email",
			"property": "default",
			"property_type": "Text",
			"value": "Company Email",
		},
		{
			"doctype": "Employee",
			"doctype_or_field": "DocField",
			"fieldname": "salary_mode",
			"property": "default",
			"property_type": "Text",
			"value": "Bank",
		},
		{
			"doctype": "Employee",
			"doctype_or_field": "DocField",
			"fieldname": "person_to_be_contacted",
			"property": "reqd",
			"property_type": "Check",
			"value": 1,
		},
		{
			"doctype": "Employee",
			"doctype_or_field": "DocField",
			"fieldname": "emergency_phone_number",
			"property": "reqd",
			"property_type": "Check",
			"value": 1,
		},
		{
			"doctype": "Employee",
			"doctype_or_field": "DocField",
			"fieldname": "relation",
			"property": "reqd",
			"property_type": "Check",
			"value": 1,
		},
		{
			"doctype": "Employee",
			"doctype_or_field": "DocField",
			"fieldname": "salary_mode",
			"property": "reqd",
			"property_type": "Check",
			"value": 1,
		},
	]
