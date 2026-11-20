import importlib

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from artem_erp.custom_fields_and_property_setter.custom_fields import CUSTOM_FIELDS
from artem_erp.custom_fields_and_property_setter.property_setter import get_property_setters


def sync_customizations():
	"""Create app-owned custom fields and property setters on every site migration."""
	# Cleanup obsolete fields
	if frappe.db.exists("Custom Field", "Asset Category-custom_default_warranty_months"):
		frappe.delete_doc(
			"Custom Field",
			"Asset Category-custom_default_warranty_months",
			ignore_permissions=True,
			force=True,
		)

	# Only create custom fields for DocTypes that exist on the current site
	available_custom_fields = {
		dt: fields for dt, fields in CUSTOM_FIELDS.items() if frappe.db.exists("DocType", dt)
	}
	if available_custom_fields:
		create_custom_fields(available_custom_fields, update=True, ignore_validate=True)

	make_property_setter()

	if frappe.db.exists("DocType", "Asset"):
		sync_asset_field_order()
	if frappe.db.exists("DocType", "Employee"):
		sync_employee_field_order()

	# Rebuild cached metadata so newly-created fields are immediately available in Desk.
	for dt in [
		"Asset Category",
		"Asset",
		"Employee",
		"Asset Maintenance Log",
		"Asset Repair",
		"Employee Asset Allocation",
		"Employee Asset Allocation Item",
		"Asset Assignment History",
	]:
		if frappe.db.exists("DocType", dt):
			frappe.clear_cache(doctype=dt)


def sync_employee_field_order():
	"""Ensure Allocated Devices & Assets section and Assigned Assets table
	are positioned in the Overview tab right after Company Details,
	before contact_details (Address & Contacts tab)."""
	import json

	if not frappe.db.exists("DocType", "Employee"):
		return

	meta = frappe.get_meta("Employee")
	fields = [f.fieldname for f in meta.fields]

	cluster = [
		"custom_assigned_assets_section",
		"custom_assigned_assets",
	]

	# Remove cluster from existing positions if present
	remaining = [f for f in fields if f not in cluster]

	# Insert cluster before contact_details (the start of the Address & Contacts tab)
	if "contact_details" in remaining:
		pos = remaining.index("contact_details")
	elif "branch" in remaining:
		pos = remaining.index("branch") + 1
	else:
		pos = len(remaining)

	new_order = remaining[:pos] + cluster + remaining[pos:]

	frappe.make_property_setter(
		{
			"doctype": "Employee",
			"doctype_or_field": "DocType",
			"property": "field_order",
			"value": json.dumps(new_order),
			"property_type": "Data",
		},
		validate_fields_for_doctype=False,
	)


def sync_asset_field_order():
	"""Ensure Custodian, Employee Details, Specifications, Warranty, and Maintenance
	are positioned in the Details section (before Depreciation and More Info tabs)."""
	import json

	if not frappe.db.exists("DocType", "Asset"):
		return

	meta = frappe.get_meta("Asset")
	fields = [f.fieldname for f in meta.fields]

	it_details_cluster = [
		"custodian",
		"custom_employee_name",
		"custom_employee_email",
		"custom_assignment_date",
		"custom_spec_section",
		"custom_specifications",
		"custom_warranty_billing_section",
		"custom_bill_copy",
		"custom_warranty_billing_col_break",
		"custom_warranty_start",
		"custom_warranty_expiry",
		"custom_warranty_document",
		"custom_maintenance_section",
		"custom_maintenance_count",
		"custom_column_break_maint",
		"custom_total_maintenance_cost",
		"custom_maintenance_section_table",
		"custom_maintenance_records",
	]

	# Remove cluster fields from their current positions
	remaining = [f for f in fields if f not in it_details_cluster]

	# Insert cluster into Details section right after custom_device_id / custom_asset_status
	if "custom_device_id" in remaining:
		pos = remaining.index("custom_device_id") + 1
	elif "custom_asset_status" in remaining:
		pos = remaining.index("custom_asset_status") + 1
	elif "custom_series_number" in remaining:
		pos = remaining.index("custom_series_number") + 1
	else:
		pos = remaining.index("asset_category") + 1

	new_order = remaining[:pos] + it_details_cluster + remaining[pos:]

	frappe.make_property_setter(
		{
			"doctype": "Asset",
			"doctype_or_field": "DocType",
			"property": "field_order",
			"value": json.dumps(new_order),
			"property_type": "Data",
		},
		validate_fields_for_doctype=False,
	)


def after_migrate():
	sync_customizations()
	setup_workspace_shortcuts()
	try:
		# Backfill custom_asset_status for legacy assets
		frappe.db.sql(
			"""
			UPDATE `tabAsset`
			SET custom_asset_status = IF(custodian IS NOT NULL AND custodian != '', 'Assigned', 'In Stock')
			WHERE (custom_asset_status IS NULL OR custom_asset_status = '') AND docstatus < 2
			"""
		)
	except Exception:
		pass
	try:
		from artem_erp.artem_erp.doctype.employee_asset_allocation.employee_asset_allocation import (
			sync_all_employee_allocations,
		)

		sync_all_employee_allocations()
	except Exception:
		pass


def after_install():
	sync_customizations()
	setup_workspace_shortcuts()
	create_workflow()


def setup_workspace_shortcuts():
	try:
		from artem_erp.patches.create_role_based_hrms_workspaces import execute as setup_hrms_workspaces

		setup_hrms_workspaces()
	except Exception:
		pass

	try:
		from artem_erp.patches.payroll_shortcut import execute as setup_payroll_shortcuts

		setup_payroll_shortcuts()
	except Exception:
		pass

	try:
		from artem_erp.asset_maintenance_setup import setup_asset_maintenance_suite

		setup_asset_maintenance_suite()
	except Exception:
		pass


def make_property_setter():
	for property_setter in get_property_setters():
		dt = property_setter.get("doctype")
		if dt and not frappe.db.exists("DocType", dt):
			continue
		try:
			frappe.make_property_setter(property_setter, validate_fields_for_doctype=False)
		except Exception:
			pass


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
	try:
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
	except Exception:
		pass


def make_workflow(file_path, module_name, doctype):
	try:
		module = importlib.import_module(file_path)
		workflow_function = getattr(module, module_name)

		for workflow in workflow_function():
			name = workflow.get("name")

			if doctype == "Workflow":
				doc_type = workflow.get("document_type")
				if doc_type and not frappe.db.exists("DocType", doc_type):
					continue

			if frappe.db.exists(doctype, name):
				doc = frappe.get_doc(doctype, name)
				doc.update(workflow)
				doc.save()
			else:
				doc = frappe.new_doc(doctype)
				doc.update(workflow)
				doc.insert()
	except Exception:
		pass
