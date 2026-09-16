# Copyright (c) 2025, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Contacts(Document):

    def before_delete(self):
        """
        Runs when Contact is deleted
        """
        lead = frappe.db.get_value(
            "Lead",
            {"converted_contact": self.name},
            "name"
        )

        if lead:
            frappe.db.set_value(
                "Lead",
                lead,
                "converted_contact",
                None
            )
