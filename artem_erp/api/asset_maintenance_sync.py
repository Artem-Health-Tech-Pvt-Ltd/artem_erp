# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate, nowdate


def sync_asset_records(doc, method=None):
	"""Orchestrates synchronization of custom Asset maintenance child rows
	with standard ERPNext Asset Maintenance Log and Asset Repair documents."""
	if getattr(frappe.flags, "in_asset_maintenance_sync", False):
		return

	frappe.flags.in_asset_maintenance_sync = True
	try:
		records = doc.get("custom_maintenance_records") or []
		for row in records:
			if not getattr(row, "name", None) or str(row.name).startswith("new-"):
				continue

			# 1. Sync standard maintenance log for history/servicing
			sync_maintenance_record(doc, row)

			# 2. Sync standard Asset Repair if repair is required or already linked
			if row.get("repair_required") or row.get("asset_repair"):
				sync_asset_repair(doc, row)

		# 3. Refresh maintenance totals
		sync_asset_maintenance_summary(doc.name)

		# 4. Synchronize Custom Asset Status based on active repairs and custodian
		update_asset_maintenance_status(doc.name)
	finally:
		frappe.flags.in_asset_maintenance_sync = False


def sync_maintenance_record(asset_doc, row):
	"""Creates or updates the corresponding standard Asset Maintenance Log.

	Status mapping (ERPNext standard Asset Maintenance Log only supports Planned, Completed, Cancelled, Overdue):
	- Planned -> Planned
	- In Progress -> Planned
	- Completed -> Completed
	- Cancelled -> Cancelled
	"""
	if not getattr(row, "name", None):
		return None

	existing_log = None
	if row.get("maintenance_log") and frappe.db.exists("Asset Maintenance Log", row.maintenance_log):
		existing_log = row.maintenance_log
	else:
		existing_log = frappe.db.get_value(
			"Asset Maintenance Log",
			{
				"custom_source_row_id": row.name,
				"custom_created_from_asset": 1,
			},
			"name",
		)

	if existing_log:
		log = frappe.get_doc("Asset Maintenance Log", existing_log)
	else:
		log = frappe.new_doc("Asset Maintenance Log")
		log.custom_created_from_asset = 1

	# Only link to existing Asset Maintenance plan if one exists (do not auto-create dummy plans)
	existing_plan = frappe.db.get_value("Asset Maintenance", {"asset_name": asset_doc.name}, "name")
	if existing_plan:
		log.asset_maintenance = existing_plan

	log.custom_source_asset = asset_doc.name
	log.custom_source_row_id = row.name
	log.due_date = row.maintenance_date or nowdate()
	log.description = row.description or f"{row.maintenance_type or 'General'} Maintenance"
	log.custom_cost = flt(row.cost)

	# Format actions performed HTML
	log.actions_performed = (
		f"<p><b>Maintenance Type:</b> {row.maintenance_type or 'General'}</p>"
		f"<p><b>Status:</b> {row.maintenance_status or 'Planned'}</p>"
		f"<p><b>Description:</b> {row.description or 'No description provided'}</p>"
		f"<p><b>Cost:</b> {flt(row.cost)}</p>"
	)

	# Status mapping: standard log only supports Planned, Completed, Cancelled, Overdue
	current_status = getattr(row, "maintenance_status", "Planned") or "Planned"
	if current_status == "Completed":
		log.maintenance_status = "Completed"
		log.completion_date = row.get("completion_date") or row.maintenance_date or nowdate()
	elif current_status == "Cancelled":
		log.maintenance_status = "Cancelled"
		log.completion_date = None
	else:
		# Maps Planned and In Progress to Planned
		log.maintenance_status = "Planned"
		log.completion_date = None

	log.flags.ignore_permissions = True
	log.flags.ignore_mandatory = True
	log.flags.ignore_validate = True

	if log.is_new():
		log.insert(ignore_permissions=True)
	else:
		log.save(ignore_permissions=True)

	# Keep child row reference in sync
	if row.get("maintenance_log") != log.name:
		row.maintenance_log = log.name
		frappe.db.set_value(
			"Asset Maintenance Record",
			row.name,
			"maintenance_log",
			log.name,
			update_modified=False,
		)

	return log.name


