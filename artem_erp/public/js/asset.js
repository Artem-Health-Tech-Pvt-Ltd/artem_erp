// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

// ─── CSS injected once ────────────────────────────────────────────────────────
frappe.dom.set_style(`
	.spec-required::after  { content: " *"; color: var(--red-500, #e03131); }
	.spec-hint             { font-size: 0.75rem; color: var(--text-muted); margin-top: 2px; }
	.grid-row[data-spec-mandatory="1"] .col.spec_name .static-area {
		font-weight: 600;
	}
`);

// ─── Main form handler ────────────────────────────────────────────────────────
frappe.ui.form.on("Asset", {
	setup(frm) {
		_patch_meta_dependencies();
		_bypass_purchase_validation(frm);
		frm.events.toggle_reference_doc = () => _bypass_purchase_validation(frm);
	},

	onload(frm) {
		_patch_meta_dependencies();
		_bypass_purchase_validation(frm);
		frm.events.toggle_reference_doc = () => _bypass_purchase_validation(frm);
		if (frm.cscript) {
			frm.cscript.toggle_reference_doc = () => _bypass_purchase_validation(frm);
		}
		_ensure_core_fields_visible(frm);
		_position_custodian_in_details(frm);
	},

	toggle_reference_doc(frm) {
		_bypass_purchase_validation(frm);
	},

	onload_post_render(frm) {
		_bypass_purchase_validation(frm);
		_ensure_core_fields_visible(frm);
		_position_custodian_in_details(frm);
	},

	refresh(frm) {
		_patch_meta_dependencies();
		_bypass_purchase_validation(frm);
		_hide_standard_fields(frm);
		_ensure_core_fields_visible(frm);
		_position_custodian_in_details(frm);

		if (frm.is_new()) {
			frm.set_df_property("asset_category", "read_only", 0);
			frm.set_df_property("asset_category", "reqd", 1);
			frm.set_df_property("custom_series_number", "read_only", 0);
			if (!frm.doc.custom_asset_status) {
				frm.set_value("custom_asset_status", frm.doc.custodian ? "Assigned" : "In Stock");
			}
		} else {
			// After save: lock asset_category and custom_series_number (ID must match prefix)
			frm.set_df_property("asset_category", "read_only", 1);
			frm.set_df_property("custom_series_number", "read_only", 1);

			// Standard maintenance module navigation shortcuts
			frm.add_custom_button(
				__("Asset Maintenance Logs"),
				() => {
					frappe.set_route("List", "Asset Maintenance Log", {
						custom_source_asset: frm.doc.name,
					});
				},
				__("Maintenance")
			);

			frm.add_custom_button(
				__("Asset Repairs"),
				() => {
					frappe.set_route("List", "Asset Repair", {
						asset: frm.doc.name,
					});
				},
				__("Maintenance")
			);

			frm.add_custom_button(
				__("Assignment History"),
				() => {
					frappe.set_route("List", "Asset Assignment History", {
						asset: frm.doc.name,
					});
				},
				__("Allocation")
			);

			frm.add_custom_button(
				__("Employee Allocation"),
				() => {
					if (frm.doc.custodian) {
						frappe.set_route("Form", "Employee Asset Allocation", frm.doc.custodian);
					} else {
						frappe.set_route("List", "Employee Asset Allocation");
					}
				},
				__("Allocation")
			);

			_render_assignment_history(frm);
		}

		if (frm.doc.custom_series_number) {
			_update_asset_number_preview(frm);
		}

		// Re-run after any async layout dependency refresh
		setTimeout(() => {
			_bypass_purchase_validation(frm);
			_ensure_core_fields_visible(frm);
			_position_custodian_in_details(frm);
			_decorate_spec_grid(frm);
		}, 100);
	},

	before_save(frm) {
		_bypass_purchase_validation(frm);
	},

	asset_category(frm) {
		if (!frm.doc.asset_category) {
			frm.set_value("custom_series_number", "");
			return;
		}

		// 1. Fetch next sequential number and auto-populate editable custom_series_number
		if (frm.is_new()) {
			frappe.call({
				method: "artem_erp.artem_erp.doctype.asset_category_specification.asset_category_specification.get_next_asset_number",
				args: { asset_category: frm.doc.asset_category },
				callback: function (r) {
					if (r.message && r.message.next_number) {
						frm.set_value("custom_series_number", r.message.next_number);
						_update_asset_number_preview(frm, r.message.prefix);
					}
				},
			});
		}

		// 2. Dynamic naming series
		_update_naming_series(frm);

		// 3. Load specs (with confirm if values already exist)
		_load_specs_from_category(frm);
	},

	custom_series_number(frm) {
		_update_asset_number_preview(frm);
	},

	custodian(frm) {
		if (frm.doc.custodian) {
			frappe.db.get_value(
				"Employee",
				frm.doc.custodian,
				["employee_name", "company_email", "personal_email", "prefered_email", "user_id"],
				(r) => {
					if (r) {
						frm.set_value("custom_employee_name", r.employee_name || "");
						const email =
							r.company_email ||
							r.personal_email ||
							r.user_id ||
							r.prefered_email ||
							"";
						frm.set_value("custom_employee_email", email);
					}
				}
			);
			if (!frm.doc.custom_assignment_date) {
				frm.set_value("custom_assignment_date", frappe.datetime.nowdate());
			}

			// When assigned to an employee, automatically set status to Assigned
			// (Takes it out of repair if it was in repair)
			frm.set_value("custom_asset_status", "Assigned");
		} else {
			// Cleared custodian: clear employee details and assignment date
			frm.set_value("custom_employee_name", "");
			frm.set_value("custom_employee_email", "");
			frm.set_value("custom_assignment_date", "");

			// If not in repair, it becomes In Stock
			if (frm.doc.custom_asset_status !== "In Repair") {
				frm.set_value("custom_asset_status", "In Stock");
			}
		}
	},

	custom_asset_status(frm) {
		const status = frm.doc.custom_asset_status;
		if (status === "Assigned" && !frm.doc.custodian) {
			frappe.show_alert({
				message: __("Please select a Custodian for Assigned status."),
				indicator: "orange",
			});
		} else if (status === "In Stock" && frm.doc.custodian) {
			frappe.confirm(
				__(
					"Setting status to <b>In Stock</b> will clear the current Custodian. Do you want to continue?"
				),
				() => {
					frm.set_value("custodian", "");
				},
				() => {
					// Revert status back
					frm.set_value("custom_asset_status", "Assigned");
				}
			);
		}
	},

	custom_maintenance_records_add(frm) {
		_calculate_maintenance_summary(frm);
	},

	custom_maintenance_records_remove(frm) {
		_calculate_maintenance_summary(frm);
	},

	validate(frm) {
		_bypass_purchase_validation(frm);

		// Client-side: collect mandatory spec rows with empty values
		let missing = (frm.doc.custom_specifications || [])
			.filter((r) => r.is_mandatory && !String(r.value || "").trim())
			.map((r) => r.spec_name);

		if (missing.length) {
			frappe.msgprint({
				title: __("Mandatory Specification Missing"),
				indicator: "red",
				message: __("Required specifications for <b>{0}</b>:<br><br><ul>{1}</ul>", [
					frm.doc.asset_category,
					missing.map((m) => `<li><b>${m}</b></li>`).join(""),
				]),
			});
			frappe.validated = false;
		}
	},
});

