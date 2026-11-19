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
			"label": _("Asset Category"),
			"fieldname": "asset_category",
			"fieldtype": "Link",
			"options": "Asset Category",
			"width": 130,
		},
		{
			"label": _("Maintenance Date"),
			"fieldname": "maintenance_date",
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"label": _("Maintenance Type"),
			"fieldname": "maintenance_type",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("Description / Repair Details"),
			"fieldname": "description",
			"fieldtype": "Small Text",
			"width": 260,
		},
		{
			"label": _("Cost"),
			"fieldname": "cost",
			"fieldtype": "Currency",
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
			"width": 150,
		},
		{
			"label": _("Current Status"),
			"fieldname": "custom_asset_status",
			"fieldtype": "Data",
			"width": 110,
		},
	]


def get_data(filters):
	conditions = []
	values = {}

	if filters.get("asset"):
		conditions.append("a.name = %(asset)s")
		values["asset"] = filters["asset"]

	if filters.get("asset_category"):
		conditions.append("a.asset_category = %(asset_category)s")
		values["asset_category"] = filters["asset_category"]

	if filters.get("maintenance_type"):
		conditions.append("mr.maintenance_type = %(maintenance_type)s")
		values["maintenance_type"] = filters["maintenance_type"]

	if filters.get("custodian"):
		conditions.append("a.custodian = %(custodian)s")
		values["custodian"] = filters["custodian"]

	if filters.get("from_date"):
		conditions.append("mr.maintenance_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("mr.maintenance_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

	sql = f"""
		SELECT
			a.name AS asset,
			a.asset_name,
			a.asset_category,
			mr.maintenance_date,
			mr.maintenance_type,
			mr.description,
			mr.cost,
			a.custodian,
			a.custom_employee_name,
			COALESCE(a.custom_asset_status, a.status) AS custom_asset_status
		FROM
			`tabAsset Maintenance Record` mr
		INNER JOIN
			`tabAsset` a ON mr.parent = a.name
		{where_clause}
		ORDER BY
			mr.maintenance_date DESC, mr.creation DESC
	"""

	return frappe.db.sql(sql, values, as_dict=1)


def get_chart_data(data):
	if not data:
		return None

	type_costs = {}
	for row in data:
		m_type = row.get("maintenance_type") or "Other"
		cost = row.get("cost") or 0.0
		type_costs[m_type] = type_costs.get(m_type, 0.0) + float(cost)

	labels = list(type_costs.keys())
	values = [round(type_costs[k], 2) for k in labels]

	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": _("Cost"), "values": values}],
		},
		"type": "donut",
		"colors": ["#4f46e5", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"],
	}


def get_report_summary(data):
	if not data:
		return []

	total_cost = sum(float(r.get("cost") or 0.0) for r in data)
	total_records = len(data)
	unique_assets = len({r.get("asset") for r in data if r.get("asset")})

	return [
		{
			"value": total_records,
			"label": _("Total Maintenance Records"),
			"datatype": "Int",
		},
		{
			"value": unique_assets,
			"label": _("Distinct Assets Serviced"),
			"datatype": "Int",
		},
		{
			"value": total_cost,
			"label": _("Total Expenditure"),
			"datatype": "Currency",
		},
	]

