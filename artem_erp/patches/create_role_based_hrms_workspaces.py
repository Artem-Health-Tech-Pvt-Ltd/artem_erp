import json
import os
import shutil

import frappe
from frappe import _
from frappe.modules.export_file import export_to_files


def execute():
	"""
	Migration patch to configure custom workspaces:
	1. Employee Dashboard (Roles: Employee, Manager)
	   - Unified custom workspace for Employee self-service and Manager team operations.

	Configures Workspace, Workspace Sidebar, and Desktop Icon for Employee Dashboard.
	Idempotent and safe to run multiple times without creating duplicates.
	"""
	frappe.flags.in_patch = True
	frappe.flags.in_migrate = True

	# 1. Ensure required roles exist
	ensure_roles(["Employee", "Manager", "HR User", "HR Manager"])

	# 3. Get unified workspace configurations (Employee Dashboard only)
	workspaces = get_workspace_configs()

	# 4. Create or update each workspace, its sidebar, and desktop icon
	for ws_data in workspaces:
		setup_workspace(ws_data)
		setup_workspace_sidebar(ws_data)
		setup_desktop_icon(ws_data)

	# 5. Clear relevant caches so new desk navigation loads immediately
	frappe.clear_cache()
	if hasattr(frappe.cache, "delete_key"):
		frappe.cache.delete_key("desktop_icons")
		frappe.cache.delete_key("bootinfo")


def ensure_roles(roles):
	"""Ensure standard and custom roles exist in the database with desk access."""
	for role_name in roles:
		if not frappe.db.exists("Role", role_name):
			try:
				role_doc = frappe.get_doc(
					{
						"doctype": "Role",
						"role_name": role_name,
						"desk_access": 1,
					}
				)
				role_doc.insert(ignore_permissions=True)
				frappe.logger().info(f"Created missing Role: {role_name}")
			except Exception as e:
				frappe.log_error(f"Failed to create Role {role_name}: {e}", "Role Creation Error")

	# Set home page for Employee & Manager roles to directly open Employee Dashboard workspace
	for r in ["Employee", "Manager"]:
		if frappe.db.exists("Role", r):
			frappe.db.set_value("Role", r, "home_page", "desk/employee-dashboard")


def setup_workspace(ws_data):
	"""Create or update Workspace document and export standard file."""
	ws_name = ws_data["name"]

	if frappe.db.exists("Workspace", ws_name):
		ws = frappe.get_doc("Workspace", ws_name)
	else:
		ws = frappe.new_doc("Workspace")
		ws.name = ws_name
		ws.label = ws_name

	ws.title = ws_data.get("title", ws_name)
	ws.icon = ws_data.get("icon", "folder")
	ws.module = ws_data.get("module", "Artem ERP")
	ws.app = ws_data.get("app", "artem_erp")
	ws.public = 1
	ws.is_hidden = 0
	ws.hide_custom = 0
	ws.type = "Workspace"

	# Manage Roles
	ws.set("roles", [])
	for target_role in ws_data.get("roles", []):
		ws.append("roles", {"role": target_role})

	# Manage Shortcuts
	ws.set("shortcuts", [])
	for s in ws_data.get("shortcuts", []):
		shortcut_row = {
			"label": s["label"],
			"type": s.get("type", "DocType"),
			"link_to": s.get("link_to"),
			"doc_view": s.get("doc_view", "List"),
			"icon": s.get("icon"),
			"color": s.get("color", "Grey"),
		}
		if s.get("type") == "Report":
			shortcut_row["report_ref_doctype"] = s.get("report_ref_doctype", "")
			if s.get("is_query_report"):
				shortcut_row["stats_filter"] = "[]"
		ws.append("shortcuts", shortcut_row)

	# Manage Cards and Links
	ws.set("links", [])
	for card in ws_data.get("cards", []):
		card_row = {
			"label": card["label"],
			"type": "Card Break",
			"icon": card.get("icon", "folder"),
			"link_count": len(card.get("links", [])),
		}
		ws.append("links", card_row)

		for link in card.get("links", []):
			link_row = {
				"label": link["label"],
				"type": "Link",
				"link_type": link.get("link_type", "DocType"),
				"link_to": link.get("link_to"),
				"icon": link.get("icon", "file-text"),
				"is_query_report": 1 if link.get("is_query_report") else 0,
			}
			ws.append("links", link_row)

	# Build rich blocks content for standard canvas rendering
	ws.content = build_workspace_content(ws_data)

	ws.flags.ignore_permissions = True
	ws.flags.ignore_links = True
	ws.save(ignore_permissions=True)

	# Export to app folder
	try:
		export_to_files(record_list=[["Workspace", ws.name]], record_module=ws.module)
	except Exception as e:
		frappe.logger().warning(f"Could not export Workspace {ws_name} to file: {e}")

	frappe.logger().info(f"Configured Workspace: {ws_name}")


