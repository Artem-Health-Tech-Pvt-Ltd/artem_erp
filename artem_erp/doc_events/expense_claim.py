import frappe
from frappe.utils import now_datetime
from frappe.model.workflow import get_workflow


def track_workflow_actions(doc, method=None):
	"""
	Record workflow action history for Expense Claim in custom_expense_claim_approval_hiestory
	when workflow transition occurs.
	"""
	doc_before_save = doc.get_doc_before_save()
	if not doc_before_save:
		return

	# Compare workflow states
	workflow = get_workflow(doc.doctype)
	if not workflow:
		return

	state_field = workflow.workflow_state_field
	from_state = doc_before_save.get(state_field)
	to_state = doc.get(state_field)

	# If workflow state has not changed, return
	if not from_state or not to_state or from_state == to_state:
		return

	# Find transition action corresponding to from_state -> to_state
	action_name = None
	for transition in workflow.transitions:
		if transition.state == from_state and transition.next_state == to_state:
			action_name = transition.action
			break

	if not action_name:
		return

	# Current session user and employee name
	current_user = frappe.session.user
	employee_name = frappe.db.get_value("Employee", {"user_id": current_user}, "employee_name") or frappe.utils.get_fullname(current_user)

	# Determine original requested amount from the first workflow action or before_save
	history_rows = doc.get("custom_expense_claim_approval_hiestory") or []
	original_requested_amount = None
	if history_rows:
		# Use the requested amount from the initial Request for Approval / first row
		original_requested_amount = history_rows[0].get("requested_amount")

	if not original_requested_amount:
		original_requested_amount = (
			doc_before_save.get("total_claimed_amount")
			if doc_before_save and doc_before_save.get("total_claimed_amount") is not None
			else doc.get("total_claimed_amount")
		)

	# In Expense Claim, expense amount cannot be changed during workflow
	action_lower = action_name.strip().lower()
	if action_lower == "request for approval":
		request_amount = doc.get("total_claimed_amount") or original_requested_amount or 0
		approved_amount = 0
	elif action_lower == "approve":
		request_amount = original_requested_amount or doc.get("total_claimed_amount") or 0
		approved_amount = doc.get("total_claimed_amount") or 0
	elif action_lower == "reject":
		request_amount = original_requested_amount or doc.get("total_claimed_amount") or 0
		approved_amount = 0
	else:
		request_amount = original_requested_amount or doc.get("total_claimed_amount") or 0
		approved_amount = doc.get("total_claimed_amount") or 0

	remark = (
		doc.get("custom_approval_reject_reason")
		or (doc.name and frappe.db.get_value("Expense Claim", doc.name, "custom_approval_reject_reason"))
		or ""
	)

	# Append to history child table
	doc.append(
		"custom_expense_claim_approval_hiestory",
		{
			"action_by": current_user,
			"action_by_name": employee_name,
			"from_state": from_state,
			"to_state": to_state,
			"action": action_name,
			"time": now_datetime(),
			"requested_amount": request_amount,
			"approved_amount": approved_amount,
			"remark": remark,
		},
	)

	# Clear temporary reason field
	doc.custom_approval_reject_reason = ""


def on_update(doc, method=None):
	"""
	When Expense Claim is saved or updated:
	- Set is_claim_raise = 1 on all linked Expense records.
	- If any Expense was removed from this Expense Claim, reset its is_claim_raise = 0.
	"""
	update_linked_expenses(doc)


def on_cancel(doc, method=None):
	"""
	When Expense Claim is cancelled, unmark is_claim_raise = 0 on linked Expense records.
	"""
	reset_linked_expenses(doc)


def on_trash(doc, method=None):
	"""
	When Expense Claim is deleted, unmark is_claim_raise = 0 on linked Expense records.
	"""
	reset_linked_expenses(doc)


def update_linked_expenses(doc):
	current_expenses = [d.custom_expense for d in doc.get("expenses") or [] if d.custom_expense]

	# Mark is_claim_raise = 1 for currently linked expenses
	for exp_name in current_expenses:
		frappe.db.set_value("Expense", exp_name, "is_claim_raise", 1, update_modified=False)

	# If this is an existing doc, find any expenses that were removed in this update
	if doc.name:
		doc_before_save = doc.get_doc_before_save()
		if doc_before_save:
			previous_expenses = [d.custom_expense for d in doc_before_save.get("expenses") or [] if d.custom_expense]
			removed_expenses = set(previous_expenses) - set(current_expenses)
			for exp_name in removed_expenses:
				frappe.db.set_value("Expense", exp_name, "is_claim_raise", 0, update_modified=False)


def reset_linked_expenses(doc):
	for d in doc.get("expenses") or []:
		if d.custom_expense:
			frappe.db.set_value("Expense", d.custom_expense, "is_claim_raise", 0, update_modified=False)

