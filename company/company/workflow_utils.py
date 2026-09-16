import frappe

@frappe.whitelist()
def update_lead_workflow():
    """
    Programmatically update the Lead Workflow to allow transitions between any two states.
    Ensures that 'Move to [State]' actions exist in Workflow Action Master.
    """
    try:
        # 1. Get all documented states for Lead Workflow
        states = frappe.db.get_all("Workflow Document State", {"parent": "Lead Workflow"}, pluck="state")
        
        if not states:
            print("No states found for Lead Workflow")
            return

        # 2. Ensure all actions exist in Workflow Action Master
        for ns in states:
            action_name = f"Move to {ns}"
            if not frappe.db.exists("Workflow Action Master", action_name):
                frappe.get_doc({
                    "doctype": "Workflow Action Master",
                    "workflow_action_name": action_name
                }).insert(ignore_permissions=True)
        
        # 3. Clear existing transitions and add all possible combinations
        frappe.db.delete("Workflow Transition", {"parent": "Lead Workflow"})
        
        idx = 0
        for s in states:
            for ns in states:
                if s == ns: continue
                idx += 1
                doc = frappe.new_doc("Workflow Transition")
                doc.parent = "Lead Workflow"
                doc.parenttype = "Workflow"
                doc.parentfield = "transitions"
                doc.state = s
                doc.action = f"Move to {ns}"
                doc.next_state = ns
                doc.allowed = "All"
                doc.idx = idx
                doc.insert(ignore_permissions=True)
        
        frappe.db.commit()
        print(f"Workflow transitions updated successfully. Total transitions: {idx}")
        return {"status": "success", "transitions": idx}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Lead Workflow Update Error")
        print(f"Error: {str(e)}")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def update_lead_workflow_v2():

    workflow_name = "Lead Workflow"

    states = [
        "New Lead",
        "Contacted",
        "Qualified",
        "Proposal Sent",
        "In Negotiation",
        "Follow-up Scheduled",
        "On Hold",
        "Proposal Approved",
        "Proposal Rejected",
        "In Active",
        "Not Interested"
    ]

    # Create Workflow Action Master records
    for state in states:
        action_name = f"Move to {state}"

        if not frappe.db.exists(
            "Workflow Action Master",
            action_name
        ):
            frappe.get_doc({
                "doctype": "Workflow Action Master",
                "workflow_action_name": action_name
            }).insert(
                ignore_permissions=True
            )

    # Remove existing transitions
    frappe.db.delete(
        "Workflow Transition",
        {
            "parent": workflow_name
        }
    )

    idx = 1

    # Create all possible transitions
    for current_state in states:
        for next_state in states:

            if current_state == next_state:
                continue

            frappe.get_doc({
                "doctype": "Workflow Transition",
                "parent": workflow_name,
                "parenttype": "Workflow",
                "parentfield": "transitions",
                "state": current_state,
                "action": f"Move to {next_state}",
                "next_state": next_state,
                "allowed": "All",
                "idx": idx
            }).insert(
                ignore_permissions=True
            )

            idx += 1

    frappe.db.commit()

    return {
        "status": "success",
        "states": len(states),
        "transitions": idx - 1
    }

# -------------------------------------------------------------------------------------------------------------------
# bench --site erp.localhost.innoblitz execute company.company.workflow_utils.create_lead_workflow
# bench --site erp.localhost.innoblitz execute company.company.workflow_utils.create_reimbursement_workflow
# bench --site erp.localhost.innoblitz execute company.company.workflow_utils.create_request_workflow
# bench --site erp.localhost.innoblitz execute company.company.workflow_utils.create_wfh_attendance_workflow
# bench --site erp.localhost.innoblitz execute company.company.workflow_utils.create_leave_application_workflow
# -------------------------------------------------------------------------------------------------------------------

