import frappe
from frappe.utils import now_datetime
from frappe.model.workflow import get_workflow


def track_workflow_actions(doc, method=None):
	"""
	Record workflow action history for Employee Advance in custom_employee_advance_approval_hiestory
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
	history_rows = doc.get("custom_employee_advance_approval_hiestory") or []
	original_requested_amount = None
	if history_rows:
		# Use the requested amount from the initial Request for Approval / first row
		original_requested_amount = history_rows[0].get("requested_amount")

	if not original_requested_amount:
		original_requested_amount = (
			doc_before_save.get("advance_amount")
			if doc_before_save and doc_before_save.get("advance_amount") is not None
			else doc.get("advance_amount")
		)

	# Handle Requested Amount & Approved Amount based on action:
	# - "Request for approval": Requested Amount = advance_amount, Approved Amount = 0
	# - "Approve" / Other approval actions: Requested Amount = original requested amount, Approved Amount = updated advance_amount
	# - "Reject": Requested Amount = original requested amount, Approved Amount = 0
	action_lower = action_name.strip().lower()
	if action_lower == "request for approval":
		request_amount = doc.get("advance_amount") or original_requested_amount or 0
		approved_amount = 0
	elif action_lower == "approve":
		request_amount = original_requested_amount or doc.get("advance_amount") or 0
		approved_amount = doc.get("advance_amount") or 0
	elif action_lower == "reject":
		request_amount = original_requested_amount or doc.get("advance_amount") or 0
		approved_amount = 0
	else:
		request_amount = original_requested_amount or doc.get("advance_amount") or 0
		approved_amount = doc.get("advance_amount") or 0

	remark = (
		doc.get("custom_approval_reject_reason")
		or (doc.name and frappe.db.get_value("Employee Advance", doc.name, "custom_approval_reject_reason"))
		or ""
	)

	# Append to history child table
	doc.append(
		"custom_employee_advance_approval_hiestory",
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