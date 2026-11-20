// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.query_reports["Asset Repair Tracking"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status Filter"),
			fieldtype: "Select",
			options: "In Repair\nAssigned\nIn Stock\nAll",
			default: "In Repair",
		},
		{
			fieldname: "asset_category",
			label: __("Asset Category"),
			fieldtype: "Link",
			options: "Asset Category",
		},
		{
			fieldname: "custodian",
			label: __("Custodian / Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "custom_asset_status") {
			if (data.custom_asset_status === "In Repair") {
				value = `<span class="indicator red">${value}</span>`;
			} else if (data.custom_asset_status === "Assigned") {
				value = `<span class="indicator blue">${value}</span>`;
			}
		}
		return value;
	},
};
