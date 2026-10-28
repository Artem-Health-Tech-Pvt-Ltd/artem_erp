# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

from artem_erp.auto_email.attendance_penalty_email import (
	send_attendance_penalty_email,
)
from artem_erp.auto_email.birthday_and_work_anniversary import (
	send_birthday_and_anniversary_wishes,
	send_birthday_wishes,
	send_work_anniversary_wishes,
)
from artem_erp.auto_email.team_availability_email import (
	send_daily_team_availability_notifications,
)
from artem_erp.auto_email.utils import (
	clean_email,
	format_date_range,
	get_artem_settings,
	get_configured_cc,
	get_employee_recipient_email,
	get_initials,
	get_leave_emoji,
	get_ordinal,
	parse_cc_recipients,
)

__all__ = [
	"clean_email",
	"format_date_range",
	"get_artem_settings",
	"get_configured_cc",
	"get_employee_recipient_email",
	"get_initials",
	"get_leave_emoji",
	"get_ordinal",
	"parse_cc_recipients",
	"send_attendance_penalty_email",
	"send_birthday_and_anniversary_wishes",
	"send_birthday_wishes",
	"send_daily_team_availability_notifications",
	"send_work_anniversary_wishes",
]
