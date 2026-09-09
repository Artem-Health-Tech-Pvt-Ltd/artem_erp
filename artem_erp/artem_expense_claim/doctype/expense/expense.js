frappe.ui.form.on("Expense", {
	refresh(frm) {
		if (frm.doc.is_claim_raise) {
			frm.disable_form();
			frm.dashboard.set_headline_alert(
				__("This Expense is linked to an Expense Claim and cannot be edited."),
				"orange"
			);
			return;
		}
		fetch_expense_limit(frm);
	},

	expense_date(frm) {
		fetch_expense_limit(frm);
	},

	city(frm) {
		reset_expense_travel_and_amount_fields(frm);
		fetch_expense_limit(frm);
	},

	expense_category(frm) {
		reset_expense_travel_and_amount_fields(frm);
		fetch_expense_limit(frm);
	},

	employee(frm) {
		reset_expense_travel_and_amount_fields(frm);
		fetch_expense_limit(frm);
	},

	employee_grade(frm) {
		reset_expense_travel_and_amount_fields(frm);
		fetch_expense_limit(frm);
	},

	total_distance_in_km(frm) {
		calculate_per_km_total(frm);
	},

	per_km_rate(frm) {
		calculate_per_km_total(frm);
	},

	total_amount(frm) {
		calculate_overlimit(frm, true);
	},

	limit_amount(frm) {
		calculate_overlimit(frm, false);
	},
});

function reset_expense_travel_and_amount_fields(frm) {
	frm.set_value("from_city", "");
	frm.set_value("to_city", "");
	frm.set_value("total_distance_in_km", 0);
	frm.set_value("per_km_rate", 0);
	frm.set_value("total_amount", 0);
	frm.set_value("limit_amount", 0);
	frm.set_value("is_overlimit__expense", 0);
	frm.set_df_property("limit_amount", "description", "");
	frm.doc.__available_limit = 0;
	frm.doc.__used_amount = 0;
}

function toggle_per_km_fields(frm, is_per_km = false) {
	frm.doc.__is_per_km = is_per_km;

	frm.toggle_display(
		["total_distance_in_km", "per_km_rate", "section_break_vefr", "from_city", "to_city"],
		is_per_km
	);
	frm.toggle_reqd(["total_distance_in_km", "per_km_rate"], is_per_km);
	frm.set_df_property("total_amount", "read_only", is_per_km ? 1 : 0);
	frm.toggle_display(["limit_amount"], !is_per_km);

	if (is_per_km) {
		frm.set_df_property("limit_amount", "description", "");
	}
}

function calculate_per_km_total(frm) {
	if (frm.doc.__is_per_km) {
		const distance = flt(frm.doc.total_distance_in_km);
		const rate = flt(frm.doc.per_km_rate);
		const total = distance * rate;
		frm.set_value("total_amount", total);
	}
}

function fetch_expense_limit(frm) {
	if (!frm.doc.city || !frm.doc.expense_category) {
		frm.set_value("limit_amount", 0);
		toggle_per_km_fields(frm, false);
		frm.set_df_property("limit_amount", "description", "");
		return;
	}

	frappe.call({
		method: "artem_erp.artem_expense_claim.doctype.expense.expense.get_expense_limit",
		args: {
			expense_category: frm.doc.expense_category,
			city: frm.doc.city,
			employee: frm.doc.employee,
			employee_grade: frm.doc.employee_grade,
			expense_date: frm.doc.expense_date,
			expense_name: frm.doc.name,
		},
		callback: function (r) {
			if (r.message) {
				const is_per_km = Boolean(r.message.is_per_km);
				const limit_amount = flt(r.message.limit_amount);
				const used_amount = flt(r.message.used_amount);
				const available_limit = flt(r.message.available_limit);

				frm.doc.__available_limit = available_limit;
				frm.doc.__used_amount = used_amount;

				toggle_per_km_fields(frm, is_per_km);

				if (r.message.employee_grade && !frm.doc.employee_grade) {
					frm.set_value("employee_grade", r.message.employee_grade);
				}

				if (is_per_km) {
					frm.set_value("per_km_rate", limit_amount);
					frm.set_value("limit_amount", 0);
					frm.set_df_property("limit_amount", "description", "");
					calculate_per_km_total(frm);
					frm.set_value("is_overlimit__expense", 0);
				} else {
					frm.set_value("per_km_rate", 0);
					frm.set_value("limit_amount", limit_amount);

					if (limit_amount > 0) {
						const color_class = available_limit <= 0 ? "text-danger" : "text-success";
						const desc = `<span class="text-muted">${__("Used")}: <b>${format_currency(
							used_amount
						)}</b> | ${__("Available")}: <b class="${color_class}">${format_currency(
							available_limit
						)}</b> (${__("for selected expense date")})</span>`;
						frm.set_df_property("limit_amount", "description", desc);
					} else {
						frm.set_df_property("limit_amount", "description", "");
					}

					calculate_overlimit(frm, false);
				}
			}
		},
	});
}

function calculate_overlimit(frm, show_message = false) {
	if (frm.doc.__is_per_km) {
		frm.set_value("is_overlimit__expense", 0);
		return;
	}

	const total_amount = flt(frm.doc.total_amount);
	const limit_amount = flt(frm.doc.limit_amount);
	const available_limit =
		frm.doc.__available_limit !== undefined ? flt(frm.doc.__available_limit) : limit_amount;

	if (limit_amount > 0 && total_amount > available_limit) {
		frm.set_value("is_overlimit__expense", 1);
		if (show_message) {
			frappe.call({
				method: "artem_erp.artem_expense_claim.doctype.expense.expense.check_expense_overlimit",
				args: {
					employee: frm.doc.employee,
					expense_category: frm.doc.expense_category,
					expense_date: frm.doc.expense_date,
					total_amount: total_amount,
					limit_amount: limit_amount,
					expense_name: frm.doc.name,
				},
				callback: function (r) {
					if (r.message && !r.message.allowed) {
						frappe.msgprint({
							title: __("Over-Limit Expense"),
							message: __(
								"The entered expense amount exceeds the allowed limit. Please contact the HR Team or your Reporting Manager for approval."
							),
							indicator: "orange",
						});
					}
				},
			});
		}
	} else {
		frm.set_value("is_overlimit__expense", 0);
	}
}