def build_workspace_content(ws_data):
	"""Generate standard block content JSON for Desk workspace builder."""
	blocks = []

	# Shortcuts header & blocks
	shortcuts = ws_data.get("shortcuts", [])
	if shortcuts:
		blocks.append(
			{
				"id": f"hdr_shortcuts_{frappe.generate_hash(length=8)}",
				"type": "header",
				"data": {"text": f'<span class="h4"><b>{_("Quick Access")}</b></span>', "col": 12},
			}
		)
		for s in shortcuts:
			blocks.append(
				{
					"id": f"sc_{frappe.generate_hash(length=8)}",
					"type": "shortcut",
					"data": {"shortcut_name": s["label"], "col": 3},
				}
			)
		blocks.append(
			{
				"id": f"spc_{frappe.generate_hash(length=8)}",
				"type": "spacer",
				"data": {"col": 12},
			}
		)

	# Cards header & blocks
	cards = ws_data.get("cards", [])
	if cards:
		blocks.append(
			{
				"id": f"hdr_cards_{frappe.generate_hash(length=8)}",
				"type": "header",
				"data": {"text": f'<span class="h4"><b>{_("Masters & Reports")}</b></span>', "col": 12},
			}
		)
		for card in cards:
			blocks.append(
				{
					"id": f"card_{frappe.generate_hash(length=8)}",
					"type": "card",
					"data": {"card_name": card["label"], "col": 4},
				}
			)

	return json.dumps(blocks)


def setup_workspace_sidebar(ws_data):
	"""Create or update Workspace Sidebar document and export standard file."""
	sb_name = ws_data["name"]

	if frappe.db.exists("Workspace Sidebar", sb_name):
		sb = frappe.get_doc("Workspace Sidebar", sb_name)
	else:
		sb = frappe.new_doc("Workspace Sidebar")
		sb.title = sb_name

	sb.header_icon = ws_data.get("icon", "folder")
	sb.app = ws_data.get("app", "artem_erp")
	sb.module = ws_data.get("module", "Artem ERP")
	sb.standard = 1
	sb.for_user = ""

	# Build sidebar items
	items = [
		# Workspace Home
		{
			"type": "Link",
			"label": "Home",
			"link_type": "Workspace",
			"link_to": sb_name,
			"icon": "home",
			"child": 0,
			"collapsible": 0,
			"indent": 0,
			"keep_closed": 0,
			"show_arrow": 0,
		}
	]

	for card in ws_data.get("cards", []):
		# Section Break
		items.append(
			{
				"type": "Section Break",
				"label": card["label"],
				"link_type": "DocType",
				"link_to": "",
				"icon": card.get("icon", "folder"),
				"child": 0,
				"collapsible": 1,
				"indent": 0,
				"keep_closed": 0,
				"show_arrow": 0,
			}
		)

		# Card Links
		for l in card.get("links", []):
			item_data = {
				"type": "Link",
				"label": l["label"],
				"link_to": l["link_to"],
				"link_type": l.get("link_type", "DocType"),
				"icon": l.get("icon", "file-text"),
				"child": 1,
				"collapsible": 1,
				"indent": 0,
				"keep_closed": 0,
				"show_arrow": 0,
			}
			if l.get("route_options"):
				item_data["route_options"] = l["route_options"]
			items.append(item_data)

	sb.set("items", [])
	for it in items:
		sb.append("items", it)

	sb.save(ignore_permissions=True)

	# Export to app folder
	try:
		sb.export_sidebar()
	except Exception as e:
		frappe.logger().warning(f"Could not export Sidebar {sb_name}: {e}")

	frappe.logger().info(f"Configured Workspace Sidebar: {sb_name}")


