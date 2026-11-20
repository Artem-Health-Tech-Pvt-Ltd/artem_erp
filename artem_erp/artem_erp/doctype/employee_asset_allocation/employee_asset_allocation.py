# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, nowdate


class EmployeeAssetAllocation(Document):
	def onload(self):
		pass

	def validate(self):
		self.sync_with_employee_and_assets()

	def sync_with_employee_and_assets(self):
		"""Pulls latest employee details directly from Employee DocType
		and currently assigned assets directly from Asset DocType without duplicating data."""
		if not self.employee:
			return

		emp = frappe.db.get_value(
			"Employee",
			self.employee,
			[
				"name",
				"employee_name",
				"company_email",
				"personal_email",
				"user_id",
				"prefered_email",
				"department",
				"designation",
				"company",
			],
			as_dict=True,
		)
		if emp:
			self.employee_id = emp.name
			self.employee_name = emp.employee_name or ""
			self.employee_email = (
				emp.company_email or emp.personal_email or emp.user_id or emp.prefered_email or ""
			)
			self.department = emp.department or ""
			self.designation = emp.designation or ""
			self.company = emp.company or ""

		# Retrieve all assets currently assigned to this employee
		active_assets = frappe.get_all(
			"Asset",
			filters={"custodian": self.employee, "docstatus": ["!=", 2]},
			fields=[
				"name",
				"asset_name",
				"asset_category",
				"location",
				"custom_assignment_date",
				"custom_asset_status",
				"status",
			],
			order_by="creation desc",
		)

		self.set("items", [])
		for a in active_assets:
			status_val = a.get("custom_asset_status") or a.get("status") or "Assigned"
			self.append(
				"items",
				{
					"asset": a.name,
					"asset_name": a.asset_name,
					"asset_category": a.asset_category,
					"location": a.location,
					"assignment_date": a.custom_assignment_date,
					"status": status_val,
					"allocation_status": "Assigned",
				},
			)

		self.total_assigned_assets = len(self.items)


@frappe.whitelist()
def get_available_assets(category=None, search_term=None):
	"""Returns all assets currently available for assignment (custom_asset_status = 'In Stock' and no custodian)."""
	filters = [
		["Asset", "docstatus", "!=", 2],
		["Asset", "custom_asset_status", "=", "In Stock"],
	]

	if category:
		filters.append(["Asset", "asset_category", "=", category])

	or_filters = []
	if search_term:
		search_like = f"%{search_term}%"
		or_filters = [
			["Asset", "name", "like", search_like],
			["Asset", "asset_name", "like", search_like],
		]

	assets = frappe.get_all(
		"Asset",
		filters=filters,
		or_filters=or_filters if or_filters else None,
		fields=["name", "asset_name", "asset_category", "custom_asset_status", "location", "company"],
		order_by="name asc",
		limit_page_length=100,
	)

	available = []
	for a in assets:
		is_under_repair = frappe.db.exists(
			"Asset Repair",
			{"asset": a.name, "repair_status": "Pending", "docstatus": ("<", 2)},
		)
		if not is_under_repair:
			available.append(a)

	return available


@frappe.whitelist()
def assign_assets_to_employee(employee, asset_names):
	"""Server-side transactional method to assign multiple assets to an employee."""
	if not employee:
		frappe.throw(_("Employee is required."))

	if isinstance(asset_names, str):
		asset_names = frappe.parse_json(asset_names)

	if not asset_names:
		frappe.throw(_("Please select at least one asset to assign."))

	emp_details = frappe.db.get_value(
		"Employee",
		employee,
		[
			"name",
			"employee_name",
			"company_email",
			"personal_email",
			"user_id",
			"prefered_email",
			"department",
			"designation",
			"company",
		],
		as_dict=True,
	)
	if not emp_details:
		frappe.throw(_("Employee {0} not found.").format(employee))

	emp_email = (
		emp_details.company_email
		or emp_details.personal_email
		or emp_details.user_id
		or emp_details.prefered_email
		or ""
	)
	curr_date = nowdate()
	curr_dt = now_datetime()
	assigned_now = []

	for asset_name in asset_names:
		asset = frappe.db.get_value(
			"Asset",
			asset_name,
			["name", "asset_name", "asset_category", "custom_asset_status", "custodian", "docstatus"],
			as_dict=True,
		)
		if not asset:
			frappe.throw(_("Asset {0} not found.").format(asset_name))

		if asset.docstatus == 2:
			frappe.throw(_("Asset {0} is cancelled.").format(asset_name))

		if asset.custodian:
			frappe.throw(
				_("Asset {0} is already assigned to employee {1}.").format(asset_name, asset.custodian)
			)

		if asset.custom_asset_status != "In Stock":
			frappe.throw(
				_("Asset {0} is not available for assignment. Current Status: {1}").format(
					asset_name, asset.custom_asset_status
				)
			)

		active_repair = frappe.db.exists(
			"Asset Repair",
			{"asset": asset_name, "repair_status": "Pending", "docstatus": ("<", 2)},
		)
		if active_repair:
			frappe.throw(_("Asset {0} is currently Under Repair and cannot be assigned.").format(asset_name))

	frappe.flags.in_allocation_action = True
	try:
		for asset_name in asset_names:
			frappe.db.set_value(
				"Asset",
				asset_name,
				{
					"custodian": employee,
					"custom_employee_name": emp_details.employee_name or "",
					"custom_employee_email": emp_email,
					"custom_assignment_date": curr_date,
					"custom_asset_status": "Assigned",
				},
				update_modified=False,
			)

			from artem_erp.services.asset_assignment_service import record_assignment

			record_assignment(
				asset=asset_name,
				employee=employee,
				previous_custodian=None,
				assignment_date=curr_dt,
				remarks=_("Assigned via Employee Asset Allocation."),
			)
			assigned_now.append(asset_name)

		# 2. Update Employee Asset Allocation document
		if frappe.db.exists("Employee Asset Allocation", employee):
			alloc_doc = frappe.get_doc("Employee Asset Allocation", employee)
		else:
			alloc_doc = frappe.new_doc("Employee Asset Allocation")
			alloc_doc.employee = employee

		alloc_doc.sync_with_employee_and_assets()
		alloc_doc.flags.ignore_permissions = True
		alloc_doc.save(ignore_permissions=True)

		# 3. Synchronize Employee's custom_assigned_assets table
		_sync_employee_assets_table(employee)

		frappe.db.commit()
		return {"message": _("Successfully assigned {0} asset(s).").format(len(assigned_now))}
	finally:
		frappe.flags.in_allocation_action = False


