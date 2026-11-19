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
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Asset",
			"width": 140,
		},
		{
			"label": _("Asset Name"),
			"fieldname": "asset_name",
			"fieldtype": "Data",
			"width": 170,
		},
		{
			"label": _("Category"),
			"fieldname": "asset_category",
			"fieldtype": "Link",
			"options": "Asset Category",
			"width": 130,
		},
		{
			"label": _("Current Status"),
			"fieldname": "custom_asset_status",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Custodian"),
			"fieldname": "custodian",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 130,
		},
		{
			"label": _("Employee Name"),
			"fieldname": "custom_employee_name",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Total Maintenance Count"),
			"fieldname": "custom_maintenance_count",
			"fieldtype": "Int",
			"width": 160,
		},
		{
			"label": _("Total Maintenance Cost"),
			"fieldname": "custom_total_maintenance_cost",
			"fieldtype": "Currency",
			"width": 160,
		},
		{
			"label": _("Last Maintenance Date"),
			"fieldname": "last_maintenance_date",
			"fieldtype": "Date",
			"width": 140,
		},
		{
			"label": _("Last Service Type"),
			"fieldname": "last_maintenance_type",
			"fieldtype": "Data",
			"width": 150,
		},
	]


def get_data(filters):
	conditions = ["a.docstatus != 2"]
	values = {}

	if filters.get("asset_category"):
		conditions.append("a.asset_category = %(asset_category)s")
		values["asset_category"] = filters["asset_category"]

	if filters.get("status"):
		conditions.append("COALESCE(a.custom_asset_status, a.status) = %(status)s")
		values["status"] = filters["status"]

	if filters.get("custodian"):
		conditions.append("a.custodian = %(custodian)s")
		values["custodian"] = filters["custodian"]

	has_maint = filters.get("has_maintenance")
	if has_maint == "With Maintenance":
		conditions.append("COALESCE(a.custom_maintenance_count, 0) > 0")
	elif has_maint == "Never Maintained":
		conditions.append("COALESCE(a.custom_maintenance_count, 0) = 0")

	where_clause = f"WHERE {' AND '.join(conditions)}"

	sql = f"""
		SELECT
			a.name,
			a.asset_name,
			a.asset_category,
			COALESCE(a.custom_asset_status, a.status) AS custom_asset_status,
			a.custodian,
			a.custom_employee_name,
			COALESCE(a.custom_maintenance_count, 0) AS custom_maintenance_count,
			COALESCE(a.custom_total_maintenance_cost, 0.0) AS custom_total_maintenance_cost,
			last_rec.maintenance_date AS last_maintenance_date,
			last_rec.maintenance_type AS last_maintenance_type
		FROM
			`tabAsset` a
		LEFT JOIN (
			SELECT
				parent,
				maintenance_date,
				maintenance_type
			FROM
				`tabAsset Maintenance Record`
			WHERE
				(parent, maintenance_date) IN (
					SELECT parent, MAX(maintenance_date)
					FROM `tabAsset Maintenance Record`
					GROUP BY parent
				)
		) last_rec ON last_rec.parent = a.name
		{where_clause}
		ORDER BY
			CASE WHEN COALESCE(a.custom_asset_status, a.status) = 'In Repair' THEN 0 ELSE 1 END,
			a.custom_total_maintenance_cost DESC,
			a.name ASC
	"""

	return frappe.db.sql(sql, values, as_dict=1)


def get_chart_data(data):
	if not data:
		return None

	status_counts = {}
	for row in data:
		st = row.get("custom_asset_status") or "In Stock"
		status_counts[st] = status_counts.get(st, 0) + 1

	labels = list(status_counts.keys())
	values = [status_counts[k] for k in labels]

	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": _("Assets"), "values": values}],
		},
		"type": "percentage",
		"colors": ["#10b981", "#3b82f6", "#ef4444", "#f59e0b"],
	}


def get_report_summary(data):
	if not data:
		return []

	total_assets = len(data)
	in_repair = sum(1 for r in data if r.get("custom_asset_status") == "In Repair")
	undergone_maint = sum(1 for r in data if (r.get("custom_maintenance_count") or 0) > 0)
	never_maintained = total_assets - undergone_maint
	total_cost = sum(float(r.get("custom_total_maintenance_cost") or 0.0) for r in data)

	return [
		{
			"value": total_assets,
			"label": _("Total Assets"),
			"datatype": "Int",
		},
		{
			"value": in_repair,
			"label": _("Assets In Repair"),
			"indicator": "Red" if in_repair > 0 else "Green",
			"datatype": "Int",
		},
		{
			"value": undergone_maint,
			"label": _("Assets Maintained"),
			"datatype": "Int",
		},
		{
			"value": never_maintained,
			"label": _("Never Maintained"),
			"datatype": "Int",
		},
		{
			"value": total_cost,
			"label": _("Total Maintenance Cost"),
			"datatype": "Currency",
		},
	]

