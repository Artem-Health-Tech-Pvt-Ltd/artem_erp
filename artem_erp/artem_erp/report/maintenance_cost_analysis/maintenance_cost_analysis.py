# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	group_by = filters.get("group_by") or "By Category"
	columns = get_columns(group_by)
	data = get_data(filters, group_by)
	chart = get_chart_data(data, group_by)
	report_summary = get_report_summary(data, group_by)
	return columns, data, None, chart, report_summary


def get_columns(group_by):
	if group_by == "By Category":
		return [
			{
				"label": _("Asset Category"),
				"fieldname": "asset_category",
				"fieldtype": "Link",
				"options": "Asset Category",
				"width": 170,
			},
			{
				"label": _("Total Assets"),
				"fieldname": "total_assets",
				"fieldtype": "Int",
				"width": 120,
			},
			{
				"label": _("Serviced Assets"),
				"fieldname": "serviced_assets",
				"fieldtype": "Int",
				"width": 130,
			},
			{
				"label": _("Assets In Repair"),
				"fieldname": "in_repair_assets",
				"fieldtype": "Int",
				"width": 130,
			},
			{
				"label": _("Total Service Records"),
				"fieldname": "total_records",
				"fieldtype": "Int",
				"width": 160,
			},
			{
				"label": _("Total Maintenance Cost"),
				"fieldname": "total_cost",
				"fieldtype": "Currency",
				"width": 180,
			},
			{
				"label": _("Average Cost Per Asset"),
				"fieldname": "avg_cost_per_asset",
				"fieldtype": "Currency",
				"width": 170,
			},
		]
	elif group_by == "By Month":
		return [
			{
				"label": _("Period (Year-Month)"),
				"fieldname": "period",
				"fieldtype": "Data",
				"width": 180,
			},
			{
				"label": _("Maintenance Records"),
				"fieldname": "record_count",
				"fieldtype": "Int",
				"width": 160,
			},
			{
				"label": _("Assets Serviced"),
				"fieldname": "asset_count",
				"fieldtype": "Int",
				"width": 140,
			},
			{
				"label": _("Total Cost"),
				"fieldname": "total_cost",
				"fieldtype": "Currency",
				"width": 180,
			},
		]
	elif group_by == "By Year":
		return [
			{
				"label": _("Year"),
				"fieldname": "period",
				"fieldtype": "Data",
				"width": 140,
			},
			{
				"label": _("Maintenance Records"),
				"fieldname": "record_count",
				"fieldtype": "Int",
				"width": 160,
			},
			{
				"label": _("Assets Serviced"),
				"fieldname": "asset_count",
				"fieldtype": "Int",
				"width": 140,
			},
			{
				"label": _("Total Cost"),
				"fieldname": "total_cost",
				"fieldtype": "Currency",
				"width": 180,
			},
		]
	else:  # "By Asset"
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
				"label": _("Status"),
				"fieldname": "custom_asset_status",
				"fieldtype": "Data",
				"width": 110,
			},
			{
				"label": _("Net Purchase Amount"),
				"fieldname": "net_purchase_amount",
				"fieldtype": "Currency",
				"width": 160,
			},
			{
				"label": _("Maintenance Records"),
				"fieldname": "custom_maintenance_count",
				"fieldtype": "Int",
				"width": 150,
			},
			{
				"label": _("Total Maintenance Cost"),
				"fieldname": "custom_total_maintenance_cost",
				"fieldtype": "Currency",
				"width": 180,
			},
			{
				"label": _("Maint. Cost as % of Asset Value"),
				"fieldname": "cost_ratio_pct",
				"fieldtype": "Percent",
				"width": 200,
			},
		]


def get_data(filters, group_by):
	if group_by == "By Category":
		return get_category_data(filters)
	elif group_by == "By Month":
		return get_period_data(filters, period_format="%Y-%m")
	elif group_by == "By Year":
		return get_period_data(filters, period_format="%Y")
	else:
		return get_asset_data(filters)


def get_category_data(filters):
	category_filter = ""
	values = {}
	if filters.get("asset_category"):
		category_filter = "AND a.asset_category = %(asset_category)s"
		values["asset_category"] = filters["asset_category"]

	sql = f"""
		SELECT
			a.asset_category,
			COUNT(DISTINCT a.name) AS total_assets,
			COUNT(DISTINCT CASE WHEN COALESCE(a.custom_maintenance_count, 0) > 0 THEN a.name END) AS serviced_assets,
			COUNT(DISTINCT CASE WHEN COALESCE(a.custom_asset_status, a.status) = 'In Repair' THEN a.name END) AS in_repair_assets,
			COALESCE(SUM(mr.cost_sum), 0) AS total_cost,
			COALESCE(SUM(mr.rec_count), 0) AS total_records
		FROM
			`tabAsset` a
		LEFT JOIN (
			SELECT
				parent,
				COUNT(name) AS rec_count,
				SUM(cost) AS cost_sum
			FROM
				`tabAsset Maintenance Record`
			GROUP BY
				parent
		) mr ON mr.parent = a.name
		WHERE
			a.docstatus != 2
			{category_filter}
		GROUP BY
			a.asset_category
		ORDER BY
			total_cost DESC, total_assets DESC
	"""

	raw_data = frappe.db.sql(sql, values, as_dict=1)
	for row in raw_data:
		total_a = row.get("total_assets") or 0
		tot_cost = float(row.get("total_cost") or 0.0)
		row["avg_cost_per_asset"] = round(tot_cost / total_a, 2) if total_a > 0 else 0.0

	return raw_data


