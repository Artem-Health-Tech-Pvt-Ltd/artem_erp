# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist()
def get_maintenance_dashboard_data():
	"""Whitelisted API returning all core KPIs and chart datasets for the
	Asset Maintenance Dashboard."""
	return {
		"kpis": get_kpis(),
		"by_category": get_by_category(),
		"by_type": get_by_type(),
		"monthly_cost": get_monthly_cost(),
		"repair_status": get_repair_status(),
		"top_expensive_assets": get_top_expensive_assets(),
	}


def get_kpis():
	total_assets = frappe.db.count("Asset", {"docstatus": ["!=", 2]})
	in_repair = frappe.db.count("Asset", {"custom_asset_status": "In Repair", "docstatus": ["!=", 2]})
	never_maintained = frappe.db.count(
		"Asset",
		{"custom_maintenance_count": 0, "docstatus": ["!=", 2]},
	)
	serviced_assets = total_assets - never_maintained

	maint_summary = frappe.db.sql(
		"""
		SELECT
			COUNT(name) AS total_records,
			COALESCE(SUM(cost), 0.0) AS total_cost
		FROM
			`tabAsset Maintenance Record`
		""",
		as_dict=1,
	)[0]

	return {
		"total_assets": total_assets,
		"in_repair": in_repair,
		"serviced_assets": serviced_assets,
		"never_maintained": never_maintained,
		"total_records": maint_summary.total_records or 0,
		"total_expenditure": round(float(maint_summary.total_cost or 0.0), 2),
	}


def get_by_category():
	return frappe.db.sql(
		"""
		SELECT
			a.asset_category,
			COUNT(DISTINCT a.name) AS total_assets,
			COUNT(DISTINCT CASE WHEN COALESCE(a.custom_asset_status, a.status) = 'In Repair' THEN a.name END) AS in_repair,
			COUNT(mr.name) AS maintenance_count,
			COALESCE(SUM(mr.cost), 0.0) AS total_cost
		FROM
			`tabAsset` a
		LEFT JOIN
			`tabAsset Maintenance Record` mr ON mr.parent = a.name
		WHERE
			a.docstatus != 2
		GROUP BY
			a.asset_category
		ORDER BY
			total_cost DESC, maintenance_count DESC
		""",
		as_dict=1,
	)


def get_by_type():
	return frappe.db.sql(
		"""
		SELECT
			COALESCE(maintenance_type, 'Other') AS maintenance_type,
			COUNT(name) AS count,
			COALESCE(SUM(cost), 0.0) AS total_cost
		FROM
			`tabAsset Maintenance Record`
		GROUP BY
			maintenance_type
		ORDER BY
			total_cost DESC
		""",
		as_dict=1,
	)


def get_monthly_cost():
	return frappe.db.sql(
		"""
		SELECT
			DATE_FORMAT(maintenance_date, '%Y-%m') AS period,
			COUNT(name) AS count,
			COALESCE(SUM(cost), 0.0) AS total_cost
		FROM
			`tabAsset Maintenance Record`
		GROUP BY
			period
		ORDER BY
			period ASC
		LIMIT 12
		""",
		as_dict=1,
	)


def get_repair_status():
	return frappe.db.sql(
		"""
		SELECT
			COALESCE(custom_asset_status, status) AS status,
			COUNT(name) AS count
		FROM
			`tabAsset`
		WHERE
			docstatus != 2
		GROUP BY
			status
		ORDER BY
			count DESC
		""",
		as_dict=1,
	)


def get_top_expensive_assets(limit=10):
	return frappe.db.sql(
		"""
		SELECT
			a.name AS asset,
			a.asset_name,
			a.asset_category,
			COALESCE(a.custom_asset_status, a.status) AS status,
			a.custodian,
			a.custom_employee_name,
			COALESCE(a.custom_maintenance_count, 0) AS maintenance_count,
			COALESCE(a.custom_total_maintenance_cost, 0.0) AS total_cost
		FROM
			`tabAsset` a
		WHERE
			a.docstatus != 2 AND COALESCE(a.custom_total_maintenance_cost, 0) > 0
		ORDER BY
			a.custom_total_maintenance_cost DESC
		LIMIT %s
		""",
		(limit,),
		as_dict=1,
	)
