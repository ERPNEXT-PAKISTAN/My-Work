"""Recorded approval is separate from docstatus and payment/fulfilment."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import frappe
from my_work.status_labels import describe
from my_work import api


class TestStatusLabels(unittest.TestCase):
    def setUp(self):
        clock = patch("my_work.loading.nowdate", return_value="2026-11-03")
        clock.start(); self.addCleanup(clock.stop)

    def describe(self,doctype='Sales Order',status=0,fields=None,permitted=None,workflow=None,expense_info=None,submittable=True):
        fields=fields or {}
        doc=frappe._dict(doctype=doctype,docstatus=status,**fields)
        meta=SimpleNamespace(is_submittable=submittable,get_field=lambda name:name in fields)
        return describe(doc,meta,workflow,set(fields) if permitted is None else permitted,expense_info)

    def test_submitted_does_not_invent_approval(self):
        result=self.describe(status=1,fields={'status':'To Deliver and Bill'})
        self.assertEqual(result['key'],'no_separate_approval')
        self.assertEqual(result['document_label'],'Submitted · Final')
        self.assertEqual(result['document_variant'],'info')

    def test_native_draft_without_decision_field_is_not_submitted(self):
        result=self.describe()
        self.assertEqual(result['document_label'],'Draft · Not Final')
        self.assertEqual(result['key'],'no_separate_approval')

    def test_draft_approval_decision_is_not_submitted(self):
        result=self.describe('Expense Claim',fields={'approval_status':'Approved'})
        self.assertEqual(result['key'],'approved');self.assertEqual(result['variant'],'success')
        self.assertIn('still Draft',result['explanation'])
        self.assertEqual(result['document_label'],'Draft · Not Final')

    def test_expense_claim_pending_and_rejected_decisions(self):
        for decision,key in [('Draft','not_approved'),('Pending','not_approved'),('Rejected','rejected')]:
            result=self.describe('Expense Claim',fields={'approval_status':decision})
            self.assertEqual(result['key'],key)

    def test_cancelled_document_does_not_display_current_approval(self):
        result=self.describe('Expense Claim',2,{'approval_status':'Approved'})
        self.assertEqual(result['key'],'cancelled');self.assertIn('historical',result['explanation'])

    def test_leave_approval_uses_native_decision(self):
        for status,key in [('Open','not_approved'),('Approved','approved'),('Rejected','rejected')]:
            self.assertEqual(self.describe('Leave Application',fields={'status':status})['key'],key)

    def test_record_does_not_invent_approval_or_submission(self):
        result=self.describe('Employee Checkin',submittable=False)
        self.assertEqual(result['key'],'no_separate_approval');self.assertEqual(result['document_label'],'Recorded')

    def test_protected_approval_field_is_not_inferred_from_docstatus(self):
        result=self.describe('Expense Claim',1,{'approval_status':'Approved'},permitted=set())
        self.assertEqual(result['key'],'unavailable');self.assertNotEqual(result['label'],'Approved')

    def test_unfamiliar_workflow_state_is_not_assumed_approved(self):
        wf=SimpleNamespace(workflow_state_field='workflow_state')
        result=self.describe(fields={'workflow_state':'Checked by Supervisor'},workflow=wf)
        self.assertEqual(result['key'],'workflow')
        self.assertEqual(result['label'],'Checked by Supervisor')

    def test_conflict_is_highlighted_before_approval(self):
        result=self.describe('Expense Claim',1,{'approval_status':'Approved'},expense_info={'has_conflict':True})
        self.assertEqual(result['key'],'conflict');self.assertEqual(result['variant'],'danger')

    def test_decision_filter_keeps_native_submitted_out_of_approved(self):
        rows=[dict(doctype='Sales Order',name='SO',module='Selling',modified='1',views=['all'],status_summary={'key':'no_separate_approval'}),dict(doctype='Expense Claim',name='EC',module='HR',modified='2',views=['all'],status_summary={'key':'approved'})]
        with patch.object(api,'_user'),patch.object(api,'_sources',return_value=[]),patch.object(api,'_rows',return_value=rows),patch.object(api,'_approval_status_options',return_value=[]):
            result=api.dashboard(decision='approved')
            self.assertEqual([row['name'] for row in result['data']],['EC'])
