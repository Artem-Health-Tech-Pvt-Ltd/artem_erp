# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import re
from email.utils import getaddresses, parseaddr

import frappe
from frappe.utils import getdate


def clean_email(addr: str) -> str:
	"""
	Extract lowercase email from an address string (e.g. '"Name" <user@example.com>' -> 'user@example.com').
	"""
	if not addr:
		return ""
	return parseaddr(str(addr))[1].lower().strip()


def get_ordinal(n: int) -> str:
	"""
	Return the ordinal string for a given integer (e.g. 1 -> 1st, 2 -> 2nd, 3 -> 3rd).
	"""
	if 11 <= (n % 100) <= 13:
		suffix = "th"
	else:
		suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
	return f"{n}{suffix}"


def get_leave_emoji(leave_type: str | None) -> str:
	"""
	Return an appropriate emoji for a given leave type name.
	e.g. Sick Leave -> 🤒, Casual Leave -> 🌴, Birthday Leave -> 🎂, etc.
	"""
	if not leave_type:
		return "🏖️"

	lt = str(leave_type).lower().strip()
	if "sick" in lt:
		return "🤒"
	if "casual" in lt:
		return "🌴"
	if "birthday" in lt:
		return "🎂"
	if "marriage" in lt or "wedding" in lt:
		return "💍"
	if "maternity" in lt:
		return "🤰"
	if "paternity" in lt:
		return "👶"
	if "compensatory" in lt or "comp" in lt:
		return "⚖️"
	if "holiday" in lt or "vacation" in lt:
		return "🎉"
	if "privilege" in lt:
		return "🏖️"
	if "partial" in lt:
		return "⏱️"
	if "unpaid" in lt or "without pay" in lt:
		return "📝"

	return "🏖️"


def get_initials(name: str) -> str:
	"""
	Generate a 2-letter uppercase initials string from an employee name.
	e.g. 'Kapadia Miraj Rajeshbhai' -> 'KR', 'Twisha Bhaveshkumar' -> 'TB'
	"""
	parts = (name or "").strip().split()
	if not parts:
		return "EM"
	if len(parts) == 1:
		return parts[0][:2].upper()
	return f"{parts[0][0]}{parts[-1][0]}".upper()


def format_date_range(from_date, to_date) -> str:
	"""
	Format date range string matching.
	"""
	if not from_date and not to_date:
		return ""
	f_date = getdate(from_date) if from_date else None
	t_date = getdate(to_date) if to_date else None

	f_str = f_date.strftime("%d %b, %Y") if f_date else ""
	t_str = t_date.strftime("%d %b, %Y") if t_date else ""

	if f_str and t_str:
		return f"{f_str} - {t_str}"
	return f_str or t_str


def get_employee_recipient_email(employee) -> str | None:
	"""
	Determine the recipient email address for an employee.
	Only considers prefered_email or company_email (prefered_email first, then company_email).
	"""
	for field in ("prefered_email", "company_email"):
		val = employee.get(field) if isinstance(employee, dict) else getattr(employee, field, None)
		if val:
			val_str = str(val).strip()
			if "@" in val_str and "." in val_str:
				clean = clean_email(val_str)
				if clean and "@" in clean and "." in clean:
					return clean

	return None


def get_artem_settings():
	"""
	Retrieve the Artem Setting single document.
	"""
	try:
		return frappe.get_single("Artem Setting")
	except Exception as e:
		frappe.log_error(
			title="Artem Setting Not Found",
			message=f"Failed to fetch Artem Setting: {e}\n\n{frappe.get_traceback()}",
			reference_doctype="Artem Setting",
			reference_name="Artem Setting",
		)
		return None


def parse_cc_recipients(cc_input) -> list[str]:
	"""
	Parse raw CC recipients string, list, or Table MultiSelect rows into properly formatted email address list.
	Supports:
	- Email Group Table child rows or names (e.g. "Artem-Ahmedabad", "Mumbai Team"), fetching their members dynamically
	- Comma, semicolon, or newline delimited addresses
	- "Name" email@example.com
	- "Name" <email@example.com>
	- email@example.com
	Deduplicates preserving order.
	"""
	if not cc_input:
		return []

	if isinstance(cc_input, list):
		raw_items = cc_input
	else:
		raw_items = [cc_input]

	recipients: list[str] = []
	for item in raw_items:
		if not item:
			continue

		if isinstance(item, dict):
			item = item.get("email_group") or item.get("email") or ""
		elif hasattr(item, "email_group"):
			item = getattr(item, "email_group", "")

		item_str = str(item).strip()
		if not item_str:
			continue

		# Split on comma, semicolon, newline
		tokens = re.split(r"[;\r\n,]+", item_str)
		for token in tokens:
			token = token.strip()
			if not token:
				continue

			# Check if token is an Email Group in Frappe (e.g., Artem-Ahmedabad, Mumbai Team)
			if frappe.db and frappe.db.exists("Email Group", token):
				members = frappe.get_all(
					"Email Group Member",
					filters={"email_group": token, "unsubscribed": 0},
					pluck="email",
				)
				for member_email in members:
					if member_email and member_email.strip():
						recipients.append(member_email.strip())
				continue

			# Normalize '"Name" email@example.com' to '"Name" <email@example.com>'
			normalized = re.sub(
				r'"([^"]+)"\s+([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-.]+)',
				r'"\1" <\2>',
				token,
			)

			parsed = getaddresses([normalized])
			for name, email in parsed:
				email = email.strip()
				if email and "@" in email and "." in email:
					if name:
						recipients.append(f'"{name}" <{email}>')
					else:
						recipients.append(email)

	# Deduplicate preserving order
	seen = set()
	deduped: list[str] = []
	for addr in recipients:
		clean = clean_email(addr)
		if clean and clean not in seen:
			seen.add(clean)
			deduped.append(addr)

	return deduped


def get_configured_cc(artem_setting) -> list[str]:
	"""
	Retrieve and parse CC recipients dynamically from Artem Setting.
	Extracts Email Groups from the 'company_team_emails' Table MultiSelect (Email Group Table)
	and fetches all active member email addresses from Email Group Member.
	"""
	if not artem_setting:
		return []

	raw_groups = artem_setting.get("company_team_emails") or []
	group_names: list[str] = []

	if isinstance(raw_groups, list):
		for row in raw_groups:
			if isinstance(row, dict):
				grp = row.get("email_group")
			elif hasattr(row, "email_group"):
				grp = getattr(row, "email_group", None)
			else:
				grp = str(row).strip()
			if grp:
				group_names.append(str(grp).strip())
	elif isinstance(raw_groups, str):
		group_names = [g.strip() for g in re.split(r"[;\r\n,]+", raw_groups) if g.strip()]

	return parse_cc_recipients(group_names)
