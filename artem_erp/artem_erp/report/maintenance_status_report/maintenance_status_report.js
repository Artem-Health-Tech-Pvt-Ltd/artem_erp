// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.query_reports["Maintenance Status Report"] = {
	filters: [
		{
			fieldname: "asset_category",
			label: __("Asset Category"),
			fieldtype: "Link",
			options: "Asset Category",
		},
		{
			fieldname: "status",
			label: __("Asset Status"),
			fieldtype: "Select",
			options: "\nIn Stock\nAssigned\nIn Repair",
		},
		{
			fieldname: "custodian",
			label: __("Custodian / Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "has_maintenance",
			label: __("Maintenance Filter"),
			fieldtype: "Select",
			options: "All\nWith Maintenance\nNever Maintained",
			default: "All",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "custom_asset_status") {
			if (data.custom_asset_status === "In Repair") {
				value = `<span class="indicator red">${value}</span>`;
			} else if (data.custom_asset_status === "Assigned") {
				value = `<span class="indicator blue">${value}</span>`;
			} else if (data.custom_asset_status === "In Stock") {
				value = `<span class="indicator green">${value}</span>`;
			}
		}
		return value;
	},
};
