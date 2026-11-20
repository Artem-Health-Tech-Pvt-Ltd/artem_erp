// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt
//
// Asset list view: colour indicators + custom columns

frappe.listview_settings["Asset"] = {
	// ── Columns shown in the list ────────────────────────────────────────────
	add_fields: [
		"asset_name",
		"asset_category",
		"custodian",
		"custom_employee_name",
		"location",
		"status",
		"custom_asset_status",
		"custom_warranty_expiry",
	],

	// ── Indicator colour logic ───────────────────────────────────────────────
	get_indicator(doc) {
		const today = frappe.datetime.get_today();

		// Warranty expired
		if (doc.custom_warranty_expiry && doc.custom_warranty_expiry < today) {
			return [__("Warranty Expired"), "red", "custom_warranty_expiry,<,today"];
		}

		// In Repair
		if (doc.custom_asset_status === "In Repair") {
			return [__("In Repair"), "orange", "custom_asset_status,=,In Repair"];
		}

		// Assigned (has custodian or marked Assigned)
		if (doc.custom_asset_status === "Assigned" || doc.custodian) {
			return [__("Assigned"), "green", "custom_asset_status,=,Assigned"];
		}

		// In Stock
		return [__("In Stock"), "blue", "custom_asset_status,=,In Stock"];
	},

	// ── Filters exposed in the sidebar ──────────────────────────────────────
	filters: [["Asset", "asset_category", "is", "set"]],
};
