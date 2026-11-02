// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.query_reports["Expense Claim Details Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "expense_claim_type",
			label: __("Expense Claim Type"),
			fieldtype: "Autocomplete",
			options: get_expense_claim_type_options(),
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
			fieldname: "status",
			label: __("Claim Status"),
			fieldtype: "Select",
			options: "\nDraft\nPaid\nUnpaid\nRejected\nSubmitted\nCancelled",
		},
		{
			fieldname: "approval_status",
			label: __("Approval Status"),
			fieldtype: "Select",
			options: "\nDraft\nApproved\nRejected\nCancelled",
		},
	],

	onload: function (report) {
		if (frappe.route_options) {
			const claim_type =
				frappe.route_options.expense_claim_type || frappe.route_options.expense_claim_type_id;
			if (claim_type) {
				report.set_filter_value("expense_claim_type", claim_type);
			}
		}
	},

	after_refresh: function (report) {
		if (!report.$summary) return;

		report.$summary.css({
			display: "flex",
			"flex-wrap": "wrap",
			gap: "14px",
			"margin-bottom": "18px",
		});

		const colorStyles = {
			blue: { border: "#2563eb", bg: "#eff6ff", text: "#1d4ed8" },
			purple: { border: "#7c3aed", bg: "#f5f3ff", text: "#6d28d9" },
			orange: { border: "#d97706", bg: "#fffbeb", text: "#b45309" },
			green: { border: "#059669", bg: "#ecfdf5", text: "#047857" },
			red: { border: "#dc2626", bg: "#fef2f2", text: "#b91c1c" },
		};

		report.$summary.find(".summary-item").each(function () {
			const $item = $(this);
			const $val = $item.find(".summary-value");
			let matched = null;

			for (const key of Object.keys(colorStyles)) {
				if ($val.hasClass(key)) {
					matched = colorStyles[key];
					break;
				}
			}

			if (matched) {
				$item.css({
					background: matched.bg,
					"border-left": `4px solid ${matched.border}`,
					"border-radius": "8px",
					padding: "05px 18px",
					"box-shadow": "0 1px 3px rgba(0, 0, 0, 0.05)",
					"min-width": "160px",
				});
				$val.css({
					color: matched.text,
					"font-weight": "600",
				});
			}
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