def sync_asset_repair(asset_doc, row):
	"""Creates or updates the corresponding standard ERPNext Asset Repair document."""
	if not getattr(row, "name", None):
		return None

	existing_repair = None
	if row.get("asset_repair") and frappe.db.exists("Asset Repair", row.asset_repair):
		existing_repair = row.asset_repair
	else:
		existing_repair = frappe.db.get_value(
			"Asset Repair",
			{
				"custom_source_asset_row": row.name,
				"custom_created_from_asset": 1,
			},
			"name",
		)

	if existing_repair:
		repair = frappe.get_doc("Asset Repair", existing_repair)
	elif row.get("repair_required"):
		repair = frappe.new_doc("Asset Repair")
		repair.custom_created_from_asset = 1
	else:
		return None

	repair.asset = asset_doc.name
	repair.company = asset_doc.company or frappe.defaults.get_user_default("company")
	repair.custom_source_asset_row = row.name

	fail_date = row.maintenance_date or nowdate()
	repair.failure_date = get_datetime(f"{fail_date} 09:00:00")
	repair.description = row.description or f"Breakdown / Repair for {row.maintenance_type or 'Hardware'}"

	maint_status = getattr(row, "maintenance_status", "Planned") or "Planned"
	if maint_status == "Completed":
		repair.repair_status = "Completed"
		comp_date = row.get("completion_date") or fail_date
		repair.completion_date = get_datetime(f"{comp_date} 18:00:00")
	elif maint_status == "Cancelled":
		repair.repair_status = "Cancelled"
	else:
		repair.repair_status = "Pending"
		repair.completion_date = None

	repair.flags.ignore_permissions = True
	repair.flags.ignore_mandatory = True

	if repair.is_new():
		repair.insert(ignore_permissions=True)
	else:
		repair.save(ignore_permissions=True)

	# Keep child row reference in sync
	if row.get("asset_repair") != repair.name:
		row.asset_repair = repair.name
		frappe.db.set_value(
			"Asset Maintenance Record",
			row.name,
			"asset_repair",
			repair.name,
			update_modified=False,
		)

	return repair.name


def update_asset_maintenance_status(asset_name):
	"""Determines and synchronizes ONLY the custom Asset Status ('custom_asset_status').
	Never overwrites the standard ERPNext Asset 'status' field.

	Rules:
	- 'In Repair' if ANY active repair exists (Asset Repair with repair_status='Pending'
	   OR child row with repair_required=1 and maintenance_status='In Progress').
	   Note: 'Planned' repairs do not make the asset unavailable.
	- 'Assigned' if no active repair and custodian is set.
	- 'In Stock' if no active repair and no custodian.
	"""
	if not asset_name or not frappe.db.exists("Asset", asset_name):
		return None

	# 1. Check for standard Asset Repair records in Pending status (docstatus < 2)
	active_repair = frappe.db.exists(
		"Asset Repair",
		{
			"asset": asset_name,
			"repair_status": "Pending",
			"docstatus": ("<", 2),
		},
	)

	# 2. Check for child table rows marked as repair_required and currently In Progress
	active_child_repair = frappe.db.exists(
		"Asset Maintenance Record",
		{
			"parent": asset_name,
			"repair_required": 1,
			"maintenance_status": "In Progress",
		},
	)

	has_active_repair = bool(active_repair or active_child_repair)
	custodian = frappe.db.get_value("Asset", asset_name, "custodian")

	if has_active_repair:
		new_status = "In Repair"
	elif custodian:
		new_status = "Assigned"
	else:
		new_status = "In Stock"

	current_status = frappe.db.get_value("Asset", asset_name, "custom_asset_status")
	if current_status != new_status:
		frappe.db.set_value(
			"Asset",
			asset_name,
			"custom_asset_status",
			new_status,
			update_modified=False,
		)

	return new_status


