"""Linked previews retain task identity and source document read permissions."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import frappe
from my_work import assignment_details as details


class TestAssignmentDetails(unittest.TestCase):
    def task(self):
        return frappe._dict(reference_type='Expense Claim',reference_name='DEMO-EXP-1')

    def test_brief_shows_readable_claim_amount_employee_and_state(self):
        values=dict(doctype='Expense Claim',total_claimed_amount=15000,currency='PKR',employee_name='Demo Employee',status='Unpaid',private_note='PRIVATE')
        doc=MagicMock();doc.doctype='Expense Claim';doc.get.side_effect=values.get
        with patch.object(details.frappe,'get_doc',return_value=doc),patch.object(details.frappe,'get_meta'),patch.object(details,'get_permitted_fields',return_value=['total_claimed_amount','currency','employee_name','status']):
            result=details.reference_brief(self.task())
        self.assertEqual(result['amount'],15000);self.assertEqual(result['currency'],'PKR')
        self.assertEqual(result['fields'][0]['value'],'Demo Employee')
        self.assertNotIn('PRIVATE',str(result));doc.check_permission.assert_called_once_with('read')

    def test_unreadable_reference_exposes_no_preview(self):
        doc=MagicMock();doc.check_permission.side_effect=frappe.PermissionError
        with patch.object(details.frappe,'get_doc',return_value=doc),patch.object(details,'get_permitted_fields') as fields:
            self.assertIsNone(details.reference_brief(self.task()))
        fields.assert_not_called()
        with patch('my_work.api.review',side_effect=frappe.PermissionError):
            self.assertIsNone(details.reference_review(self.task()))

    def test_review_is_a_readonly_subset_with_primary_line_items(self):
        source=dict(doctype='Expense Claim',name='DEMO-EXP-1',fields=[],summary_fields=[dict(fieldname='employee',label='Employee',value='Demo Employee')],remark_fields=[],currency='PKR',business_status='Unpaid',state='Submitted',flow_mode='standard',tables=[dict(label='Expense Details',columns=['expense_type','amount'],rows=[{'expense_type':'Travel','amount':15000}],total=15000),dict(fieldname='taxes',label='Taxes')],actions=['Cancel'],tools={'can_share':True},activity=[{'content':'private source activity'}])
        with patch('my_work.api.review',return_value={'data':source}) as review:
            result=details.reference_review(self.task())
        review.assert_called_once_with('Expense Claim','DEMO-EXP-1')
        self.assertNotIn('actions',result);self.assertNotIn('tools',result);self.assertNotIn('activity',result)
        self.assertEqual(len(result['tables']),1)
        self.assertEqual(result['summary_fields'][-1]['value'],'Unpaid')

    def test_empty_or_chained_task_reference_is_not_followed(self):
        with patch.object(details.frappe,'get_doc') as get:
            self.assertIsNone(details.reference_brief(frappe._dict()))
            self.assertIsNone(details.reference_brief(frappe._dict(reference_type='ToDo',reference_name='OTHER-TODO')))
        get.assert_not_called()