// ─── Child table handler (Value column edited) ────────────────────────────────
frappe.ui.form.on("Asset Specification", {
	value(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		_validate_spec_row_type(row);
	},
});

// ─── Maintenance Record child table handler ───────────────────────────────────
frappe.ui.form.on("Asset Maintenance Record", {
	cost(frm, cdt, cdn) {
		_calculate_maintenance_summary(frm);
	},
	custom_maintenance_records_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.maintenance_status) {
			frappe.model.set_value(cdt, cdn, "maintenance_status", "Planned");
		}
		_calculate_maintenance_summary(frm);
	},
	custom_maintenance_records_remove(frm, cdt, cdn) {
		_calculate_maintenance_summary(frm);
	},
	repair_required(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.repair_required) {
			if (row.maintenance_status === "Completed") {
				frappe.model.set_value(cdt, cdn, "maintenance_status", "In Progress");
			}
			frappe.show_alert({
				message: __(
					"Repair marked as required. You can click 'Create / Open Asset Repair' to manage breakdown repair details."
				),
				indicator: "blue",
			});
		}
	},
	maintenance_status(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.maintenance_status === "Completed" && !row.completion_date) {
			frappe.model.set_value(cdt, cdn, "completion_date", frappe.datetime.nowdate());
		}
	},
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const grid_row =
			frm.fields_dict.custom_maintenance_records?.grid?.grid_rows_by_docname[cdn];
		if (!grid_row || !grid_row.grid_form) return;

		const repair_wrapper = grid_row.grid_form.fields_dict["asset_repair"]?.$wrapper;
		if (repair_wrapper) {
			repair_wrapper.find(".create-repair-btn-container").remove();
			const has_repair = Boolean(row.asset_repair);
			const label = has_repair
				? __("Open Asset Repair ({0})", [row.asset_repair])
				: __("Create / Open Asset Repair");

			const $btn = $(`
				<div class="create-repair-btn-container" style="margin-top: 6px;">
					<button type="button" class="btn btn-xs ${
						has_repair ? "btn-info" : "btn-primary"
					} create-repair-btn">
						<i class="fa fa-wrench"></i> ${label}
					</button>
				</div>
			`);

			$btn.find("button").on("click", (e) => {
				e.preventDefault();
				_handle_create_or_open_repair(frm, row);
			});

			repair_wrapper.append($btn);
		}
	},
});

