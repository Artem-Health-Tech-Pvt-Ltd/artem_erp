// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.listview_settings["Employee Asset Allocation"] = {
	add_fields: [
		"employee",
		"employee_name",
		"department",
		"designation",
		"company",
		"total_assigned_assets",
	],
	get_indicator: function (doc) {
		if (doc.total_assigned_assets > 0) {
			return [__("{0} Assigned", [doc.total_assigned_assets]), "blue"];
		} else {
			return [__("No Active Assets"), "gray"];
		}
	},
};