def setup_desktop_icon(ws_data):
	"""Create or update Desktop Icon document and export standard file."""
	label = ws_data["name"]

	if frappe.db.exists("Desktop Icon", label):
		di = frappe.get_doc("Desktop Icon", label)
	else:
		di = frappe.new_doc("Desktop Icon")
		di.label = label

	di.icon_type = "Link"
	di.link_type = "Workspace Sidebar"
	di.link_to = label
	di.icon = ws_data.get("icon", "folder")
	di.standard = 1
	di.app = ws_data.get("app", "artem_erp")
	di.hidden = 0

	# Assign roles
	di.set("roles", [])
	for role in ws_data.get("roles", []):
		di.append("roles", {"role": role})

	di.save(ignore_permissions=True)

	# Export to app folder
	try:
		di.export_desktop_icon()
	except Exception as e:
		frappe.logger().warning(f"Could not export Desktop Icon {label}: {e}")

	frappe.logger().info(f"Configured Desktop Icon: {label}")


def get_workspace_configs():
	"""
	Returns the definition of the 2 Workspaces:
	1. Employee Dashboard (Unified Workspace for Employee & Manager)
	"""
	return [
		# ============================================================
		# 1. UNIFIED EMPLOYEE DASHBOARD WORKSPACE (Employee & Manager)
		# ============================================================
		{
			"name": "Employee Dashboard",
			"title": "Employee Dashboard",
			"icon": "dashboard",
			"module": "Artem ERP",
			"app": "artem_erp",
			"roles": ["Employee", "Manager", "HR User", "HR Manager"],
			"shortcuts": [
				{
					"label": "Leave Applications",
					"type": "DocType",
					"link_to": "Leave Application",
					"doc_view": "List",
					"icon": "calendar-plus",
					"color": "Blue",
				},
				{
					"label": "Punch Logs",
					"type": "DocType",
					"link_to": "Employee Checkin",
					"doc_view": "List",
					"icon": "clock",
					"color": "Green",
				},
				{
					"label": "Attendance Regularization Requests",
					"type": "DocType",
					"link_to": "Attendance Request",
					"doc_view": "List",
					"icon": "calendar-check",
					"color": "Orange",
				},
				{
					"label": "Attendance Logs",
					"type": "DocType",
					"link_to": "Attendance",
					"doc_view": "List",
					"icon": "history",
					"color": "Grey",
				},
				{
					"label": "Leave Balance",
					"type": "Report",
					"link_to": "Employee Leave Balance",
					"icon": "scale",
					"color": "Cyan",
				},
				{
					"label": "Payslips",
					"type": "DocType",
					"link_to": "Salary Slip",
					"doc_view": "List",
					"icon": "file-text",
					"color": "Purple",
				},
				{
					"label": "Expense Claims",
					"type": "DocType",
					"link_to": "Expense Claim",
					"doc_view": "List",
					"icon": "wallet",
					"color": "Yellow",
				},
				{
					"label": "Employee Advances",
					"type": "DocType",
					"link_to": "Employee Advance",
					"doc_view": "List",
					"icon": "hand-coins",
					"color": "Light Blue",
				},
				{
					"label": "Monthly Attendance Details",
					"type": "Report",
					"link_to": "Employee Monthly Attendance Details",
					"is_query_report": 1,
					"icon": "table",
					"color": "Green",
				},
				{
					"label": "Asset",
					"type": "DocType",
					"link_to": "Asset",
					"doc_view": "List",
					"icon": "box",
					"color": "Blue",
				},
			],
			"cards": [
				{
					"label": "Employee Information",
					"icon": "user",
					"links": [
						{
							"label": "Employee Profile",
							"link_type": "DocType",
							"link_to": "Employee",
							"icon": "user",
							"route_options": '{"doc_view": "List"}',
						},
					],
				},
				{
					"label": "Attendance",
					"icon": "calendar-check",
					"links": [
						{
							"label": "Punch Logs",
							"link_type": "DocType",
							"link_to": "Employee Checkin",
							"icon": "clock",
						},
						{
							"label": "Attendance Logs",
							"link_type": "DocType",
							"link_to": "Attendance",
							"icon": "history",
						},
						{
							"label": "Attendance Regularization Request",
							"link_type": "DocType",
							"link_to": "Attendance Request",
							"icon": "calendar-check",
						},
					],
				},
				{
					"label": "Leave & Holidays",
					"icon": "calendar-minus",
					"links": [
						{
							"label": "Leave Applications",
							"link_type": "DocType",
							"link_to": "Leave Application",
							"icon": "calendar-plus",
						},
						{
							"label": "Leave Balance",
							"link_type": "Report",
							"link_to": "Employee Leave Balance",
							"is_query_report": 1,
							"icon": "scale",
						},
						{
							"label": "Holiday List",
							"link_type": "DocType",
							"link_to": "Holiday List",
							"icon": "calendar",
						},
						{
							"label": "Comp-off",
							"link_type": "DocType",
							"link_to": "Compensatory Leave Request",
							"icon": "clock-plus",
						},
					],
				},
				{
					"label": "Payroll & Tax",
					"icon": "receipt",
					"links": [
						{
							"label": "Payslips",
							"link_type": "DocType",
							"link_to": "Salary Slip",
							"icon": "file-text",
						},
						{
							"label": "CTC Break-up",
							"link_type": "Report",
							"link_to": "Employee CTC Breakup",
							"is_query_report": 1,
							"icon": "file-chart-column-increasing",
						},
						{
							"label": "Tax Declarations",
							"link_type": "DocType",
							"link_to": "Employee Tax Exemption Declaration",
							"icon": "file-check",
						},
						{
							"label": "Tax Proofs",
							"link_type": "DocType",
							"link_to": "Employee Tax Exemption Proof Submission",
							"icon": "file-input",
						},
					],
				},
				{
					"label": "Expenses & Advances",
					"icon": "wallet",
					"links": [
						{
							"label": "Expense Claims",
							"link_type": "DocType",
							"link_to": "Expense Claim",
							"icon": "wallet",
						},
						{
							"label": "Employee Advances",
							"link_type": "DocType",
							"link_to": "Employee Advance",
							"icon": "hand-coins",
						},
					],
				},
				{
					"label": "Assets",
					"icon": "box",
					"links": [
						{"label": "Asset", "link_type": "DocType", "link_to": "Asset", "icon": "box"},
					],
				},
				{
					"label": "Reports",
					"icon": "bar-chart-2",
					"links": [
						{
							"label": "Employee Monthly Attendance Details",
							"link_type": "Report",
							"link_to": "Employee Monthly Attendance Details",
							"is_query_report": 1,
							"icon": "table",
						},
					],
				},
				{
					"label": "Settings",
					"icon": "setting-gear",
					"links": [
						{
							"label": "Artem Setting",
							"link_type": "DocType",
							"link_to": "Artem Setting",
							"icon": "setting-gear",
						},
						{
							"label": "Biometric Device Details",
							"link_type": "DocType",
							"link_to": "Biometric Device Details",
							"icon": "cpu",
						},
						{
							"label": "Artem Biometric Configuration",
							"link_type": "DocType",
							"link_to": "Artem Biometric Configuration Setting",
							"icon": "settings",
						},
					],
				},
			],
		},
	]
