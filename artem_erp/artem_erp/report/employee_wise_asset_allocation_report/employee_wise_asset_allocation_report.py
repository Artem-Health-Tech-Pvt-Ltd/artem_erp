# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _

def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart_data(data)
	report_summary = get_report_summary(data)
	return columns, data, None, chart, report_summary

def get_columns():
	return [
		{
			"label": _("Asset ID"),
			"fieldname": "asset",
			"fieldtype": "Link",
			"options": "Asset",
			"width": 140,
		},
		{
			"label": _("Asset Name"),
			"fieldname": "asset_name",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Category"),
			"fieldname": "asset_category",
			"fieldtype": "Link",
			"options": "Asset Category",
			"width": 140,
		},
		{
			"label": _("Previous Custodian"),
			"fieldname": "previous_custodian",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 130,
		},
		{
			"label": _("Previous Custodian Name"),
			"fieldname": "previous_custodian_name",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("Employee"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 130,
		},
		{
			"label": _("Employee Name"),
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Department"),
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": 140,
		},
		{
			"label": _("Allocation Status"),
			"fieldname": "assignment_status",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": _("Current Asset Status"),
			"fieldname": "asset_status",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Assignment Date"),
			"fieldname": "assignment_date",
			"fieldtype": "Datetime",
			"width": 150,
		},
		{
			"label": _("Return Date"),
			"fieldname": "return_date",
			"fieldtype": "Datetime",
			"width": 150,
		},
		{
			"label": _("Movement Ref"),
			"fieldname": "asset_movement",
			"fieldtype": "Link",
			"options": "Asset Movement",
			"width": 140,
		},
		{
			"label": _("Assigned By"),
			"fieldname": "assigned_by",
			"fieldtype": "Link",
			"options": "User",
			"width": 130,
		},
		{
			"label": _("Returned By"),
			"fieldname": "returned_by",
			"fieldtype": "Link",
			"options": "User",
			"width": 130,
		},
		{
			"label": _("Remarks"),
			"fieldname": "remarks",
			"fieldtype": "Data",
			"width": 200,
		},
	]

def get_data(filters):
	conditions = []
	values = {}

	if filters.get("employee"):
		conditions.append("h.employee = %(employee)s")
		values["employee"] = filters.get("employee")

	if filters.get("asset_category"):
		conditions.append("h.asset_category = %(asset_category)s")
		values["asset_category"] = filters.get("asset_category")

	if filters.get("asset"):
		conditions.append("h.asset = %(asset)s")
		values["asset"] = filters.get("asset")

	if filters.get("assignment_status"):
		conditions.append("h.assignment_status = %(assignment_status)s")
		values["assignment_status"] = filters.get("assignment_status")

	if filters.get("from_date"):
		conditions.append("DATE(h.assignment_date) >= %(from_date)s")
		values["from_date"] = filters.get("from_date")

	if filters.get("to_date"):
		conditions.append("DATE(h.assignment_date) <= %(to_date)s")
		values["to_date"] = filters.get("to_date")

	if filters.get("department"):
		conditions.append("e.department = %(department)s")
		values["department"] = filters.get("department")

	if filters.get("company"):
		conditions.append("e.company = %(company)s")
		values["company"] = filters.get("company")

	if filters.get("asset_status"):
		conditions.append("COALESCE(a.custom_asset_status, 'In Stock') = %(asset_status)s")
		values["asset_status"] = filters.get("asset_status")

	where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

	sql = f"""
		SELECT
			h.name,
			h.asset,
			h.asset_name,
			h.asset_category,
			h.previous_custodian,
			h.previous_custodian_name,
			h.employee,
			h.employee_name,
			e.department,
			h.assignment_status,
			COALESCE(a.custom_asset_status, 'In Stock') as asset_status,
			h.assignment_date,
			h.return_date,
			h.asset_movement,
			h.assigned_by,
			h.returned_by,
			h.remarks
		FROM
			`tabAsset Assignment History` h
		LEFT JOIN
			`tabEmployee` e ON h.employee = e.name
		LEFT JOIN
			`tabAsset` a ON h.asset = a.name
		{where_clause}
		ORDER BY
			h.assignment_date DESC, h.creation DESC
	"""

	return frappe.db.sql(sql, values, as_dict=True)

def get_report_summary(data):
	if not data:
		return []

	total = len(data)
	assigned_count = sum(1 for d in data if d.get("assignment_status") == "Assigned")
	returned_count = sum(1 for d in data if d.get("assignment_status") == "Returned")
	unique_assets = len(set(d.get("asset") for d in data if d.get("asset")))
	unique_employees = len(set(d.get("employee") for d in data if d.get("employee")))

	return [
		{"value": total, "label": _("Total Transactions"), "datatype": "Int"},
		{"value": assigned_count, "label": _("Active Assignments"), "datatype": "Int", "indicator": "Blue"},
		{"value": returned_count, "label": _("Returns"), "datatype": "Int", "indicator": "Green"},
		{"value": unique_assets, "label": _("Unique Assets"), "datatype": "Int"},
		{"value": unique_employees, "label": _("Unique Employees"), "datatype": "Int"},
	]

def get_chart_data(data):
	if not data:
		return None

	status_counts = {}
	for row in data:
		st = row.get("assignment_status") or _("Assigned")
		status_counts[st] = status_counts.get(st, 0) + 1

	color_map = {
		"Assigned": "#1b84ff",
		"Returned": "#17c653",
		"Transferred": "#7239ea",
	}
	colors = [color_map.get(k, "#a1a5b7") for k in status_counts.keys()]

	return {
		"data": {
			"labels": list(status_counts.keys()),
			"datasets": [{"name": _("Count"), "values": list(status_counts.values())}],
		},
		"type": "donut",
		"colors": colors,
	}

