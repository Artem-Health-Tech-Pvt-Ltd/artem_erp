"""Patch to synchronize Asset custom fields, Property Setters, and Details field order.
Ensures Custodian, Employee Details, and Specifications are correctly placed in the Details section.
"""

import frappe
from artem_erp.install import sync_customizations


def execute():
	sync_customizations()
	frappe.db.commit()

