import os
import frappe

def get_context(context):
    """
    Route fallback for face-api models.
    Redirects any /models/<filename> request to /assets/company/crm/models/<filename>.
    """
    path = frappe.request.path or ""
    if path.startswith("/models/"):
        filename = path[len("/models/"):].strip("/")
    else:
        filename = frappe.form_dict.get("model_file") or ""

    filename = os.path.basename(filename)
    if filename:
        target_url = f"/assets/company/crm/models/{filename}"
        frappe.redirect(target_url)

    frappe.throw("Model not found", frappe.PageDoesNotExistError)
