// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

console.log(" --------- >> Custom Attendance Request JS loaded <<------------");
frappe.ui.form.on("Attendance Request", {
	onload(frm) {
		frm.trigger("fetch_company_attendance_config");
	},

	refresh(frm) {
		frm.trigger("fetch_company_attendance_config");
	},

	company(frm) {
		frm.trigger("fetch_company_attendance_config");
	},

	employee(frm) {
		if (frm.doc.employee) {
			frappe.db.get_value("Employee", frm.doc.employee, "company", (r) => {
				if (r && r.company && frm.doc.company !== r.company) {
					frm.set_value("company", r.company);
				}
				frm.trigger("fetch_company_attendance_config");
			});
		}
	},

	from_date(frm) {
		if (!frm.doc.from_date) return;

		const config = frm.company_attendance_config || {};
		if (config.enable_single_day) {
			// In single-day mode, To Date must always be equal to From Date
			frm.set_value("to_date", frm.doc.from_date);
		} else if (frm.doc.to_date) {
			frm.trigger("validate_max_days");
		}

		frm.trigger("detect_shifts");
	},

	to_date(frm) {
		if (!frm.doc.to_date) return;

		const config = frm.company_attendance_config || {};
		if (config.enable_single_day) {
			if (frm.doc.from_date && frm.doc.to_date !== frm.doc.from_date) {
				frm.set_value("to_date", frm.doc.from_date);
				frappe.show_alert({
					message: __(
						"Single-day attendance regularization is enabled. To Date must match From Date."
					),
					indicator: "orange",
				});
				return;
			}
		} else {
			if (!frm.trigger("validate_max_days")) {
				return;
			}
		}

		frm.trigger("detect_shifts");
	},

	shift(frm) {
		if (frm.has_same_date_multiple_shifts && frm.doc.shift) {
			frm.has_multiple_shifts = false;
		}
	},

	validate(frm) {
		if (frm.has_unassigned_dates) {
			frappe.validated = false;
			frappe.throw({
				title: __("No Shift Assigned"),
				message:
					frm.unassigned_dates_message ||
					__("No shift is assigned for one or more selected dates."),
				indicator: "red",
			});
			return false;
		}

		if (frm.has_multiple_shifts) {
			frappe.validated = false;
			frappe.throw({
				title: __("Multiple Shifts Found in the Selected Date Range"),
				message:
					frm.multiple_shifts_message ||
					__(
						"The selected date range contains multiple shift assignments across different dates. Please create separate Attendance Requests for each shift period."
					),
				indicator: "red",
			});
			return false;
		}

		if (frm.has_same_date_multiple_shifts && !frm.doc.shift) {
			frappe.validated = false;
			frappe.throw({
				title: __("Shift Selection Required"),
				message:
					frm.same_date_shifts_message ||
					__(
						"Multiple shifts are assigned for the selected date. Please select one shift before submitting the Attendance Request."
					),
				indicator: "orange",
			});
			return false;
		}

		const config = frm.company_attendance_config || {};
		if (config.enable_single_day) {
			if (frm.doc.from_date !== frm.doc.to_date) {
				frappe.validated = false;
				frappe.throw({
					title: __("Single-Day Attendance Regularization"),
					message: __(
						"Attendance Regularization is restricted to a single day. From Date and To Date must be the same."
					),
				});
				return false;
			}
		} else if (config.max_days > 0 && frm.doc.from_date && frm.doc.to_date) {
			const total_days = frappe.datetime.get_diff(frm.doc.to_date, frm.doc.from_date) + 1;
			if (total_days > config.max_days) {
				frappe.validated = false;
				const message =
					config.max_days > 1
						? __(
								"The selected date range exceeds the maximum allowed limit of {0} days. Please select {0} (or less days).",
								[config.max_days]
						  )
						: __(
								"The selected date range exceeds the maximum allowed limit of 1 day. Please select 1 day."
						  );
				frappe.throw({
					title: __("Maximum Allowed Days Exceeded"),
					message: message,
				});
				return false;
			}
		}
	},

	fetch_company_attendance_config(frm) {
		const company = frm.doc.company;
		const employee = frm.doc.employee;

		if (!company && !employee) return;

		frappe.call({
			method: "artem_erp.doc_events.attendance_request.get_company_attendance_regularization_config",
			args: {
				company: company,
				employee: employee,
			},
			callback(r) {
				if (r.message) {
					frm.company_attendance_config = r.message;
					frm.trigger("apply_company_config_ui");
					if (frm.doc.employee && frm.doc.from_date) {
						frm.trigger("detect_shifts");
					}
				}
			},
		});
	},

	apply_company_config_ui(frm) {
		const config = frm.company_attendance_config || {};
		if (frm.doc.docstatus === 0) {
			if (config.enable_single_day) {
				frm.set_df_property("to_date", "read_only", 1);
				if (frm.doc.from_date && frm.doc.to_date !== frm.doc.from_date) {
					frm.set_value("to_date", frm.doc.from_date);
				}
				if (frm.doc.shift && !frm.has_same_date_multiple_shifts) {
					frm.set_df_property("shift", "read_only", 1);
				}
			} else {
				frm.set_df_property("to_date", "read_only", 0);
				frm.set_df_property("shift", "read_only", 0);
			}
		}
	},

	validate_max_days(frm) {
		const config = frm.company_attendance_config || {};
		if (
			!config.enable_single_day &&
			config.max_days > 0 &&
			frm.doc.from_date &&
			frm.doc.to_date
		) {
			const total_days = frappe.datetime.get_diff(frm.doc.to_date, frm.doc.from_date) + 1;
			if (total_days > config.max_days) {
				const message =
					config.max_days > 1
						? __(
								"The selected date range exceeds the maximum allowed limit of {0} days. Please select {0} (or less days).",
								[config.max_days]
						  )
						: __(
								"The selected date range exceeds the maximum allowed limit of 1 day. Please select 1 day."
						  );
				frappe.throw({
					title: __("Maximum Allowed Days Exceeded"),
					message: message,
					indicator: "red",
				});
				return false;
			}
		}
		return true;
	},

	detect_shifts(frm) {
		if (!frm.doc.employee || !frm.doc.from_date) return;

		const config = frm.company_attendance_config || {};
		const to_date = config.enable_single_day
			? frm.doc.from_date
			: frm.doc.to_date || frm.doc.from_date;

		// Shift detection runs for all attendance requests
		frappe.call({
			method: "artem_erp.doc_events.attendance_request.detect_shifts_and_validate",
			args: {
				employee: frm.doc.employee,
				from_date: frm.doc.from_date,
				to_date: to_date,
				company: frm.doc.company,
			},
			callback(r) {
				if (!r.message) return;
				const res = r.message;

				if (res.has_unassigned_dates) {
					frm.has_unassigned_dates = true;
					frm.unassigned_dates_message = res.unassigned_dates_message;
					frm.has_multiple_shifts = false;
					frm.multiple_shifts_message = null;
					frm.has_same_date_multiple_shifts = false;
					frm.set_query("shift", null);
					frm.set_df_property("shift", "reqd", 0);
					frm.set_df_property(
						"shift",
						"description",
						__("No shift assigned on some dates.")
					);
					frm.set_df_property("shift", "read_only", 0);
				} else if (res.has_multiple_shifts) {
					// Different shifts across dates with no single common shift
					frm.has_unassigned_dates = false;
					frm.has_multiple_shifts = true;
					frm.multiple_shifts_message = res.multiple_shifts_message;
					frm.has_same_date_multiple_shifts = false;
					frm.same_date_shifts = [];
					frm.same_date_shifts_message = null;
					frm.set_query("shift", null);
					frm.set_df_property("shift", "reqd", 0);
					frm.set_value("shift", "");
					frm.set_df_property(
						"shift",
						"description",
						__(
							"Different shifts assigned across dates. Please create separate requests for each shift period."
						)
					);
					frm.set_df_property("shift", "read_only", 0);

					frappe.show_alert({
						message: __(
							"Different shifts assigned across dates. Please create separate Attendance Requests for each shift period."
						),
						indicator: "red",
					});
				} else if (
					res.has_same_date_multiple_shifts ||
					(res.common_shifts && res.common_shifts.length > 1)
				) {
					// Multiple shifts on date, or multiple common shifts
					frm.has_unassigned_dates = false;
					frm.has_multiple_shifts = false;
					frm.multiple_shifts_message = null;
					frm.has_same_date_multiple_shifts = true;
					frm.common_shifts =
						res.common_shifts && res.common_shifts.length
							? res.common_shifts
							: res.same_date_shifts;
					frm.same_date_shifts = frm.common_shifts;
					frm.same_date_shifts_message = res.same_date_shifts_message;

					frm.set_df_property("shift", "reqd", 1);
					frm.set_df_property("shift", "read_only", 0);

					const details =
						res.common_shifts_details && res.common_shifts_details.length
							? res.common_shifts_details
							: res.same_date_shifts_details || [];

					if (details.length) {
						const details_str = details
							.map((d) => `${d.shift}${d.time_label ? ` (${d.time_label})` : ""}`)
							.join(", ");
						frm.set_df_property(
							"shift",
							"description",
							__("Applicable shifts: {0}", [details_str])
						);
					}

					// Filter shift link field options to only the applicable shifts
					frm.set_query("shift", function () {
						return {
							filters: {
								name: ["in", frm.common_shifts],
							},
						};
					});

					// If currently selected shift is not valid for this date range, clear it
					if (frm.doc.shift && !frm.common_shifts.includes(frm.doc.shift)) {
						frm.set_value("shift", "");
					}

					// If no shift is selected yet, show a non-intrusive alert
					if (!frm.doc.shift) {
						frappe.show_alert({
							message: __(
								"Please select one of the applicable shifts from the Shift field."
							),
							indicator: "orange",
						});
					}
				} else if (res.single_shift) {
					frm.has_unassigned_dates = false;
					frm.has_same_date_multiple_shifts = false;
					frm.same_date_shifts = [];
					frm.same_date_shifts_message = null;
					frm.has_multiple_shifts = false;
					frm.multiple_shifts_message = null;
					frm.set_query("shift", null);
					frm.set_df_property("shift", "reqd", 0);
					frm.set_df_property("shift", "description", "");
					frm.set_value("shift", res.single_shift);
					if (config.enable_single_day) {
						frm.set_df_property("shift", "read_only", 1);
					} else {
						frm.set_df_property("shift", "read_only", 0);
					}
				} else if (res.no_shift_found) {
					frm.has_unassigned_dates = false;
					frm.has_same_date_multiple_shifts = false;
					frm.same_date_shifts = [];
					frm.same_date_shifts_message = null;
					frm.has_multiple_shifts = false;
					frm.multiple_shifts_message = null;
					frm.set_query("shift", null);
					frm.set_df_property("shift", "reqd", 0);
					frm.set_df_property("shift", "description", "");
					frm.set_df_property("shift", "read_only", 0);
				}
			},
		});
	},
});
