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


def before_submit(doc, method=None):
	check_additional_salary_review_completed(doc)
