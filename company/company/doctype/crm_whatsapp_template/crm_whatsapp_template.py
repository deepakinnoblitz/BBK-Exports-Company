# Copyright (c) 2026, Deepak and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CRMWhatsAppTemplate(Document):
    pass


@frappe.whitelist()
def get_whatsapp_template_variables(used_for):
    """
    Returns template variables for selected document types.
    Supports comma-separated multi-select values like "Lead,Deal,Proposal".
    """

    # Map frontend values to (actual_doctype, variable_prefix)
    doctype_map = {
        "Lead": ("Lead", None),
        "Contact": ("Contacts", None),
        "Contacts": ("Contacts", None),
        "Account": ("Accounts", None),
        "Accounts": ("Accounts", None),
        "Deal": ("Deal", None),
        "Deals": ("Deal", None),
        "Proposal": ("Proposal", "proposal"),  # rendered as {{ proposal.fieldname }}
        "Proposals": ("Proposal", "proposal"),
        "Invoice": ("Invoice", None),
        "Estimation": ("Estimation", None),
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
        "status",
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

    # Only expand these doctypes when following Link fields
    allowed_link_doctypes = {
        "Lead",
        "Contacts",
        "Accounts",
        "Deal",
        "Proposal",
        "Invoice",
        "Estimation",
    }

    # Split comma-separated values and process each
    selected_types = [t.strip() for t in used_for.split(",") if t.strip()]

    all_variables = []
    visited = set()

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
                not df.fieldname
                or df.fieldname in exclude
                or df.fieldtype in ignore_fieldtypes
                or df.hidden
            ):
                continue

            # Build variable name with optional prefix
            if prefix:
                var_name = f"{prefix}.{df.fieldname}"
                variable = f"{{{{{var_name}}}}}"
                display_label = f"{df.label} (Proposal)"
            else:
                var_name = df.fieldname
                variable = f"{{{{{df.fieldname}}}}}"
                display_label = df.label

            if var_name not in visited:
                visited.add(var_name)
                all_variables.append({
                    "label": display_label,
                    "fieldname": var_name,
                    "variable": variable,
                    "fieldtype": df.fieldtype,
                })

            # Expand only business link doctypes (only when no prefix to avoid nested prefixes)
            if (
                not prefix
                and df.fieldtype == "Link"
                and df.options
                and df.options in allowed_link_doctypes
            ):
                try:
                    link_meta = frappe.get_meta(df.options)

                    for link_df in link_meta.fields:

                        if (
                            not link_df.fieldname
                            or link_df.fieldname in exclude
                            or link_df.fieldtype in ignore_fieldtypes
                            or link_df.hidden
                        ):
                            continue

                        linked_var = f"{df.fieldname}.{link_df.fieldname}"

                        if linked_var in visited:
                            continue

                        visited.add(linked_var)

                        all_variables.append({
                            "label": f"{df.label} → {link_df.label}",
                            "fieldname": linked_var,
                            "variable": f"{{{{{linked_var}}}}}",
                            "fieldtype": link_df.fieldtype,
                        })

                except Exception:
                    pass

    return sorted(
        all_variables,
        key=lambda x: x["label"].lower()
    )