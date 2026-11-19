// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Asset Allocation", {
	refresh(frm) {
		_add_allocation_buttons(frm);
		_filter_items_display(frm);
	},

	employee(frm) {
		if (frm.doc.employee) {
			if (frm.is_new()) {
				// Check if allocation document already exists for this employee
				frappe.db.get_value("Employee Asset Allocation", frm.doc.employee, "name", (r) => {
					if (r && r.name && r.name !== frm.doc.name) {
						frappe.set_route("Form", "Employee Asset Allocation", r.name);
					}
				});
			}

			frappe.db.get_value(
				"Employee",
				frm.doc.employee,
				["name", "employee_name", "company_email", "personal_email", "user_id", "prefered_email", "department", "designation", "company"],
				(r) => {
					if (r) {
						frm.set_value("employee_id", r.name);
						frm.set_value("employee_name", r.employee_name || "");
						const email = r.company_email || r.personal_email || r.user_id || r.prefered_email || "";
						frm.set_value("employee_email", email);
						frm.set_value("department", r.department || "");
						frm.set_value("designation", r.designation || "");
						frm.set_value("company", r.company || "");
					}
				}
			);
		}
	},
});

function _add_allocation_buttons(frm) {
	if (!frm.doc.employee) return;

	// 1. Assign Assets Button
	frm.add_custom_button(__("Assign Assets"), () => {
		_show_assign_assets_dialog(frm);
	}, __("Actions")).addClass("btn-primary");

	// 2. Return Asset Button
	const has_assigned = (frm.doc.items || []).some(row => row.allocation_status === "Assigned");
	if (has_assigned) {
		frm.add_custom_button(__("Return Assets"), () => {
			_show_return_assets_dialog(frm);
		}, __("Actions")).addClass("btn-danger");
	}
}

function _show_assign_assets_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Select Assets to Assign to {0}", [frm.doc.employee_name || frm.doc.employee]),
		size: "large",
		fields: [
			{
				fieldname: "category_filter",
				fieldtype: "Link",
				options: "Asset Category",
				label: __("Filter by Category"),
				change: () => _reload_available_assets_grid(dialog),
			},
			{
				fieldname: "search_term",
				fieldtype: "Data",
				label: __("Search Asset ID / Name"),
				change: () => _reload_available_assets_grid(dialog),
			},
			{
				fieldname: "assets_html",
				fieldtype: "HTML",
			},
		],
		primary_action_label: __("Assign Selected Assets"),
		primary_action(data) {
			const selected = [];
			dialog.$wrapper.find('input[type="checkbox"][name="selected_asset"]:checked').each(function () {
				selected.push($(this).val());
			});

			if (!selected.length) {
				frappe.msgprint({
					title: __("No Assets Selected"),
					indicator: "orange",
					message: __("Please select at least one asset to assign."),
				});
				return;
			}

			frappe.call({
				method: "artem_erp.artem_erp.doctype.employee_asset_allocation.employee_asset_allocation.assign_assets_to_employee",
				args: {
					employee: frm.doc.employee,
					asset_names: selected,
				},
				freeze: true,
				freeze_message: __("Assigning selected assets..."),
				callback(r) {
					if (!r.exc) {
						dialog.hide();
						frappe.show_alert({
							message: r.message.message || __("Assets assigned successfully!"),
							indicator: "green",
						});
						frm.reload_doc();
					}
				},
			});
		},
	});

	dialog.show();
	_reload_available_assets_grid(dialog);
}

function _reload_available_assets_grid(dialog) {
	const category = dialog.get_value("category_filter");
	const search_term = dialog.get_value("search_term");

	frappe.call({
		method: "artem_erp.artem_erp.doctype.employee_asset_allocation.employee_asset_allocation.get_available_assets",
		args: {
			category: category,
			search_term: search_term,
		},
		callback(r) {
			const assets = r.message || [];
			let html = `
				<div style="max-height: 380px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius);">
					<table class="table table-bordered table-hover" style="margin-bottom: 0;">
						<thead style="background: var(--bg-light-gray); position: sticky; top: 0; z-index: 1;">
							<tr>
								<th style="width: 40px; text-align: center;">
									<input type="checkbox" id="select_all_assets" />
								</th>
								<th>${__("Asset ID")}</th>
								<th>${__("Asset Name")}</th>
								<th>${__("Category")}</th>
								<th>${__("Status")}</th>
								<th>${__("Location")}</th>
							</tr>
						</thead>
						<tbody>
			`;

			if (!assets.length) {
				html += `
					<tr>
						<td colspan="6" class="text-center text-muted" style="padding: 24px;">
							${__("No In-Stock assets available for assignment matching filters.")}
						</td>
					</tr>
				`;
			} else {
				assets.forEach(a => {
					html += `
						<tr>
							<td style="text-align: center;">
								<input type="checkbox" name="selected_asset" value="${frappe.utils.escape_html(a.name)}" />
							</td>
							<td><b>${frappe.utils.escape_html(a.name)}</b></td>
							<td>${frappe.utils.escape_html(a.asset_name || "")}</td>
							<td><span class="badge badge-secondary">${frappe.utils.escape_html(a.asset_category || "")}</span></td>
							<td><span class="indicator-pill green">${frappe.utils.escape_html(a.custom_asset_status || "In Stock")}</span></td>
							<td>${frappe.utils.escape_html(a.location || "")}</td>
						</tr>
					`;
				});
			}

			html += `</tbody></table></div>`;
			dialog.fields_dict.assets_html.$wrapper.html(html);

			// Select All binding
			dialog.$wrapper.find("#select_all_assets").on("change", function () {
				const is_checked = $(this).is(":checked");
				dialog.$wrapper.find('input[name="selected_asset"]').prop("checked", is_checked);
			});
		},
	});
}

