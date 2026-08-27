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
	]
}
