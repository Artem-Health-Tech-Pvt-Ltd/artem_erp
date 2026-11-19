# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from artem_erp.asset_maintenance_setup import sync_assets_workspace_sidebar


def execute():
	"""Updates standard ERPNext Assets workspace sidebar and workspace
	to remove obsolete capitalization/depreciation items and include
	the custom Asset Dashboard, Employee Allocation, and Maintenance suite."""
	sync_assets_workspace_sidebar()
	frappe.db.commit()