@frappe.whitelist()
def create_lead_workflow():
    workflow_name = "Lead Doctype Workflow"
    
    if frappe.db.exists("Workflow", workflow_name):
        return {
            "status": "success",
            "message": "Workflow already exists",
            "total_states": 0,
            "total_transitions": 0
        }
        
    states = [
        "New Lead", "Contacted", "Qualified", "Proposal Sent", 
        "In Negotiation", "Follow-up Scheduled", "On Hold", 
        "In Active", "Not Interested", "Closed"
    ]
    
    for state in states:
        if not frappe.db.exists("Workflow State", state):
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": state
            }).insert(ignore_permissions=True, ignore_mandatory=True)
            
    for state in states:
        action_name = f"Move to {state}"
        if not frappe.db.exists("Workflow Action Master", action_name):
            frappe.get_doc({
                "doctype": "Workflow Action Master",
                "workflow_action_name": action_name
            }).insert(ignore_permissions=True, ignore_mandatory=True)
            
    workflow_doc = {
        "doctype": "Workflow",
        "workflow_name": workflow_name,
        "document_type": "Lead",
        "workflow_state_field": "workflow_state",
        "is_active": 0,
        "states": [],
        "transitions": []
    }
    
    for state in states:
        workflow_doc["states"].append({
            "state": state,
            "doc_status": "0",
            "allow_edit": "All"
        })
        
    transition_count = 0
    for from_state in states:
        for to_state in states:
            if from_state != to_state:
                workflow_doc["transitions"].append({
                    "state": from_state,
                    "action": f"Move to {to_state}",
                    "next_state": to_state,
                    "allowed": "All"
                })
                transition_count += 1
                
    doc = frappe.get_doc(workflow_doc)
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    frappe.db.commit()
    
    return {
        "status": "success",
        "message": "Workflow created successfully",
        "total_states": len(states),
        "total_transitions": transition_count
    }


@frappe.whitelist()
def create_reimbursement_workflow():
    workflow_name = "Reimbursement Claim Doctype Workflow"
    
    if frappe.db.exists("Workflow", workflow_name):
        return {
            "status": "success",
            "message": "Workflow already exists",
            "total_states": 0,
            "total_transitions": 0
        }
        
    states_data = [
        {"state": "Draft", "doc_status": "0", "allow_edit": "Employee"},
        {"state": "Pending", "doc_status": "1", "allow_edit": "HR"},
        {"state": "Approved", "doc_status": "1", "allow_edit": "HR"},
        {"state": "Paid", "doc_status": "1", "allow_edit": "HR"},
        {"state": "Rejected", "doc_status": "2", "allow_edit": "HR"}
    ]
    
    transitions_data = [
        {"state": "Draft", "action": "Submit", "next_state": "Pending", "allowed": "Employee"},
        {"state": "Pending", "action": "Approve", "next_state": "Approved", "allowed": "HR"},
        {"state": "Pending", "action": "Reject", "next_state": "Rejected", "allowed": "HR"},
        {"state": "Approved", "action": "Mark Paid", "next_state": "Paid", "allowed": "HR"}
    ]
    
    for s in states_data:
        if not frappe.db.exists("Workflow State", s["state"]):
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": s["state"]
            }).insert(ignore_permissions=True, ignore_mandatory=True)
            
    for t in transitions_data:
        action_name = t["action"]
        if not frappe.db.exists("Workflow Action Master", action_name):
            frappe.get_doc({
                "doctype": "Workflow Action Master",
                "workflow_action_name": action_name
            }).insert(ignore_permissions=True, ignore_mandatory=True)
            
    workflow_doc = {
        "doctype": "Workflow",
        "workflow_name": workflow_name,
        "document_type": "Reimbursement Claim",
        "workflow_state_field": "workflow_state",
        "is_active": 0,
        "states": [],
        "transitions": []
    }
    
    for s in states_data:
        workflow_doc["states"].append({
            "state": s["state"],
            "doc_status": s["doc_status"],
            "allow_edit": s["allow_edit"]
        })
        
    for t in transitions_data:
        workflow_doc["transitions"].append({
            "state": t["state"],
            "action": t["action"],
            "next_state": t["next_state"],
            "allowed": t["allowed"]
        })
                
    doc = frappe.get_doc(workflow_doc)
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    frappe.db.commit()
    
    return {
        "status": "success",
        "message": "Workflow created successfully",
        "total_states": len(states_data),
        "total_transitions": len(transitions_data)
    }


