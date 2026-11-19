// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.query_reports["Employee-wise Asset Allocation Report"] = {
	"filters": [
		{
			"fieldname": "employee",
			"label": __("Employee"),
			"fieldtype": "Link",
			"options": "Employee"
		},
		{
			"fieldname": "department",
			"label": __("Department"),
			"fieldtype": "Link",
			"options": "Department"
		},
		{
			"fieldname": "asset_category",
			"label": __("Asset Category"),
			"fieldtype": "Link",
			"options": "Asset Category"
		},
		{
			"fieldname": "asset",
			"label": __("Asset"),
			"fieldtype": "Link",
			"options": "Asset"
		},
		{
			"fieldname": "assignment_status",
			"label": __("Allocation Status"),
			"fieldtype": "Select",
			"options": "\nAssigned\nReturned"
		},
		{
			"fieldname": "asset_status",
			"label": __("Asset Status"),
			"fieldtype": "Select",
			"options": "\nIn Stock\nAssigned\nIn Repair"
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date"
		}
	],
	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "assignment_status") {
			if (data.assignment_status === "Assigned") {
				value = `<span class="indicator-pill blue">${__("Assigned")}</span>`;
			} else if (data.assignment_status === "Returned") {
				value = `<span class="indicator-pill green">${__("Returned")}</span>`;
			}
		}
		if (column.fieldname === "asset_status") {
			if (data.asset_status === "Assigned") {
				value = `<span class="indicator-pill blue">${__("Assigned")}</span>`;
			} else if (data.asset_status === "In Stock") {
				value = `<span class="indicator-pill green">${__("In Stock")}</span>`;
			} else if (data.asset_status === "In Repair") {
				value = `<span class="indicator-pill orange">${__("In Repair")}</span>`;
			}
		}
		return value;
	}
};

