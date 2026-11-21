// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employees Salary Component Override", {
	setup: function (frm) {
		// Filter Employee field based on selected Company
		frm.set_query("employee", function () {
			let filters = {
				status: "Active",
			};
			if (frm.doc.company) {
				filters.company = frm.doc.company;
			}
			return {
				filters: filters,
			};
		});

		// Filter Salary Component in child table to only allow override-enabled components
		frm.set_query("salary_component", "override_details", function () {
			if (!frm.doc.salary_structure) {
				return {};
			}
			return {
				query: "artem_erp.artem_erp.doctype.employees_salary_component_override.employees_salary_component_override.get_eligible_components_query",
				filters: {
					salary_structure: frm.doc.salary_structure,
					salary_structure_assignment: frm.doc.salary_structure_assignment,
					employee: frm.doc.employee,
				},
			};
		});
	},

	onload: function (frm) {
		// Prevent default empty row in child table on new form
		if (
			frm.is_new() &&
			frm.doc.override_details &&
			frm.doc.override_details.length === 1 &&
			!frm.doc.override_details[0].salary_component
		) {
			frm.clear_table("override_details");
			frm.refresh_field("override_details");
		}
	},

	onload_post_render: function (frm) {
		// Extra guard to remove default empty row after DOM render on new form
		if (
			frm.is_new() &&
			frm.doc.override_details &&
			frm.doc.override_details.length === 1 &&
			!frm.doc.override_details[0].salary_component
		) {
			frm.clear_table("override_details");
			frm.refresh_field("override_details");
		}
	},

	refresh: function (frm) {
		// Prevent default empty row in child table on new form
		if (
			frm.is_new() &&
			frm.doc.override_details &&
			frm.doc.override_details.length === 1 &&
			!frm.doc.override_details[0].salary_component
		) {
			frm.clear_table("override_details");
			frm.refresh_field("override_details");
		}

		// Set visual dashboard status alert
		if (frm.doc.docstatus === 1) {
			if (frm.doc.is_active) {
				frm.dashboard.set_headline_alert(
					'<div class="row align-items-center"><div class="col"><span class="indicator-pill green">Active Override</span> — Overridden amounts will be applied during Salary Slip generation.</div></div>'
				);
			} else {
				frm.dashboard.set_headline_alert(
					'<div class="row align-items-center"><div class="col"><span class="indicator-pill orange">Deactivated</span> — Reverted to standard Salary Structure formulas.</div></div>'
				);
			}
		}

		// Hide overridden_salary_structure_assignment if empty, show if set
		frm.set_df_property(
			"overridden_salary_structure_assignment",
			"hidden",
			!frm.doc.overridden_salary_structure_assignment
		);

		// Button to auto-fetch eligible components from assigned salary structure
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Fetch Eligible Components"), function () {
				fetch_eligible_components(frm);
			});

			// If structure_amount is 0 or not calculated in draft rows, auto-refresh structure amounts
			if (
				frm.doc.salary_structure_assignment &&
				frm.doc.override_details &&
				frm.doc.override_details.length > 0
			) {
				const has_zero_struct_amt = frm.doc.override_details.some(
					(row) => !flt(row.structure_amount)
				);
				if (has_zero_struct_amt) {
					refresh_structure_amounts(frm);
				}
			}
		}
	},

	company: function (frm) {
		// When company changes, verify employee belongs to new company
		if (frm.doc.employee) {
			frappe.db.get_value("Employee", frm.doc.employee, "company", function (r) {
				if (r && r.company && r.company !== frm.doc.company) {
					frm.set_value("employee", "");
					frm.set_value("employee_name", "");
					frm.set_value("salary_structure", "");
					frm.set_value("salary_structure_assignment", "");
					frm.clear_table("override_details");
					frm.refresh_field("override_details");
				}
			});
		}
	},

	employee: function (frm) {
		if (!frm.doc.employee) {
			frm.set_value("employee_name", "");
			frm.set_value("salary_structure", "");
			frm.set_value("salary_structure_assignment", "");
			return;
		}

		frappe.call({
			method: "artem_erp.artem_erp.doctype.employees_salary_component_override.employees_salary_component_override.get_active_assignment_details",
			args: {
				employee: frm.doc.employee,
				effective_date: frm.doc.effective_from_date || frappe.datetime.get_today(),
			},
			callback: function (r) {
				if (r.message && r.message.salary_structure_assignment) {
					frm.set_value(
						"salary_structure_assignment",
						r.message.salary_structure_assignment
					);
					frm.set_value("salary_structure", r.message.salary_structure);
					if (r.message.company && !frm.doc.company) {
						frm.set_value("company", r.message.company);
					}
					frappe.show_alert({
						message: __("Loaded active assignment {0} with structure {1}", [
							r.message.salary_structure_assignment,
							r.message.salary_structure,
						]),
						indicator: "green",
					});

					// Refresh structure amounts in existing rows if any
					if (frm.doc.override_details && frm.doc.override_details.length > 0) {
						refresh_structure_amounts(frm);
					}
				} else {
					frappe.msgprint({
						title: __("No Active Assignment"),
						message: __(
							"No submitted Salary Structure Assignment found for Employee {0}.",
							[frm.doc.employee]
						),
						indicator: "orange",
					});
				}
			},
		});
	},

	salary_structure: function (frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Fetch Eligible Components"), function () {
				fetch_eligible_components(frm);
			});
		}
	},

	salary_structure_assignment: function (frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Fetch Eligible Components"), function () {
				fetch_eligible_components(frm);
			});
		}
		if (
			frm.doc.salary_structure_assignment &&
			frm.doc.override_details &&
			frm.doc.override_details.length > 0
		) {
			refresh_structure_amounts(frm);
		}
	},

	effective_from_date: function (frm) {
		if (frm.doc.employee && !frm.doc.salary_structure_assignment) {
			frm.trigger("employee");
		}
	},

	is_active: function (frm) {
		if (frm.doc.docstatus === 1) {
			if (frm.doc.is_active) {
				frm.dashboard.set_headline_alert(
					'<div class="row align-items-center"><div class="col"><span class="indicator-pill green">' +
						__("Active Override") +
						"</span> — " +
						__("Overridden amounts will be applied during Salary Slip generation.") +
						"</div></div>"
				);
			} else {
				frm.dashboard.set_headline_alert(
					'<div class="row align-items-center"><div class="col"><span class="indicator-pill orange">' +
						__("Deactivated") +
						"</span> — " +
						__("Reverted to standard Salary Structure formulas.") +
						"</div></div>"
				);
			}
		}
	},
});

