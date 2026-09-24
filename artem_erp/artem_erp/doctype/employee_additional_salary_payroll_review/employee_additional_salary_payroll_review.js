// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Additional Salary Payroll Review", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			// Button: Sync Additional Salary
			frm.add_custom_button(__("Sync Additional Salary"), function () {
				frm.call({
					doc: frm.doc,
					method: "sync_review",
					freeze: true,
					freeze_message: __("Synchronizing Additional Salary records..."),
					callback: function (r) {
						if (r.message) {
							frappe.msgprint({
								message: r.message.message || __("Synchronization completed."),
								indicator: r.message.indicator || "blue",
							});
						}
						frm.reload_doc();
					},
				});
			});
		}
	},

	validate(frm) {
		const check_table = (table_name, label) => {
			for (const row of frm.doc[table_name] || []) {
				const paid = flt(row.paid_amount);
				const total = flt(row.total_amount);
				if (paid > 0 && paid > total) {
					frappe.msgprint({
						title: __("Invalid Paid Amount"),
						message: __(
							"{0}: Row {1} ({2}) - Paid Amount ({3}) must be less than or equal to Total Amount ({4}).",
							[label, row.idx, row.employee, paid, total]
						),
						indicator: "red",
					});
					frappe.validated = false;
					return false;
				}
			}
			return true;
		};

		if (
			!check_table(
				"additional_salary_payment_details",
				__("Current Month Additional Salaries")
			)
		)
			return;
		if (
			!check_table(
				"previous_pending_additional_salary",
				__("Previous Pending Additional Salaries")
			)
		)
			return;
	},
});

frappe.ui.form.on("Additional Salary Payment Details", {
	pay_action(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const total = flt(row.total_amount);

		if (row.pay_action === "Pay") {
			frappe.model.set_value(cdt, cdn, "paid_amount", total);
			frappe.model.set_value(cdt, cdn, "remaining_amount", 0);
			frappe.model.set_value(cdt, cdn, "paid_percentage", 100);
		} else if (
			row.pay_action === "Never Pay" ||
			row.pay_action === "Paid Outside ERP Payroll"
		) {
			frappe.model.set_value(cdt, cdn, "paid_amount", 0);
			frappe.model.set_value(cdt, cdn, "remaining_amount", 0);
			frappe.model.set_value(cdt, cdn, "paid_percentage", 0);
		} else if (row.pay_action === "On Hold") {
			frappe.model.set_value(cdt, cdn, "paid_amount", 0);
			frappe.model.set_value(cdt, cdn, "remaining_amount", total);
			frappe.model.set_value(cdt, cdn, "paid_percentage", 0);
		} else if (row.pay_action === "Partially Paid") {
			const paid = flt(row.paid_amount);
			frappe.model.set_value(cdt, cdn, "remaining_amount", Math.max(0, total - paid));
		}
	},

	paid_amount(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const total = flt(row.total_amount);
		const paid = flt(row.paid_amount);

		if (paid > 0 && paid > total) {
			frappe.msgprint({
				title: __("Invalid Paid Amount"),
				message: __("Paid Amount must be less than or equal to Total Amount ({0}).", [
					total,
				]),
				indicator: "orange",
			});
			frappe.model.set_value(cdt, cdn, "paid_amount", total);
			return;
		}

		if (row.pay_action === "Partially Paid") {
			const remaining = Math.max(0, total - paid);
			const pct = total > 0 ? (paid / total) * 100 : 0;
			frappe.model.set_value(cdt, cdn, "remaining_amount", remaining);
			frappe.model.set_value(cdt, cdn, "paid_percentage", pct);
		}
	},

	paid_percentage(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.pay_action === "Partially Paid") {
			const total = flt(row.total_amount);
			const pct = flt(row.paid_percentage);
			if (pct > 100) {
				frappe.msgprint({
					title: __("Invalid Percentage"),
					message: __("Paid Percentage cannot be greater than 100%."),
					indicator: "orange",
				});
				frappe.model.set_value(cdt, cdn, "paid_percentage", 100);
				return;
			}
			const paid = (pct / 100) * total;
			const remaining = Math.max(0, total - paid);
			frappe.model.set_value(cdt, cdn, "paid_amount", paid);
			frappe.model.set_value(cdt, cdn, "remaining_amount", remaining);
		}
	},
});

