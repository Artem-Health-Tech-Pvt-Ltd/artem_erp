frappe.ui.form.on("Leave Application", {
	refresh(frm) {
		toggle_partial_day_view(frm);
		toggle_sandwich_fields(frm);
		render_sandwich_leave_banners(frm);
	},

	half_day(frm) {
		reset_sandwich_flags(frm);
	},

	before_save(frm) {
		if (
			frm.doc.docstatus !== 0 ||
			frm.doc.custom_is_sandwich_leave ||
			frm.doc.custom_sandwich_rule_confirmed ||
			frm.doc.custom_apply_sandwich_exemption ||
			frm.doc.half_day ||
			frm.doc.custom_is_partial_day_leave ||
			frm.sandwich_checked ||
			!frm.doc.employee ||
			!frm.doc.from_date ||
			!frm.doc.to_date ||
			!frm.doc.leave_type
		) {
			return;
		}

		// Halt save synchronously to check sandwich leave condition
		frappe.validated = false;

		frappe.call({
			method: "artem_erp.doc_events.sandwich_leave.check_sandwich_condition",
			args: {
				employee: frm.doc.employee,
				from_date: frm.doc.from_date,
				to_date: frm.doc.to_date,
				leave_type: frm.doc.leave_type,
				name: frm.doc.name,
				half_day: frm.doc.half_day,
				is_partial_day: frm.doc.custom_is_partial_day_leave,
			},
			callback(r) {
				if (r.message && r.message.sandwich_detected) {
					if (
						r.message.is_single_application_holiday &&
						cint(r.message.exemptions_remaining) <= 0
					) {
						frm.sandwich_checked = true;
						frm.save();
						return;
					}
					show_sandwich_confirmation_dialog(frm, r.message);
				} else {
					frm.sandwich_checked = true;
					frm.save();
				}
			},
		});
	},

	after_save(frm) {
		frm.sandwich_checked = false;
	},

	employee(frm) {
		reset_sandwich_flags(frm);
	},

	from_date(frm) {
		reset_sandwich_flags(frm);
		if (frm.doc.custom_is_partial_day_leave) {
			frm.set_value("to_date", frm.doc.from_date);
			fetch_and_calculate_partial_day(frm);
		}
	},

	to_date(frm) {
		reset_sandwich_flags(frm);
		if (
			frm.doc.custom_is_partial_day_leave &&
			frm.doc.from_date &&
			frm.doc.to_date !== frm.doc.from_date
		) {
			frm.set_value("to_date", frm.doc.from_date);
		}
	},

	custom_sandwich_rule_confirmed(frm) {
		if (frm.doc.custom_sandwich_rule_confirmed) {
			frm.set_value("custom_apply_sandwich_exemption", 0);
		}
	},

	custom_apply_sandwich_exemption(frm) {
		if (frm.doc.custom_apply_sandwich_exemption) {
			frm.set_value("custom_sandwich_rule_confirmed", 0);
		}
	},

	leave_type(frm) {
		reset_sandwich_flags(frm);
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

function reset_sandwich_flags(frm) {
	frm.sandwich_checked = false;
	if (
		frm.doc &&
		(frm.doc.custom_sandwich_rule_confirmed || frm.doc.custom_apply_sandwich_exemption)
	) {
		frm.set_value("custom_sandwich_rule_confirmed", 0);
		frm.set_value("custom_apply_sandwich_exemption", 0);
	}
}

function show_sandwich_confirmation_dialog(frm, res) {
	const formatted_dates = (res.intervening_dates || []).map((d) =>
		frappe.datetime && frappe.datetime.str_to_user
			? frappe.datetime.str_to_user(d)
			: frappe.format(d, { fieldtype: "Date" })
	);
	const dates_str = formatted_dates.join(", ");
	const days_count = res.intervening_days_count || (res.intervening_dates || []).length;
	const rem = cint(res.exemptions_remaining);
	const allowed = cint(res.exemptions_allowed);

	let exemption_note = "";
	if (allowed > 0) {
		if (rem > 0) {
			exemption_note =
				`<p class="mt-2 mb-0 text-success" style="font-size: 13px; color: #0d5310;">` +
				__(
					"You have <b>{0}</b> of <b>{1}</b> sandwich leave exemption(s) remaining for this leave year.",
					[rem, allowed]
				) +
				`</p>`;
		} else {
			exemption_note =
				`<p class="mt-2 mb-0 text-danger" style="font-size: 13px; color: #dc3545;">` +
				__(
					"All <b>{0}</b> sandwich leave exemptions have been consumed for this leave year.",
					[allowed]
				) +
				`</p>`;
		}
	}

	let message_html = "";
	if (res.is_single_application_holiday) {
		const from_date_str =
			frappe.datetime && frappe.datetime.str_to_user
				? frappe.datetime.str_to_user(frm.doc.from_date)
				: frappe.format(frm.doc.from_date, { fieldtype: "Date" });
		const to_date_str =
			frappe.datetime && frappe.datetime.str_to_user
				? frappe.datetime.str_to_user(frm.doc.to_date)
				: frappe.format(frm.doc.to_date, { fieldtype: "Date" });

		message_html = `
			<div style="font-size: 13px; line-height: 1.6;">
				<p>
					${__("Sandwich Leave condition detected:")}<br>
					${__(
						"The selected Leave Type (<b>{0}</b>) includes intervening holidays / weekly offs ({1} day(s): <b>{2}</b>) between {3} and {4} as leave.",
						[frm.doc.leave_type, days_count, dates_str, from_date_str, to_date_str]
					)}
				</p>
				<p class="mb-0">
					${__(
						"Under Sandwich Leave policy, these intervening days will be counted as leave unless an exemption is applied."
					)}
				</p>
				${exemption_note}
			</div>
		`;
	} else {
		const prior_link = frappe.utils.get_form_link(
			"Leave Application",
			res.prior_leave,
			true,
			res.prior_leave
		);

		message_html = `
			<div style="font-size: 13px; line-height: 1.6;">
				<p>
					${__("Sandwich Leave condition detected:")}<br>
					${__(
						"Intervening non-working days ({0} day(s): <b>{1}</b>) fall between earlier leave application {2} and this application.",
						[days_count, dates_str, prior_link]
					)}
				</p>
				<p class="mb-0">
					${__(
						"Under Sandwich Leave policy, these intervening days will be automatically deducted as leave upon manager approval."
					)}
				</p>
				${exemption_note}
			</div>
		`;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Sandwich Leave Confirmation Required"),
		indicator: "orange",
		primary_action_label: __("Confirm Sandwich Leave"),
		primary_action: () => {
			dialog.hide();
			frm.set_value("custom_sandwich_rule_confirmed", 1).then(() => {
				frm.set_value("custom_apply_sandwich_exemption", 0).then(() => {
					frm.save();
				});
			});
		},
		secondary_action_label: __("Cancel"),
		secondary_action: () => {
			dialog.hide();
		},
	});

	if (rem > 0) {
		const exemption_btn = $(`
			<button type="button" class="btn btn-sm btn-info" style="margin-right: 8px; background-color: #1b8bf8; border-color: #1b8bf8; color: #ffffff;">
				${__("Apply Exemption")}
			</button>
		`).click(() => {
			dialog.hide();
			frm.set_value("custom_apply_sandwich_exemption", 1).then(() => {
				frm.set_value("custom_sandwich_rule_confirmed", 0).then(() => {
					if (res.is_single_application_holiday) {
						const new_days = Math.max(
							0,
							flt(frm.doc.total_leave_days) - flt(days_count)
						);
						frm.set_value("total_leave_days", new_days).then(() => {
							frm.save();
						});
					} else {
						frm.save();
					}
				});
			});
		});

		dialog.standard_actions.find(".btn-modal-primary").before(exemption_btn);
	}

	dialog.$body.html(message_html);
	dialog.show();
}

function toggle_sandwich_fields(frm) {
	const is_sandwich = cint(frm.doc.custom_is_sandwich_leave);
	frm.toggle_display("custom_parent_leave_application", is_sandwich);
	frm.toggle_display("custom_prior_leave_application", is_sandwich);
}

function render_sandwich_leave_banners(frm) {
	if (frm.dashboard && frm.dashboard.clear_headline) {
		frm.dashboard.clear_headline();
	}

	if (frm.doc.custom_is_sandwich_leave) {
		frm.dashboard.set_headline_alert(
			__(
				"This is an automatically generated Sandwich Leave record. Parent Leave: {0}, Prior Leave: {1}",
				[
					frappe.utils.get_form_link(
						"Leave Application",
						frm.doc.custom_parent_leave_application,
						true,
						frm.doc.custom_parent_leave_application
					),
					frappe.utils.get_form_link(
						"Leave Application",
						frm.doc.custom_prior_leave_application,
						true,
						frm.doc.custom_prior_leave_application
					),
				]
			),
			"blue"
		);
	} else if (frm.doc.custom_apply_sandwich_exemption) {
		frm.dashboard.set_headline_alert(
			__("Sandwich Leave Exemption was applied for this leave application."),
			"green"
		);
	} else if (frm.doc.custom_sandwich_detected && frm.doc.custom_sandwich_rule_confirmed) {
		let details = {};
		try {
			details = frm.doc.custom_sandwich_details
				? JSON.parse(frm.doc.custom_sandwich_details)
				: {};
		} catch (e) {
			// ignore json parse error
		}

		if (details.is_single_application_holiday) {
			frm.dashboard.set_headline_alert(
				__(
					"Sandwich Leave Rule confirmed. Intervening non-working days are counted as leave."
				),
				"orange"
			);
		} else {
			frm.dashboard.set_headline_alert(
				__(
					"Sandwich Leave condition detected. Intervening non-working days will be processed upon approval."
				),
				"orange"
			);
		}
	}
}

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
