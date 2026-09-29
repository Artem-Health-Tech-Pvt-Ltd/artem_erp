// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.query_reports["Employee Monthly Attendance Details"] = {
	filters: [
		{
			fieldname: "filter_based_on",
			label: __("Filter Based On"),
			fieldtype: "Select",
			options: ["Month", "Date Range"],
			default: "Month",
			reqd: 1,
			on_change: (report) => {
				let filter_based_on = frappe.query_report.get_filter_value("filter_based_on");

				if (filter_based_on == "Month") {
					set_reqd_filter("month", true);
					set_reqd_filter("year", true);
					set_reqd_filter("start_date", false);
					set_reqd_filter("end_date", false);
				}
				if (filter_based_on == "Date Range") {
					set_reqd_filter("month", false);
					set_reqd_filter("year", false);
					set_reqd_filter("start_date", true);
					set_reqd_filter("end_date", true);
				}
				report.refresh();
			},
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: [
				{ value: 1, label: __("Jan") },
				{ value: 2, label: __("Feb") },
				{ value: 3, label: __("Mar") },
				{ value: 4, label: __("Apr") },
				{ value: 5, label: __("May") },
				{ value: 6, label: __("June") },
				{ value: 7, label: __("July") },
				{ value: 8, label: __("Aug") },
				{ value: 9, label: __("Sep") },
				{ value: 10, label: __("Oct") },
				{ value: 11, label: __("Nov") },
				{ value: 12, label: __("Dec") },
			],
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1,
			depends_on: "eval:doc.filter_based_on == 'Month'",
		},
		{
			fieldname: "start_date",
			label: __("Start Date"),
			fieldtype: "Date",
			depends_on: "eval:doc.filter_based_on == 'Date Range'",
			on_change: validate_date_range,
		},
		{
			fieldname: "end_date",
			label: __("End Date"),
			fieldtype: "Date",
			depends_on: "eval:doc.filter_based_on == 'Date Range'",
			on_change: validate_date_range,
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Select",
			depends_on: "eval:doc.filter_based_on == 'Month'",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			options: "Company",
			default: frappe.defaults.get_user_default("Company")
				? [frappe.defaults.get_user_default("Company")]
				: [],
			reqd: 1,
			get_data: function (txt) {
				return frappe.db.get_link_options("Company", txt);
			},
			on_change: function (report) {
				let department_filter = frappe.query_report.get_filter("department");
				if (department_filter) {
					department_filter.set_value([]);
					if (department_filter.set_options) {
						department_filter.set_options();
					}
				}
				report.refresh();
			},
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "MultiSelectList",
			options: "Department",
			get_data: function (txt) {
				let companies = frappe.query_report.get_filter_value("company");
				if (!companies) return [];
				if (typeof companies === "string") {
					companies = [companies];
				}
				if (!companies.length) return [];

				return frappe
					.call({
						method: "artem_erp.artem_erp.report.employee_monthly_attendance_details.employee_monthly_attendance_details.get_departments_for_companies",
						args: {
							companies: companies,
							include_descendants:
								frappe.query_report.get_filter_value(
									"include_company_descendants"
								) || 0,
							txt: txt || "",
						},
					})
					.then((r) => r.message || []);
			},
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			get_query: () => {
				let company = frappe.query_report.get_filter_value("company");
				let department = frappe.query_report.get_filter_value("department");
				let filters = {};

				if (company) {
					if (Array.isArray(company) && company.length) {
						filters.company = ["in", company];
					} else if (typeof company === "string") {
						filters.company = company;
					}
				}
				if (department) {
					if (Array.isArray(department) && department.length) {
						filters.department = ["in", department];
					} else if (typeof department === "string") {
						filters.department = department;
					}
				}
				return { filters: filters };
			},
		},
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: ["", "Branch", "Grade", "Department", "Designation"],
		},
		{
			fieldname: "include_company_descendants",
			label: __("Include Company Descendants"),
			fieldtype: "Check",
			default: 1,
			on_change: function (report) {
				let department_filter = frappe.query_report.get_filter("department");
				if (department_filter && department_filter.set_options) {
					department_filter.set_options();
				}
				report.refresh();
			},
		},
		{
			fieldname: "summarized_view",
			label: __("Summarized View"),
			fieldtype: "Check",
			default: 0,
			on_change: function (report) {
				if (frappe.query_report.get_filter_value("summarized_view")) {
					const detailed_with_summary =
						frappe.query_report.get_filter("detailed_with_summary");
					if (detailed_with_summary && detailed_with_summary.get_value()) {
						detailed_with_summary.set_input(0);
					}
				}
				report.refresh();
			},
		},
		{
			fieldname: "detailed_with_summary",
			label: __("Detailed with Summary"),
			fieldtype: "Check",
			default: 0,
			on_change: function (report) {
				if (frappe.query_report.get_filter_value("detailed_with_summary")) {
					const summarized_view = frappe.query_report.get_filter("summarized_view");
					if (summarized_view && summarized_view.get_value()) {
						summarized_view.set_input(0);
					}
				}
				report.refresh();
			},
		},
	],
	onload: function () {
		return frappe.call({
			method: "artem_erp.artem_erp.report.employee_monthly_attendance_details.employee_monthly_attendance_details.get_attendance_years",
			callback: function (r) {
				var year_filter = frappe.query_report.get_filter("year");
				year_filter.df.options = r.message;
				year_filter.df.default = r.message.split("\n")[0];
				year_filter.refresh();
				year_filter.set_input(year_filter.df.default);
			},
		});
	},
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const summarized_view = frappe.query_report.get_filter_value("summarized_view");
		const group_by = frappe.query_report.get_filter_value("group_by");

		if (group_by && column.colIndex === 1) {
			value = "<strong>" + value + "</strong>";
		}

		if (!summarized_view) {
			if ((group_by && column.colIndex > 3) || (!group_by && column.colIndex > 2)) {
				if (value == "HD/P") value = "<span style='color:#914EE3'>" + value + "</span>";
				else if (value == "HD/A")
					value = "<span style='color:orange'>" + value + "</span>";
				else if (value == "P" || value == "WFH")
					value = "<span style='color:green'>" + value + "</span>";
				else if (value == "A") value = "<span style='color:red'>" + value + "</span>";
				else if (value == "L") value = "<span style='color:#318AD8'>" + value + "</span>";
				else if (value == "H" || value == "WO")
					value = "<span style='color:#878787'>" + value + "</span>";
				else if (column.fieldtype === "Data" || !column.fieldtype)
					value = "<span style='color:#878787'>" + value + "</span>";
			}
		}

		return value;
	},
};
function set_reqd_filter(fieldname, is_reqd) {
	let filter = frappe.query_report.get_filter(fieldname);
	filter.df.reqd = is_reqd;
	filter.refresh();
}
function validate_date_range(report) {
	let start_date = frappe.query_report.get_filter_value("start_date");
	let end_date = frappe.query_report.get_filter_value("end_date");
	if (!(start_date && end_date)) return;

	let start = frappe.datetime.str_to_obj(start_date);
	let end = frappe.datetime.str_to_obj(end_date);
	let milli_seconds_in_a_day = 24 * 60 * 60 * 1000;
	let day_diff = Math.floor((end - start) / milli_seconds_in_a_day);
	if (day_diff > 90) {
		frappe.throw({
			message: __("Please set a date range less than 90 days."),
			title: __("Date Range Exceeded"),
		});
	}
	report.refresh();
}