@frappe.whitelist()
def create_request_workflow():
    workflow_name = "Request Doctype Workflow"
    
    if frappe.db.exists("Workflow", workflow_name):
        return {
            "status": "success",
            "message": "Workflow already exists",
            "total_states": 0,
            "total_transitions": 0
        }
        
    states_data = [
        {"state": "Draft", "doc_status": "0", "allow_edit": "Employee"},
        {"state": "Pending", "doc_status": "1", "allow_edit": "HR"},
        {"state": "Clarification Requested", "doc_status": "1", "allow_edit": "Employee"},
        {"state": "Approved", "doc_status": "1", "allow_edit": "Employee"},
        {"state": "Rejected", "doc_status": "2", "allow_edit": "HR"}
    ]
    
    transitions_data = [
        {"state": "Draft", "action": "Submit", "next_state": "Pending", "allowed": "Employee"},
        {"state": "Pending", "action": "Approve", "next_state": "Approved", "allowed": "HR"},
        {"state": "Pending", "action": "Reject", "next_state": "Rejected", "allowed": "HR"},
        {"state": "Pending", "action": "Ask Clarification", "next_state": "Clarification Requested", "allowed": "HR"},
        {"state": "Clarification Requested", "action": "Reply", "next_state": "Pending", "allowed": "Employee"},
        {"state": "Clarification Requested", "action": "Approve", "next_state": "Approved", "allowed": "HR"},
        {"state": "Clarification Requested", "action": "Reject", "next_state": "Rejected", "allowed": "HR"}
    ]
    
    for s in states_data:
        if not frappe.db.exists("Workflow State", s["state"]):
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": s["state"]
            }).insert(ignore_permissions=True, ignore_mandatory=True)
            
    for t in transitions_data:
        action_name = t["action"]
        if not frappe.db.exists("Workflow Action Master", action_name):
            frappe.get_doc({
                "doctype": "Workflow Action Master",
                "workflow_action_name": action_name
            }).insert(ignore_permissions=True, ignore_mandatory=True)
            
    workflow_doc = {
        "doctype": "Workflow",
        "workflow_name": workflow_name,
        "document_type": "Request",
        "workflow_state_field": "workflow_state",
        "is_active": 0,
        "states": [],
        "transitions": []
    }
    
    for s in states_data:
        workflow_doc["states"].append({
            "state": s["state"],
            "doc_status": s["doc_status"],
            "allow_edit": s["allow_edit"]
        })
        
    for t in transitions_data:
        workflow_doc["transitions"].append({
            "state": t["state"],
            "action": t["action"],
            "next_state": t["next_state"],
            "allowed": t["allowed"]
        })
                
    doc = frappe.get_doc(workflow_doc)
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    frappe.db.commit()
    
    return {
        "status": "success",
        "message": "Workflow created successfully",
        "total_states": len(states_data),
        "total_transitions": len(transitions_data)
    }


@frappe.whitelist()
def create_wfh_attendance_workflow():
    workflow_name = "WFH Attendance Doctype Workflow"
    
    if frappe.db.exists("Workflow", workflow_name):
        return {
            "status": "success",
            "message": "Workflow already exists",
            "total_states": 0,
            "total_transitions": 0
        }
        
    states_data = [
        {"state": "Draft", "doc_status": "0", "allow_edit": "Employee"},
        {"state": "Pending", "doc_status": "1", "allow_edit": "HR"},
        {"state": "Approved", "doc_status": "1", "allow_edit": "Employee"},
        {"state": "Rejected", "doc_status": "2", "allow_edit": "HR"}
    ]
    
    transitions_data = [
        {"state": "Draft", "action": "Submit", "next_state": "Pending", "allowed": "Employee"},
        {"state": "Pending", "action": "Approve", "next_state": "Approved", "allowed": "HR"},
        {"state": "Pending", "action": "Reject", "next_state": "Rejected", "allowed": "HR"}
    ]
    
    for s in states_data:
        if not frappe.db.exists("Workflow State", s["state"]):
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": s["state"]
            }).insert(ignore_permissions=True, ignore_mandatory=True)
            
    for t in transitions_data:
        action_name = t["action"]
        if not frappe.db.exists("Workflow Action Master", action_name):
            frappe.get_doc({
                "doctype": "Workflow Action Master",
                "workflow_action_name": action_name
            }).insert(ignore_permissions=True, ignore_mandatory=True)
            
    workflow_doc = {
        "doctype": "Workflow",
        "workflow_name": workflow_name,
        "document_type": "WFH Attendance",
        "workflow_state_field": "workflow_state",
        "is_active": 0,
        "states": [],
        "transitions": []
    }
    
    for s in states_data:
        workflow_doc["states"].append({
            "state": s["state"],
            "doc_status": s["doc_status"],
            "allow_edit": s["allow_edit"]
        })
        
    for t in transitions_data:
        workflow_doc["transitions"].append({
            "state": t["state"],
            "action": t["action"],
            "next_state": t["next_state"],
            "allowed": t["allowed"]
        })
                
    doc = frappe.get_doc(workflow_doc)
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    frappe.db.commit()
    
    return {
        "status": "success",
        "message": "Workflow created successfully",
        "total_states": len(states_data),
        "total_transitions": len(transitions_data)
    }


