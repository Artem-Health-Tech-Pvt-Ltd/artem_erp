"""Patch to create Asset Maintenance reports, dashboard, number cards, and custom workspace.
"""

import frappe
from artem_erp.asset_maintenance_setup import setup_asset_maintenance_suite


def execute():
	setup_asset_maintenance_suite()
	frappe.db.commit()

