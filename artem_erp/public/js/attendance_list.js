frappe.provide("frappe.listview_settings");

frappe.listview_settings["Attendance"] = frappe.listview_settings["Attendance"] || {};

// Hide ID (Name) column
frappe.listview_settings["Attendance"].hide_name_column = true;

// Ensure required fields are always fetched in list view
const required_fields = [
	"status",
	"attendance_date",
	"custom_penalty",
	"attendance_request",
	"custom_is_partial_day",
	"custom_partial_day_type",
	"custom_partial_day_duration",
];
if (!frappe.listview_settings["Attendance"].add_fields) {
	frappe.listview_settings["Attendance"].add_fields = required_fields;
} else {
	required_fields.forEach((field) => {
		if (!frappe.listview_settings["Attendance"].add_fields.includes(field)) {
			frappe.listview_settings["Attendance"].add_fields.push(field);
		}
	});
}

// Global cache for Attendance Request reasons
window.artem_attendance_requests_cache = window.artem_attendance_requests_cache || {};

// Add penalty indicator badge, OD badge, RG badge, and Partial Day badge on the row
const existing_attendance_refresh = frappe.listview_settings["Attendance"].refresh;
frappe.listview_settings["Attendance"].refresh = function (list_view) {
	if (existing_attendance_refresh) {
		existing_attendance_refresh(list_view);
	}

	// Ensure Employee Name column has sufficient width so badges never overlap or hide under column 2
	if (list_view.column_max_widths) {
		list_view.column_max_widths["employee_name"] = Math.max(
			list_view.column_max_widths["employee_name"] || 0,
			280
		);
		list_view.apply_column_widths();
	}

	// Inject custom CSS styling for badges and column widths
	if (!$("#attendance-badges-list-style").length) {
		$(`<style id="attendance-badges-list-style">
			/* Give Employee Name column ample space so badges never hide under Status column */
			.list-row-col.list-subject,
			.list-row-head .list-header-subject,
			.list-row-col[data-fieldname="employee_name"] {
				min-width: 270px !important;
				flex: 1 0 270px !important;
			}

			.list-row-col.list-subject {
				display: inline-flex !important;
				align-items: center !important;
				overflow: visible !important;
			}

			.list-row-col.list-subject .level-item {
				display: inline-flex !important;
				align-items: center !important;
				min-width: 0 !important;
				overflow: visible !important;
				max-width: 100% !important;
			}

			.list-row-col.list-subject a {
				overflow: hidden !important;
				text-overflow: ellipsis !important;
				white-space: nowrap !important;
				min-width: 0 !important;
			}

			.attendance-penalty-badge {
				background-color: #e24c4c !important;
				color: #ffffff !important;
				font-size: 11px;
				font-weight: 600;
				padding: 2px 8px;
				border-radius: 10px;
				display: inline-flex;
				align-items: center;
				justify-content: center;
				margin-right: 6px;
				margin-left: 2px;
				vertical-align: middle;
				line-height: 1.3;
				white-space: nowrap;
				flex-shrink: 0;
			}
			.attendance-penalty-badge * {
				color: #ffffff !important;
			}

			.attendance-od-badge {
				background-color: #f8dd71c2 !important;
				color: #000000 !important;
				font-size: 11px;
				font-weight: 700;
				padding: 2px 8px;
				border-radius: 10px;
				display: inline-flex;
				align-items: center;
				justify-content: center;
				margin-right: 6px;
				margin-left: 2px;
				vertical-align: middle;
				line-height: 1.3;
				white-space: nowrap;
				flex-shrink: 0;
			}
			.attendance-od-badge * {
				color: #000000 !important;
			}

			.attendance-rg-badge {
				background-color: #82c7e5e0 !important;
				color: #133946 !important;
				font-size: 11px;
				font-weight: 700;
				padding: 2px 8px;
				border-radius: 10px;
				display: inline-flex;
				align-items: center;
				justify-content: center;
				margin-right: 6px;
				margin-left: 2px;
				vertical-align: middle;
				line-height: 1.3;
				white-space: nowrap;
				flex-shrink: 0;
			}
			.attendance-rg-badge * {
				color: #134644 !important;
			}

			.attendance-pd-badge {
				background-color: #f6a2f2de !important;
				color: #000000 !important;
				font-size: 11px;
				font-weight: 600;
				padding: 3px 8px;
				border-radius: 10px;
				display: inline-flex;
				align-items: center;
				justify-content: center;
				margin-right: 6px;
				margin-left: 2px;
				vertical-align: middle;
				line-height: 1.3;
				white-space: nowrap;
				flex-shrink: 0;
			}
			.attendance-pd-badge * {
				color: #ffffff !important;
			}
		</style>`).appendTo("head");
	}

	if (!list_view.data || !list_view.data.length) {
		return;
	}

	// Check which attendance_request IDs need fetching
	const missing_request_ids = [];
	list_view.data.forEach((doc) => {
		if (
			doc.attendance_request &&
			window.artem_attendance_requests_cache[doc.attendance_request] === undefined
		) {
			missing_request_ids.push(doc.attendance_request);
		}
	});

	// Render immediately with cached data
	render_attendance_badges(list_view);

	// Fetch any missing request reasons asynchronously and re-render
	if (missing_request_ids.length) {
		const unique_ids = [...new Set(missing_request_ids)];
		frappe.db
			.get_list("Attendance Request", {
				filters: { name: ["in", unique_ids] },
				fields: ["name", "reason"],
				limit: unique_ids.length,
			})
			.then((records) => {
				(records || []).forEach((r) => {
					window.artem_attendance_requests_cache[r.name] = r.reason || null;
				});
				unique_ids.forEach((id) => {
					if (window.artem_attendance_requests_cache[id] === undefined) {
						window.artem_attendance_requests_cache[id] = null;
					}
				});
				render_attendance_badges(list_view);
			});
	}
};

