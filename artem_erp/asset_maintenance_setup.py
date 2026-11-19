# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import json
import frappe


def setup_asset_maintenance_suite():
	"""Sets up Reports, Number Cards, Dashboard Charts, Dashboard, and the Asset Maintenance
	Management Workspace."""
	reload_reports()
	setup_number_cards()
	setup_dashboard_charts()
	setup_dashboard()
	setup_maintenance_workspace()
	setup_asset_management_workspace()
	isolate_standard_erpnext_maintenance()
	sync_assets_workspace_sidebar()


def reload_reports():
	"""Ensure custom reports are loaded into database metadata."""
	reports = [
		"maintenance_history_report",
		"maintenance_status_report",
		"maintenance_cost_analysis",
		"asset_repair_tracking",
		"employee_wise_asset_allocation_report",
	]
	for r in reports:
		try:
			frappe.reload_doc("artem_erp", "report", r, force=True)
		except Exception:
			pass


def setup_number_cards():
	"""Creates standard Number Cards for maintenance KPIs."""
	cards = [
		{
			"name": "Assets In Stock",
			"label": "Assets In Stock",
			"document_type": "Asset",
			"function": "Count",
			"filters_json": json.dumps([["Asset", "custom_asset_status", "=", "In Stock"], ["Asset", "docstatus", "!=", 2]]),
			"color": "#10b981",
		},
		{
			"name": "Assets Assigned",
			"label": "Assets Assigned",
			"document_type": "Asset",
			"function": "Count",
			"filters_json": json.dumps([["Asset", "custom_asset_status", "=", "Assigned"], ["Asset", "docstatus", "!=", 2]]),
			"color": "#3b82f6",
		},
		{
			"name": "Assets In Repair",
			"label": "Assets In Repair",
			"document_type": "Asset",
			"function": "Count",
			"filters_json": json.dumps([["Asset", "custom_asset_status", "=", "In Repair"], ["Asset", "docstatus", "!=", 2]]),
			"color": "#ef4444",
		},
		{
			"name": "Total Maintenance Records",
			"label": "Total Maintenance Records",
			"document_type": "Asset Maintenance Record",
			"parent_document_type": "Asset",
			"function": "Count",
			"filters_json": json.dumps([]),
			"color": "#3b82f6",
		},
		{
			"name": "Total Maintenance Expenditure",
			"label": "Total Maintenance Expenditure",
			"document_type": "Asset Maintenance Record",
			"parent_document_type": "Asset",
			"function": "Sum",
			"aggregate_function_based_on": "cost",
			"filters_json": json.dumps([]),
			"color": "#10b981",
		},
		{
			"name": "Never Maintained Assets",
			"label": "Never Maintained Assets",
			"document_type": "Asset",
			"function": "Count",
			"filters_json": json.dumps([["Asset", "custom_maintenance_count", "=", 0], ["Asset", "docstatus", "!=", 2]]),
			"color": "#6b7280",
		},
	]

	for card_data in cards:
		name = card_data["name"]
		if frappe.db.exists("Number Card", name):
			doc = frappe.get_doc("Number Card", name)
			doc.update(card_data)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.new_doc("Number Card")
			doc.update(card_data)
			doc.is_standard = 0
			doc.module = "Artem ERP"
			doc.insert(ignore_permissions=True)


