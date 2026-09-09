frappe.ui.form.on("Employee Advance", {
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
								"Employee Advance",
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
