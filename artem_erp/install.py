import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from artem_erp.custom_fields_and_property_setter.custom_fields import CUSTOM_FIELDS
from artem_erp.custom_fields_and_property_setter.property_setter import get_property_setters


def after_migrate():
    create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)
    make_property_setter()
    setup_workspace_shortcuts()


def after_install():
    create_custom_fields(CUSTOM_FIELDS, update=True, ignore_validate=True)
    make_property_setter()
    setup_workspace_shortcuts()


def setup_workspace_shortcuts():
    from artem_erp.patches.payroll_shortcut import execute as setup_payroll_shortcuts

    setup_payroll_shortcuts()


def make_property_setter():
    for property_setter in get_property_setters():
        frappe.make_property_setter(property_setter, validate_fields_for_doctype=False)


def add_workspace_shortcut(
    workspace_name,
    label,
    link_to,
    icon=None,
    link_type="DocType",
    item_type="Link",
    parent_label=None,
    child=None,
    insert_after=None,
):
    if not frappe.db.exists("Workspace Sidebar", workspace_name):
        return

    workspace = frappe.get_doc("Workspace Sidebar", workspace_name)

    # Prevent duplicate shortcut
    for item in workspace.items:
        if item.label == label and item.link_to == link_to:
            return

    new_item = {
        "label": label,
        "link_type": link_type,
        "type": item_type,
        "link_to": link_to,
        "icon": icon,
        "child": 1 if parent_label else 0,
    }

    # Add shortcut under parent section
    if parent_label:
        parent_index = None

        for index, item in enumerate(workspace.items):
            if item.label == parent_label:
                parent_index = index
                break

        if parent_index is None:
            frappe.throw(
                f"Parent section '{parent_label}' not found "
                f"in workspace '{workspace_name}'"
            )

        workspace.append("items", new_item, position=parent_index + 1)

    # Add shortcut after a specific item
    elif insert_after:
        insert_index = None

        for index, item in enumerate(workspace.items):
            if item.label == insert_after:
                insert_index = index
                break

        if insert_index is None:
            frappe.throw(
                f"Item '{insert_after}' not found "
                f"in workspace '{workspace_name}'"
            )

        workspace.append("items", new_item, position=insert_index + 1)

    # Add as normal top-level shortcut
    else:
        # Add as normal shortcut
        workspace.append("items", new_item)

    workspace.save()