def get_period_data(filters, period_format):
	conditions = []
	values = {}

	if filters.get("asset_category"):
		conditions.append("a.asset_category = %(asset_category)s")
		values["asset_category"] = filters["asset_category"]

	if filters.get("from_date"):
		conditions.append("mr.maintenance_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]

	if filters.get("to_date"):
		conditions.append("mr.maintenance_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

	sql = f"""
		SELECT
			DATE_FORMAT(mr.maintenance_date, '{period_format}') AS period,
			COUNT(mr.name) AS record_count,
			COUNT(DISTINCT a.name) AS asset_count,
			COALESCE(SUM(mr.cost), 0.0) AS total_cost
		FROM
			`tabAsset Maintenance Record` mr
		INNER JOIN
			`tabAsset` a ON mr.parent = a.name
		{where_clause}
		GROUP BY
			period
		ORDER BY
			period DESC
	"""

	return frappe.db.sql(sql, values, as_dict=1)


def get_asset_data(filters):
	conditions = ["a.docstatus != 2"]
	values = {}

	if filters.get("asset_category"):
		conditions.append("a.asset_category = %(asset_category)s")
		values["asset_category"] = filters["asset_category"]

	if filters.get("status"):
		conditions.append("COALESCE(a.custom_asset_status, a.status) = %(status)s")
		values["status"] = filters["status"]

	where_clause = f"WHERE {' AND '.join(conditions)}"

	sql = f"""
		SELECT
			a.name,
			a.asset_name,
			a.asset_category,
			COALESCE(a.custom_asset_status, a.status) AS custom_asset_status,
			COALESCE(a.net_purchase_amount, 0.0) AS net_purchase_amount,
			COALESCE(a.custom_maintenance_count, 0) AS custom_maintenance_count,
			COALESCE(a.custom_total_maintenance_cost, 0.0) AS custom_total_maintenance_cost
		FROM
			`tabAsset` a
		{where_clause}
		ORDER BY
			a.custom_total_maintenance_cost DESC,
			a.custom_maintenance_count DESC
	"""

	raw_data = frappe.db.sql(sql, values, as_dict=1)
	for row in raw_data:
		npa = float(row.get("net_purchase_amount") or 0.0)
		mc = float(row.get("custom_total_maintenance_cost") or 0.0)
		row["cost_ratio_pct"] = round((mc / npa) * 100, 2) if npa > 0 else 0.0

	return raw_data


def get_chart_data(data, group_by):
	if not data:
		return None

	if group_by == "By Category":
		labels = [r.get("asset_category") or _("Unknown") for r in data]
		values = [round(float(r.get("total_cost") or 0.0), 2) for r in data]
		return {
			"data": {
				"labels": labels,
				"datasets": [{"name": _("Total Cost"), "values": values}],
			},
			"type": "bar",
			"colors": ["#4f46e5"],
		}
	elif group_by in ("By Month", "By Year"):
		# Chronological order for time series chart
		chrono = list(reversed(data))
		labels = [r.get("period") for r in chrono]
		values = [round(float(r.get("total_cost") or 0.0), 2) for r in chrono]
		return {
			"data": {
				"labels": labels,
				"datasets": [{"name": _("Expenditure"), "values": values}],
			},
			"type": "line",
			"colors": ["#10b981"],
		}
	else:
		# Top 10 highest cost assets
		top_assets = data[:10]
		labels = [f"{r.get('name')}: {r.get('asset_name')}" for r in top_assets]
		values = [round(float(r.get("custom_total_maintenance_cost") or 0.0), 2) for r in top_assets]
		return {
			"data": {
				"labels": labels,
				"datasets": [{"name": _("Maintenance Cost"), "values": values}],
			},
			"type": "bar",
			"colors": ["#f59e0b"],
		}


def get_report_summary(data, group_by):
	if not data:
		return []

	if group_by == "By Category":
		total_cost = sum(float(r.get("total_cost") or 0.0) for r in data)
		total_records = sum(int(r.get("total_records") or 0) for r in data)
		total_assets = sum(int(r.get("total_assets") or 0) for r in data)
		return [
			{"value": len(data), "label": _("Categories Analyzed"), "datatype": "Int"},
			{"value": total_assets, "label": _("Total Assets"), "datatype": "Int"},
			{"value": total_records, "label": _("Total Maintenance Events"), "datatype": "Int"},
			{"value": total_cost, "label": _("Total Expenditure"), "datatype": "Currency"},
		]
	elif group_by in ("By Month", "By Year"):
		total_cost = sum(float(r.get("total_cost") or 0.0) for r in data)
		total_records = sum(int(r.get("record_count") or 0) for r in data)
		return [
			{"value": len(data), "label": _("Periods Recorded"), "datatype": "Int"},
			{"value": total_records, "label": _("Total Records"), "datatype": "Int"},
			{"value": total_cost, "label": _("Total Expenditure"), "datatype": "Currency"},
		]
	else:
		total_cost = sum(float(r.get("custom_total_maintenance_cost") or 0.0) for r in data)
		with_maint = sum(1 for r in data if (r.get("custom_maintenance_count") or 0) > 0)
		return [
			{"value": len(data), "label": _("Total Assets"), "datatype": "Int"},
			{"value": with_maint, "label": _("Assets With Maintenance"), "datatype": "Int"},
			{"value": total_cost, "label": _("Total Expenditure"), "datatype": "Currency"},
		]