// ═════════════════════════════════════════════════════════════════════════════
// Helper functions
// ═════════════════════════════════════════════════════════════════════════════

function _patch_meta_dependencies() {
	// Strip item_code and tab dependencies so Frappe's layout engine doesn't hide core fields
	[
		"asset_category",
		"asset_name",
		"custom_series_number",
		"custom_asset_status",
		"custodian",
		"custom_employee_name",
		"custom_employee_email",
		"custom_assignment_date",
	].forEach((fieldname) => {
		const meta_df = frappe.meta.get_docfield("Asset", fieldname);
		if (meta_df) {
			meta_df.depends_on = "";
			meta_df.mandatory_depends_on = "";
			meta_df.read_only_depends_on = "";
			if (fieldname === "asset_category") {
				meta_df.fetch_from = "";
			}
		}
		if (frappe.meta.docfield_map && frappe.meta.docfield_map["Asset"]) {
			const mdf = frappe.meta.docfield_map["Asset"][fieldname];
			if (mdf) {
				mdf.depends_on = "";
				mdf.mandatory_depends_on = "";
				mdf.read_only_depends_on = "";
				if (fieldname === "asset_category") {
					mdf.fetch_from = "";
				}
			}
		}
	});
}

function _bypass_purchase_validation(frm) {
	// 1. Mark as Existing Asset so standard ERPNext asset.js never sets purchase receipt/invoice as mandatory
	if (frm.doc.asset_type !== "Existing Asset") {
		frm.set_value("asset_type", "Existing Asset");
	}
	frm.doc.is_existing_asset = 1;

	// 2. Ensure purchase_date is populated so standard DB validation passes
	if (!frm.doc.purchase_date) {
		const def_date = frm.doc.custom_warranty_start || frappe.datetime.nowdate();
		frm.set_value("purchase_date", def_date);
	}

	// 3. Force non-mandatory on all purchase reference fields
	const purchase_fields = [
		"purchase_receipt",
		"purchase_receipt_item",
		"purchase_invoice",
		"purchase_invoice_item",
		"purchase_date",
	];

	purchase_fields.forEach((fn) => {
		const df = frappe.meta.get_docfield("Asset", fn);
		if (df) {
			df.reqd = 0;
			df.mandatory_depends_on = "";
		}
		if (frm.fields_dict && frm.fields_dict[fn] && frm.fields_dict[fn].df) {
			frm.fields_dict[fn].df.reqd = 0;
			frm.fields_dict[fn].df.mandatory_depends_on = "";
		}
		frm.toggle_reqd(fn, 0);
	});
}

