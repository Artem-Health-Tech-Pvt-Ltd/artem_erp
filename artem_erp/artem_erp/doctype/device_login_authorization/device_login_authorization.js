frappe.ui.form.on("Device Login Authorization", {
	refresh(frm) {
		if (frm.doc.status === "Blocked") {
			frm.set_df_property("remarks", "reqd", 1);
		}
	},

	before_workflow_action(frm) {
		if (frm.selected_workflow_action === "Block Device") {
			frappe.dom.unfreeze();
			return new Promise((resolve, reject) => {
				let is_submitted = false;
				let dialog = new frappe.ui.Dialog({
					title: __("Reason for Blocking Device"),
					fields: [
						{
							label: __("Remarks"),
							fieldname: "remarks",
							fieldtype: "Small Text",
							reqd: 1,
							default: (frm.doc.remarks || "").trim(),
						},
					],
					primary_action_label: __("Block Device"),
					primary_action(values) {
						const remarks_value = (values.remarks || "").trim();
						if (!remarks_value) {
							frappe.msgprint({
								title: __("Mandatory Field"),
								message: __("Remarks are mandatory when blocking a device."),
								indicator: "red",
							});
							return;
						}
						is_submitted = true;
						dialog.hide();
						frappe.dom.freeze();

						// Persist remarks to DB before apply_workflow runs
						frappe.db
							.set_value(frm.doctype, frm.docname, "remarks", remarks_value)
							.then(() => {
								frm.doc.remarks = remarks_value;
								frm.refresh_field("remarks");
								resolve();
							})
							.catch((err) => {
								frm.selected_workflow_action = null;
								frappe.dom.unfreeze();
								reject(err);
							});
					},
				});

				dialog.onhide = () => {
					if (!is_submitted) {
						frm.selected_workflow_action = null;
						frappe.dom.unfreeze();
						reject();
					}
				};

				dialog.show();
			});
		}
	},
});
