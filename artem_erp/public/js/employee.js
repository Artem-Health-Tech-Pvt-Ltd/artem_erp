// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee", {
	onload(frm) {
		_ensure_assets_section_visible(frm);
		if (
			!frm.is_new() &&
			frm.doc.name &&
			(!frm.doc.custom_assigned_assets || frm.doc.custom_assigned_assets.length === 0)
		) {
			_sync_assigned_assets(frm);
		}
	},

	onload_post_render(frm) {
		_ensure_assets_section_visible(frm);
	},

	refresh(frm) {
		_ensure_assets_section_visible(frm);
		setTimeout(() => {
			_ensure_assets_section_visible(frm);
		}, 100);
		setTimeout(() => {
			_ensure_assets_section_visible(frm);
		}, 300);
	},
});

frappe.ui.form.on("Employee Assigned Asset", {
	asset(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.asset) return;

		frappe.db.get_value(
			"Asset",
			row.asset,
			[
				"asset_name",
				"asset_category",
				"location",
				"custom_assignment_date",
				"status",
				"custom_asset_status",
			],
			(r) => {
				if (r) {
					frappe.model.set_value(cdt, cdn, "asset_name", r.asset_name || "");
					frappe.model.set_value(cdt, cdn, "asset_category", r.asset_category || "");
					frappe.model.set_value(cdt, cdn, "location", r.location || "");
					frappe.model.set_value(
						cdt,
						cdn,
						"assignment_date",
						r.custom_assignment_date || frappe.datetime.get_today()
					);
					const st =
						r.custom_asset_status ||
						(r.status === "In Stock" ? "Assigned" : r.status) ||
						"Assigned";
					frappe.model.set_value(cdt, cdn, "status", st);
				}
			}
		);
	},
});

function _ensure_assets_section_visible(frm) {
	if (!frm || !frm.fields_dict) return;

	// 1. Unhide fields via Frappe API
	["custom_assigned_assets_section", "custom_assigned_assets"].forEach((fn) => {
		const df = frappe.meta.get_docfield("Employee", fn);
		if (df) {
			df.hidden = 0;
			df.depends_on = "";
			df.mandatory_depends_on = "";
		}
		frm.set_df_property(fn, "hidden", 0);
	});
	frm.toggle_display("custom_assigned_assets", true);

	// 2. DOM level: locate the section and ensure it is in Overview tab right after Company Details
	const $wrapper = frm.layout ? frm.layout.wrapper : $(frm.wrapper);
	const $sec = $wrapper.find('.form-section[data-fieldname="custom_assigned_assets_section"]');
	const $company_sec = $wrapper.find('.form-section[data-fieldname="company_details_section"]');

	if ($sec.length) {
		if ($company_sec.length && !$sec.prev().is($company_sec)) {
			$sec.insertAfter($company_sec);
		}
		$sec.removeClass("empty-section hide-control hide").show();
		$sec.css("display", "block");
		$sec.find(".section-head").show();
		$sec.find(".section-body").removeClass("hide").show();
	}

	const tbl = frm.get_field("custom_assigned_assets");
	if (tbl && tbl.$wrapper) {
		tbl.$wrapper.removeClass("hide-control hide").show();
		tbl.$wrapper.css("display", "block");
		tbl.refresh();
	}
}

function _sync_assigned_assets(frm) {
	const was_dirty = frm.is_dirty();
	frappe.call({
		method: "artem_erp.doc_events.employee.get_employee_assigned_assets",
		args: {
			employee: frm.doc.name,
		},
		callback: function (r) {
			if (r.message && r.message.length) {
				const existing_assets = (frm.doc.custom_assigned_assets || []).map(
					(row) => row.asset
				);
				const fetched_assets = r.message.map((row) => row.name);

				const has_changes =
					existing_assets.length !== fetched_assets.length ||
					!existing_assets.every((a, i) => a === fetched_assets[i]);

				if (has_changes) {
					frm.clear_table("custom_assigned_assets");
					r.message.forEach((row) => {
						const child = frm.add_child("custom_assigned_assets");
						child.asset = row.name;
						child.asset_name = row.asset_name || "";
						child.asset_category = row.asset_category || "";
						child.location = row.location || "";
						child.assignment_date = row.custom_assignment_date || "";
						child.status = row.custom_asset_status || "Assigned";
					});
					frm.refresh_field("custom_assigned_assets");

					if (!was_dirty) {
						frm.dirty(false);
						if (frm.doc) {
							delete frm.doc.__unsaved;
						}
						if (frm.page && frm.page.clear_indicator) {
							frm.page.clear_indicator();
						}
					}
				}
			}
		},
	});
}
