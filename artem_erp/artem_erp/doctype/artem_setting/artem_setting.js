// Copyright (c) 2026, Artem Healthtech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Artem Setting", {
	validate(frm) {
		if (frm.doc.attendance_lock_reminder_day) {
			let day = cint(frm.doc.attendance_lock_reminder_day);
			if (day < 1 || day > 31) {
				frappe.msgprint(__("Attendance Lock Reminder Day must be between 1 and 31."));
				frappe.validated = false;
			}
		}
	},
	attendance_lock_reminder_day(frm) {
		if (frm.doc.attendance_lock_reminder_day) {
			let day = cint(frm.doc.attendance_lock_reminder_day);
			if (day < 1 || day > 31) {
				frappe.msgprint(__("Attendance Lock Reminder Day must be between 1 and 31."));
				frm.set_value("attendance_lock_reminder_day", "");
			}
		}
	},
});
