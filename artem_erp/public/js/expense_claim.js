frappe.ui.form.on("Expense Claim", {
	setup(frm) {
		set_child_table_queries(frm);
	},

	refresh(frm) {
		set_child_table_queries(frm);

		// Ensure amount in child table is not editable
		frm.set_df_property("expenses", "cannot_add_rows", frm.doc.docstatus > 0);
		frm.fields_dict["expenses"]?.grid?.toggle_enable("amount", false);
	},

	before_workflow_action(frm) {
		const action = (frm.selected_workflow_action || "").trim();
		const lower_action = action.toLowerCase();

		if (["approve", "reject", "cancel"].includes(lower_action)) {
			// Unfreeze UI because Frappe freezes the DOM right before triggering before_workflow_action
			frappe.dom.unfreeze();

			return new Promise((resolve, reject) => {
				const dialog_title = __(
					lower_action === "approve"
						? "Approval Reason"
						: lower_action === "reject"
						? "Reject Reason"
						: "Cancel Reason"
				);

				const d = new frappe.ui.Dialog({
					title: dialog_title,
					fields: [
						{
							fieldname: "reason",
							fieldtype: "Small Text",
							label: __("Approval/Reject Reason"),
							reqd: 1,
						},
					],
					primary_action_label: __("Submit"),
					primary_action(values) {
						const reason = (values.reason || "").trim();
						if (!reason) {
							return;
						}
						frappe.db
							.set_value(
								"Expense Claim",
								frm.doc.name,
								"custom_approval_reject_reason",
								reason
							)
							.then(() => {
								frm.doc.custom_approval_reject_reason = reason;
								d.hide();
								frappe.dom.freeze();
								resolve();
							});
					},
				});

				d.onhide = () => {
					if (!frm.doc.custom_approval_reject_reason) {
						frappe.dom.unfreeze();
						reject();
					}
				};

				d.show();
			});
		}
	},
});

frappe.ui.form.on("Expense Claim Detail", {
	custom_expense(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (!row.custom_expense) {
			frappe.model.set_value(cdt, cdn, "amount", 0);
			return;
		}

		frappe.db.get_value("Expense", row.custom_expense, "total_amount").then((r) => {
			frappe.model.set_value(cdt, cdn, "amount", r.message?.total_amount || 0);
		});
	},
});

function set_child_table_queries(frm) {
	// Filter custom_expense for current employee and not yet claimed
	frm.set_query("custom_expense", "expenses", function (doc, cdt, cdn) {
		return {
			filters: [
				["Expense", "employee", "=", doc.employee || ""],
				["Expense", "is_claim_raise", "=", 0],
			],
		};
	});

	// Filter custom_request_form (Travel Request) for current employee and submitted (docstatus = 1)
	frm.set_query("custom_request_form", "expenses", function (doc, cdt, cdn) {
		return {
			filters: {
				employee: doc.employee || "",
				docstatus: 1,
			},
		};
	});
}
