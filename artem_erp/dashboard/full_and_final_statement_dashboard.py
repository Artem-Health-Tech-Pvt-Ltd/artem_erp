from frappe import _


def get_data(data=None):
	return {
		"fieldname": "reference_name",
		"non_standard_fieldnames": {
			"Journal Entry": "reference_name",
			"Salary Withholding": "custom_fnf_reference",
		},
		"internal_links": {
			"Salary Slip": ["payables", "reference_document"],
			"Salary Withholding": ["payables", "custom_fnf_reference"],
		},
		"transactions": [
			{
				"label": _("Payment"),
				"items": ["Journal Entry"],
			},
			{
				"label": _("Reference"),
				"items": ["Salary Slip", "Salary Withholding"],
			},
		],
	}