function _ensure_core_fields_visible(frm) {
	const core_fields = [
		"asset_category",
		"asset_name",
		"custom_series_number",
		"custom_asset_status",
		"custodian",
		"custom_employee_name",
		"custom_employee_email",
		"custom_assignment_date",
	];

	core_fields.forEach((fieldname) => {
		const df = frappe.meta.get_docfield("Asset", fieldname);
		if (df) {
			df.depends_on = "";
			df.mandatory_depends_on = "";
			df.read_only_depends_on = "";
			df.hidden = 0;
			if (fieldname === "asset_category") {
				df.fetch_from = "";
				df.reqd = 1;
				df.read_only = frm.is_new() ? 0 : 1;
			}
			if (fieldname === "custom_series_number") {
				df.read_only = frm.is_new() ? 0 : 1;
			}
			if (fieldname === "custodian") {
				df.read_only = 0;
			}
			if (fieldname === "custom_asset_status") {
				df.options = "In Stock\nAssigned\nIn Repair";
			}
		}

		const field = frm.get_field(fieldname);
		if (field) {
			if (field.df) {
				field.df.depends_on = "";
				field.df.mandatory_depends_on = "";
				field.df.read_only_depends_on = "";
				field.df.hidden_due_to_dependency = false;
				field.df.hidden = 0;
				if (fieldname === "asset_category") {
					field.df.fetch_from = "";
					field.df.reqd = 1;
					field.df.read_only = frm.is_new() ? 0 : 1;
				}
				if (fieldname === "custom_series_number") {
					field.df.read_only = frm.is_new() ? 0 : 1;
				}
				if (fieldname === "custodian") {
					field.df.read_only = 0;
				}
				if (fieldname === "custom_asset_status") {
					field.df.options = "In Stock\nAssigned\nIn Repair";
				}
			}
			if (field.$wrapper) {
				field.$wrapper.removeClass("hide-control");
				field.$wrapper.show();
			}
			field.refresh();
		}

		frm.toggle_display(fieldname, true);
	});
}

function _position_custodian_in_details(frm) {
	// 1. If form has tab panes, ensure Custodian, Specifications, Warranty, and Maintenance
	// reside inside the first tab ('Details') and never in 'More Info'.
	if (frm.layout && frm.layout.tabs && frm.layout.tabs.length > 0) {
		const $details_tab = frm.layout.tabs[0].$wrapper;
		if ($details_tab && $details_tab.length) {
			const it_fields = [
				"custom_it_details_section",
				"custom_series_number",
				"custom_asset_status",
				"custodian",
				"custom_employee_name",
				"custom_employee_email",
				"custom_assignment_date",
				"custom_spec_section",
				"custom_specifications",
				"custom_warranty_billing_section",
				"custom_bill_copy",
				"custom_warranty_billing_col_break",
				"custom_warranty_start",
				"custom_warranty_expiry",
				"custom_warranty_document",
				"custom_maintenance_section",
				"custom_maintenance_count",
				"custom_column_break_maint",
				"custom_total_maintenance_cost",
				"custom_maintenance_section_table",
				"custom_maintenance_records",
			];

			it_fields.forEach((fn) => {
				const f = frm.get_field(fn);
				if (f && f.$wrapper && !$.contains($details_tab[0], f.$wrapper[0])) {
					$details_tab.append(f.$wrapper);
				}
			});
		}
	}

	// 2. Position Custodian and its related details immediately before the Specification field
	const spec_sec = frm.get_field("custom_spec_section");
	if (spec_sec && spec_sec.$wrapper) {
		const pre_spec_fields = [
			"custom_series_number",
			"custom_asset_status",
			"custodian",
			"custom_employee_name",
			"custom_employee_email",
			"custom_assignment_date",
		];

		pre_spec_fields.forEach((fn) => {
			const f = frm.get_field(fn);
			if (f && f.$wrapper && spec_sec.$wrapper) {
				f.$wrapper.insertBefore(spec_sec.$wrapper);
			}
		});
	}
}

