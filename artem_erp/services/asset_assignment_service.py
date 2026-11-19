# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime, nowdate


def get_request_cache_key(asset, employee, status, movement=None):
	return f"{asset}_{employee or ''}_{status}_{movement or ''}"


def is_recently_logged(asset, employee, status, movement=None):
	"""Check memory cache and recent DB records to avoid duplicate history logging."""
	if not hasattr(frappe.flags, "recent_assignment_history"):
		frappe.flags.recent_assignment_history = set()

	cache_key = get_request_cache_key(asset, employee, status, movement)
	if cache_key in frappe.flags.recent_assignment_history:
		return True

	# If tied to an Asset Movement, check DB existence
	if movement:
		if frappe.db.exists(
			"Asset Assignment History",
			{
				"asset": asset,
				"asset_movement": movement,
				"assignment_status": status,
			},
		):
			frappe.flags.recent_assignment_history.add(cache_key)
			return True

	# Check for duplicate created within the last 5 seconds
	recent_id = frappe.db.sql(
		"""
		SELECT name FROM `tabAsset Assignment History`
		WHERE asset = %(asset)s
		  AND COALESCE(employee, '') = %(employee)s
		  AND assignment_status = %(status)s
		  AND creation >= NOW() - INTERVAL 5 SECOND
		LIMIT 1
		""",
		{
			"asset": asset,
			"employee": employee or "",
			"status": status,
		},
	)
	if recent_id:
		frappe.flags.recent_assignment_history.add(cache_key)
		return True

	return False


def mark_as_logged(asset, employee, status, movement=None):
	if not hasattr(frappe.flags, "recent_assignment_history"):
		frappe.flags.recent_assignment_history = set()
	cache_key = get_request_cache_key(asset, employee, status, movement)
	frappe.flags.recent_assignment_history.add(cache_key)


def record_assignment(
	asset,
	employee,
	previous_custodian=None,
	assignment_date=None,
	asset_movement=None,
	remarks=None,
	assigned_by=None,
):
	"""Creates a new 'Assigned' record in Asset Assignment History with full audit details."""
	if not asset or not employee:
		return None

	if is_recently_logged(asset, employee, "Assigned", asset_movement):
		return None

	asset_meta = frappe.db.get_value(
		"Asset",
		asset,
		["name", "asset_name", "asset_category"],
		as_dict=True,
	) or {}

	emp_meta = frappe.db.get_value(
		"Employee",
		employee,
		["name", "employee_name", "company_email", "personal_email", "user_id", "prefered_email"],
		as_dict=True,
	) or {}

	emp_email = (
		emp_meta.get("company_email")
		or emp_meta.get("personal_email")
		or emp_meta.get("user_id")
		or emp_meta.get("prefered_email")
		or ""
	)

	prev_name = ""
	if previous_custodian:
		prev_name = frappe.db.get_value("Employee", previous_custodian, "employee_name") or ""

	curr_dt = assignment_date or now_datetime()

	doc = frappe.get_doc({
		"doctype": "Asset Assignment History",
		"asset": asset,
		"asset_id": asset,
		"asset_name": asset_meta.get("asset_name") or asset,
		"asset_category": asset_meta.get("asset_category") or "",
		"previous_custodian": previous_custodian or None,
		"previous_custodian_name": prev_name,
		"employee": employee,
		"employee_id": emp_meta.get("name") or employee,
		"employee_name": emp_meta.get("employee_name") or "",
		"employee_email": emp_email,
		"assignment_date": curr_dt,
		"assignment_status": "Assigned",
		"asset_movement": asset_movement or None,
		"assigned_by": assigned_by or frappe.session.user,
		"remarks": remarks or _("Asset assigned to custodian."),
	})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)

	mark_as_logged(asset, employee, "Assigned", asset_movement)
	return doc.name


