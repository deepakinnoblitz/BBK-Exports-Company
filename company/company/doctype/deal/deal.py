import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime
import json

class Deal(Document):
    def before_save(self):
        self.validate_estimation_stage()
        self.log_stage_history()

    def validate_estimation_stage(self):
        if self.stage in ["Estimation Created", "Estimation Sent"]:
            est_count = frappe.db.count("Estimation", {"deal": self.name})
            if est_count == 0:
                frappe.throw("At least one Estimation must be created.")
        elif self.stage in ["Invoice Created", "Invoice Sent"]:
            inv_count = frappe.db.count("Invoice", {"deal": self.name})
            if inv_count == 0:
                frappe.throw("At least one Invoice must be created.")

    def log_stage_history(self):
        if self.is_new():
            return

        old_stage = frappe.db.get_value("Deal", self.name, "stage")
        new_stage = self.stage

        if not old_stage or old_stage == new_stage:
            return

        self.append("stage_history", {
            "state_from": old_stage,
            "state_to": new_stage,
            "date_and_time": now_datetime(),
            "change_by": frappe.session.user
        })
 
@frappe.whitelist()
def get_deals_list(start=0, page_length=20, search=None, stage=None, sort_by=None, filterValues=None):
    start = int(start)
    page_length = int(page_length)
   
    filters = []
    if filterValues:
        if isinstance(filterValues, str):
            filterValues = json.loads(filterValues)
           
        for key, value in filterValues.items():
            if value and value != 'all':
                filters.append(f"d.{key} = {frappe.db.escape(value)}")
 
    if stage and stage != 'all' and (not filterValues or not filterValues.get('stage')):
        filters.append(f"d.stage = {frappe.db.escape(stage)}")

    # --- Row-level security: restrict to owner when User Permission exists ---
    current_user = frappe.session.user
    has_user_permission = frappe.db.exists("User Permission", {"user": current_user})
    if has_user_permission:
        filters.append(f"d.owner = {frappe.db.escape(current_user)}")
 
    search_condition = ""
    if search:
        search_term = f"%{search}%"
        search_condition = f"AND (d.name LIKE {frappe.db.escape(search_term)} OR d.deal_title LIKE {frappe.db.escape(search_term)} OR d.account LIKE {frappe.db.escape(search_term)})"
 
    filter_condition = " AND ".join(filters)
    if filter_condition:
        filter_condition = "AND " + filter_condition
 
    order_by = "d.creation DESC"
    if sort_by:
        if sort_by == 'contact_name_asc':
            order_by = "c.first_name ASC"
        elif sort_by == 'contact_name_desc':
            order_by = "c.first_name DESC"
        else:
            # Convert standard frappe sort format e.g. "creation_desc" -> "d.creation DESC"
            parts = sort_by.rsplit('_', 1)
            if len(parts) == 2 and parts[1] in ['asc', 'desc']:
                field, direction = parts
                # Map common fields if necessary or use directly
                order_by = f"d.{field} {direction.upper()}"
 
    sql = f"""
        SELECT
            d.name, d.deal_title, d.account, d.contact, d.value,
            d.expected_close_date, d.stage, d.probability, d.type,
            d.source_lead, d.next_step, d.notes, d.deal_owner, d.owner, d.creation,
            c.first_name as contact_name, a.account_name
        FROM
            `tabDeal` d
        LEFT JOIN
            `tabContacts` c ON d.contact = c.name
        LEFT JOIN
            `tabAccounts` a ON d.account = a.name
        WHERE
            1=1
            {filter_condition}
            {search_condition}
        ORDER BY
            {order_by}
        LIMIT
            {page_length} OFFSET {start}
    """
 
    data = frappe.db.sql(sql, as_dict=True)
   
    # Get total count for pagination
    count_sql = f"""
        SELECT COUNT(*) as total
        FROM `tabDeal` d
        LEFT JOIN `tabContacts` c ON d.contact = c.name
        WHERE
            1=1
            {filter_condition}
            {search_condition}
    """
    count = frappe.db.sql(count_sql, as_dict=True)[0].total
 
    return {
        "data": data,
        "total": count
    }
 
@frappe.whitelist()
def get_deal_details(name=None):
    if not name:
        name = frappe.form_dict.get('name')
    
    if not name:
        return None

    sql = f"""
        SELECT
            d.name, d.deal_title, d.account, d.contact, d.value,
            d.expected_close_date, d.stage, d.probability, d.type,
            d.source_lead, d.next_step, d.notes, d.deal_owner, d.owner, d.creation, d.modified,
            c.first_name as contact_name, a.account_name
        FROM
            `tabDeal` d
        LEFT JOIN
            `tabContacts` c ON d.contact = c.name
        LEFT JOIN
            `tabAccounts` a ON d.account = a.name
        WHERE
            d.name = {frappe.db.escape(name)}
    """
   
    data = frappe.db.sql(sql, as_dict=True)
   
    if not data:
        return None
       
    deal_doc = data[0]

    history = frappe.get_all(
        "Deal Pipeline Timeline",
        filters={"parent": name, "parenttype": "Deal", "parentfield": "stage_history"},
        fields=["state_from", "state_to", "date_and_time", "change_by"],
        order_by="date_and_time DESC"
    )
    for h in history:
        if h.get("change_by"):
            user_full_name = frappe.db.get_value("User", h["change_by"], "full_name")
            h["change_by_name"] = user_full_name or h["change_by"]

    deal_owner_id = deal_doc.get("deal_owner") or deal_doc.get("owner")
    if deal_owner_id:
        deal_doc["deal_owner_name"] = frappe.db.get_value("User", deal_owner_id, "full_name") or deal_owner_id

    deal_doc["stage_history"] = history
    return deal_doc
 