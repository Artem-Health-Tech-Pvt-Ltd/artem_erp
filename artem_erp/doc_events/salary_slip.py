import frappe

from artem_erp.override.salary_slip import update_additional_salary_payment_history


def on_submit(doc, method=None):
	update_additional_salary_payment_history(doc, cancel=False)


def on_cancel(doc, method=None):
	update_additional_salary_payment_history(doc, cancel=True)
