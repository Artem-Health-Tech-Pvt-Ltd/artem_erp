// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.query_reports["Expense Claim Type Breakup Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "expense_claim_type",
			label: __("Expense Claim Type"),
			fieldtype: "Autocomplete",
			options: get_expense_claim_type_options(),
		},
		{
			fieldname: "approval_status",
			label: __("Approval Status"),
			fieldtype: "Select",
			options: "\nDraft\nApproved\nRejected\nCancelled",
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "action" && data && (data.expense_claim_type || data.expense_claim_type_id)) {
			const claim_type = frappe.utils.escape_html(data.expense_claim_type_id || data.expense_claim_type);
			return `<button type="button" class="btn btn-xs btn-primary btn-view-expense-claims" data-claim-type="${claim_type}">${__("View Expense Claims")}</button>`;
		}
		return value;
	},

	onload: function (report) {
		report.page.wrapper.off("click", ".btn-view-expense-claims").on("click", ".btn-view-expense-claims", function (e) {
			e.stopPropagation();
			e.preventDefault();

			const claim_type = $(this).attr("data-claim-type");
			if (!claim_type) return;

			frappe.route_options = {
				expense_claim_type: claim_type,
				expense_claim_type_id: claim_type,
				from_date: report.get_filter_value("from_date"),
				to_date: report.get_filter_value("to_date"),
				company: report.get_filter_value("company"),
				employee: report.get_filter_value("employee"),
				department: report.get_filter_value("department"),
			};

			frappe.set_route("query-report", "Expense Claim Details Report");
		});
	},
};

function get_expense_claim_type_options() {
	let options = [];
	frappe.db
		.get_list("Expense Claim Type", { fields: ["name"], limit: 200 })
		.then((res) => {
			(res || []).forEach((d) => {
				if (d && d.name) {
					options.push(d.name);
				}
			});
		});
	return options;
}