def setup_dashboard_charts():
	"""Creates Dashboard Charts for category, type, monthly cost, and repair status."""
	charts = [
		{
			"name": "Asset Maintenance by Category",
			"chart_name": "Asset Maintenance by Category",
			"chart_type": "Group By",
			"document_type": "Asset",
			"group_by_based_on": "asset_category",
			"aggregate_function_based_on": "custom_total_maintenance_cost",
			"group_by_type": "Sum",
			"type": "Bar",
			"filters_json": json.dumps([["Asset", "docstatus", "!=", 2]]),
			"color": "#4f46e5",
		},
		{
			"name": "Asset Maintenance by Type",
			"chart_name": "Asset Maintenance by Type",
			"chart_type": "Group By",
			"document_type": "Asset Maintenance Record",
			"parent_document_type": "Asset",
			"group_by_based_on": "maintenance_type",
			"aggregate_function_based_on": "cost",
			"group_by_type": "Sum",
			"type": "Donut",
			"filters_json": json.dumps([]),
			"color": "#06b6d4",
		},
		{
			"name": "Asset Repair Status",
			"chart_name": "Asset Repair Status",
			"chart_type": "Group By",
			"document_type": "Asset",
			"group_by_based_on": "custom_asset_status",
			"group_by_type": "Count",
			"type": "Percentage",
			"filters_json": json.dumps([["Asset", "docstatus", "!=", 2]]),
			"color": "#f59e0b",
		},
	]

	for c in charts:
		name = c["name"]
		if frappe.db.exists("Dashboard Chart", name):
			doc = frappe.get_doc("Dashboard Chart", name)
			doc.update(c)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.new_doc("Dashboard Chart")
			doc.update(c)
			doc.is_standard = 0
			doc.module = "Artem ERP"
			doc.insert(ignore_permissions=True)


def setup_dashboard():
	"""Creates the central Asset Maintenance Dashboard."""
	dash_name = "Asset Maintenance Dashboard"
	chart_links = [
		{"chart": "Asset Maintenance by Category", "width": "Half"},
		{"chart": "Asset Maintenance by Type", "width": "Half"},
		{"chart": "Asset Repair Status", "width": "Half"},
	]
	card_links = [
		{"card": "Assets In Repair"},
		{"card": "Total Maintenance Records"},
		{"card": "Total Maintenance Expenditure"},
		{"card": "Never Maintained Assets"},
	]

	if frappe.db.exists("Dashboard", dash_name):
		dash = frappe.get_doc("Dashboard", dash_name)
	else:
		dash = frappe.new_doc("Dashboard")
		dash.dashboard_name = dash_name
		dash.module = "Artem ERP"
		dash.is_standard = 0

	dash.set("charts", [])
	dash.set("cards", [])

	for cl in chart_links:
		dash.append("charts", cl)

	for cdl in card_links:
		dash.append("cards", cdl)

	dash.save(ignore_permissions=True)