@frappe.whitelist()
def return_assets_from_employee(employee, asset_names, remarks=None):
	"""Server-side transactional method to return assigned assets from an employee."""
	if not employee:
		frappe.throw(_("Employee is required."))

	if isinstance(asset_names, str):
		asset_names = frappe.parse_json(asset_names)

	if not asset_names:
		frappe.throw(_("Please select at least one asset to return."))

	curr_dt = now_datetime()
	returned_now = []

	frappe.flags.in_allocation_action = True
	try:
		for asset_name in asset_names:
			active_repair = frappe.db.exists(
				"Asset Repair",
				{"asset": asset_name, "repair_status": "Pending", "docstatus": ("<", 2)},
			)
			active_child_repair = frappe.db.exists(
				"Asset Maintenance Record",
				{"parent": asset_name, "repair_required": 1, "maintenance_status": "In Progress"},
			)

			new_status = "In Repair" if (active_repair or active_child_repair) else "In Stock"

			frappe.db.set_value(
				"Asset",
				asset_name,
				{
					"custodian": None,
					"custom_employee_name": "",
					"custom_employee_email": "",
					"custom_assignment_date": None,
					"custom_asset_status": new_status,
				},
				update_modified=False,
			)

			from artem_erp.services.asset_assignment_service import record_return

			record_return(
				asset=asset_name,
				employee=employee,
				return_date=curr_dt,
				remarks=remarks or _("Returned via Employee Asset Allocation."),
			)

			returned_now.append(asset_name)

		# Update Employee Asset Allocation document
		if frappe.db.exists("Employee Asset Allocation", employee):
			alloc_doc = frappe.get_doc("Employee Asset Allocation", employee)
			alloc_doc.sync_with_employee_and_assets()
			alloc_doc.flags.ignore_permissions = True
			alloc_doc.save(ignore_permissions=True)

		# Synchronize Employee's custom_assigned_assets table
		_sync_employee_assets_table(employee)

		frappe.db.commit()
		return {"message": _("Successfully returned {0} asset(s).").format(len(returned_now))}
	finally:
		frappe.flags.in_allocation_action = False


def _sync_employee_assets_table(employee):
	"""Syncs the child table on Employee document directly."""
	if not employee or not frappe.db.exists("Employee", employee):
		return
	try:
		emp = frappe.get_doc("Employee", employee)
		from artem_erp.doc_events.employee import sync_employee_assets_table

		sync_employee_assets_table(emp)
		emp.flags.ignore_validate = True
		emp.flags.ignore_mandatory = True
		emp.save(ignore_permissions=True)
	except Exception:
		pass


def sync_assignment_on_asset_save(asset_doc):
	"""Bidirectional synchronization: updates Asset Assignment History and Employee Asset Allocation
	when an Asset's custodian is updated directly on the Asset form."""
	from artem_erp.services.asset_assignment_service import handle_asset_custodian_change

	handle_asset_custodian_change(asset_doc)


def sync_all_employee_allocations():
	"""Ensures Employee Asset Allocation records exist for all employees,
	directly mirroring Asset & Employee records."""
	all_employees = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name")

	for emp_id in all_employees:
		try:
			if frappe.db.exists("Employee Asset Allocation", emp_id):
				doc = frappe.get_doc("Employee Asset Allocation", emp_id)
			else:
				doc = frappe.new_doc("Employee Asset Allocation")
				doc.employee = emp_id

			doc.sync_with_employee_and_assets()
			doc.flags.ignore_permissions = True
			doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)
		except Exception:
			pass

	frappe.db.commit()