function render_attendance_badges(list_view) {
	if (!list_view.data || !list_view.data.length) return;

	list_view.data.forEach((doc) => {
		const escaped_name = (doc.name || "").replace(/'/g, "\\'");
		const $checkbox = list_view.$result.find(
			`.list-row-checkbox[data-name='${escaped_name}']`
		);
		const $row_container = $checkbox.closest(".list-row-container");
		if (!$row_container.length) return;

		// Find Employee Name link in subject column
		let $subject_link = $row_container.find(".list-subject a");
		if (!$subject_link.length) {
			$subject_link = $row_container.find(`a[data-name='${escaped_name}']`).first();
		}
		if (!$subject_link.length) return;

		// Highlight row if penalty
		if (doc.custom_penalty) {
			$row_container.addClass("attendance-penalty-row");
			$row_container.find(".list-row").addClass("attendance-penalty-row");
		} else {
			$row_container.removeClass("attendance-penalty-row");
			$row_container.find(".list-row").removeClass("attendance-penalty-row");
		}

		// Clean up existing badges
		$row_container
			.find(
				".attendance-penalty-badge, .attendance-od-badge, .attendance-rg-badge, .attendance-pd-badge"
			)
			.remove();

		// Build badges to place next to Employee Name
		const badges_html = [];
		if (doc.custom_penalty) {
			badges_html.push(`<span class="attendance-penalty-badge">${__("Penalty")}</span>`);
		}

		const req_reason = doc.attendance_request
			? window.artem_attendance_requests_cache[doc.attendance_request]
			: null;

		if (req_reason === "On Duty") {
			badges_html.push(
				`<span class="attendance-od-badge" title="${__("On Duty")}">${__(
					"On Duty"
				)}</span>`
			);
		} else if (req_reason === "Regularization") {
			badges_html.push(
				`<span class="attendance-rg-badge" title="${__("Regularization")}">${__(
					"REG"
				)}</span>`
			);
		}

		if (doc.custom_is_partial_day) {
			badges_html.push(
				`<span class="attendance-pd-badge" title="${__("Partial Day")}: ${
					doc.custom_partial_day_type || ""
				} (${doc.custom_partial_day_duration || 0} mins)">${__("Partial Day")}</span>`
			);
		}

		if (badges_html.length) {
			$subject_link.after(badges_html.join(""));
		}
	});
}
