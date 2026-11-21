import json

import frappe


def execute():
	"""Sets company logo and favicon across Navbar Settings, Website Settings, and Desktop Icon."""
	logo_path = "/assets/artem_erp/images/artem_logo.png"
	favicon_path = "/assets/artem_erp/images/favicon.png"

	# 1. Navbar Settings (sets top navbar desk / desktop brand logo)
	try:
		if frappe.db.exists("DocType", "Navbar Settings"):
			frappe.db.set_single_value("Navbar Settings", "app_logo", logo_path)
	except Exception:
		frappe.log_error(
			title="Set Company Logo Patch: Navbar Settings Error",
			message=frappe.get_traceback(),
		)

	# 2. Website Settings (sets website logo, browser tab favicon, and splash image)
	try:
		if frappe.db.exists("DocType", "Website Settings"):
			frappe.db.set_single_value("Website Settings", "app_logo", logo_path)
			frappe.db.set_single_value("Website Settings", "favicon", favicon_path)
			frappe.db.set_single_value("Website Settings", "splash_image", logo_path)
	except Exception:
		frappe.log_error(
			title="Set Company Logo Patch: Website Settings Error",
			message=frappe.get_traceback(),
		)

	# 3. Desktop Icon and Desktop Layout (sets logo for Employee Dashboard desktop icon & sidebar header)
	try:
		if frappe.db.exists("DocType", "Desktop Icon") and frappe.db.exists(
			"Desktop Icon", "Employee Dashboard"
		):
			frappe.db.set_value(
				"Desktop Icon",
				"Employee Dashboard",
				{
					"logo_url": logo_path,
					"icon_image": logo_path,
					"app": "artem_erp",
				},
				update_modified=False,
			)

		if frappe.db.exists("DocType", "Desktop Layout"):
			layouts = frappe.get_all("Desktop Layout", fields=["name", "layout"])
			for l in layouts:
				try:
					items = json.loads(l.layout)
					changed = False
					for it in items:
						if it.get("label") == "Employee Dashboard" or it.get("name") == "Employee Dashboard":
							it["logo_url"] = logo_path
							it["icon_image"] = logo_path
							it["app"] = "artem_erp"
							changed = True
					if changed:
						frappe.db.set_value(
							"Desktop Layout", l.name, "layout", json.dumps(items), update_modified=False
						)
				except Exception:
					frappe.log_error(
						title=f"Set Company Logo Patch: Desktop Layout Error for {l.name}",
						message=frappe.get_traceback(),
					)
	except Exception:
		frappe.log_error(
			title="Set Company Logo Patch: Desktop Icon/Layout Error",
			message=frappe.get_traceback(),
		)

	try:
		frappe.cache.delete_key("desktop_icons")
		frappe.cache.delete_key("bootinfo")
	except Exception:
		frappe.log_error(
			title="Set Company Logo Patch: Cache Delete Error",
			message=frappe.get_traceback(),
		)

	frappe.clear_cache()