function _hide_standard_fields(frm) {
	// Asset Type
	frm.toggle_display("asset_type", false);

	// Insurance section
	frm.toggle_display(
		[
			"insurance_details",
			"section_break_insurance",
			"policy_number",
			"insurer",
			"insured_value",
			"insurance_start_date",
			"insurance_end_date",
			"comprehensive_insurance",
		],
		false
	);

	// Additional / accounting info
	frm.toggle_display(
		[
			"additional_info_section",
			"more_info",
			"accounting_dimensions_section",
			"branch",
			"customer",
			"asset_owner",
		],
		false
	);

	// Standard purchase fields (we use custom_bill_copy instead)
	frm.toggle_display(
		[
			"purchase_receipt",
			"purchase_receipt_item",
			"purchase_invoice",
			"purchase_invoice_item",
			"purchase_date",
			"supplier",
			"is_existing_asset",
		],
		false
	);

	// Depreciation
	frm.toggle_display(
		[
			"depreciation_section",
			"calculate_depreciation",
			"depreciation_schedule_section",
			"schedules",
		],
		false
	);

	// Naming / item (auto-managed)
	frm.toggle_display(["naming_series", "item_code", "item_name", "custom_device_id"], false);

	// Ensure custodian and custom details are explicitly visible
	frm.toggle_display(
		[
			"custodian",
			"custom_asset_status",
			"custom_employee_name",
			"custom_employee_email",
			"custom_assignment_date",
		],
		true
	);
}

function _update_naming_series(frm) {
	frappe.db.get_value(
		"Asset Category",
		frm.doc.asset_category,
		["custom_asset_series", "custom_series_prefix", "custom_default_item"],
		(r) => {
			if (!r) return;

			// Series
			let series = r.custom_asset_series || "";
			if (!series && r.custom_series_prefix) {
				series = `${r.custom_series_prefix.trim().toUpperCase()}-.####`;
			}
			if (series) {
				let opts = series
					.split(/[\n,]/)
					.map((s) => s.trim())
					.filter(Boolean);
				if (opts.length) {
					frm.set_df_property("naming_series", "options", opts);
					if (!opts.includes(frm.doc.naming_series)) {
						frm.set_value("naming_series", opts[0]);
					}
				}
			}

			// Auto-fill item_code
			if (r.custom_default_item && !frm.doc.item_code) {
				frm.set_value("item_code", r.custom_default_item);
			}
		}
	);
}

function _load_specs_from_category(frm) {
	frappe.model.with_doc("Asset Category", frm.doc.asset_category, () => {
		const cat = frappe.get_doc("Asset Category", frm.doc.asset_category);
		const specs = cat.custom_specifications || [];

		const populate = (spec_rows) => {
			frm.clear_table("custom_specifications");

			spec_rows.forEach((row) => {
				const child = frm.add_child("custom_specifications");
				child.spec_name = row.spec_name || "";
				child.data_type = row.data_type || "Data";
				child.options = row.options || "";
				child.is_mandatory = row.is_mandatory ? 1 : 0;
				child.value = row.default_value || "";
			});

			frm.refresh_field("custom_specifications");
			setTimeout(() => _decorate_spec_grid(frm), 150);

			if (!spec_rows.length) {
				frappe.show_alert({
					message: __("No specification template found for category {0}.", [
						frm.doc.asset_category,
					]),
					indicator: "orange",
				});
			}
		};

		_confirm_if_has_values(frm, () => populate(specs));
	});
}

function _confirm_if_has_values(frm, cb) {
	const has_values = (frm.doc.custom_specifications || []).some(
		(r) => r.value && String(r.value).trim()
	);

	if (has_values) {
		frappe.confirm(
			__(
				"Changing the category will reset the Specifications table with defaults for <b>{0}</b>. Continue?",
				[frm.doc.asset_category]
			),
			cb
		);
	} else {
		cb();
	}
}

