// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.query_reports["Maintenance History Report"] = {
	filters: [
		{
			fieldname: "asset",
			label: __("Asset"),
			fieldtype: "Link",
			options: "Asset",
		},
		{
			fieldname: "asset_category",
			label: __("Asset Category"),
			fieldtype: "Link",
			options: "Asset Category",
		},
		{
			fieldname: "maintenance_type",
			label: __("Maintenance Type"),
			fieldtype: "Select",
			options: "\nHardware Repair\nSoftware / OS\nCleaning / Servicing\nUpgrade\nBattery / Power\nOther",
		},
		{
			fieldname: "custodian",
			label: __("Custodian / Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],
};

