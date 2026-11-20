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
			"label": _("Asset Category"),
			"fieldname": "asset_category",
			"fieldtype": "Link",
			"options": "Asset Category",
			"width": 130,
		},
		{
			"label": _("Status"),
			"fieldname": "custom_asset_status",
			"fieldtype": "Data",
			"width": 110,
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
		{
			"label": _("Maintenance Remarks / Description"),
			"fieldname": "last_description",
			"fieldtype": "Small Text",
			"width": 260,
		},
		{
			"label": _("Total Maintenance Cost"),
			"fieldname": "custom_total_maintenance_cost",
			"fieldtype": "Currency",
			"width": 160,
		},
	]


def get_data(filters):
	conditions = [
		"a.docstatus != 2",
		"COALESCE(a.custom_asset_status, a.status) = 'In Repair'"
		if not filters.get("status")
		else "COALESCE(a.custom_asset_status, a.status) = %(status)s",
	]
	values = {}

	if filters.get("status"):
		values["status"] = filters["status"]

	if filters.get("asset_category"):
		conditions.append("a.asset_category = %(asset_category)s")
		values["asset_category"] = filters["asset_category"]

	if filters.get("custodian"):
		conditions.append("a.custodian = %(custodian)s")
		values["custodian"] = filters["custodian"]

	where_clause = f"WHERE {' AND '.join(conditions)}"

	sql = f"""
		SELECT
			a.name,
			a.asset_name,
			a.asset_category,
			COALESCE(a.custom_asset_status, a.status) AS custom_asset_status,
			a.custodian,
			a.custom_employee_name,
			COALESCE(a.custom_total_maintenance_cost, 0.0) AS custom_total_maintenance_cost,
			last_rec.maintenance_date AS last_maintenance_date,
			last_rec.maintenance_type AS last_maintenance_type,
			last_rec.description AS last_description
		FROM
			`tabAsset` a
		LEFT JOIN (
			SELECT
				parent,
				maintenance_date,
				maintenance_type,
				description
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
			last_rec.maintenance_date DESC,
			a.name ASC
	"""

	return frappe.db.sql(sql, values, as_dict=1)


def get_chart_data(data):
	if not data:
		return None

	cat_counts = {}
	for row in data:
		cat = row.get("asset_category") or "Unknown"
		cat_counts[cat] = cat_counts.get(cat, 0) + 1

	labels = list(cat_counts.keys())
	values = [cat_counts[k] for k in labels]

	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": _("In Repair"), "values": values}],
		},
		"type": "bar",
		"colors": ["#ef4444"],
	}


def get_report_summary(data):
	if not data:
		return []

	total_in_repair = len(data)
	total_cost = sum(float(r.get("custom_total_maintenance_cost") or 0.0) for r in data)
	categories = len({r.get("asset_category") for r in data if r.get("asset_category")})

	return [
		{
			"value": total_in_repair,
			"label": _("Assets Currently In Repair"),
			"indicator": "Red" if total_in_repair > 0 else "Green",
			"datatype": "Int",
		},
		{
			"value": categories,
			"label": _("Affected Categories"),
			"datatype": "Int",
		},
		{
			"value": total_cost,
			"label": _("Cumulative Maintenance Cost"),
			"datatype": "Currency",
		},
	]
