import unittest
import frappe


class TestProposal(unittest.TestCase):
    def test_sent_status_requires_attachment(self):
        proposal = frappe.get_doc({
            "doctype": "Proposal",
            "proposal_title": "Test Proposal",
            "client_name": "Test Client",
            "status": "Sent",
            "proposal_date": frappe.utils.nowdate(),
            "attachments_table": []
        })

        with self.assertRaises(frappe.ValidationError):
            proposal.insert()