def record_return(
	asset,
	employee,
	return_date=None,
	asset_movement=None,
	remarks=None,
	returned_by=None,
):
	"""Closes the active assignment or creates a 'Returned' record in Asset Assignment History."""
	if not asset or not employee:
		return None

	if is_recently_logged(asset, employee, "Returned", asset_movement):
		return None

	curr_dt = return_date or now_datetime()

	# Find active assignment record that is not returned yet
	active_history = frappe.db.get_value(
		"Asset Assignment History",
		{
			"asset": asset,
			"employee": employee,
			"assignment_status": "Assigned",
		},
		"name",
		order_by="creation desc",
	)

	if active_history:
		frappe.db.set_value(
			"Asset Assignment History",
			active_history,
			{
				"return_date": curr_dt,
				"assignment_status": "Returned",
				"asset_movement": asset_movement or frappe.db.get_value("Asset Assignment History", active_history, "asset_movement"),
				"returned_by": returned_by or frappe.session.user,
				"remarks": remarks or frappe.db.get_value("Asset Assignment History", active_history, "remarks") or _("Asset returned."),
			},
			update_modified=False,
		)
		mark_as_logged(asset, employee, "Returned", asset_movement)
		return active_history

	# If no active assignment record exists to close, create a standalone return entry
	asset_meta = frappe.db.get_value(
		"Asset",
		asset,
		["name", "asset_name", "asset_category"],
		as_dict=True,
	) or {}

	emp_meta = frappe.db.get_value(
		"Employee",
		employee,
		["name", "employee_name", "company_email", "personal_email", "user_id", "prefered_email"],
		as_dict=True,
	) or {}

	emp_email = (
		emp_meta.get("company_email")
		or emp_meta.get("personal_email")
		or emp_meta.get("user_id")
		or emp_meta.get("prefered_email")
		or ""
	)

	doc = frappe.get_doc({
		"doctype": "Asset Assignment History",
		"asset": asset,
		"asset_id": asset,
		"asset_name": asset_meta.get("asset_name") or asset,
		"asset_category": asset_meta.get("asset_category") or "",
		"employee": employee,
		"employee_id": emp_meta.get("name") or employee,
		"employee_name": emp_meta.get("employee_name") or "",
		"employee_email": emp_email,
		"return_date": curr_dt,
		"assignment_status": "Returned",
		"asset_movement": asset_movement or None,
		"returned_by": returned_by or frappe.session.user,
		"remarks": remarks or _("Asset returned by custodian."),
	})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)

	mark_as_logged(asset, employee, "Returned", asset_movement)
	return doc.name


def handle_asset_custodian_change(asset_doc):
	"""Invoked when Asset DocType is saved or updated.
	Detects custodian changes (new assignment, return, or transfer) and records history."""
	# Guard: Avoid re-processing if triggered within Asset Movement or Allocation dialog
	if getattr(frappe.flags, "in_asset_movement", False):
		return
	if getattr(frappe.flags, "in_allocation_action", False):
		return

	prev_custodian = None
	if hasattr(asset_doc, "get_doc_before_save"):
		prev_doc = asset_doc.get_doc_before_save()
		if prev_doc:
			prev_custodian = prev_doc.custodian

	# Fallback if _doc_before_save was not available: check active DB assignment
	if not prev_custodian and getattr(asset_doc, "name", None):
		active_in_db = frappe.db.get_value(
			"Asset Assignment History",
			{"asset": asset_doc.name, "assignment_status": "Assigned"},
			"employee",
			order_by="creation desc",
		)
		if active_in_db and active_in_db != asset_doc.custodian:
			prev_custodian = active_in_db

	curr_custodian = asset_doc.custodian

	if prev_custodian == curr_custodian:
		return

	assign_dt = now_datetime()
	if getattr(asset_doc, "custom_assignment_date", None):
		try:
			assign_dt = get_datetime(asset_doc.custom_assignment_date)
		except Exception:
			pass

	# Case 1: Return (Previous custodian set, current is empty)
	if prev_custodian and not curr_custodian:
		record_return(
			asset=asset_doc.name,
			employee=prev_custodian,
			return_date=now_datetime(),
			remarks=_("Returned via Asset form update."),
		)
		sync_employee_allocation_record(prev_custodian)

	# Case 2: New Assignment (Previous custodian empty, current is set)
	elif not prev_custodian and curr_custodian:
		record_assignment(
			asset=asset_doc.name,
			employee=curr_custodian,
			previous_custodian=None,
			assignment_date=assign_dt,
			remarks=_("Assigned via Asset form update."),
		)
		sync_employee_allocation_record(curr_custodian)

	# Case 3: Employee-to-Employee Transfer (Both set and different)
	elif prev_custodian and curr_custodian and prev_custodian != curr_custodian:
		record_return(
			asset=asset_doc.name,
			employee=prev_custodian,
			return_date=now_datetime(),
			remarks=_("Transferred to {0} via Asset form update.").format(curr_custodian),
		)
		record_assignment(
			asset=asset_doc.name,
			employee=curr_custodian,
			previous_custodian=prev_custodian,
			assignment_date=assign_dt,
			remarks=_("Transferred from {0} via Asset form update.").format(prev_custodian),
		)
		sync_employee_allocation_record(prev_custodian)
		sync_employee_allocation_record(curr_custodian)


