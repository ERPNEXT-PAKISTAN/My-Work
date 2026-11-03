"""Exercise configured transitions through core apply_workflow without site writes."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import frappe
from frappe.model.docstatus import DocStatus
from frappe.model import workflow as core
from frappe.workflow.doctype.workflow.workflow import Workflow
from my_work.workflow_setup import definition
from my_work import workflow_support


class TestExpenseWorkflowDefinition(unittest.TestCase):
    def workflow(self):
        data=definition()
        return frappe._dict(workflow_state_field='workflow_state',states=[frappe._dict(row) for row in data['states']],transitions=[frappe._dict(row) for row in data['transitions']])

    def test_native_docstatus_validation_and_legacy_compatibility(self):
        wf=self.workflow();Workflow.validate_docstatus(wf)
        self.assertEqual(next(s.doc_status for s in wf.states if s.state=='Rejected'),'2')
        self.assertEqual(next(s.doc_status for s in wf.states if s.state=='Request Rejected'),'0')
        self.assertTrue(next(s.is_optional_state for s in wf.states if s.state=='Cancelled'))

    def exercise(self,source,action,initial,expected,method):
        wf=self.workflow();transition=next(t for t in wf.transitions if t.state==source and t.action==action)
        values={'doctype':'Expense Claim','name':'TEST-WORKFLOW','owner':'employee@example.test','workflow_state':source,'approval_status':initial}
        doc=MagicMock();doc.docstatus=DocStatus(1 if source=='Approved' else 0);doc.meta=SimpleNamespace(queue_in_background=False)
        doc.get.side_effect=values.get;doc.set.side_effect=lambda key,value:values.update({key:value})
        def persist():
            self.assertEqual(values['approval_status'],expected)
            if method=='submit':doc.docstatus=DocStatus(1)
            if method=='cancel':doc.docstatus=DocStatus(2)
        getattr(doc,method).side_effect=persist
        with patch.object(frappe,'session',SimpleNamespace(user='approver@example.test')),patch.object(frappe,'get_doc',return_value=doc),patch.object(core,'get_workflow',return_value=wf),patch.object(core,'get_transitions',return_value=[transition]):
            core.apply_workflow('{}',action)
        getattr(doc,method).assert_called_once()
        self.assertEqual(values['workflow_state'],transition.next_state)
        return doc

    def test_approve_sets_native_decision_before_core_submission(self):
        self.exercise('Pending','Approve','Draft','Approved','submit')

    def test_reject_remains_draft_and_sets_rejected_decision(self):
        doc=self.exercise('Pending','Reject','Draft','Rejected','save')
        doc.submit.assert_not_called();doc.cancel.assert_not_called()

    def test_return_resets_decision_without_submission(self):
        self.exercise('Pending','Return','Approved','Draft','save')

    def test_resubmit_returns_to_pending(self):
        self.exercise('Returned','Resubmit','Draft','Draft','save')

    def test_cancel_sets_cancelled_decision_before_core_cancellation(self):
        self.exercise('Approved','Cancel','Approved','Cancelled','cancel')


class TestWorkflowActionSynchronization(unittest.TestCase):
    def setUp(self):
        for name,value in [('session',SimpleNamespace(user='employee@example.test')),('db',MagicMock())]:
            context=patch.object(frappe,name,value);context.start();self.addCleanup(context.stop)
        wf=SimpleNamespace(states=[SimpleNamespace(state='Request Rejected')],workflow_state_field='workflow_state')
        for target,value in [('get_workflow_name','Expense Claim')]:
            context=patch.object(workflow_support,target,return_value=value);context.start();self.addCleanup(context.stop)
        context=patch.object(frappe,'get_cached_doc',return_value=wf);context.start();self.addCleanup(context.stop)
        context=patch('frappe.desk.notifications.clear_doctype_notifications');context.start();self.addCleanup(context.stop)

    def document(self,state):
        doc=MagicMock(doctype='Expense Claim',name='TEST-1');doc.get.side_effect={'workflow_state':state}.get
        doc.get_doc_before_save.return_value=None
        return doc

    def test_resubmit_completes_actual_actor_task_and_reopens_native_approval(self):
        doc=self.document('Pending');before=MagicMock();before.get.side_effect={'workflow_state':'Returned','owner':'employee@example.test'}.get;doc.get_doc_before_save.return_value=before
        action=MagicMock(workflow_state='Returned',name='RETURN-TASK');action.permitted_roles=[SimpleNamespace(role='Employee')]
        transition=frappe._dict(next_state='Pending',allowed='Employee',allow_self_approval=1)
        frappe.db.exists.return_value=False
        with patch.object(workflow_support,'get_next_possible_transitions',return_value=[SimpleNamespace(allowed='Expense Approver')]),patch.object(workflow_support,'get_transitions',return_value=[transition]),patch.object(frappe,'get_all',return_value=['RETURN-TASK']),patch.object(frappe,'get_doc',return_value=action),patch.object(workflow_support,'update_completed_workflow_actions_using_role') as complete,patch.object(workflow_support,'create_workflow_actions_for_roles') as create,patch.object(workflow_support,'_retire') as retire:
            result=workflow_support.synchronize(doc)
        self.assertEqual(result['completed_transition'],1);self.assertEqual(result['created'],1)
        self.assertEqual(complete.call_args.kwargs['workflow_action'][0].role,'Employee')
        create.assert_called_once_with(['Expense Approver'],doc);retire.assert_not_called();doc.save.assert_not_called()

    def test_configuration_cleanup_does_not_record_a_fabricated_approver(self):
        doc=self.document('Approved');action=MagicMock(workflow_state='Approved',name='STALE-TASK')
        with patch.object(workflow_support,'get_next_possible_transitions',return_value=[]),patch.object(frappe,'get_all',return_value=['STALE-TASK']),patch.object(frappe,'get_doc',return_value=action),patch.object(workflow_support,'create_workflow_actions_for_roles') as create:
            result=workflow_support.synchronize(doc,configuration_migration=True)
        self.assertEqual(result['retired'],1);self.assertEqual(action.status,'Completed')
        self.assertIsNone(action.completed_by);self.assertIsNone(action.completed_by_role)
        action.add_comment.assert_called_once();create.assert_not_called();doc.save.assert_not_called()

    def test_existing_current_action_is_not_duplicated(self):
        doc=self.document('Pending');action=MagicMock(workflow_state='Pending');action.permitted_roles=[SimpleNamespace(role='Expense Approver')];frappe.db.exists.return_value=True
        with patch.object(workflow_support,'get_next_possible_transitions',return_value=[SimpleNamespace(allowed='Expense Approver')]),patch.object(frappe,'get_all',return_value=['PENDING-TASK']),patch.object(frappe,'get_doc',return_value=action),patch.object(workflow_support,'create_workflow_actions_for_roles') as create:
            result=workflow_support.synchronize(doc)
        self.assertIsNone(result);create.assert_not_called();action.save.assert_not_called()

class TestConfiguredFlowInMyWork(unittest.TestCase):
    def test_optional_cancel_does_not_make_a_paid_claim_pending(self):
        from my_work import api
        data=definition();wf=frappe._dict(workflow_state_field='workflow_state',states=[frappe._dict(r) for r in data['states']],transitions=[frappe._dict(r) for r in data['transitions']])
        values={'workflow_state':'Approved','approval_status':'Approved','status':'Paid','grand_total':0,'total_amount_reimbursed':0,'total_advance_amount':100}
        doc=MagicMock(doctype='Expense Claim',docstatus=1);doc.get.side_effect=values.get
        with patch.object(frappe,'db',MagicMock()):
            info=api._expense_status(doc,wf,set(values))
            views,*_=api._document_views(doc,wf,True,True,['Cancel'],True,set(values))
        self.assertTrue(info['completed']);self.assertIn('completed',views);self.assertNotIn('approvals',views)

class TestDraftSubmissionPhase(unittest.TestCase):
    workflow = TestExpenseWorkflowDefinition.workflow
    exercise = TestExpenseWorkflowDefinition.exercise

    def test_submit_for_approval_stays_unposted(self):
        doc=self.exercise('Draft','Submit for Approval','Draft','Draft','save')
        doc.submit.assert_not_called()

    def test_requester_draft_submit_task_is_not_an_approval(self):
        from my_work import api
        wf=self.workflow();values={'workflow_state':'Draft','approval_status':'Draft','status':'Draft'}
        doc=MagicMock(doctype='Expense Claim',docstatus=0);doc.get.side_effect=values.get
        with patch.object(frappe,'db',MagicMock()):
            views,*_=api._document_views(doc,wf,True,False,['Submit for Approval'],True,set(values))
        self.assertIn('drafts',views);self.assertNotIn('approvals',views)
