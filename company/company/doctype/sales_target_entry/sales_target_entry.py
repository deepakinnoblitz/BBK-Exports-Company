import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class SalesTargetEntry(Document):
    pass


@frappe.whitelist()
def get_next_sales_target_preview():
    today = now_datetime()

    # Financial Year (April -March)
    if today.month >= 4:
        fy_start = str(today.year)[-2:]
        fy_end = str(today.year + 1)[-2:]
    else:
        fy_start = str(today.year - 1)[-2:]
        fy_end = str(today.year)[-2:]

    fy = f"{fy_start}-{fy_end}"
    prefix = f"IB-ST/{fy}/"

    last = frappe.db.sql(
        """
        SELECT sales_entry_id
        FROM `tabSales Target Entry`
        WHERE sales_entry_id LIKE %s
        ORDER BY creation DESC
        LIMIT 1
        """,
        (prefix + "%",),
        as_dict=True,
    )

    if last:
        last_no = int(last[0].sales_entry_id.split("/")[-1]) + 1
    else:
        last_no = 1

    return f"{prefix}{last_no:03d}"