def handle_asset_movement_submit(movement_doc):
	"""Handles standard Asset Movement submission.
	Automatically creates Assignment History for issues, returns, and transfers."""
	frappe.flags.in_asset_movement = True
	try:
		tx_date = movement_doc.transaction_date or now_datetime()

		for item in movement_doc.assets:
			asset_id = item.asset
			from_emp = item.from_employee
			to_emp = item.to_employee
			purpose = movement_doc.purpose

			# Fallback: if from_emp was left blank, check if asset currently has an active custodian
			if not from_emp:
				active_cust = frappe.db.get_value(
					"Asset Assignment History",
					{"asset": asset_id, "assignment_status": "Assigned"},
					"employee",
					order_by="creation desc",
				)
				if active_cust and active_cust != to_emp:
					from_emp = active_cust

			if from_emp and to_emp:
				# ─── Employee-to-Employee Transfer ─────────────────────────────
				record_return(
					asset=asset_id,
					employee=from_emp,
					return_date=tx_date,
					asset_movement=movement_doc.name,
					remarks=_("Transferred to {0} via Asset Movement {1} ({2}).").format(
						to_emp, movement_doc.name, purpose
					),
				)
				record_assignment(
					asset=asset_id,
					employee=to_emp,
					previous_custodian=from_emp,
					assignment_date=tx_date,
					asset_movement=movement_doc.name,
					remarks=_("Transferred from {0} via Asset Movement {1} ({2}).").format(
						from_emp, movement_doc.name, purpose
					),
				)
				update_asset_after_movement(asset_id, custodian=to_emp, status="Assigned", tx_date=tx_date)
				sync_employee_allocation_record(from_emp)
				sync_employee_allocation_record(to_emp)

			elif to_emp and not from_emp:
				# ─── New Assignment / Issue ────────────────────────────────────
				record_assignment(
					asset=asset_id,
					employee=to_emp,
					previous_custodian=None,
					assignment_date=tx_date,
					asset_movement=movement_doc.name,
					remarks=_("Issued via Asset Movement {0} ({1}).").format(movement_doc.name, purpose),
				)
				update_asset_after_movement(asset_id, custodian=to_emp, status="Assigned", tx_date=tx_date)
				sync_employee_allocation_record(to_emp)

			elif from_emp and not to_emp:
				# ─── Return / Receipt into Stock ──────────────────────────────
				record_return(
					asset=asset_id,
					employee=from_emp,
					return_date=tx_date,
					asset_movement=movement_doc.name,
					remarks=_("Returned via Asset Movement {0} ({1}).").format(movement_doc.name, purpose),
				)

				# Check active repair
				is_repair = frappe.db.exists(
					"Asset Repair",
					{"asset": asset_id, "repair_status": "Pending", "docstatus": ("<", 2)},
				)
				new_status = "In Repair" if is_repair else "In Stock"
				update_asset_after_movement(asset_id, custodian=None, status=new_status, tx_date=None)
				sync_employee_allocation_record(from_emp)

	finally:
		frappe.flags.in_asset_movement = False


def update_asset_after_movement(asset_id, custodian, status, tx_date):
	"""Updates Asset custom fields ensuring status and custodian consistency."""
	emp_name, emp_email = "", ""
	if custodian:
		emp = frappe.db.get_value(
			"Employee",
			custodian,
			["employee_name", "company_email", "personal_email", "user_id", "prefered_email"],
			as_dict=True,
		) or {}
		emp_name = emp.get("employee_name") or ""
		emp_email = (
			emp.get("company_email")
			or emp.get("personal_email")
			or emp.get("user_id")
			or emp.get("prefered_email")
			or ""
		)

	date_val = None
	if tx_date:
		try:
			date_val = get_datetime(tx_date).date()
		except Exception:
			date_val = nowdate()

	frappe.db.set_value(
		"Asset",
		asset_id,
		{
			"custodian": custodian,
			"custom_asset_status": status,
			"custom_employee_name": emp_name,
			"custom_employee_email": emp_email,
			"custom_assignment_date": date_val,
		},
		update_modified=False,
	)


def sync_employee_allocation_record(employee):
	"""Synchronizes Employee Asset Allocation and Employee's custom child table."""
	if not employee or not frappe.db.exists("Employee", employee):
		return

	try:
		if frappe.db.exists("Employee Asset Allocation", employee):
			alloc = frappe.get_doc("Employee Asset Allocation", employee)
		else:
			alloc = frappe.new_doc("Employee Asset Allocation")
			alloc.employee = employee

		alloc.sync_with_employee_and_assets()
		alloc.flags.ignore_permissions = True
		alloc.flags.ignore_mandatory = True
		alloc.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(f"Failed to sync allocation for {employee}")

	# Sync Employee DocType child table
	try:
		emp = frappe.get_doc("Employee", employee)
		from artem_erp.doc_events.employee import sync_employee_assets_table
		sync_employee_assets_table(emp)
		emp.flags.ignore_validate = True
		emp.flags.ignore_mandatory = True
		emp.save(ignore_permissions=True)
	except Exception:
		pass
