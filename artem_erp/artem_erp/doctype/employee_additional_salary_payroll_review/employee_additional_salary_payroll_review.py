# Copyright (c) 2026, Artem Healthtech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate


class EmployeeAdditionalSalaryPayrollReview(Document):
    def autoname(self):
        if not self.company:
            frappe.throw(_("Company is required."))

        if not self.payroll_from_date or not self.payroll_to_date:
            frappe.throw(_("Payroll from and to date are required."))

        company_abbr = frappe.db.get_value(
            "Company",
            self.company,
            "abbr",
        )

        payroll_month = getdate(self.payroll_from_date)
        self.name = f"{company_abbr}-{payroll_month.strftime('%b-%Y')}"

    def validate(self):
        self.validate_dates()
        self.validate_paid_amount_limit()
        self.validate_is_reviewed_completion()
        self.validate_paid_amount_mandatory()

    def validate_dates(self):
        if self.payroll_from_date and self.payroll_to_date:
            if getdate(self.payroll_to_date) < getdate(self.payroll_from_date):
                frappe.throw(_("Payroll To Date cannot be earlier than Payroll From Date."))

    def validate_paid_amount_limit(self):
        """
        Validates that paid_amount must be less than or equal to total_amount if paid_amount > 0.
        """
        exceeded_current = [
            row
            for row in (self.additional_salary_payment_details or [])
            if flt(row.paid_amount) > 0 and flt(row.paid_amount) > flt(row.total_amount)
        ]
        exceeded_pending = [
            row
            for row in (self.previous_pending_additional_salary or [])
            if flt(row.paid_amount) > 0 and flt(row.paid_amount) > flt(row.total_amount)
        ]

        if exceeded_current or exceeded_pending:
            details = []
            if exceeded_current:
                details.append(
                    _("From Current Month Additional Salary Details Table: {0}").format(
                        ", ".join(
                            f"Row {r.idx} ({r.employee} - Paid: {r.paid_amount}, Total: {r.total_amount})"
                            for r in exceeded_current
                        )
                    )
                )
            if exceeded_pending:
                details.append(
                    _("From Previous Pending Details Table: {0}").format(
                        ", ".join(
                            f"Row {r.idx} ({r.employee} - Paid: {r.paid_amount}, Total: {r.total_amount})"
                            for r in exceeded_pending
                        )
                    )
                )

            frappe.throw(
                _(
                    "Paid Amount must be less than or equal to Total Amount when Paid Amount is greater than 0.<br><br>"
                    "The following record(s) have Paid Amount exceeding Total Amount:<br>{0}"
                ).format("<br>".join(details)),
                title=_("Invalid Paid Amount"),
            )

    def validate_is_reviewed_completion(self):
        """
        If any child row has Is Reviewed = 0, the parent review cannot be submitted
        and its Status cannot be changed to Completed.
        The parent review can be marked Completed only when all child rows have Is Reviewed = 1.
        """
        wants_completed = self.status == "Completed" or self.docstatus == 1

        if wants_completed:
            unreviewed_current = [
                row for row in (self.additional_salary_payment_details or [])
                if not cint(row.is_reviewed)
            ]
            unreviewed_pending = [
                row for row in (self.previous_pending_additional_salary or [])
                if not cint(row.is_reviewed)
            ]

            if unreviewed_current or unreviewed_pending:
                details = []
                if unreviewed_current:
                    details.append(
                        _("From Current Month Additional Salary Details Table (Row {0})").format(
                            ", ".join(str(r.idx) for r in unreviewed_current)
                        )
                    )
                if unreviewed_pending:
                    details.append(
                        _("From Previous Pending Details Table (Row {0})").format(
                            ", ".join(str(r.idx) for r in unreviewed_pending)
                        )
                    )

                action = _("submitted") if self.docstatus == 1 else _("marked as Completed")
                frappe.throw(
                    _(
                        "Please review all Additional Salary records before you {0} because not all Additional Salary records have been reviewed.<br><br>"
                        "The following records are still pending review: <br>{1}"
                    ).format(action, "<br>".join(details)),
                    title=_("Review Pending"),
                )

        if self.docstatus == 1 and self.status != "Completed":
            self.status = "Completed"

    def validate_paid_amount_mandatory(self):
        """
        Validates that paid_amount is set and greater than 0 whenever pay_action is 'Pay' or 'Partially Paid'.
        """
        wants_completed = self.status == "Completed" or self.docstatus == 1
        if not wants_completed:
            return

        missing_current = [
            row
            for row in (self.additional_salary_payment_details or [])
            if row.pay_action in ("Pay", "Partially Paid") and flt(row.paid_amount) <= 0
        ]
        missing_pending = [
            row
            for row in (self.previous_pending_additional_salary or [])
            if row.pay_action in ("Pay", "Partially Paid") and flt(row.paid_amount) <= 0
        ]

        if missing_current or missing_pending:
            details = []
            if missing_current:
                details.append(
                    _("From Current Month Additional Salary Details Table: {0}").format(
                        ", ".join(f"Row {r.idx} ({r.employee} - {r.pay_action})" for r in missing_current)
                    )
                )
            if missing_pending:
                details.append(
                    _("From Previous Pending Details Table: {0}").format(
                        ", ".join(f"Row {r.idx} ({r.employee} - {r.pay_action})" for r in missing_pending)
                    )
                )

            action = _("submitted") if self.docstatus == 1 else _("marked as Completed")
            frappe.throw(
                _(
                    "Paid Amount is mandatory and must be greater than 0 when Pay Action is 'Pay' or 'Partially Paid'.<br><br>"
                    "The following record(s) must have a valid Paid Amount before this review can be {0}:<br>{1}"
                ).format(action, "<br>".join(details)),
                title=_("Mandatory Paid Amount"),
            )

    def before_submit(self):
        self.validate_is_reviewed_completion()
        self.validate_paid_amount_mandatory()
        self.validate_paid_amount_limit()
        self.status = "Completed"

    @frappe.whitelist()
    def sync_review(self):
        """
        Manually trigger synchronization for this review from form view.
        """
        from artem_erp.artem_erp.doctype.employee_additional_salary_payroll_review.monthly_weekly_payroll_review import (
            sync_additional_salaries_for_review,
        )

        res = sync_additional_salaries_for_review(self)
        if res.get("added_current") or res.get("added_pending"):
            self.save()
            frappe.db.commit() # nosemgrep
        return res