frappe.ui.form.on("Attendance", {
	refresh(frm) {
		update_attendance_request_button(frm);
		show_partial_day_indicator(frm);
	},
	employee(frm) {
		update_attendance_request_button(frm);
	},
	attendance_date(frm) {
		update_attendance_request_button(frm);
	},
	status(frm) {
		update_attendance_request_button(frm);
	},
});

function show_partial_day_indicator(frm) {
	if (frm.doc.custom_is_partial_day) {
		frm.dashboard.set_headline_alert(
			__(
				"Approved Partial Day Leave ({0}): {1} mins allowance. Adjusted Required Hours: {2}",
				[
					frm.doc.custom_partial_day_type || "",
					frm.doc.custom_partial_day_duration || 0,
					frm.doc.custom_adjusted_required_hours || 0,
				]
			),
			"purple"
		);
	}
}

function update_attendance_request_button(frm) {
	if (!frm.doc.employee || !frm.doc.attendance_date) {
		frm.remove_custom_button(__("Attendance Request"), __("Create"));
		return;
	}

	frappe.call({
		method: "artem_erp.doc_events.attendance.can_create_attendance_request",
		args: {
			employee: frm.doc.employee,
			attendance_date: frm.doc.attendance_date,
			status: frm.doc.status,
			attendance_name: frm.is_new() ? null : frm.doc.name,
			is_new: frm.is_new(),
		},
		callback(r) {
			if (r.message && r.message.can_create) {
				// Remove any existing button to prevent duplicates
				frm.remove_custom_button(__("Attendance Request"), __("Create"));
				frm.add_custom_button(
					__("Attendance Request"),
					() => {
						let default_values = {
							employee: frm.doc.employee,
							from_date: frm.doc.attendance_date,
							to_date: frm.doc.attendance_date,
						};
						frappe.new_doc("Attendance Request", default_values);
					},
					__("Create")
				);
			} else {
				frm.remove_custom_button(__("Attendance Request"), __("Create"));
			}
		},
	});
}