function fetch_eligible_components(frm) {
	if (!frm.doc.salary_structure) {
		frappe.msgprint({
			title: __("Salary Structure Required"),
			message: __(
				"Please select an Employee with an active Salary Structure Assignment first."
			),
			indicator: "orange",
		});
		return;
	}

	// Remove any blank rows without salary_component first
	if (frm.doc.override_details) {
		let had_empty = false;
		frm.doc.override_details = frm.doc.override_details.filter((row) => {
			if (!row.salary_component) {
				had_empty = true;
				return false;
			}
			return true;
		});
		if (had_empty) {
			frm.refresh_field("override_details");
		}
	}

	frappe.call({
		method: "artem_erp.artem_erp.doctype.employees_salary_component_override.employees_salary_component_override.get_eligible_components",
		args: {
			salary_structure: frm.doc.salary_structure,
			salary_structure_assignment: frm.doc.salary_structure_assignment,
			employee: frm.doc.employee,
		},
		callback: function (r) {
			if (r.message && r.message.length > 0) {
				const existing_comps = new Set(
					(frm.doc.override_details || []).map((d) => d.salary_component)
				);
				let added_count = 0;
				let updated_count = 0;

				r.message.forEach((comp) => {
					if (!existing_comps.has(comp.salary_component)) {
						let row = frm.add_child("override_details");
						row.salary_component = comp.salary_component;
						row.abbr = comp.abbr;
						row.component_type = comp.component_type;
						row.structure_amount = flt(comp.structure_amount);
						row.override_amount = 0.0;
						row.difference_amount = 0.0;
						added_count++;
					} else {
						(frm.doc.override_details || []).forEach((row) => {
							if (row.salary_component === comp.salary_component) {
								let new_struct = flt(comp.structure_amount);
								if (
									flt(row.structure_amount) !== new_struct ||
									!row.abbr ||
									!row.component_type
								) {
									row.abbr = comp.abbr;
									row.component_type = comp.component_type;
									row.structure_amount = new_struct;
									row.difference_amount = flt(row.override_amount)
										? flt(row.override_amount) - new_struct
										: 0.0;
									updated_count++;
								}
							}
						});
					}
				});

				frm.refresh_field("override_details");
				if (added_count > 0 || updated_count > 0) {
					let msgs = [];
					if (added_count > 0)
						msgs.push(__("Added {0} eligible components", [added_count]));
					if (updated_count > 0)
						msgs.push(
							__("Updated structure amounts for {0} components", [updated_count])
						);
					frappe.show_alert({
						message: msgs.join(", "),
						indicator: "green",
					});
				} else {
					frappe.show_alert({
						message: __("All eligible components are already added and up-to-date"),
						indicator: "blue",
					});
				}
			} else {
				frappe.msgprint({
					title: __("No Eligible Components"),
					message: __(
						"No components in Salary Structure {0} have 'Allow Override' enabled.",
						[frm.doc.salary_structure]
					),
					indicator: "orange",
				});
			}
		},
	});
}

