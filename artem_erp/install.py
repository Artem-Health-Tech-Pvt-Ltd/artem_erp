import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from artem_erp.custom_fields_and_property_setter.custom_fields import CUSTOM_FIELDS
from artem_erp.custom_fields_and_property_setter.property_setter import get_property_setters


def after_migrate():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)
	make_property_setter()


def after_install():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)
	make_property_setter()


def make_property_setter():
	for property_setter in get_property_setters():
		frappe.make_property_setter(property_setter, validate_fields_for_doctype=False)
