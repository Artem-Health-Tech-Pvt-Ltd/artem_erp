frappe.ui.form.on("Full and Final Statement", {
	setup: function (frm) {
		frm.ignore_doctypes_on_cancel_all = [
			"Salary Withholding",
			"Salary Withholding Cycle",
			"Salary Slip",
		];
	},

	onload: function (frm) {
		frm.ignore_doctypes_on_cancel_all = [
			"Salary Withholding",
			"Salary Withholding Cycle",
			"Salary Slip",
		];
	},

	refresh: function (frm) {
		frm.ignore_doctypes_on_cancel_all = [
			"Salary Withholding",
			"Salary Withholding Cycle",
			"Salary Slip",
		];
		if (frm.doc.employee && frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Fetch Withheld Salary"),
				function () {
					fetch_withheld_salaries_client(frm, true);
				},
				__("Actions")
			);

			// Automatically ensure withheld salaries are loaded if payables has no withholding row yet
			let has_withholding = (frm.doc.payables || []).some(
				(d) => d.component === "Salary Withholding Release"
			);
			if (!has_withholding) {
				fetch_withheld_salaries_client(frm, false);
			}
		}
	},

	employee: function (frm) {
		if (frm.doc.employee) {
			// Allow standard get_outstanding_statements to run, then ensure withholdings are loaded
			setTimeout(() => {
				fetch_withheld_salaries_client(frm, false);
			}, 500);
		}
	},
});

function fetch_withheld_salaries_client(frm, show_alert) {
	if (!frm.doc.employee) return;

	frappe.call({
		method: "artem_erp.doc_events.full_and_final_statement.get_partial_withholding_rows",
		args: {
			employee: frm.doc.employee,
			company: frm.doc.company,
		},
		callback: function (r) {
			if (r.message && r.message.length) {
				let existing_refs = (frm.doc.payables || []).map((d) => d.reference_document);
				let added = 0;
				r.message.forEach((row) => {
					if (!existing_refs.includes(row.reference_document)) {
						let child = frm.add_child("payables");
						Object.assign(child, row);
						existing_refs.push(row.reference_document);
						added++;
					}
				});

				if (added > 0) {
					frm.refresh_field("payables");
					frm.trigger("calculate_total_payable_amt");
					if (show_alert) {
						frappe.show_alert({
							message: __("Fetched {0} withheld salary record(s)", [added]),
							indicator: "green",
						});
					}
				} else if (show_alert) {
					frappe.show_alert({
						message: __("All withheld salary records are already added"),
						indicator: "blue",
					});
				}
			} else if (show_alert) {
				frappe.show_alert({
					message: __("No pending salary withholdings found for this employee"),
					indicator: "blue",
				});
			}
		},
	});
}

frappe.ui.form.on("Full and Final Outstanding Statement", {
	reference_document: function (frm, cdt, cdn) {
		const child = locals[cdt][cdn];
		if (child.reference_document_type === "Salary Slip" && child.reference_document) {
			frappe.db.get_value(
				"Salary Slip",
				child.reference_document,
				[
					"custom_is_partially_withheld",
					"custom_withheld_amount",
					"custom_salary_withholding",
					"salary_withholding",
				],
				function (val) {
					if (
						val &&
						(val.custom_is_partially_withheld || flt(val.custom_withheld_amount) > 0)
					) {
						frappe.model.set_value(
							cdt,
							cdn,
							"component",
							"Salary Withholding Release"
						);
						frappe.model.set_value(cdt, cdn, "paid_via_salary_slip", 0);
					}
				}
			);
		}
	},
});
