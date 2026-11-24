# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Fix existing asset statuses, assignment dates, and child table rows."""
	# 1. Update Asset custom_asset_status and assignment date for assets with custodian
	frappe.db.sql(
		"""
		UPDATE `tabAsset`
		SET
			custom_asset_status = 'Assigned',
			custom_assignment_date = COALESCE(custom_assignment_date, DATE(creation), CURDATE())
		WHERE
			custodian IS NOT NULL
			AND custodian != ''
			AND (custom_asset_status IS NULL OR custom_asset_status != 'In Repair')
		"""
	)

	# 2. Update Asset custom_asset_status for unassigned assets
	frappe.db.sql(
		"""
		UPDATE `tabAsset`
		SET
			custom_asset_status = 'In Stock'
		WHERE
			(custodian IS NULL OR custodian = '')
			AND (custom_asset_status IS NULL OR custom_asset_status = 'Assigned')
		"""
	)

	# 3. Fix status and assignment_date in tabEmployee Assigned Asset
	frappe.db.sql(
		"""
		UPDATE `tabEmployee Assigned Asset` eaa
		JOIN `tabAsset` a ON eaa.asset = a.name
		SET
			eaa.status = COALESCE(a.custom_asset_status, 'Assigned'),
			eaa.assignment_date = COALESCE(a.custom_assignment_date, eaa.assignment_date, DATE(a.creation), CURDATE()),
			eaa.asset_name = COALESCE(a.asset_name, eaa.asset_name),
			eaa.asset_category = COALESCE(a.asset_category, eaa.asset_category),
			eaa.location = COALESCE(a.location, eaa.location)
		"""
	)

	# 4. Synchronize Employee records having assigned assets
	try:
		employees_with_assets = frappe.db.sql(
			"""
			SELECT DISTINCT custodian FROM `tabAsset`
			WHERE custodian IS NOT NULL AND custodian != '' AND docstatus != 2
			""",
			pluck=True,
		)
		from artem_erp.doc_events.employee import sync_employee_assets_table

		for emp_id in employees_with_assets:
			if frappe.db.exists("Employee", emp_id):
				try:
					emp = frappe.get_doc("Employee", emp_id)
					sync_employee_assets_table(emp)
					emp.flags.ignore_validate = True
					emp.flags.ignore_mandatory = True
					emp.save(ignore_permissions=True)
				except Exception:
					pass
	except Exception:
		pass

	frappe.db.commit()
