frappe.ui.form.on("Salary Slip", {
	setup(frm) {
		frm.ignore_doctypes_on_cancel_all = [
			"Salary Withholding",
			"Salary Withholding Cycle",
			"Full and Final Statement",
			"Full and Final Outstanding Statement",
		];
	},

	onload(frm) {
		frm.ignore_doctypes_on_cancel_all = [
			"Salary Withholding",
			"Salary Withholding Cycle",
			"Full and Final Statement",
			"Full and Final Outstanding Statement",
		];
	},

	refresh(frm) {
		frm.ignore_doctypes_on_cancel_all = [
			"Salary Withholding",
			"Salary Withholding Cycle",
			"Full and Final Statement",
			"Full and Final Outstanding Statement",
		];
	},
});
