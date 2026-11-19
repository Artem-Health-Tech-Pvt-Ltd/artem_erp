import frappe
from frappe import _


def validate_aadhaar_number(doc, method=None):
	aadhaar_number = doc.get("custom_aadhaar_number")

	if not aadhaar_number or not str(aadhaar_number).strip():
		return

	aadhaar_number = str(aadhaar_number).strip()

	if not aadhaar_number.isdigit():
		frappe.throw(
			_("Aadhaar Number must contain only digits."),
			title=_("Invalid Aadhaar Number"),
		)

	if len(aadhaar_number) != 12:
		frappe.throw(
			_("Aadhaar Number must be exactly 12 digits."),
			title=_("Invalid Aadhaar Number"),
		)

	existing_employee = frappe.db.exists(
		"Employee",
		{
			"custom_aadhaar_number": aadhaar_number,
			"name": ["!=", doc.name],
		},
	)

	if existing_employee:
		frappe.throw(
			_("Aadhaar Number already exists for Employee {0}.").format(existing_employee),
			title=_("Duplicate Aadhaar Number"),
		)


def validate(doc, method=None):
	"""Main validate event for Employee."""
	validate_aadhaar_number(doc, method)
	sync_manual_asset_assignments(doc)


def onload(doc, method=None):
	"""Called when Employee is opened in Desk."""
	pass


@frappe.whitelist()
def get_employee_assigned_assets(employee):
	"""Return all active assets assigned to this employee."""
	if not employee:
		return []
	assets = frappe.get_all(
		"Asset",
		filters={"custodian": employee, "docstatus": ["!=", 2]},
		fields=["name", "asset_name", "asset_category", "location", "custom_assignment_date", "status", "custom_asset_status"],
		order_by="creation desc",
	)
	for a in assets:
		st = a.get("custom_asset_status")
		if st not in ("Assigned", "In Repair"):
			st = "Assigned"
		a["custom_asset_status"] = st
		a["status"] = st
	return assets


def sync_employee_assets_table(doc):
	"""Helper to sync custom_assigned_assets child rows from Asset table."""
	if not doc.name:
		return
	assets = frappe.get_all(
		"Asset",
		filters={"custodian": doc.name, "docstatus": ["!=", 2]},
		fields=["name", "asset_name", "asset_category", "location", "custom_assignment_date", "status", "custom_asset_status"],
		order_by="creation desc",
	)
	doc.set("custom_assigned_assets", [])
	for a in assets:
		assigned_status = a.get("custom_asset_status")
		if assigned_status not in ("Assigned", "In Repair"):
			assigned_status = "Assigned"
		doc.append(
			"custom_assigned_assets",
			{
				"asset": a.name,
				"asset_name": a.asset_name,
				"asset_category": a.asset_category,
				"location": a.location,
				"assignment_date": a.custom_assignment_date or frappe.utils.nowdate(),
				"status": assigned_status,
			},
		)


def sync_manual_asset_assignments(doc):
	"""If assets were manually added to the child table in Desk, link them to this employee."""
	if not doc.name or doc.is_new():
		return

	table_assets = {row.asset for row in doc.get("custom_assigned_assets", []) if row.asset}
	db_assets = set(
		frappe.get_all(
			"Asset",
			filters={"custodian": doc.name, "docstatus": ["!=", 2]},
			pluck="name",
		)
	)

	# New assets added in table -> update custodian, status and assignment date
	for new_asset in (table_assets - db_assets):
		frappe.db.set_value(
			"Asset",
			new_asset,
			{
				"custodian": doc.name,
				"custom_asset_status": "Assigned",
				"custom_employee_name": doc.employee_name or "",
				"custom_employee_email": (
					doc.company_email or doc.personal_email or doc.user_id or doc.prefered_email or ""
				),
				"custom_assignment_date": frappe.utils.nowdate(),
			},
			update_modified=False,
		)
		from artem_erp.services.asset_assignment_service import record_assignment
		record_assignment(
			asset=new_asset,
			employee=doc.name,
			assignment_date=frappe.utils.now_datetime(),
			remarks=_("Assigned via Employee form child table."),
		)

	# If assets were removed from child table -> return them to In Stock
	for removed_asset in (db_assets - table_assets):
		frappe.db.set_value(
			"Asset",
			removed_asset,
			{
				"custodian": None,
				"custom_asset_status": "In Stock",
				"custom_employee_name": "",
				"custom_employee_email": "",
				"custom_assignment_date": None,
			},
			update_modified=False,
		)
		from artem_erp.services.asset_assignment_service import record_return
		record_return(
			asset=removed_asset,
			employee=doc.name,
			return_date=frappe.utils.now_datetime(),
			remarks=_("Removed from Employee form child table."),
		)
