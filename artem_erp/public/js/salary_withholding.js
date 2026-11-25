frappe.ui.form.on("Salary Withholding", {
	refresh: function (frm) {
		frm.trigger("toggle_percentage_fields");
	},

	custom_withholding_mode: function (frm) {
		frm.trigger("toggle_percentage_fields");
		if (frm.doc.custom_withholding_mode === "Percentage") {
			if (!frm.doc.custom_withholding_percentage) {
				frm.set_value("custom_withholding_percentage", 50.0);
			}
			if (!frm.doc.custom_withholding_component) {
				frm.set_value("custom_withholding_component", "Salary Withholding");
			}
		}
	},

	toggle_percentage_fields: function (frm) {
		let is_pct = frm.doc.custom_withholding_mode === "Percentage";
		frm.toggle_display("custom_withholding_percentage", is_pct);
		frm.toggle_display("custom_calculation_base", is_pct);
		frm.toggle_display("custom_withholding_col_break", is_pct);
		frm.toggle_display("custom_withholding_component", is_pct);
		frm.toggle_display("custom_holdback_account", is_pct);
		frm.toggle_reqd("custom_withholding_percentage", is_pct);
	},

	validate: function (frm) {
		if (frm.doc.custom_withholding_mode === "Percentage") {
			let pct = flt(frm.doc.custom_withholding_percentage);
			if (pct <= 0 || pct > 100) {
				frappe.msgprint(
					__("Withholding Percentage must be greater than 0% and at most 100%")
				);
				frappe.validated = false;
			}
		}
	},
});