function _decorate_spec_grid(frm) {
	const grid =
		frm.fields_dict["custom_specifications"] && frm.fields_dict["custom_specifications"].grid;
	if (!grid) return;

	// Disable add/delete row buttons — users only fill the Value column
	grid.cannot_add_rows = true;
	grid.wrapper.find(".grid-add-row, .btn-open-row .fa-trash").hide();

	grid.grid_rows.forEach((grid_row) => {
		const doc = grid_row.doc;
		if (!doc) return;

		const $row = grid_row.wrapper;

		// Red asterisk on mandatory specs
		if (doc.is_mandatory) {
			$row.attr("data-spec-mandatory", "1");
			$row.find(".col[data-fieldname='spec_name'] .static-area").addClass("spec-required");
		}

		// Type hints in the Value cell
		let hint = "";
		if (doc.data_type === "Int") hint = __("Number expected");
		if (doc.data_type === "Float") hint = __("Decimal number expected");
		if (doc.data_type === "Date") hint = __("Date (YYYY-MM-DD)");
		if (doc.data_type === "Select" && doc.options) {
			hint = doc.options.split("\n").filter(Boolean).join(" / ");
		}
		if (hint) {
			const $val_cell = $row.find(".col[data-fieldname='value']");
			if ($val_cell.length && !$val_cell.find(".spec-hint").length) {
				$val_cell.append(`<div class="spec-hint">${hint}</div>`);
			}
		}
	});
}

function _validate_spec_row_type(row) {
	const val = String(row.value || "").trim();
	if (!val) return;

	const dt = row.data_type || "Data";
	let err = "";

	if (dt === "Int" && !/^-?\d+$/.test(val)) {
		err = __("'{0}' must be a whole number.", [row.spec_name]);
	} else if (dt === "Float" && isNaN(parseFloat(val))) {
		err = __("'{0}' must be a number.", [row.spec_name]);
	} else if (dt === "Date" && isNaN(Date.parse(val))) {
		err = __("'{0}' must be a valid date (YYYY-MM-DD).", [row.spec_name]);
	} else if (dt === "Select" && row.options) {
		const opts = row.options
			.split("\n")
			.map((o) => o.trim().toLowerCase())
			.filter(Boolean);
		if (opts.length && !opts.includes(val.toLowerCase())) {
			err = __("'{0}' must be one of: {1}", [
				row.spec_name,
				row.options.split("\n").filter(Boolean).join(", "),
			]);
		}
	}
	if (err) {
		frappe.show_alert({ message: err, indicator: "red" });
	}
}

function _calculate_maintenance_summary(frm) {
	const records = frm.doc.custom_maintenance_records || [];
	const count = records.length;
	const total_cost = records.reduce((acc, row) => acc + (flt(row.cost) || 0), 0);
	frm.set_value("custom_maintenance_count", count);
	frm.set_value("custom_total_maintenance_cost", total_cost);
}

function _update_asset_number_preview(frm, category_prefix) {
	let num = (frm.doc.custom_series_number || "").toString().trim();
	if (!num || !frm.doc.asset_category) {
		frm.set_df_property(
			"custom_series_number",
			"description",
			__("Sequential number for this asset (e.g. 001, 046).")
		);
		return;
	}

	if (category_prefix) {
		frm.set_df_property(
			"custom_series_number",
			"description",
			__("Final Asset ID will be: <b>{0}-{1}</b>", [category_prefix, num])
		);
	} else {
		frappe.db.get_value(
			"Asset Category",
			frm.doc.asset_category,
			["custom_series_prefix", "custom_asset_series"],
			(r) => {
				let prefix = (r && r.custom_series_prefix) || "";
				if (!prefix && r && r.custom_asset_series) {
					prefix = r.custom_asset_series.split("-")[0];
				}
				if (!prefix) prefix = frm.doc.asset_category;
				frm.set_df_property(
					"custom_series_number",
					"description",
					__("Final Asset ID will be: <b>{0}-{1}</b>", [prefix, num])
				);
			}
		);
	}
}

function _handle_create_or_open_repair(frm, row) {
	if (row.asset_repair) {
		frappe.set_route("Form", "Asset Repair", row.asset_repair);
		return;
	}

	if (frm.is_new() || !row.name || String(row.name).startsWith("new-")) {
		frappe.msgprint({
			title: __("Save Required"),
			indicator: "orange",
			message: __("Please save the Asset first before creating an Asset Repair document."),
		});
		return;
	}

	frappe.call({
		method: "artem_erp.api.asset_maintenance_sync.create_or_open_asset_repair",
		args: {
			asset_name: frm.doc.name,
			row_id: row.name,
		},
		freeze: true,
		freeze_message: __("Preparing Asset Repair..."),
		callback: function (r) {
			if (r.message && r.message.repair_name) {
				frm.reload_doc();
				frappe.set_route("Form", "Asset Repair", r.message.repair_name);
			}
		},
	});
}

