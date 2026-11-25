import json
from collections import defaultdict

import frappe
from frappe.desk.form.linked_with import (
	SubmittableDocumentTree,
)
from frappe.desk.form.linked_with import (
	cancel_all_linked_docs as standard_cancel_all_linked_docs,
)

DOCS_TO_IGNORE_ON_CANCEL = {
	"Salary Slip": [
		"Salary Withholding",
		"Salary Withholding Cycle",
		"Full and Final Statement",
		"Full and Final Outstanding Statement",
		"Salary Slip",
	],
	"Full and Final Statement": [
		"Salary Withholding",
		"Salary Withholding Cycle",
		"Salary Slip",
		"Full and Final Outstanding Statement",
		"Full and Final Statement",
		"Journal Entry",
		"GL Entry",
	],
	"Salary Withholding": [
		"Salary Slip",
		"Salary Withholding Cycle",
		"Full and Final Statement",
		"Payroll Entry",
	],
}


@frappe.whitelist()
def get_submitted_linked_docs(
	doctype: str, name: str, ignore_doctypes_on_cancel_all: str | list[str] | None = None
) -> dict:
	"""
	Custom override for get_submitted_linked_docs.
	Prevents cascade cancellation modals between Salary Slip, Full and Final Statement,
	and Salary Withholding.
	"""
	if isinstance(ignore_doctypes_on_cancel_all, str):
		ignore_doctypes_on_cancel_all = json.loads(ignore_doctypes_on_cancel_all)
	if not ignore_doctypes_on_cancel_all:
		ignore_doctypes_on_cancel_all = []

	auto_ignore = DOCS_TO_IGNORE_ON_CANCEL.get(doctype, [])
	for dt in auto_ignore:
		if dt not in ignore_doctypes_on_cancel_all:
			ignore_doctypes_on_cancel_all.append(dt)

	frappe.has_permission(doctype, doc=name, throw=True)
	tree = SubmittableDocumentTree(doctype, name)
	visited_documents = tree.get_all_children(ignore_doctypes_on_cancel_all)

	docs = []
	for dt, names in visited_documents.items():
		if dt in ignore_doctypes_on_cancel_all:
			continue
		for doc_name in names:
			docs.append({"doctype": dt, "name": doc_name, "docstatus": 1})

	return {"docs": docs, "count": len(docs)}


@frappe.whitelist()
def cancel_all_linked_docs(docs: str, ignore_doctypes_on_cancel_all: str | list[str] | None = None):
	"""
	Custom override for cancel_all_linked_docs.
	Ensures Salary Withholding is never cancelled automatically when other documents are cancelled.
	"""
	if isinstance(docs, str):
		doc_list = json.loads(docs)
	else:
		doc_list = docs or []

	filtered_docs = [
		d for d in doc_list if d.get("doctype") not in ("Salary Withholding", "Salary Withholding Cycle")
	]

	if isinstance(ignore_doctypes_on_cancel_all, str):
		ignore_doctypes_on_cancel_all = json.loads(ignore_doctypes_on_cancel_all)
	if not ignore_doctypes_on_cancel_all:
		ignore_doctypes_on_cancel_all = []

	for dt in ("Salary Withholding", "Salary Withholding Cycle"):
		if dt not in ignore_doctypes_on_cancel_all:
			ignore_doctypes_on_cancel_all.append(dt)

	return standard_cancel_all_linked_docs(json.dumps(filtered_docs), ignore_doctypes_on_cancel_all)
