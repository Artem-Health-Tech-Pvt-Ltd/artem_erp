import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import update_permission_property

from artem_erp.custom_fields_and_property_setter.custom_fields import CUSTOM_FIELDS
from artem_erp.custom_fields_and_property_setter.property_setter import get_property_setters
from artem_erp.role_and_permission.role_and_permission import ROLE_PERMISSIONS



def after_migrate():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)
	make_property_setter()
	setup_role_permissions()


def after_install():
	create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)
	make_property_setter()
	setup_role_permissions()


def make_property_setter():
	for property_setter in get_property_setters():
		frappe.make_property_setter(property_setter, validate_fields_for_doctype=False)


def setup_role_permissions():
    """
    Create/update Custom DocPerm permissions for all configured roles.
    """

    for role, doctypes in ROLE_PERMISSIONS.items():

        # Skip if Role does not exist
        if not frappe.db.exists("Role", role):
            continue

        for doctype, permissions in doctypes.items():

            # Skip if DocType does not exist
            if not frappe.db.exists("DocType", doctype):
                continue

            for permission, value in permissions.items():

                # Skip unsupported/invalid permission types
                if permission == "mask":
                    continue

                update_permission_property(
                    doctype=doctype,
                    role=role,
                    permlevel=0,
                    ptype=permission,
                    value=value,
                    validate=False,
                )

            # Clear DocType permission cache
            frappe.clear_cache(doctype=doctype)

    frappe.clear_cache()