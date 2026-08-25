frappe.ui.form.on("Shift Assignment", {
	refresh(frm) {
		if (!frm.doc.custom_shift_assignment_location) {
			return;
		}

		let changed = false;

		const promises = frm.doc.custom_shift_assignment_location.map((row) => {
			if (!row.shift_location) {
				return Promise.resolve();
			}

			return frappe.db
				.get_value("Shift Location", row.shift_location, [
					"latitude",
					"longitude",
					"checkin_radius",
				])
				.then((r) => {
					if (!r.message) {
						return;
					}

					const master = r.message;

					if (row.latitude != master.latitude) {
						frappe.model.set_value(row.doctype, row.name, "latitude", master.latitude);

						changed = true;
					}

					if (row.longitude != master.longitude) {
						frappe.model.set_value(
							row.doctype,
							row.name,
							"longitude",
							master.longitude
						);

						changed = true;
					}

					if (row.checkin_radius != master.checkin_radius) {
						frappe.model.set_value(
							row.doctype,
							row.name,
							"checkin_radius",
							master.checkin_radius
						);

						changed = true;
					}
				});
		});

		Promise.all(promises).then(() => {
			if (changed && !frm.is_new()) {
				frm.save();
			}
		});
	},
});

frappe.ui.form.on("Shift Assignment Location", {
	shift_location(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (!row.shift_location) {
			return;
		}

		frappe.db
			.get_value("Shift Location", row.shift_location, [
				"latitude",
				"longitude",
				"checkin_radius",
			])
			.then((r) => {
				if (!r.message) {
					return;
				}

				const master = r.message;

				const updates = [];

				if (row.latitude != master.latitude) {
					updates.push(frappe.model.set_value(cdt, cdn, "latitude", master.latitude));
				}

				if (row.longitude != master.longitude) {
					updates.push(frappe.model.set_value(cdt, cdn, "longitude", master.longitude));
				}

				if (row.checkin_radius != master.checkin_radius) {
					updates.push(
						frappe.model.set_value(cdt, cdn, "checkin_radius", master.checkin_radius)
					);
				}

				Promise.all(updates).then(() => {
					if (updates.length && !frm.is_new()) {
						frm.save();
					}
				});
			});
	},
});
