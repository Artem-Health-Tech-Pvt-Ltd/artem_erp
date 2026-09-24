frappe.ui.form.on("Additional Salary", {
	refresh: function (frm) {
		if (frm.is_new() && frm.doc.employee && !frm.doc.custom_annual_gross_earning && !frm.doc.custom_ctc) {
			frm.trigger("fetch_salary_structure_assignment_details");
		}
	},

	employee: function (frm) {
		frm.trigger("fetch_salary_structure_assignment_details");
	},

	validate: function (frm) {
		if (frm.doc.from_date && frm.doc.to_date && frm.doc.to_date <= frm.doc.from_date) {
			frappe.throw(__("To Date must be greater than From Date."));
		}
	},

	from_date: function (frm) {
		if (frm.doc.from_date && frm.doc.to_date && frm.doc.to_date <= frm.doc.from_date) {
			frappe.msgprint(__("To Date must be greater than From Date."));
			frm.set_value("to_date", "");
		}
	},

	to_date: function (frm) {
		if (frm.doc.from_date && frm.doc.to_date && frm.doc.to_date <= frm.doc.from_date) {
			frappe.msgprint(__("To Date must be greater than From Date."));
			frm.set_value("to_date", "");
		}
	},

	fetch_salary_structure_assignment_details: function (frm) {
		if (!frm.doc.employee) {
			frm.set_value("custom_annual_gross_earning", 0);
			frm.set_value("custom_ctc", 0);
			return;
		}

		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Salary Structure Assignment",
				filters: {
					employee: frm.doc.employee,
					docstatus: 1,
				},
				fieldname: ["annual_gross_earning", "ctc"],
				order_by: "from_date desc",
			},
			callback: function (r) {
				if (r && r.message) {
					frm.set_value("custom_annual_gross_earning", r.message.annual_gross_earning || 0);
					frm.set_value("custom_ctc", r.message.ctc || 0);
				} else {
					frm.set_value("custom_annual_gross_earning", 0);
					frm.set_value("custom_ctc", 0);
				}
			},
		});
	},
});

