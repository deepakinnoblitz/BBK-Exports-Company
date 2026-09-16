# Copyright (c) 2025, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class LeaveAllocation(Document):

    def validate(self):
        self.validate_balance()
        self.validate_overlap()

    def validate_balance(self):
        if flt(self.total_leaves_allocated) < flt(self.total_leaves_taken):
            frappe.throw(
                _(
                    "Total Leaves Allocated ({0}) cannot be less than Total Leaves Taken ({1})"
                ).format(
                    self.total_leaves_allocated,
                    self.total_leaves_taken,
                )
            )

    def validate_overlap(self):
        if not self.from_date or not self.to_date:
            return

        overlapping = frappe.db.sql(
            """
            SELECT name
            FROM `tabLeave Allocation`
            WHERE employee=%s
            AND leave_type=%s
            AND docstatus < 2
            AND name != %s
            AND (
                (%s BETWEEN from_date AND to_date)
                OR
                (%s BETWEEN from_date AND to_date)
                OR
                (from_date BETWEEN %s AND %s)
            )
            """,
            (
                self.employee,
                self.leave_type,
                self.name or "New",
                self.from_date,
                self.to_date,
                self.from_date,
                self.to_date,
            ),
            as_dict=True,
        )

        if overlapping:
            frappe.throw(
                _(
                    "Employee {0} already has a {1} allocation for an overlapping period: {2}"
                ).format(
                    self.employee,
                    self.leave_type,
                    overlapping[0].name,
                )
            )

    def on_update(self):
        if frappe.flags.in_leave_allocation_sync:
            return

        self.sync_manual_changes()

    def sync_manual_changes(self):

        leave = frappe.get_cached_doc(
            "Leave Type",
            self.leave_type
        )

        # Only carry-forward leave types
        if not leave.carry_forward:
            return

        before = self.get_doc_before_save()

        # Ignore inserts
        if not before:
            return

        old_balance = (
            flt(before.total_leaves_allocated)
            - flt(before.total_leaves_taken)
        )

        new_balance = (
            flt(self.total_leaves_allocated)
            - flt(self.total_leaves_taken)
        )

        # Nothing changed
        if old_balance == new_balance:
            return

        frappe.flags.in_leave_allocation_sync = True

        try:
            from company.company.api import sync_future_leave_allocations

            sync_future_leave_allocations(
                self.employee,
                self.leave_type,
                self.from_date,
                max(0, new_balance),
            )

        finally:
            frappe.flags.in_leave_allocation_sync = False