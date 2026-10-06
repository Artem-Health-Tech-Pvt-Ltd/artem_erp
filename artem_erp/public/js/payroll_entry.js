// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Payroll Entry", {
	refresh(frm) {
		update_payroll_entry_actions(frm);
	},

	onload_post_render(frm) {
		update_payroll_entry_actions(frm);
	},

	company(frm) {
		update_payroll_entry_actions(frm);
	},

	start_date(frm) {
		update_payroll_entry_actions(frm);
	},

	end_date(frm) {
		update_payroll_entry_actions(frm);
	},
});

function update_payroll_entry_actions(frm) {
	if (frm.is_new() || frm.doc.docstatus !== 0) {
		frm.remove_custom_button(__("Review Employee Additional Salary"));
		frm._additional_salary_review_in_draft = false;
		return;
	}

	if (!frm.doc.company || !frm.doc.start_date || !frm.doc.end_date) {
		frm.remove_custom_button(__("Review Employee Additional Salary"));
		frm._additional_salary_review_in_draft = false;
		return;
	}

	// If review was already detected as draft in this session, keep Create Salary Slips hidden and provide Save immediately
	if (frm._additional_salary_review_in_draft) {
		apply_draft_review_actions(frm, frm._review_doc_name);
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

			if (r.message && r.message.exists && r.message.docstatus === 0) {
				frm._additional_salary_review_in_draft = true;
				frm._review_doc_name = r.message.name;
				apply_draft_review_actions(frm, r.message.name);
			} else {
				frm._additional_salary_review_in_draft = false;
				frm._review_doc_name = null;
				frm.remove_custom_button(__("Review Employee Additional Salary"));

				// Review is submitted or doesn't exist:
				// If form is dirty, primary action should be "Save"
				if (frm.is_dirty()) {
					frm.page.set_primary_action(__("Save"), () => frm.save());
				} else if (
					(frm.doc.employees || []).length &&
					!frappe.model.has_workflow(frm.doctype) &&
					!cint(frm.doc.salary_slips_created) &&
					frm.doc.overtime_step !== "Create" &&
					frm.doc.overtime_step !== "Submit"
				) {
					// Review is submitted: restore standard "Create Salary Slips"
					frm.page.set_primary_action(__("Create Salary Slips"), () => {
						frm.save("Submit").then(() => {
							frm.page.clear_primary_action();
							frm.refresh();
						});
					});
				}
			}
		},
	});
}

function apply_draft_review_actions(frm, review_name) {
	review_name = review_name || frm._review_doc_name;

	// 1. Show "Review Employee Additional Salary" custom button
	frm.remove_custom_button(__("Review Employee Additional Salary"));
	if (review_name) {
		frm.add_custom_button(__("Review Employee Additional Salary"), function () {
			if (frm.is_dirty()) {
				frappe.confirm(
					__(
						"You have unsaved changes. Do you want to save before reviewing Additional Salaries?"
					),
					() => {
						frm.save().then(() => {
							frappe.set_route(
								"Form",
								"Employee Additional Salary Payroll Review",
								review_name
							);
						});
					},
					() => {
						frappe.set_route(
							"Form",
							"Employee Additional Salary Payroll Review",
							review_name
						);
					}
				);
			} else {
				frappe.set_route("Form", "Employee Additional Salary Payroll Review", review_name);
			}
		});
	}

	// 2. "Create Salary Slips" MUST NOT be displayed while Review is in Draft.
	// Set primary action to "Save" so user can edit and save in draft status (including Ctrl+S).
	frm.page.set_primary_action(__("Save"), () => frm.save());
}
