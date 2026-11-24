# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe

from artem_erp.services.asset_assignment_service import (
	handle_asset_movement_submit,
	sync_employee_allocation_record,
)


def on_submit(doc, method=None):
	"""Hook triggered on submission of standard Asset Movement."""
	handle_asset_movement_submit(doc)


def on_cancel(doc, method=None):
	"""Hook triggered on cancellation of standard Asset Movement."""
	affected_employees = set()
	for item in doc.assets:
		if item.from_employee:
			affected_employees.add(item.from_employee)
		if item.to_employee:
			affected_employees.add(item.to_employee)

	for emp in affected_employees:
		sync_employee_allocation_record(emp)