def setup_maintenance_workspace():
	"""Creates or updates the dedicated 'Asset Maintenance Management' Workspace."""
	ws_name = "Asset Maintenance Management"

	content_blocks = [
		{"id": "hdr_kpi", "type": "header", "data": {"text": "<span class=\"h4\"><b>Maintenance Overview &amp; KPIs</b></span>", "col": 12}},
		{"id": "nc_in_repair", "type": "number_card", "data": {"number_card_name": "Assets In Repair", "col": 3}},
		{"id": "nc_tot_records", "type": "number_card", "data": {"number_card_name": "Total Maintenance Records", "col": 3}},
		{"id": "nc_tot_cost", "type": "number_card", "data": {"number_card_name": "Total Maintenance Expenditure", "col": 3}},
		{"id": "nc_never_maint", "type": "number_card", "data": {"number_card_name": "Never Maintained Assets", "col": 3}},
		{"id": "spc_1", "type": "spacer", "data": {"col": 12}},
		{"id": "hdr_reports", "type": "header", "data": {"text": "<span class=\"h4\"><b>Maintenance Analytics &amp; Reports</b></span>", "col": 12}},
		{"id": "card_reports", "type": "card", "data": {"card_name": "Reports & Analytics", "col": 6}},
		{"id": "card_quick_links", "type": "card", "data": {"card_name": "Quick Operations", "col": 6}},
		{"id": "spc_2", "type": "spacer", "data": {"col": 12}},
		{"id": "hdr_charts", "type": "header", "data": {"text": "<span class=\"h4\"><b>Visual Analytics</b></span>", "col": 12}},
		{"id": "ch_by_category", "type": "chart", "data": {"chart_name": "Asset Maintenance by Category", "col": 6}},
		{"id": "ch_by_type", "type": "chart", "data": {"chart_name": "Asset Maintenance by Type", "col": 6}},
	]

	links = [
		# Card 1: Reports & Analytics
		{"label": "Reports & Analytics", "type": "Card Break"},
		{"label": "Maintenance History Report", "type": "Link", "link_type": "Report", "link_to": "Maintenance History Report", "onboard": 1},
		{"label": "Maintenance Status Report", "type": "Link", "link_type": "Report", "link_to": "Maintenance Status Report", "onboard": 1},
		{"label": "Maintenance Cost Analysis", "type": "Link", "link_type": "Report", "link_to": "Maintenance Cost Analysis", "onboard": 1},
		{"label": "Asset Repair Tracking", "type": "Link", "link_type": "Report", "link_to": "Asset Repair Tracking", "onboard": 1},
		# Card 2: Quick Operations
		{"label": "Quick Operations", "type": "Card Break"},
		{"label": "Assets Currently In Repair", "type": "Link", "link_type": "DocType", "link_to": "Asset", "dependencies": "Asset"},
		{"label": "All IT Assets", "type": "Link", "link_type": "DocType", "link_to": "Asset"},
		{"label": "Maintenance Logs", "type": "Link", "link_type": "DocType", "link_to": "Asset Maintenance Log"},
		{"label": "Asset Repairs", "type": "Link", "link_type": "DocType", "link_to": "Asset Repair"},
		{"label": "Asset Categories", "type": "Link", "link_type": "DocType", "link_to": "Asset Category"},
	]

	shortcuts = [
		{
			"label": "Assets In Repair",
			"type": "DocType",
			"link_to": "Asset",
			"color": "Red",
			"doc_view": "List",
		},
		{
			"label": "Maintenance History",
			"type": "Report",
			"link_to": "Maintenance History Report",
			"color": "Blue",
		},
		{
			"label": "Cost Analysis",
			"type": "Report",
			"link_to": "Maintenance Cost Analysis",
			"color": "Green",
		},
		{
			"label": "Repair Tracking",
			"type": "Report",
			"link_to": "Asset Repair Tracking",
			"color": "Orange",
		},
	]

	if frappe.db.exists("Workspace", ws_name):
		ws = frappe.get_doc("Workspace", ws_name)
	else:
		ws = frappe.new_doc("Workspace")
		ws.name = ws_name
		ws.label = ws_name
		ws.title = ws_name
		ws.module = "Artem ERP"
		ws.icon = "tool"
		ws.is_standard = 0
		ws.public = 1

	ws.content = json.dumps(content_blocks)
	ws.set("links", [])
	ws.set("shortcuts", [])
	ws.set("roles", [])

	for l in links:
		ws.append("links", l)
	for s in shortcuts:
		ws.append("shortcuts", s)

	valid_roles = []
	for r in ["Asset Manager", "System Manager"]:
		if frappe.db.exists("Role", r):
			valid_roles.append({"role": r})

	for r in valid_roles:
		ws.append("roles", r)

	ws.save(ignore_permissions=True)


