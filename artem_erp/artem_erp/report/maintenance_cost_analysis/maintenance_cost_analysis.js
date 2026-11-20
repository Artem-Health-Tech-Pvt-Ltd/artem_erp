// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.query_reports["Maintenance Cost Analysis"] = {
	filters: [
		{
			fieldname: "group_by",
			label: __("Analysis View"),
			fieldtype: "Select",
			options: "By Category\nBy Asset\nBy Month\nBy Year",
			default: "By Category",
			reqd: 1,
		},
		{
			fieldname: "asset_category",
			label: __("Asset Category"),
			fieldtype: "Link",
			options: "Asset Category",
		},
		{
			fieldname: "status",
			label: __("Status (for Asset View)"),
			fieldtype: "Select",
			options: "\nIn Stock\nAssigned\nIn Repair",
			depends_on: "eval:frappe.query_report.get_filter_value('group_by')=='By Asset'",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			depends_on:
				"eval:frappe.query_report.get_filter_value('group_by')=='By Month' || frappe.query_report.get_filter_value('group_by')=='By Year'",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			depends_on:
				"eval:frappe.query_report.get_filter_value('group_by')=='By Month' || frappe.query_report.get_filter_value('group_by')=='By Year'",
		},
	],
};
