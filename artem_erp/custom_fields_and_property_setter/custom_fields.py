CUSTOM_FIELDS = {
	"Shift Assignment": [
		{
			"fieldname": "custom_shift_assignment_location_section",
			"fieldtype": "Section Break",
			"label": "Shift Assignment Location",
			"insert_after": "amended_from",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_shift_assignment_location",
			"label": "Shift Assignment Location",
			"fieldtype": "Table",
			"options": "Shift Assignment Location",
			"insert_after": "custom_shift_assignment_location_section",
			"allow_on_submit": 1,
			"system_generated": 0,
		},
	],
	"Company": [
		{
			"fieldname": "custom_enable_single_day_attendance_regularization",
			"label": "Enable Single-Day Attendance Regularization",
			"fieldtype": "Check",
			"insert_after": "default_holiday_list",
			"default": "0",
			"description": "Enables single-day Attendance Requests for the company.",
			"system_generated": 0,
		},
		{
			"fieldname": "custom_max_attendance_request_days",
			"label": "Maximum Allowed Attendance Request Days",
			"fieldtype": "Int",
			"insert_after": "custom_enable_single_day_attendance_regularization",
			"default": "0",
			"description": "Defines the maximum number of calendar days an employee can select in a single Attendance Request.",
			"depends_on": "eval:!doc.custom_enable_single_day_attendance_regularization",
			"system_generated": 0,
		},
	],
}