@frappe.whitelist()
def create_leave_application_workflow():
    workflow_name = "Leave Doctype Workflow"
    
    if frappe.db.exists("Workflow", workflow_name):
        return {
            "status": "success",
            "message": "Workflow already exists",
            "total_states": 0,
            "total_transitions": 0
        }
        
    states_data = [
        {"state": "Draft", "doc_status": "0", "allow_edit": "Employee"},
        {"state": "Pending", "doc_status": "1", "allow_edit": "HR", "message": "Please approve the leave"},
        {"state": "Approved", "doc_status": "1", "allow_edit": "HR", "message": "Leave Approved"},
        {"state": "Rejected", "doc_status": "2", "allow_edit": "HR", "message": "Leave Rejected"},
        {"state": "Clarification Requested", "doc_status": "1", "allow_edit": "Employee", "message": "HR has requested clarification"}
    ]
    
    transitions_data = [
        {"state": "Draft", "action": "Submit", "next_state": "Pending", "allowed": "Employee"},
        {"state": "Pending", "action": "Approve", "next_state": "Approved", "allowed": "HR"},
        {"state": "Pending", "action": "Reject", "next_state": "Rejected", "allowed": "HR"},
        {"state": "Pending", "action": "Ask Clarification", "next_state": "Clarification Requested", "allowed": "HR"},
        {"state": "Clarification Requested", "action": "Reply", "next_state": "Pending", "allowed": "Employee"},
        {"state": "Clarification Requested", "action": "Approve", "next_state": "Approved", "allowed": "HR"},
        {"state": "Clarification Requested", "action": "Reject", "next_state": "Rejected", "allowed": "HR"}
    ]
    
    for s in states_data:
        if not frappe.db.exists("Workflow State", s["state"]):
            frappe.get_doc({
                "doctype": "Workflow State",
                "workflow_state_name": s["state"]
            }).insert(ignore_permissions=True, ignore_mandatory=True)
            
    for t in transitions_data:
        action_name = t["action"]
        if not frappe.db.exists("Workflow Action Master", action_name):
            frappe.get_doc({
                "doctype": "Workflow Action Master",
                "workflow_action_name": action_name
            }).insert(ignore_permissions=True, ignore_mandatory=True)
            
    workflow_doc = {
        "doctype": "Workflow",
        "workflow_name": workflow_name,
        "document_type": "Leave Application",
        "workflow_state_field": "workflow_state",
        "is_active": 0,
        "states": [],
        "transitions": []
    }
    
    for s in states_data:
        state_dict = {
            "state": s["state"],
            "doc_status": s["doc_status"],
            "allow_edit": s["allow_edit"]
        }
        if "message" in s:
            state_dict["message"] = s["message"]
        workflow_doc["states"].append(state_dict)
        
    for t in transitions_data:
        workflow_doc["transitions"].append({
            "state": t["state"],
            "action": t["action"],
            "next_state": t["next_state"],
            "allowed": t["allowed"]
        })
                
    doc = frappe.get_doc(workflow_doc)
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    frappe.db.commit()
    
    return {
        "status": "success",
        "message": "Workflow created successfully",
        "total_states": len(states_data),
        "total_transitions": len(transitions_data)
    }