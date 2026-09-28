import frappe
from frappe import _
from frappe.utils import get_link_to_form


def check_additional_salary_review_completed(doc):
	if not (doc.company and doc.start_date and doc.end_date):
		return

	draft_reviews = frappe.get_all(
		"Employee Additional Salary Payroll Review",
		filters={
			"company": doc.company,
			"payroll_from_date": ["<=", doc.end_date],
			"payroll_to_date": [">=", doc.start_date],
			"docstatus": 0,
		},
		fields=["name"],
		limit=1,
	)
	if draft_reviews:
		frappe.throw(
			_(
				"Cannot create Salary Slips: Employee Additional Salary Payroll Review {0} is still in Draft or In Review. Please complete and submit the review first."
			).format(get_link_to_form("Employee Additional Salary Payroll Review", draft_reviews[0].name)),
			title=_("Additional Salary Review Required"),
		)


def validate_employee_bank_details(doc):
	"""
	Validates that all employees in Payroll Entry with Salary Mode set to 'Bank'
	have Bank Name, Bank Account Number, IFSC Code, and PAN Number filled in.
	"""
	if not doc or not getattr(doc, "employees", None):
		return

	employee_ids = [d.employee for d in doc.employees if getattr(d, "employee", None)]
	_validate_employees(employee_ids)


def _validate_employees(employee_ids):
	if not employee_ids:
		return

	unique_emp_ids = list(set(employee_ids))

	employees = frappe.get_all(
		"Employee",
		filters={"name": ["in", unique_emp_ids]},
		fields=[
			"name",
			"employee_name",
			"salary_mode",
			"bank_name",
			"bank_ac_no",
			"ifsc_code",
			"pan_number",
		],
	)

	missing_details = []

	for emp in employees:
		salary_mode = (emp.get("salary_mode") or "").strip().lower()
		if salary_mode == "bank":
			missing_fields = []
			bank_name = emp.get("bank_name")
			bank_ac_no = emp.get("bank_ac_no")
			ifsc_code = emp.get("ifsc_code")
			pan_number = emp.get("pan_number")

			if not (bank_name and str(bank_name).strip()):
				missing_fields.append(_("Bank Name"))
			if not (bank_ac_no and str(bank_ac_no).strip()):
				missing_fields.append(_("Bank Account Number"))
			if not (ifsc_code and str(ifsc_code).strip()):
				missing_fields.append(_("IFSC Code"))
			if not (pan_number and str(pan_number).strip()):
				missing_fields.append(_("PAN Number"))

			if missing_fields:
				emp_name = emp.get("name")
				emp_full_name = emp.get("employee_name") or emp_name
				try:
					emp_link = get_link_to_form("Employee", emp_name, label=f"{emp_full_name} ({emp_name})")
				except Exception:
					emp_link = f"{emp_full_name} ({emp_name})"

				missing_details.append(f"<li><b>{emp_link}</b>: Missing {', '.join(missing_fields)}</li>")

	if missing_details:
		message = _(
			"Cannot create Salary Slips. The following employee(s) have Salary Mode set to 'Bank' "
			"but are missing required banking/PAN details:<br><br>"
			"<ul>{0}</ul>"
			"Please update the missing employee details before proceeding."
		).format("".join(missing_details))

		frappe.throw(message, title=_("Missing Employee Bank Details"))



def before_submit(doc, method=None):
	check_additional_salary_review_completed(doc)
	validate_employee_bank_details(doc)
