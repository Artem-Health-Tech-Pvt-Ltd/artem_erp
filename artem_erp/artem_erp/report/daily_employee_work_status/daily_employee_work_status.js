// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.query_reports["Daily Employee Work Status"] = {
	filters: [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
			max_date: frappe.datetime.str_to_obj(frappe.datetime.get_today()),
			on_change: function (report) {
				let date = report.get_filter_value("date");
				let today = frappe.datetime.get_today();
				if (date && date > today) {
					frappe.msgprint({
						title: __("Invalid Date"),
						message: __("You cannot select a future date."),
						indicator: "orange",
					});
					report.set_filter_value("date", today);
					return;
				}
				report.refresh();
			},
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Company", txt);
			},
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			get_query: function () {
				let filters = { status: ["in", ["Active", "Left"]] };
				let company = frappe.query_report.get_filter_value("company");
				let department = frappe.query_report.get_filter_value("department");

				if (company && company.length) {
					filters["company"] = ["in", company];
				}
				if (department && department.length) {
					filters["department"] = ["in", department];
				}
				return { filters: filters };
			},
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Department", txt);
			},
		},
		{
			fieldname: "shift",
			label: __("Shift"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Shift Type", txt);
			},
		},
		{
			fieldname: "work_status",
			label: __("Work Status"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				let options = [
					"Office Check-in",
					"On Leave",
					"On Duty",
					"Work From Home (WFH)",
					"No Check-in",
				];
				if (!txt) return options;
				return options.filter((opt) => opt.toLowerCase().includes(txt.toLowerCase()));
			},
		},
	],
	onload: function (report) {
		let date_filter = report.get_filter("date");
		if (date_filter && date_filter.datepicker) {
			date_filter.datepicker.update(
				"maxDate",
				frappe.datetime.str_to_obj(frappe.datetime.get_today())
			);
		}
		if (report.$report_message) {
			report.$report_message.removeClass("text-muted small");
		}
	},
	refresh: function (report) {
		let date = report.get_filter_value("date");
		let today = frappe.datetime.get_today();
		if (date && date > today) {
			frappe.msgprint({
				title: __("Invalid Date"),
				message: __("You cannot select a future date."),
				indicator: "orange",
			});
			report.set_filter_value("date", today);
			return;
		}
		if (report.$report_message) {
			report.$report_message.removeClass("text-muted small");
		}
		if (report.data && report.data.message) {
			let plain_text = $("<div>").html(report.data.message).text().trim();
			if (plain_text) {
				frappe.show_alert({ message: plain_text, indicator: "orange" }, 6);
			}
		}
	},
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "work_status" && data && data.work_status) {
			const color_map = {
				"Office Check-in": "green",
				"On Duty": "blue",
				"Work From Home (WFH)": "purple",
				"On Leave": "orange",
				"No Check-in": "red",
			};
			const color = color_map[data.work_status] || "gray";
			value = `<span class="indicator-pill ${color}">${data.work_status}</span>`;
		}
		return value;
	},
};