function _render_assignment_history(frm) {
	if (frm.is_new() || !frm.doc.name) {
		if (frm.fields_dict.custom_assignment_history_html) {
			frm.fields_dict.custom_assignment_history_html.$wrapper.html(
				`<div class="text-muted" style="padding: 10px;">${__(
					"Assignment history will be recorded after the asset is saved."
				)}</div>`
			);
		}
		return;
	}

	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Asset Assignment History",
			filters: { asset: frm.doc.name },
			fields: [
				"name",
				"asset",
				"previous_custodian",
				"previous_custodian_name",
				"employee",
				"employee_id",
				"employee_name",
				"assignment_date",
				"return_date",
				"assignment_status",
				"asset_movement",
				"assigned_by",
				"returned_by",
				"remarks",
			],
			order_by: "creation desc",
			limit_page_length: 50,
		},
		callback(r) {
			const rows = r.message || [];
			if (!frm.fields_dict.custom_assignment_history_html) return;

			let html = `
				<div style="border: 1px solid var(--border-color); border-radius: var(--border-radius); overflow-x: auto; margin-top: 5px;">
					<table class="table table-bordered table-hover" style="margin-bottom: 0;">
						<thead style="background: var(--bg-light-gray);">
							<tr>
								<th>${__("Previous Custodian")}</th>
								<th>${__("Custodian / Employee")}</th>
								<th>${__("Movement Ref")}</th>
								<th>${__("Assignment Date")}</th>
								<th>${__("Return Date")}</th>
								<th>${__("Status")}</th>
								<th>${__("Logged By")}</th>
								<th>${__("Remarks")}</th>
							</tr>
						</thead>
						<tbody>
			`;

			if (!rows.length) {
				html += `
					<tr>
						<td colspan="8" class="text-center text-muted" style="padding: 20px;">
							${__("No assignment history recorded for this asset yet.")}
						</td>
					</tr>
				`;
			} else {
				rows.forEach((row) => {
					const is_assigned = row.assignment_status === "Assigned";
					const status_badge = is_assigned
						? `<span class="indicator-pill green">${__("Assigned")}</span>`
						: `<span class="indicator-pill blue">${__("Returned")}</span>`;

					const prev_cust = row.previous_custodian
						? `<a href="/app/employee/${encodeURIComponent(
								row.previous_custodian
						  )}"><b>${frappe.utils.escape_html(
								row.previous_custodian_name || row.previous_custodian
						  )}</b></a>`
						: `<span class="text-muted">-</span>`;

					const curr_cust = row.employee
						? `<a href="/app/employee/${encodeURIComponent(
								row.employee
						  )}"><b>${frappe.utils.escape_html(
								row.employee_name || row.employee
						  )}</b></a>`
						: `<span class="text-muted">-</span>`;

					const movement_ref = row.asset_movement
						? `<a href="/app/asset-movement/${encodeURIComponent(
								row.asset_movement
						  )}" class="badge badge-info">${frappe.utils.escape_html(
								row.asset_movement
						  )}</a>`
						: `<span class="text-muted">-</span>`;

					const actor =
						(is_assigned ? row.assigned_by : row.returned_by || row.assigned_by) ||
						"-";

					html += `
						<tr>
							<td>${prev_cust}</td>
							<td>${curr_cust}</td>
							<td>${movement_ref}</td>
							<td>${row.assignment_date ? frappe.datetime.str_to_user(row.assignment_date) : "-"}</td>
							<td>${
								row.return_date
									? frappe.datetime.str_to_user(row.return_date)
									: "<span class='text-muted'>Active</span>"
							}</td>
							<td>${status_badge}</td>
							<td>${frappe.utils.escape_html(actor)}</td>
							<td>${frappe.utils.escape_html(row.remarks || "-")}</td>
						</tr>
					`;
				});
			}

			html += `</tbody></table></div>`;
			frm.fields_dict.custom_assignment_history_html.$wrapper.html(html);
		},
	});
}
