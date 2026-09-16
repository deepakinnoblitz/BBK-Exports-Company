# Copyright (c) 2026, deepak and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CRMEmailTemplate(Document):
	pass

@frappe.whitelist()
def get_email_template_variables(template_for):
    """
    Returns available variables for the selected Template For.
    Supports comma-separated multi-select values like "Lead,Contact,Proposal".
    """

    # Map frontend values to actual Frappe doctypes
    doctype_map = {
        "Lead": ("Lead", None),           # (doctype, variable_prefix)
        "Contact": ("Contacts", None),
        "Contacts": ("Contacts", None),
        "Account": ("Accounts", None),
        "Accounts": ("Accounts", None),
        "Deal": ("Deal", None),
        "Deals": ("Deal", None),
        "Proposal": ("Proposal", "proposal"),  # rendered as {{ proposal.fieldname }}
        "Proposals": ("Proposal", "proposal"),
    }

    exclude = {
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "_user_tags",
        "_comments",
        "_assign",
        "_liked_by",
        "amended_from",
        "parent",
        "parentfield",
        "parenttype",
		"activity_score",
		"converted_account",
		"converted_contact",
		"converted_deal",
		"interest_level",
		"sales_pipeline",
		"lead_score",
		"date_and_time",
		"status"
    }

    ignore_fieldtypes = {
        "Section Break",
        "Column Break",
        "Tab Break",
        "Button",
        "HTML",
        "Table",
        "Table MultiSelect",
        "Image",
        "Attach",
        "Attach Image",
        "Fold",
        "Heading",
    }

    # Split comma-separated values and process each
    selected_types = [t.strip() for t in template_for.split(",") if t.strip()]

    all_variables = []
    seen_variables = set()

    for selected in selected_types:
        mapping = doctype_map.get(selected)
        if not mapping:
            continue

        doctype, prefix = mapping

        try:
            meta = frappe.get_meta(doctype)
        except Exception:
            continue

        for df in meta.fields:
            if (
                df.fieldname
                and df.fieldname not in exclude
                and df.fieldtype not in ignore_fieldtypes
            ):
                if prefix:
                    var_name = f"{prefix}.{df.fieldname}"
                    variable = f"{{{{{var_name}}}}}"
                    display_label = f"{df.label} (Proposal)"
                else:
                    var_name = df.fieldname
                    variable = f"{{{{{df.fieldname}}}}}"
                    display_label = df.label

                if var_name not in seen_variables:
                    seen_variables.add(var_name)
                    all_variables.append({
                        "label": display_label,
                        "fieldname": var_name,
                        "variable": variable,
                        "fieldtype": df.fieldtype,
                    })

    return sorted(all_variables, key=lambda x: x["label"])