frappe.ui.form.on("Previous Pending Additional Salary", {
	additional_salary(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.additional_salary || !frm.doc.company || !frm.doc.payroll_from_date) return;

		frappe.call({
			method: "artem_erp.artem_erp.doctype.employee_additional_salary_payroll_review.monthly_weekly_payroll_review.get_previous_pending_additional_salary_details",
			args: {
				company: frm.doc.company,
				payroll_from_date: frm.doc.payroll_from_date,
				additional_salary: row.additional_salary,
			},
			callback: function (r) {
				if (r.message) {
					frappe.model.set_value(
						cdt,
						cdn,
						"previous_pay_action",
						r.message.previous_pay_action || r.message.pay_action || ""
					);
					frappe.model.set_value(
						cdt,
						cdn,
						"previous_additional_salary_total_amount",
						r.message.total_amount
					);
					frappe.model.set_value(
						cdt,
						cdn,
						"previous_additional_salary_paid_percentage",
						r.message.paid_percentage
					);
					frappe.model.set_value(
						cdt,
						cdn,
						"previous_additional_salary_paid_amount",
						r.message.paid_amount
					);
					frappe.model.set_value(
						cdt,
						cdn,
						"previous_additional_salary_remaining_amount",
						r.message.remaining_amount
					);
					frappe.model.set_value(cdt, cdn, "total_amount", r.message.remaining_amount);
					frappe.model.set_value(
						cdt,
						cdn,
						"remaining_amount",
						r.message.remaining_amount
					);
					frappe.model.set_value(cdt, cdn, "paid_amount", 0);
					frappe.model.set_value(cdt, cdn, "paid_percentage", 0);
					frappe.model.set_value(cdt, cdn, "pay_action", r.message.pay_action);
				}
			},
		});
	},

	pay_action(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const total = flt(row.total_amount);

		if (row.pay_action === "Pay") {
			frappe.model.set_value(cdt, cdn, "paid_amount", total);
			frappe.model.set_value(cdt, cdn, "remaining_amount", 0);
			frappe.model.set_value(cdt, cdn, "paid_percentage", 100);
		} else if (
			row.pay_action === "Never Pay" ||
			row.pay_action === "Paid Outside ERP Payroll"
		) {
			frappe.model.set_value(cdt, cdn, "paid_amount", 0);
			frappe.model.set_value(cdt, cdn, "remaining_amount", 0);
			frappe.model.set_value(cdt, cdn, "paid_percentage", 0);
		} else if (row.pay_action === "On Hold") {
			frappe.model.set_value(cdt, cdn, "paid_amount", 0);
			frappe.model.set_value(cdt, cdn, "remaining_amount", total);
			frappe.model.set_value(cdt, cdn, "paid_percentage", 0);
		} else if (row.pay_action === "Partially Paid") {
			const paid = flt(row.paid_amount);
			frappe.model.set_value(cdt, cdn, "remaining_amount", Math.max(0, total - paid));
		}
	},

	paid_amount(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const total = flt(row.total_amount);
		const paid = flt(row.paid_amount);

		if (paid > 0 && paid > total) {
			frappe.msgprint({
				title: __("Invalid Paid Amount"),
				message: __("Paid Amount must be less than or equal to Total Amount ({0}).", [
					total,
				]),
				indicator: "orange",
			});
			frappe.model.set_value(cdt, cdn, "paid_amount", total);
			return;
		}

		if (row.pay_action === "Partially Paid") {
			const remaining = Math.max(0, total - paid);
			const pct = total > 0 ? (paid / total) * 100 : 0;
			frappe.model.set_value(cdt, cdn, "remaining_amount", remaining);
			frappe.model.set_value(cdt, cdn, "paid_percentage", pct);
		}
	},

	paid_percentage(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.pay_action === "Partially Paid") {
			const total = flt(row.total_amount);
			const pct = flt(row.paid_percentage);
			if (pct > 100) {
				frappe.msgprint({
					title: __("Invalid Percentage"),
					message: __("Paid Percentage cannot be greater than 100%."),
					indicator: "orange",
				});
				frappe.model.set_value(cdt, cdn, "paid_percentage", 100);
				return;
			}
			const paid = (pct / 100) * total;
			const remaining = Math.max(0, total - paid);
			frappe.model.set_value(cdt, cdn, "paid_amount", paid);
			frappe.model.set_value(cdt, cdn, "remaining_amount", remaining);
		}
	},
});
