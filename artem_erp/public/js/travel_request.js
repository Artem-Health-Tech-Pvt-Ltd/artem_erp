frappe.ui.form.on("Travel Request", {
	refresh(frm) {
		calculate_all_totals(frm);
	},

	before_workflow_action(frm) {
		const action = (frm.selected_workflow_action || "").trim();
		const lower_action = action.toLowerCase();

		if (["approve", "reject", "cancel"].includes(lower_action)) {
			frappe.dom.unfreeze();

			return new Promise((resolve, reject) => {
				const dialog_title = __(
					lower_action === "approve"
						? "Approval Details"
						: lower_action === "reject"
						? "Reject Details"
						: "Cancel Details"
				);

				const is_approval = lower_action === "approve";

				const fields = [
					{
						fieldname: "advance_approved",
						fieldtype: "Currency",
						label: __("Total Advance Approved"),
						default: frm.doc.custom_total_advance_approved || frm.doc.custom_total_advance_required || 0,
						reqd: is_approval ? 1 : 0,
						hidden: !is_approval,
					},
					{
						fieldname: "reason",
						fieldtype: "Small Text",
						label: __("Reason"),
						reqd: 1,
					},
				];

				const d = new frappe.ui.Dialog({
					title: dialog_title,
					fields: fields,
					primary_action_label: __("Submit"),
					primary_action(values) {
						const reason = (values.reason || "").trim();
						if (!reason) {
							frappe.msgprint(__("Reason is required"));
							return;
						}

						const advance_approved = is_approval ? flt(values.advance_approved) : 0;

						const update_dict = {
							custom_remark: reason,
						};
						if (is_approval) {
							update_dict.custom_total_advance_approved = advance_approved;
						}

						frappe.db
							.set_value("Travel Request", frm.doc.name, update_dict)
							.then(() => {
								frm.doc.custom_remark = reason;
								if (is_approval) {
									frm.doc.custom_total_advance_approved = advance_approved;
									frm.set_value("custom_total_advance_approved", advance_approved);
								}
								d.hide();
								frappe.dom.freeze();
								resolve();
							});
					},
				});

				d.onhide = () => {
					if (!frm.doc.custom_remark) {
						frappe.dom.unfreeze();
						reject();
					}
				};

				d.show();
			});
		}
	},
});

// Travel Request Costing child table events
frappe.ui.form.on("Travel Request Costing", {
	funded_amount(frm, cdt, cdn) {
		calculate_costing_row_total(frm, cdt, cdn);
		calculate_total_estimated_cost(frm);
	},

	sponsored_amount(frm, cdt, cdn) {
		calculate_costing_row_total(frm, cdt, cdn);
		calculate_total_estimated_cost(frm);
	},

	costings_add(frm) {
		calculate_total_estimated_cost(frm);
	},

	costings_remove(frm) {
		calculate_total_estimated_cost(frm);
	},
});

// Travel Itinerary child table events
frappe.ui.form.on("Travel Itinerary", {
	advance_amount(frm, cdt, cdn) {
		calculate_total_advance_required(frm);
	},

	itinerary_add(frm) {
		calculate_total_advance_required(frm);
	},

	itinerary_remove(frm) {
		calculate_total_advance_required(frm);
	},
});

function calculate_costing_row_total(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const funded = flt(row.funded_amount);
	const sponsored = flt(row.sponsored_amount);
	const total = funded + sponsored;

	frappe.model.set_value(cdt, cdn, "total_amount", total);
}

function calculate_total_estimated_cost(frm) {
	let total_estimated = 0;
	(frm.doc.costings || []).forEach((row) => {
		total_estimated += flt(row.total_amount);
	});
	frm.set_value("custom_total_estimated_cost", total_estimated);
}

function calculate_total_advance_required(frm) {
	let total_advance = 0;
	(frm.doc.itinerary || []).forEach((row) => {
		total_advance += flt(row.advance_amount);
	});
	frm.set_value("custom_total_advance_required", total_advance);
}

function calculate_all_totals(frm) {
	calculate_total_estimated_cost(frm);
	calculate_total_advance_required(frm);
}
