frappe.ui.form.on("Leave Application", {
	refresh(frm) {
		toggle_partial_day_view(frm);
	},

	leave_type(frm) {
		if (!frm.doc.leave_type) {
			frm.set_value("custom_is_partial_day_leave", 0);
			toggle_partial_day_view(frm);
			return;
		}

		frappe.db.get_value(
			"Leave Type",
			frm.doc.leave_type,
			["custom_is_partial_day", "custom_partial_day_max_duration"],
			(r) => {
				const is_partial = r && cint(r.custom_is_partial_day);
				frm.set_value("custom_is_partial_day_leave", is_partial ? 1 : 0);
				toggle_partial_day_view(frm);

				if (is_partial) {
					// Enforce single-day
					if (frm.doc.from_date) {
						frm.set_value("to_date", frm.doc.from_date);
					}
					// Disable half day
					frm.set_value("half_day", 0);
					frm.set_df_property("half_day", "read_only", 1);

					const max_mins = cint(r.custom_partial_day_max_duration) || 90;
					frm.fields_dict.custom_partial_day_duration.set_description(
						__("Maximum allowed: {0} minutes", [max_mins])
					);

					fetch_and_calculate_partial_day(frm);
				} else {
					frm.set_df_property("half_day", "read_only", 0);
					frm.fields_dict.custom_partial_day_duration.set_description("");
				}
			}
		);
	},

	from_date(frm) {
		if (frm.doc.custom_is_partial_day_leave) {
			frm.set_value("to_date", frm.doc.from_date);
			fetch_and_calculate_partial_day(frm);
		}
	},

	to_date(frm) {
		if (
			frm.doc.custom_is_partial_day_leave &&
			frm.doc.from_date &&
			frm.doc.to_date !== frm.doc.from_date
		) {
			frm.set_value("to_date", frm.doc.from_date);
		}
	},

	custom_partial_day_type(frm) {
		if (frm.doc.custom_is_partial_day_leave) {
			fetch_and_calculate_partial_day(frm);
		}
	},

	custom_partial_day_duration(frm) {
		if (frm.doc.custom_is_partial_day_leave) {
			if (!frm.doc.leave_type) return;

			frappe.db.get_value(
				"Leave Type",
				frm.doc.leave_type,
				"custom_partial_day_max_duration",
				(r) => {
					const max_mins = (r && cint(r.custom_partial_day_max_duration)) || 90;
					const current_val = cint(frm.doc.custom_partial_day_duration);
					if (current_val > max_mins) {
						frappe.msgprint({
							title: __("Validation Warning"),
							indicator: "orange",
							message: __(
								"Requested duration ({0} minutes) exceeds the maximum allowed duration of {1} minutes.",
								[current_val, max_mins]
							),
						});
						frm.set_value("custom_partial_day_duration", max_mins);
					}
					fetch_and_calculate_partial_day(frm);
				}
			);
		}
	},
});

function toggle_partial_day_view(frm) {
	const is_partial = cint(frm.doc.custom_is_partial_day_leave);

	frm.toggle_display("custom_partial_day_section", is_partial);
	frm.toggle_reqd("custom_partial_day_type", is_partial);
	frm.toggle_reqd("custom_partial_day_duration", is_partial);

	if (is_partial) {
		frm.set_df_property("half_day", "read_only", 1);
		if (frm.doc.leave_type) {
			frappe.db.get_value(
				"Leave Type",
				frm.doc.leave_type,
				"custom_partial_day_max_duration",
				(r) => {
					const max_mins = (r && cint(r.custom_partial_day_max_duration)) || 90;
					frm.fields_dict.custom_partial_day_duration.set_description(
						__("Maximum allowed: {0} minutes", [max_mins])
					);
				}
			);
		}
	} else {
		frm.set_df_property("half_day", "read_only", 0);
	}
}

function fetch_and_calculate_partial_day(frm) {
	if (!frm.doc.employee || !frm.doc.from_date || !frm.doc.custom_is_partial_day_leave) {
		return;
	}

	frappe.call({
		method: "artem_erp.doc_events.leave_application.get_partial_day_details",
		args: {
			employee: frm.doc.employee,
			date: frm.doc.from_date,
			leave_type: frm.doc.leave_type,
			partial_day_type: frm.doc.custom_partial_day_type,
			duration_minutes: frm.doc.custom_partial_day_duration,
		},
		callback(r) {
			if (r.message) {
				const data = r.message;
				if (data.error) {
					frappe.show_alert({ message: data.error, indicator: "orange" }, 5);
				}
				if (data.shift) {
					frm.set_value("custom_shift", data.shift);
				}
				if (data.adjusted_time) {
					frm.set_value("custom_adjusted_time", data.adjusted_time);
				}
			}
		},
	});
}
