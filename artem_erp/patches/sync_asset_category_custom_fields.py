"""Ensure Asset Category IT fields exist on sites installed before this feature."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from artem_erp.custom_fields_and_property_setter.custom_fields import CUSTOM_FIELDS
from artem_erp.custom_fields_and_property_setter.property_setter import get_property_setters


def execute():
	create_custom_fields(
		{"Asset Category": CUSTOM_FIELDS["Asset Category"]},
		update=True,
		ignore_validate=True,
	)

	for property_setter in get_property_setters():
		if property_setter.get("doctype") == "Asset Category":
			frappe.make_property_setter(property_setter, validate_fields_for_doctype=False)

	frappe.clear_cache(doctype="Asset Category")
	frappe.db.commit()
