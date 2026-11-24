# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist()
def get_dashboard_data(filters=None):
	"""Returns aggregated data for the Asset Management Dashboard."""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = filters or {}

	conditions = ["docstatus < 2"]
	values = {}

	if filters.get("asset_category"):
		conditions.append("asset_category = %(asset_category)s")
		values["asset_category"] = filters.get("asset_category")

	if filters.get("status"):
		conditions.append("COALESCE(custom_asset_status, 'In Stock') = %(status)s")
		values["status"] = filters.get("status")

	if filters.get("company"):
		conditions.append("company = %(company)s")
		values["company"] = filters.get("company")

	if filters.get("location"):
		conditions.append("location = %(location)s")
		values["location"] = filters.get("location")

	where_clause = " WHERE " + " AND ".join(conditions)

	# 1. Summary Metrics
	summary_sql = f"""
		SELECT
			COUNT(*) as total_assets,
			SUM(CASE WHEN COALESCE(custom_asset_status, 'In Stock') = 'In Stock' THEN 1 ELSE 0 END) as in_stock,
			SUM(CASE WHEN custom_asset_status = 'Assigned' THEN 1 ELSE 0 END) as assigned,
			SUM(CASE WHEN custom_asset_status = 'In Repair' THEN 1 ELSE 0 END) as in_repair,
			COUNT(DISTINCT asset_category) as total_categories,
			COUNT(DISTINCT CASE WHEN custodian IS NOT NULL AND custodian != '' THEN custodian END) as employees_with_assets
		FROM
			`tabAsset`
		{where_clause}
	"""
	metrics = frappe.db.sql(summary_sql, values, as_dict=True)[0]
	total_assets = metrics.total_assets or 0
	in_stock = metrics.in_stock or 0
	assigned = metrics.assigned or 0
	in_repair = metrics.in_repair or 0
	availability_pct = round((in_stock / total_assets * 100), 1) if total_assets > 0 else 0

	# 2. Category-wise Breakdown Table
	cat_sql = f"""
		SELECT
			COALESCE(asset_category, 'Uncategorized') as category,
			COUNT(*) as total,
			SUM(CASE WHEN COALESCE(custom_asset_status, 'In Stock') = 'In Stock' THEN 1 ELSE 0 END) as in_stock,
			SUM(CASE WHEN custom_asset_status = 'Assigned' THEN 1 ELSE 0 END) as assigned,
			SUM(CASE WHEN custom_asset_status = 'In Repair' THEN 1 ELSE 0 END) as in_repair
		FROM
			`tabAsset`
		{where_clause}
		GROUP BY
			asset_category
		ORDER BY
			total DESC
	"""
	category_data = frappe.db.sql(cat_sql, values, as_dict=True)

	for cat in category_data:
		cat_total = cat.total or 0
		cat_stock = cat.in_stock or 0
		cat["availability_pct"] = round((cat_stock / cat_total * 100), 1) if cat_total > 0 else 0

	# 3. Chart 1: Category-wise Total Assets (Bar chart)
	top_categories = category_data[:10]
	chart_category_labels = [c.category for c in top_categories]
	chart_category_values = [c.total for c in top_categories]

	# 4. Chart 2: Status Distribution (Donut chart)
	status_chart = {
		"labels": [_("In Stock"), _("Assigned"), _("In Repair")],
		"datasets": [{"values": [in_stock, assigned, in_repair]}],
		"colors": ["#17c653", "#1b84ff", "#f6c000"],
	}

	# 5. Chart 3: Category vs Status (Stacked Bar)
	stacked_categories = [c.category for c in top_categories]
	stacked_in_stock = [c.in_stock for c in top_categories]
	stacked_assigned = [c.assigned for c in top_categories]
	stacked_in_repair = [c.in_repair for c in top_categories]

	category_vs_status_chart = {
		"labels": stacked_categories,
		"datasets": [
			{"name": _("In Stock"), "values": stacked_in_stock},
			{"name": _("Assigned"), "values": stacked_assigned},
			{"name": _("In Repair"), "values": stacked_in_repair},
		],
		"colors": ["#17c653", "#1b84ff", "#f6c000"],
	}

	# 6. Chart 4: Availability Donut
	availability_chart = {
		"labels": [_("Available (In Stock)"), _("Utilized / In Repair")],
		"datasets": [{"values": [in_stock, (total_assets - in_stock)]}],
		"colors": ["#17c653", "#7239ea"],
	}

	# 7. Recent Assignment Activities
	recent_assignments = frappe.db.sql(
		"""
		SELECT
			name, asset, asset_name, asset_category, employee, employee_name,
			assignment_status, assignment_date, return_date
		FROM
			`tabAsset Assignment History`
		ORDER BY
			assignment_date DESC, creation DESC
		LIMIT 8
		""",
		as_dict=True,
	)

	return {
		"cards": {
			"total_assets": total_assets,
			"in_stock": in_stock,
			"assigned": assigned,
			"in_repair": in_repair,
			"total_categories": metrics.total_categories or 0,
			"employees_with_assets": metrics.employees_with_assets or 0,
			"availability_pct": availability_pct,
		},
		"category_table": category_data,
		"charts": {
			"category_distribution": {
				"labels": chart_category_labels,
				"datasets": [{"name": _("Total Assets"), "values": chart_category_values}],
				"colors": ["#3e97ff"],
			},
			"status_distribution": status_chart,
			"category_vs_status": category_vs_status_chart,
			"availability": availability_chart,
		},
		"recent_assignments": recent_assignments,
	}
