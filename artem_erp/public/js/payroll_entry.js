// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Payroll Entry", {
	refresh(frm) {
		toggle_additional_salary_review_button(frm);
	},

	onload_post_render(frm) {
		toggle_additional_salary_review_button(frm);
	},

	company(frm) {
		toggle_additional_salary_review_button(frm);
	},

	start_date(frm) {
		toggle_additional_salary_review_button(frm);
	},

	end_date(frm) {
		toggle_additional_salary_review_button(frm);
	},
});

function toggle_additional_salary_review_button(frm) {
	if (frm.is_new() || frm.doc.docstatus !== 0) {
		frm.remove_custom_button(__("Review Employee Additional Salary"));
		return;
	}

	if (!frm.doc.company || !frm.doc.start_date || !frm.doc.end_date) {
		frm.remove_custom_button(__("Review Employee Additional Salary"));
		return;
	}

	frappe.call({
		method: "artem_erp.artem_erp.doctype.employee_additional_salary_payroll_review.monthly_weekly_payroll_review.check_payroll_review_status",
		args: {
			company: frm.doc.company,
			start_date: frm.doc.start_date,
			end_date: frm.doc.end_date,
		},
		callback: function (r) {
			if (!frm.doc || frm.doc.docstatus !== 0) return;

			frm.remove_custom_button(__("Review Employee Additional Salary"));

			if (r.message && r.message.exists && r.message.docstatus === 0) {
				// Review is in Draft: show custom button without overriding primary action / Save functionality
				frm.add_custom_button(__("Review Employee Additional Salary"), function () {
					if (frm.is_dirty()) {
						frappe.confirm(
							__("You have unsaved changes. Do you want to save before reviewing Additional Salaries?"),
							() => {
								frm.save().then(() => {
									frappe.set_route("Form", "Employee Additional Salary Payroll Review", r.message.name);
								});
							},
							() => {
								frappe.set_route("Form", "Employee Additional Salary Payroll Review", r.message.name);
							}
						);
					} else {
						frappe.set_route("Form", "Employee Additional Salary Payroll Review", r.message.name);
					}
				});
			}
		},
	});
}
