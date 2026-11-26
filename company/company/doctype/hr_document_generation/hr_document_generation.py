# -*- coding: utf-8 -*-
# Copyright (c) 2026, Administrator and contributors
# For license information, please see license.txt

import html
import re
import frappe
from frappe import _
from frappe.model.document import Document

_ESCAPED_HTML_PATTERN = re.compile(
	r"&lt;\s*/?\s*(?:div|table|thead|tbody|tr|td|th|p|h[1-6]|span|strong|b|i|em|u|ul|ol|li|br|hr|style|section|header|footer|article|img|a|!doctype|html|body)\b[^&]*&gt;",
	re.IGNORECASE,
)


def normalize_html_content(content: str) -> str:
	"""Unescape editor-escaped HTML tags (e.g. pasted HTML inside Rich Text Editor)."""
	if not content or not isinstance(content, str):
		return content or ""

	if not _ESCAPED_HTML_PATTERN.search(content):
		return content

	cleaned = re.sub(r"</p>\s*<p[^>]*>", "\n", content, flags=re.IGNORECASE)
	cleaned = re.sub(r"^\s*<p[^>]*>", "", cleaned, flags=re.IGNORECASE)
	cleaned = re.sub(r"</p>\s*$", "", cleaned, flags=re.IGNORECASE)
	cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
	cleaned = html.unescape(cleaned)
	cleaned = cleaned.replace("\u00a0", " ")
	return cleaned.strip()


class HRDocumentGeneration(Document):
	def validate(self):
		self.validate_employee()
		self.validate_template()
		self.auto_populate_details()
		self.render_document()

	def validate_employee(self):
		if not self.employee:
			frappe.throw(_("Employee is required"))

		if not frappe.db.exists("Employee", self.employee):
			frappe.throw(_("Employee {0} does not exist").format(self.employee))

		# Auto set employee name
		self.employee_name = frappe.db.get_value("Employee", self.employee, "employee_name") or ""

	def validate_template(self):
		if not self.document_template:
			frappe.throw(_("Document Template is required"))

		template = frappe.get_doc("HR Document Template", self.document_template)

		if not template.is_active:
			frappe.throw(_("HR Document Template '{0}' is not active").format(template.template_name))

		# Check Category active status
		if template.category:
			category_active = frappe.db.get_value("HR Document Category", template.category, "is_active")
			if not category_active:
				frappe.throw(_("HR Document Category '{0}' associated with template is inactive").format(template.category))

		# Auto set document type from category
		self.document_type = template.category or ""

	def auto_populate_details(self):
		if not self.generated_by:
			self.generated_by = frappe.session.user

		if not self.generated_on:
			self.generated_on = frappe.utils.now_datetime()

		if not self.status:
			self.status = "Draft"

	def render_document(self):
		if self.document_template and self.employee:
			result = render_document_template(
				template_name=self.document_template,
				employee_id=self.employee,
				custom_subject=self.subject,
				custom_content=self.template_content,
			)
			self.rendered_subject = result.get("subject", "")
			self.rendered_content = result.get("content", "")


def render_document_template(template_name, employee_id, custom_subject=None, custom_content=None):
	"""
	Renders an HR Document Template for a specific Employee.
	Supports overriding subject or template_content on individual document generation.
	"""
	if not frappe.db.exists("HR Document Template", template_name):
		frappe.throw(_("Template '{0}' does not exist").format(template_name))

	template = frappe.get_doc("HR Document Template", template_name)

	if not template.is_active:
		frappe.throw(_("Template '{0}' is not active").format(template_name))

	if template.category:
		cat_active = frappe.db.get_value("HR Document Category", template.category, "is_active")
		if not cat_active:
			frappe.throw(_("HR Document Category '{0}' is not active").format(template.category))

	if not frappe.db.exists("Employee", employee_id):
		frappe.throw(_("Employee '{0}' does not exist").format(employee_id))

	emp_doc = frappe.get_doc("Employee", employee_id)

	# Build rendering context
	context = emp_doc.as_dict().copy()
	context["doc"] = emp_doc
	context["employee"] = emp_doc
	context["current_date"] = frappe.utils.formatdate(frappe.utils.nowdate(), "yyyy-MM-dd")
	context["now"] = frappe.utils.now_datetime()

	# Determine subject and content to render (prefer custom per-document overrides if provided)
	raw_subject = custom_subject if custom_subject and custom_subject.strip() else template.subject
	raw_content = custom_content if custom_content and custom_content.strip() else template.template_content
	raw_content = normalize_html_content(raw_content)

	rendered_subject = ""
	rendered_content = ""

	if raw_subject:
		try:
			rendered_subject = frappe.render_template(raw_subject, context)
		except Exception as e:
			frappe.log_error(f"Subject Render Error: {str(e)}", "HR Document Render")
			rendered_subject = raw_subject

	if raw_content:
		try:
			rendered_content = frappe.render_template(raw_content, context)
		except Exception as e:
			frappe.log_error(f"Content Render Error: {str(e)}", "HR Document Render")
			rendered_content = raw_content
		rendered_content = normalize_html_content(rendered_content)

	return {
		"subject": rendered_subject,
		"content": rendered_content,
	}


@frappe.whitelist()
def download_rendered_pdf(name: str):
	"""Generate and return a PDF containing only the Rendered Content of an HR Document Generation record."""
	from frappe.utils.pdf import get_pdf

	if not name:
		frappe.throw(_("Document name is required"))

	frappe.has_permission("HR Document Generation", "read", name, throw=True)
	doc = frappe.get_doc("HR Document Generation", name)

	content = normalize_html_content(doc.rendered_content or "")
	if not content and doc.document_template and doc.employee:
		res = render_document_template(
			template_name=doc.document_template,
			employee_id=doc.employee,
			custom_subject=doc.subject,
			custom_content=doc.template_content,
		)
		content = normalize_html_content(res.get("content", ""))

	if not content:
		content = "<p>No rendered content available.</p>"

	title = html.escape(doc.rendered_subject or doc.subject or doc.name or "HR Document")
	full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>{title}</title>
<style>
  @page {{
    size: A4;
    margin: 10mm;
  }}
  body {{
    font-family: Arial, Helvetica, sans-serif;
    font-size: 13px;
    line-height: 1.5;
    color: #1f2937;
    margin: 0;
    padding: 0;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  table {{
    border-collapse: collapse;
  }}
  img {{
    max-width: 100%;
    height: auto;
  }}
</style>
</head>
<body>
{content}
</body>
</html>"""

	pdf_bytes = get_pdf(
		full_html,
		options={
			"page-size": "A4",
			"margin-top": "10mm",
			"margin-bottom": "10mm",
			"margin-left": "10mm",
			"margin-right": "10mm",
		},
	)

	frappe.local.response.filename = f"{doc.name}.pdf"
	frappe.local.response.filecontent = pdf_bytes
	frappe.local.response.type = "pdf"