def setup_asset_management_workspace():
	"""Creates or updates the dedicated 'Asset Management' Workspace."""
	ws_name = "Asset Management"

	content_blocks = [
		{"id": "hdr_kpi", "type": "header", "data": {"text": "<span class=\"h4\"><b>Asset Allocation &amp; Operations</b></span>", "col": 12}},
		{"id": "nc_in_stock", "type": "number_card", "data": {"number_card_name": "Assets In Stock", "col": 3}},
		{"id": "nc_assigned", "type": "number_card", "data": {"number_card_name": "Assets Assigned", "col": 3}},
		{"id": "nc_in_repair", "type": "number_card", "data": {"number_card_name": "Assets In Repair", "col": 3}},
		{"id": "nc_tot_cost", "type": "number_card", "data": {"number_card_name": "Total Maintenance Expenditure", "col": 3}},
		{"id": "spc_1", "type": "spacer", "data": {"col": 12}},
		{"id": "hdr_ops", "type": "header", "data": {"text": "<span class=\"h4\"><b>Allocation &amp; Inventory Management</b></span>", "col": 12}},
		{"id": "card_alloc", "type": "card", "data": {"card_name": "Asset Allocation & Assignment", "col": 6}},
		{"id": "card_inventory", "type": "card", "data": {"card_name": "Asset Master & Categories", "col": 6}},
		{"id": "spc_2", "type": "spacer", "data": {"col": 12}},
		{"id": "hdr_reports", "type": "header", "data": {"text": "<span class=\"h4\"><b>Asset &amp; Allocation Reports</b></span>", "col": 12}},
		{"id": "card_reports", "type": "card", "data": {"card_name": "Reports & Analytics", "col": 12}},
	]

	links = [
		# Card 1: Asset Allocation & Assignment
		{"label": "Asset Allocation & Assignment", "type": "Card Break"},
		{"label": "Employee Asset Allocation", "type": "Link", "link_type": "DocType", "link_to": "Employee Asset Allocation", "onboard": 1},
		{"label": "Asset Assignment History", "type": "Link", "link_type": "DocType", "link_to": "Asset Assignment History", "onboard": 1},
		{"label": "Asset Management Dashboard", "type": "Link", "link_type": "Page", "link_to": "asset_management_dashboard", "onboard": 1},
		# Card 2: Asset Master & Categories
		{"label": "Asset Master & Categories", "type": "Card Break"},
		{"label": "Assets", "type": "Link", "link_type": "DocType", "link_to": "Asset", "onboard": 1},
		{"label": "Asset Category", "type": "Link", "link_type": "DocType", "link_to": "Asset Category"},
		{"label": "Asset Repair", "type": "Link", "link_type": "DocType", "link_to": "Asset Repair"},
		{"label": "Employees", "type": "Link", "link_type": "DocType", "link_to": "Employee"},
		# Card 3: Reports & Analytics
		{"label": "Reports & Analytics", "type": "Card Break"},
		{"label": "Employee-wise Asset Allocation Report", "type": "Link", "link_type": "Report", "link_to": "Employee-wise Asset Allocation Report", "onboard": 1},
		{"label": "Maintenance Status Report", "type": "Link", "link_type": "Report", "link_to": "Maintenance Status Report"},
		{"label": "Maintenance History Report", "type": "Link", "link_type": "Report", "link_to": "Maintenance History Report"},
		{"label": "Maintenance Cost Analysis", "type": "Link", "link_type": "Report", "link_to": "Maintenance Cost Analysis"},
		{"label": "Asset Repair Tracking", "type": "Link", "link_type": "Report", "link_to": "Asset Repair Tracking"},
	]

	shortcuts = [
		{
			"label": "Asset Dashboard",
			"type": "Page",
			"link_to": "asset_management_dashboard",
			"color": "Blue",
		},
		{
			"label": "Employee Asset Allocation",
			"type": "DocType",
			"link_to": "Employee Asset Allocation",
			"color": "Green",
			"doc_view": "List",
		},
		{
			"label": "Assets In Stock",
			"type": "DocType",
			"link_to": "Asset",
			"color": "Green",
			"doc_view": "List",
		},
		{
			"label": "Assets In Repair",
			"type": "DocType",
			"link_to": "Asset",
			"color": "Red",
			"doc_view": "List",
		},
		{
			"label": "Assignment History",
			"type": "DocType",
			"link_to": "Asset Assignment History",
			"color": "Grey",
			"doc_view": "List",
		},
		{
			"label": "Allocation Report",
			"type": "Report",
			"link_to": "Employee-wise Asset Allocation Report",
			"color": "Orange",
		},
	]

	if frappe.db.exists("Workspace", ws_name):
		ws = frappe.get_doc("Workspace", ws_name)
	else:
		ws = frappe.new_doc("Workspace")
		ws.name = ws_name
		ws.label = ws_name
		ws.title = ws_name
		ws.module = "Artem ERP"
		ws.icon = "box"
		ws.is_standard = 0
		ws.public = 1

	ws.content = json.dumps(content_blocks)
	ws.set("links", [])
	ws.set("shortcuts", [])
	ws.set("roles", [])

	for l in links:
		ws.append("links", l)
	for s in shortcuts:
		ws.append("shortcuts", s)

	valid_roles = []
	for r in ["Asset Manager", "System Manager", "HR Manager", "HR User"]:
		if frappe.db.exists("Role", r):
			valid_roles.append({"role": r})

	for r in valid_roles:
		ws.append("roles", r)

	ws.save(ignore_permissions=True)