function _show_return_assets_dialog(frm) {
	const assigned_rows = (frm.doc.items || []).filter(r => r.allocation_status === "Assigned");
	if (!assigned_rows.length) {
		frappe.msgprint(__("No currently assigned assets to return."));
		return;
	}

	let html = `
		<div style="max-height: 250px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius); margin-bottom: 15px;">
			<table class="table table-bordered table-hover" style="margin-bottom: 0;">
				<thead style="background: var(--bg-light-gray);">
					<tr>
						<th style="width: 40px; text-align: center;"><input type="checkbox" id="select_all_return" /></th>
						<th>${__("Asset ID")}</th>
						<th>${__("Asset Name")}</th>
						<th>${__("Category")}</th>
						<th>${__("Location")}</th>
						<th>${__("Assignment Date")}</th>
					</tr>
				</thead>
				<tbody>
	`;

	assigned_rows.forEach(r => {
		html += `
			<tr>
				<td style="text-align: center;">
					<input type="checkbox" name="return_asset" value="${frappe.utils.escape_html(r.asset)}" />
				</td>
				<td><b>${frappe.utils.escape_html(r.asset)}</b></td>
				<td>${frappe.utils.escape_html(r.asset_name || "")}</td>
				<td>${frappe.utils.escape_html(r.asset_category || "")}</td>
				<td>${frappe.utils.escape_html(r.location || "")}</td>
				<td>${r.assignment_date ? frappe.datetime.str_to_user(r.assignment_date) : "-"}</td>
			</tr>
		`;
	});

	html += `</tbody></table></div>`;

	const dialog = new frappe.ui.Dialog({
		title: __("Return Assets from {0}", [frm.doc.employee_name || frm.doc.employee]),
		fields: [
			{
				fieldname: "return_html",
				fieldtype: "HTML",
			},
			{
				fieldname: "remarks",
				fieldtype: "Small Text",
				label: __("Return Remarks / Condition"),
			},
		],
		primary_action_label: __("Confirm Return"),
		primary_action(data) {
			const selected = [];
			dialog.$wrapper.find('input[type="checkbox"][name="return_asset"]:checked').each(function () {
				selected.push($(this).val());
			});

			if (!selected.length) {
				frappe.msgprint(__("Please select at least one asset to return."));
				return;
			}

			frappe.call({
				method: "artem_erp.artem_erp.doctype.employee_asset_allocation.employee_asset_allocation.return_assets_from_employee",
				args: {
					employee: frm.doc.employee,
					asset_names: selected,
					remarks: data.remarks || "",
				},
				freeze: true,
				freeze_message: __("Processing asset return..."),
				callback(r) {
					if (!r.exc) {
						dialog.hide();
						frappe.show_alert({
							message: r.message.message || __("Assets returned successfully!"),
							indicator: "green",
						});
						frm.reload_doc();
					}
				},
			});
		},
	});

	dialog.show();
	dialog.fields_dict.return_html.$wrapper.html(html);

	dialog.$wrapper.find("#select_all_return").on("change", function () {
		const is_checked = $(this).is(":checked");
		dialog.$wrapper.find('input[name="return_asset"]').prop("checked", is_checked);
	});
}

function _filter_items_display(frm) {
	// Visual indicator styling in child table rows
	(frm.doc.items || []).forEach(row => {
		const grid_row = frm.fields_dict.items?.grid?.grid_rows_by_docname[row.name];
		if (grid_row && grid_row.row) {
			if (row.allocation_status === "Returned") {
				grid_row.row.css("opacity", "0.65");
			} else {
				grid_row.row.css("font-weight", "500");
			}
		}
	});
}