function refresh_structure_amounts(frm) {
	if (!frm.doc.salary_structure) return;

	frappe.call({
		method: "artem_erp.artem_erp.doctype.employees_salary_component_override.employees_salary_component_override.get_eligible_components",
		args: {
			salary_structure: frm.doc.salary_structure,
			salary_structure_assignment: frm.doc.salary_structure_assignment,
			employee: frm.doc.employee,
		},
		callback: function (r) {
			if (r.message && r.message.length > 0 && frm.doc.override_details) {
				const map = {};
				r.message.forEach((c) => {
					map[c.salary_component] = c;
				});

				let updated = false;
				(frm.doc.override_details || []).forEach((row) => {
					let info = map[row.salary_component];
					if (info) {
						let new_struct = flt(info.structure_amount);
						if (
							flt(row.structure_amount) !== new_struct ||
							!row.abbr ||
							!row.component_type
						) {
							frappe.model.set_value(row.doctype, row.name, "abbr", info.abbr);
							frappe.model.set_value(
								row.doctype,
								row.name,
								"component_type",
								info.component_type
							);
							frappe.model.set_value(
								row.doctype,
								row.name,
								"structure_amount",
								new_struct
							);
							let diff = flt(row.override_amount)
								? flt(row.override_amount) - new_struct
								: 0.0;
							frappe.model.set_value(
								row.doctype,
								row.name,
								"difference_amount",
								diff
							);
							updated = true;
						}
					}
				});
				if (updated) {
					frm.refresh_field("override_details");
				}
			}
		},
	});
}

frappe.ui.form.on("Salary Component Override Detail", {
	salary_component: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.salary_component || !frm.doc.salary_structure) return;

		frappe.call({
			method: "artem_erp.artem_erp.doctype.employees_salary_component_override.employees_salary_component_override.get_eligible_components",
			args: {
				salary_structure: frm.doc.salary_structure,
				salary_structure_assignment: frm.doc.salary_structure_assignment,
				employee: frm.doc.employee,
			},
			callback: function (r) {
				if (r.message) {
					let comp_info = r.message.find(
						(c) => c.salary_component === row.salary_component
					);
					if (comp_info) {
						frappe.model.set_value(cdt, cdn, "abbr", comp_info.abbr);
						frappe.model.set_value(
							cdt,
							cdn,
							"component_type",
							comp_info.component_type
						);
						frappe.model.set_value(
							cdt,
							cdn,
							"structure_amount",
							flt(comp_info.structure_amount)
						);
						let diff = flt(row.override_amount)
							? flt(row.override_amount) - flt(comp_info.structure_amount)
							: 0.0;
						frappe.model.set_value(cdt, cdn, "difference_amount", diff);
					}
				}
			},
		});
	},

	override_amount: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let diff = flt(row.override_amount)
			? flt(row.override_amount) - flt(row.structure_amount)
			: 0.0;
		frappe.model.set_value(cdt, cdn, "difference_amount", diff);
	},

	structure_amount: function (frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let diff = flt(row.override_amount)
			? flt(row.override_amount) - flt(row.structure_amount)
			: 0.0;
		frappe.model.set_value(cdt, cdn, "difference_amount", diff);
	},
});
