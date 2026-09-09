import frappe
from frappe.model.workflow import get_workflow
from frappe.utils import flt, now_datetime


def validate(doc, method=None):
	"""
	- Calculate total_amount in Travel Request Costing child table rows:
	  total_amount = funded_amount + sponsored_amount
	- Auto-calculate custom_total_estimated_cost = sum(total_amount of costings)
	- Auto-calculate custom_total_advance_required = sum(advance_amount of itinerary)
	"""
	total_estimated_cost = 0.0
	for row in doc.get("costings") or []:
		funded = flt(row.funded_amount)
		sponsored = flt(row.sponsored_amount)
		row.total_amount = funded + sponsored
		total_estimated_cost += row.total_amount

	total_advance_required = 0.0
	for row in doc.get("itinerary") or []:
		total_advance_required += flt(row.advance_amount)

	doc.custom_total_estimated_cost = total_estimated_cost
	doc.custom_total_advance_required = total_advance_required


def track_workflow_actions(doc, method=None):
	"""
	Record workflow action history for Travel Request in custom_travel_request_approval_hiestory
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
	employee_name = frappe.db.get_value(
		"Employee", {"user_id": current_user}, "employee_name"
	) or frappe.utils.get_fullname(current_user)

	# Determine original requested advance amount from first history row or doc_before_save
	history_rows = doc.get("custom_travel_request_approval_hiestory") or []
	original_requested_amount = None
	if history_rows:
		original_requested_amount = history_rows[0].get("requested_amount")

	if not original_requested_amount:
		original_requested_amount = (
			doc_before_save.get("custom_total_advance_required")
			if doc_before_save and doc_before_save.get("custom_total_advance_required") is not None
			else doc.get("custom_total_advance_required")
		)

	action_lower = action_name.strip().lower()
	if action_lower == "request for approval":
		request_amount = doc.get("custom_total_advance_required") or original_requested_amount or 0
		approved_amount = 0
	elif action_lower == "approve":
		request_amount = original_requested_amount or doc.get("custom_total_advance_required") or 0
		approved_amount = doc.get("custom_total_advance_approved") or 0
	elif action_lower == "reject":
		request_amount = original_requested_amount or doc.get("custom_total_advance_required") or 0
		approved_amount = 0
	else:
		request_amount = original_requested_amount or doc.get("custom_total_advance_required") or 0
		approved_amount = doc.get("custom_total_advance_approved") or 0

	remark = (
		doc.get("custom_remark")
		or (doc.name and frappe.db.get_value("Travel Request", doc.name, "custom_remark"))
		or ""
	)

	# Append to history child table
	doc.append(
		"custom_travel_request_approval_hiestory",
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

	# Clear temporary remark field
	doc.custom_remark = ""