def sync_asset_maintenance_summary(asset_name):
	"""Recalculates total maintenance count and total expenditure for an Asset.
	Uses Asset Maintenance Record as the single source of truth for child maintenance costs
	to avoid double-counting.
	"""
	if not asset_name or not frappe.db.exists("Asset", asset_name):
		return

	count = frappe.db.count("Asset Maintenance Record", {"parent": asset_name})
	res = frappe.db.sql(
		"SELECT SUM(cost) FROM `tabAsset Maintenance Record` WHERE parent = %s",
		(asset_name,),
	)
	total_cost = flt(res[0][0]) if res and res[0][0] is not None else 0.0

	frappe.db.set_value(
		"Asset",
		asset_name,
		{
			"custom_maintenance_count": count,
			"custom_total_maintenance_cost": total_cost,
		},
		update_modified=False,
	)


def on_asset_repair_update(doc, method=None):
	"""Triggered on Asset Repair lifecycle events (on_update, on_submit, on_cancel)
	to synchronize repair progress back to the Asset's child table and recalculate status.
	"""
	if getattr(frappe.flags, "in_asset_maintenance_sync", False):
		return

	asset_name = getattr(doc, "asset", None)
	if not asset_name or not frappe.db.exists("Asset", asset_name):
		return

	frappe.flags.in_asset_maintenance_sync = True
	try:
		source_row = getattr(doc, "custom_source_asset_row", None)
		if not source_row:
			source_row = frappe.db.get_value(
				"Asset Maintenance Record",
				{"parent": asset_name, "asset_repair": doc.name},
				"name",
			)

		if source_row and frappe.db.exists("Asset Maintenance Record", source_row):
			updates = {}
			if doc.repair_status == "Completed" or doc.docstatus == 1:
				updates["maintenance_status"] = "Completed"
				if doc.completion_date:
					updates["completion_date"] = getdate(doc.completion_date)
				repair_cost = flt(doc.total_repair_cost or doc.repair_cost)
				if repair_cost > 0:
					updates["cost"] = repair_cost
			elif doc.repair_status == "Cancelled" or doc.docstatus == 2:
				updates["maintenance_status"] = "Cancelled"
			elif doc.repair_status == "Pending":
				updates["maintenance_status"] = "In Progress"

			if updates:
				frappe.db.set_value(
					"Asset Maintenance Record",
					source_row,
					updates,
					update_modified=False,
				)

		# Refresh summary and status
		sync_asset_maintenance_summary(asset_name)
		update_asset_maintenance_status(asset_name)
	finally:
		frappe.flags.in_asset_maintenance_sync = False


@frappe.whitelist()
def create_or_open_asset_repair(asset_name, row_id):
	"""Whitelisted API called by the Desk UI button to create or open
	the corresponding standard Asset Repair record from a child table row."""
	if not asset_name or not row_id:
		frappe.throw(_("Asset Name and Row ID are required."))

	row = frappe.get_doc("Asset Maintenance Record", row_id)
	if row.parent != asset_name:
		frappe.throw(_("Row {0} does not belong to Asset {1}.").format(row_id, asset_name))

	# If repair already exists, return its name
	if row.asset_repair and frappe.db.exists("Asset Repair", row.asset_repair):
		return {"repair_name": row.asset_repair}

	asset_doc = frappe.get_doc("Asset", asset_name)
	row.repair_required = 1
	if row.maintenance_status != "Completed":
		row.maintenance_status = "In Progress"

	repair_name = sync_asset_repair(asset_doc, row)
	update_asset_maintenance_status(asset_name)

	return {"repair_name": repair_name}
