import frappe
from frappe import _


def validate_aadhaar_number(doc, method=None):
	aadhaar_number = doc.get("custom_aadhaar_number")

	if not aadhaar_number:
		frappe.throw(
			_("Aadhaar Number is mandatory."),
			title=_("Aadhaar Number Required"),
		)

	aadhaar_number = str(aadhaar_number).strip()

	if not aadhaar_number.isdigit():
		frappe.throw(
			_("Aadhaar Number must contain only digits."),
			title=_("Invalid Aadhaar Number"),
		)

	if len(aadhaar_number) != 12:
		frappe.throw(
			_("Aadhaar Number must be exactly 12 digits."),
			title=_("Invalid Aadhaar Number"),
		)

	existing_employee = frappe.db.exists(
		"Employee",
		{
			"custom_aadhaar_number": aadhaar_number,
			"name": ["!=", doc.name],
		},
	)

	if existing_employee:
		frappe.throw(
			_("Aadhaar Number already exists for Employee {0}.").format(existing_employee),
			title=_("Duplicate Aadhaar Number"),
		)
