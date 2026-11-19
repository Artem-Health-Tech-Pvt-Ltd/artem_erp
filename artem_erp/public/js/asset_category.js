// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Asset Category", {
	refresh(frm) {
		// Ensure custom fields are visible even when standard ERPNext metadata hides them.
		frm.toggle_display([
			"custom_it_config_section",
			"custom_series_prefix",
			"custom_asset_series",
			"custom_column_break_it_config",
			"custom_warranty",
			"custom_default_item",
			"custom_spec_section",
			"custom_specifications",
		], true);

		// Clean-up: Hide Depreciation Options, CWIP, and Finance Book Detail sections/fields
		frm.toggle_display([
			"enable_cwip_accounting",
			"depreciation_method",
			"total_number_of_depreciations",
			"frequency_of_depreciation",
			"finance_books",
			"finance_book_detail",
			"depreciation_details_section",
			"depreciation_details",
			"depreciation_options"
		], false);
	},

	custom_series_prefix(frm) {
		update_series_preview(frm);
	},
});


function update_series_preview(frm) {
	let prefix = (frm.doc.custom_series_prefix || "").trim().toUpperCase();
	if (prefix) {
		let series = `${prefix}-.###`;
		if (frm.doc.custom_series_prefix !== prefix) {
			frm.set_value("custom_series_prefix", prefix);
		}
		frm.set_value("custom_asset_series", series);
	}
}
