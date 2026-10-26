import importlib

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
	create_workflow()


def setup_workspace_shortcuts():
	from artem_erp.patches.create_role_based_hrms_workspaces import execute as setup_hrms_workspaces
	from artem_erp.patches.payroll_shortcut import execute as setup_payroll_shortcuts

	setup_payroll_shortcuts()
	setup_hrms_workspaces()


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
			frappe.throw(f"Parent section '{parent_label}' not found in workspace '{workspace_name}'")

		workspace.append("items", new_item, position=parent_index + 1)

	# Add shortcut after a specific item
	elif insert_after:
		insert_index = None

		for index, item in enumerate(workspace.items):
			if item.label == insert_after:
				insert_index = index
				break

		if insert_index is None:
			frappe.throw(f"Item '{insert_after}' not found in workspace '{workspace_name}'")

		workspace.append("items", new_item, position=insert_index + 1)

	# Add as normal top-level shortcut
	else:
		# Add as normal shortcut
		workspace.append("items", new_item)

	workspace.save()


def create_workflow():
	fixture_folder_name = ["workflow.device_login_authorization_workflow"]

	suffix_mapping = {
		"workflow_action_master": "Workflow Action Master",
		"workflow_state": "Workflow State",
		"workflow": "Workflow",
	}

	for file_path in fixture_folder_name:
		for suffix, doctype in suffix_mapping.items():
			make_workflow(
				f"artem_erp.{file_path}.{suffix}",
				f"get_{suffix}",
				doctype,
			)


def make_workflow(file_path, module_name, doctype):
	module = importlib.import_module(file_path)
	workflow_function = getattr(module, module_name)

	for workflow in workflow_function():
		name = workflow.get("name")

		if frappe.db.exists(doctype, name):
			doc = frappe.get_doc(doctype, name)
			doc.update(workflow)
			doc.save()
		else:
			doc = frappe.new_doc(doctype)
			doc.update(workflow)
			doc.insert()