def isolate_standard_erpnext_maintenance():
	"""Hides standard ERPNext asset maintenance links from the main Assets workspace
	without deleting standard DocTypes or existing records."""
	if not frappe.db.exists("Workspace", "Assets"):
		return

	ws = frappe.get_doc("Workspace", "Assets")
	standard_maintenance_doctypes = {
		"Asset Maintenance",
		"Asset Maintenance Log",
		"Asset Repair",
		"Asset Maintenance Team",
	}

	# Remove standard maintenance links from the Assets workspace card links
	new_links = [l for l in ws.links if l.link_to not in standard_maintenance_doctypes]
	if len(new_links) != len(ws.links):
		ws.set("links", new_links)
		ws.save(ignore_permissions=True)


def sync_assets_workspace_sidebar():
	"""Updates the standard Assets Workspace Sidebar and Workspace in ERPNext
	to remove deprecated capitalization/depreciation/old maintenance links and
	add the custom Asset Management Dashboard, Employee Asset Allocation,
	Asset Assignment History, and custom Maintenance Suite."""
	# 1. Update Workspace Sidebar in DB
	sidebar = None
	if frappe.db.exists("Workspace Sidebar", "Assets"):
		sidebar = frappe.get_doc("Workspace Sidebar", "Assets")
	elif frappe.db.exists("Workspace Sidebar", {"title": "Assets"}):
		sidebar = frappe.get_doc("Workspace Sidebar", {"title": "Assets"})

	sidebar_items = [
		{
			"label": "Home",
			"type": "Link",
			"link_type": "Workspace",
			"link_to": "Assets",
			"icon": "home",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Asset Dashboard",
			"type": "Link",
			"link_type": "Page",
			"link_to": "asset_management_dashboard",
			"icon": "chart",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Asset",
			"type": "Link",
			"link_type": "DocType",
			"link_to": "Asset",
			"icon": "laptop",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Employee Asset Allocation",
			"type": "Link",
			"link_type": "DocType",
			"link_to": "Employee Asset Allocation",
			"icon": "users",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Asset Assignment History",
			"type": "Link",
			"link_type": "DocType",
			"link_to": "Asset Assignment History",
			"icon": "history",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Asset Movement",
			"type": "Link",
			"link_type": "DocType",
			"link_to": "Asset Movement",
			"icon": "move-horizontal",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		# Section Break: Maintenance
		{
			"label": "Maintenance",
			"type": "Section Break",
			"icon": "tool",
			"child": 0,
			"indent": 1,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Maintenance Overview",
			"type": "Link",
			"link_type": "Workspace",
			"link_to": "Asset Maintenance Management",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Maintenance History Report",
			"type": "Link",
			"link_type": "Report",
			"link_to": "Maintenance History Report",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Maintenance Status Report",
			"type": "Link",
			"link_type": "Report",
			"link_to": "Maintenance Status Report",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Maintenance Cost Analysis",
			"type": "Link",
			"link_type": "Report",
			"link_to": "Maintenance Cost Analysis",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Asset Repair Tracking",
			"type": "Link",
			"link_type": "Report",
			"link_to": "Asset Repair Tracking",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		# Section Break: Reports
		{
			"label": "Reports",
			"type": "Section Break",
			"icon": "sheet",
			"child": 0,
			"indent": 1,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Employee-wise Asset Allocation Report",
			"type": "Link",
			"link_type": "Report",
			"link_to": "Employee-wise Asset Allocation Report",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Fixed Asset Register",
			"type": "Link",
			"link_type": "Report",
			"link_to": "Fixed Asset Register",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Asset Activity",
			"type": "Link",
			"link_type": "Report",
			"link_to": "Asset Activity",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		# Section Break: Setup
		{
			"label": "Setup",
			"type": "Section Break",
			"icon": "database",
			"child": 0,
			"indent": 1,
			"collapsible": 1,
			"keep_closed": 1,
			"show_arrow": 0,
		},
		{
			"label": "Item",
			"type": "Link",
			"link_type": "DocType",
			"link_to": "Item",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Asset Category",
			"type": "Link",
			"link_type": "DocType",
			"link_to": "Asset Category",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		{
			"label": "Location",
			"type": "Link",
			"link_type": "DocType",
			"link_to": "Location",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
		# Settings
		{
			"label": "Settings",
			"type": "Link",
			"link_type": "DocType",
			"link_to": "Accounts Settings",
			"navigate_to_tab": "assets_tab",
			"icon": "settings",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"show_arrow": 0,
		},
	]

	if sidebar:
		sidebar.set("items", [])
		for idx, item in enumerate(sidebar_items, start=1):
			item_copy = dict(item)
			item_copy["idx"] = idx
			sidebar.append("items", item_copy)
		try:
			sidebar.save(ignore_permissions=True)
		except Exception:
			pass

	# 2. Update Workspace 'Assets' in DB
	if frappe.db.exists("Workspace", "Assets"):
		ws = frappe.get_doc("Workspace", "Assets")
		ws_links = [
			# Card: Assets
			{"label": "Assets", "type": "Card Break"},
			{"label": "Asset Management Dashboard", "type": "Link", "link_type": "Page", "link_to": "asset_management_dashboard", "onboard": 1},
			{"label": "Asset", "type": "Link", "link_type": "DocType", "link_to": "Asset", "onboard": 1},
			{"label": "Employee Asset Allocation", "type": "Link", "link_type": "DocType", "link_to": "Employee Asset Allocation", "onboard": 1},
			{"label": "Asset Assignment History", "type": "Link", "link_type": "DocType", "link_to": "Asset Assignment History", "onboard": 1},
			{"label": "Asset Movement", "type": "Link", "link_type": "DocType", "link_to": "Asset Movement"},
			{"label": "Asset Category", "type": "Link", "link_type": "DocType", "link_to": "Asset Category"},
			{"label": "Location", "type": "Link", "link_type": "DocType", "link_to": "Location"},
			# Card: Maintenance
			{"label": "Maintenance", "type": "Card Break"},
			{"label": "Maintenance Overview", "type": "Link", "link_type": "Workspace", "link_to": "Asset Maintenance Management", "onboard": 1},
			{"label": "Maintenance History Report", "type": "Link", "link_type": "Report", "link_to": "Maintenance History Report"},
			{"label": "Maintenance Status Report", "type": "Link", "link_type": "Report", "link_to": "Maintenance Status Report"},
			{"label": "Maintenance Cost Analysis", "type": "Link", "link_type": "Report", "link_to": "Maintenance Cost Analysis"},
			{"label": "Asset Repair Tracking", "type": "Link", "link_type": "Report", "link_to": "Asset Repair Tracking"},
			# Card: Reports
			{"label": "Reports", "type": "Card Break"},
			{"label": "Employee-wise Asset Allocation Report", "type": "Link", "link_type": "Report", "link_to": "Employee-wise Asset Allocation Report", "onboard": 1},
			{"label": "Fixed Asset Register", "type": "Link", "link_type": "Report", "link_to": "Fixed Asset Register"},
			{"label": "Asset Activity", "type": "Link", "link_type": "Report", "link_to": "Asset Activity"},
		]
		ws.set("links", ws_links)
		try:
			ws.save(ignore_permissions=True)
		except Exception:
			pass

	frappe.clear_cache(doctype="Workspace Sidebar")
	frappe.clear_cache(doctype="Workspace")
