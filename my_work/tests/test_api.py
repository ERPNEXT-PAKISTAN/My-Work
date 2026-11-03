"""Isolated service regression tests; no business data or workflow changes."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import frappe
from my_work import api


class TestMyWork(unittest.TestCase):
    def setUp(self):
        clock = patch("my_work.loading.nowdate", return_value="2026-11-03")
        clock.start(); self.addCleanup(clock.stop)
        self.user = patch.object(api.frappe, 'session', SimpleNamespace(user='alice@example.com'))
        self.user.start()
        self.addCleanup(self.user.stop)
        self.database = patch.object(api.frappe, "db", MagicMock())
        self.database.start()
        self.addCleanup(self.database.stop)
        self.tools = patch.object(api, "_tools", return_value={})
        self.tools.start()
        self.addCleanup(self.tools.stop)
        self.activity = patch.object(api.frappe, "get_all", return_value=[])
        self.activity.start()
        self.addCleanup(self.activity.stop)
        self.workflow_lookup = patch('my_work.claim_tools._workflow', return_value=SimpleNamespace(name='Active'))
        self.workflow_lookup.start()
        self.addCleanup(self.workflow_lookup.stop)
        self.status_options = patch.object(api, "_approval_status_options", return_value=[])
        self.status_options.start()
        self.addCleanup(self.status_options.stop)

    def denied(self, message, exc=frappe.ValidationError, *args, **kwargs):
        raise exc(message)

    def doc(self, **kwargs):
        values = dict(doctype='Expense Claim', name='EXP-1', owner='bob@example.com', modified='2026-11-03 10:00:00', docstatus=0)
        values.update(kwargs)
        d = MagicMock()
        for key, value in values.items():
            setattr(d, key, value)
        d.get.side_effect = values.get
        return d

    def test_guest_denied(self):
        with patch.object(api.frappe, 'session', SimpleNamespace(user='Guest')), patch.object(api.frappe, 'throw', side_effect=self.denied):
            with self.assertRaises(frappe.PermissionError): api._user()

    def test_website_user_denied(self):
        with patch.object(api.frappe, 'get_roles', return_value=['Website User']), patch.object(api.frappe, 'throw', side_effect=self.denied):
            with self.assertRaises(frappe.PermissionError): api._user()

    def test_request_owner(self):
        self.assertTrue(api._requested(self.doc(owner='alice@example.com')))

    def test_other_creator_not_requester(self):
        with patch.object(api, '_config', return_value={}): self.assertFalse(api._requested(self.doc()))

    def test_configured_user_requester(self):
        with patch.object(api, '_config', return_value={'requester_fields': {'Expense Claim': {'requested_by': 'user'}}}):
            self.assertTrue(api._requested(self.doc(requested_by='alice@example.com')))

    def test_employee_mapping_requires_link(self):
        with patch.object(api, '_config', return_value={'requester_fields': {'Expense Claim': {'employee': 'employee'}}}), patch.object(api.frappe.db, 'get_value', return_value=None):
            self.assertFalse(api._requested(self.doc(employee='EMP-1')))

    def test_no_workflow_state_has_no_actions(self):
        self.assertEqual(api._actions(self.doc(), SimpleNamespace(workflow_state_field='workflow_state')), [])

    def test_role_and_self_approval_filter(self):
        with patch.object(api, 'get_transitions', return_value=[SimpleNamespace(action='Approve'), SimpleNamespace(action='Return')]), patch.object(api, 'has_approval_access', side_effect=[False, True]):
            self.assertEqual(api._actions(self.doc(workflow_state='Pending'), SimpleNamespace(workflow_state_field='workflow_state')), ['Return'])

    def test_duplicate_labels_deduplicated(self):
        with patch.object(api, 'get_transitions', return_value=[SimpleNamespace(action='Approve')]*2), patch.object(api, 'has_approval_access', return_value=True):
            self.assertEqual(api._actions(self.doc(workflow_state='Pending'), SimpleNamespace(workflow_state_field='workflow_state')), ['Approve'])

    def test_document_permission_enforced(self):
        d = self.doc(); d.check_permission.side_effect = frappe.PermissionError
        with patch.object(api, '_user'), patch.object(api.frappe, 'get_doc', return_value=d):
            with self.assertRaises(frappe.PermissionError): api._document('Expense Claim', 'EXP-1')

    def test_other_assignee_denied(self):
        with patch.object(api, '_user'), patch.object(api.frappe, 'get_doc', return_value=self.doc(allocated_to='bob@example.com')), patch.object(api.frappe, 'throw', side_effect=self.denied):
            with self.assertRaises(frappe.PermissionError): api._document('ToDo', 'TASK-1')

    def test_stale_action_never_applied(self):
        with patch.object(api, '_document', return_value=self.doc()), patch.object(api.frappe.db, 'get_value'), patch.object(api.frappe, 'throw', side_effect=self.denied), patch.object(api, 'apply_workflow') as apply:
            with self.assertRaises(frappe.TimestampMismatchError): api.act('Expense Claim', 'EXP-1', 'Approve', 'old')
            apply.assert_not_called()

    def test_invalid_action_never_applied(self):
        d=self.doc()
        with patch.object(api, '_document', return_value=d), patch.object(api.frappe.db, 'get_value'), patch.object(api, 'transitions', return_value={'data': ['Return']}), patch.object(api.frappe, 'throw', side_effect=self.denied), patch.object(api, 'apply_workflow') as apply:
            with self.assertRaises(frappe.PermissionError): api.act(d.doctype, d.name, 'Approve', d.modified)
            apply.assert_not_called()

    def test_valid_action_uses_supported_api_and_audit(self):
        d=self.doc()
        with patch.object(api, '_document', return_value=d), patch.object(api.frappe.db, 'get_value'), patch.object(api, 'transitions', return_value={'data': ['Approve']}), patch.object(api, 'apply_workflow', return_value=d) as apply:
            api.act(d.doctype, d.name, 'Approve', d.modified)
            apply.assert_called_once_with(d.as_json(), 'Approve')
            d.add_comment.assert_called_once()

    def test_closed_assignment_cannot_complete_twice(self):
        d=self.doc(allocated_to='alice@example.com', status='Closed')
        with patch.object(api, '_document', return_value=d), patch.object(api.frappe.db, 'get_value'), patch.object(api.frappe, 'throw', side_effect=self.denied):
            with self.assertRaises(frappe.TimestampMismatchError): api.complete_task(d.name, d.modified)

    def test_assignment_changed_assignee_denied(self):
        d=self.doc(allocated_to='bob@example.com', status='Open')
        with patch.object(api, '_document', return_value=d), patch.object(api.frappe.db, 'get_value'), patch.object(api.frappe, 'throw', side_effect=self.denied):
            with self.assertRaises(frappe.PermissionError): api.complete_task(d.name, d.modified)

    def test_pagination_search_and_counts(self):
        rows=[dict(doctype='Expense Claim', name=f'EXP-{i}', title='Taxi', module='HR', views=['requests'], modified=str(i)) for i in range(8)]
        with patch.object(api, '_user'), patch.object(api, '_rows', return_value=rows), patch.object(api, '_sources', return_value=[]):
            r=api.dashboard(view='requests', search='taxi', start=2, page_length=3)
            self.assertEqual(r['total'], 8); self.assertEqual(len(r['data']), 3); self.assertEqual(r['summary']['requests'], 8)
            self.assertEqual(api.dashboard(view='requests', module='Accounts')['total'], 0)

    def test_page_size_clamped(self):
        with patch.object(api, '_user'), patch.object(api, '_rows', return_value=[]), patch.object(api, '_sources', return_value=[]):
            self.assertEqual(api.dashboard(page_length=9999)['page_length'], 100)
            self.assertEqual(api.dashboard(start=-20)['start'], 0)

    def test_invalid_sort_rejected(self):
        with patch.object(api, '_user'), patch.object(api.frappe, 'throw', side_effect=self.denied):
            with self.assertRaises(frappe.ValidationError): api.dashboard(sort='private_field')

    def test_history_is_scoped_to_parent(self):
        d=self.doc()
        with patch.object(api, '_document', return_value=d), patch.object(api.frappe, 'get_all', return_value=[]) as query:
            self.assertEqual(api.history(d.doctype,d.name), {'data': []})
            self.assertEqual(query.call_args.kwargs['filters']['reference_name'], d.name)

    def test_rejected_and_terminal_states(self):
        wf=SimpleNamespace(workflow_state_field='workflow_state', states=[SimpleNamespace(state='Rejected')], transitions=[])
        with patch.object(api.frappe.db, 'get_value', return_value='Danger'):
            state,rejected,complete,roles=api._state_info(self.doc(workflow_state='Rejected'),wf)
            self.assertTrue(rejected);self.assertFalse(complete);self.assertEqual(roles,[])
        with patch.object(api.frappe.db, 'get_value', return_value='Success'):
            self.assertTrue(api._state_info(self.doc(workflow_state='Approved'),wf)[2])

    def test_pending_actions_use_permission_query_and_open_status(self):
        action=SimpleNamespace(reference_doctype='Expense Claim', reference_name='EXP-1', workflow_state='Pending')
        with patch.object(api.frappe, 'get_list', return_value=[action]) as query:
            self.assertEqual(api._pending_actions(), {('Expense Claim', 'EXP-1', 'Pending')})
            self.assertEqual(query.call_args.kwargs['filters'], {'status': 'Open'})

    def test_attachment_access_checked_and_urls_omitted(self):
        files=[SimpleNamespace(name='FILE-1', file_name='receipt.pdf', is_private=1),SimpleNamespace(name='FILE-2', file_name='secret.pdf', is_private=1)]
        with patch.object(api.frappe, 'get_list', return_value=files), patch.object(api.frappe, 'has_permission', side_effect=[True,True,False]):
            result=api._attachments(self.doc())
            self.assertEqual(result,[{'name':'FILE-1','label':'receipt.pdf','private':True,'can_delete':True}])

    def test_queued_workflow_submission(self):
        d=self.doc()
        with patch.object(api,'_document',return_value=d), patch.object(api.frappe.db,'get_value'),patch.object(api,'transitions',return_value={'data':['Approve']}),patch.object(api,'apply_workflow',return_value=None):
            self.assertTrue(api.act(d.doctype,d.name,'Approve',d.modified)['data']['queued'])

    def test_generic_review_without_workflow_or_optional_fields(self):
        d=self.doc(doctype='Custom Request')
        meta=MagicMock();meta.get_field.return_value=None;meta.is_submittable=0
        with patch.object(api,'_document',return_value=d),patch.object(api.frappe,'get_meta',return_value=meta),patch.object(api.frappe.db,'get_value',return_value=None),patch.object(api,'get_permitted_fields',return_value=['name']),patch.object(api,'_config',return_value={}),patch.object(api,'_history',return_value=[]),patch.object(api,'_attachments',return_value=[]):
            result=api.review(d.doctype,d.name)['data']
            self.assertEqual(result['actions'],[]);self.assertEqual(result['fields'],[])

    def test_priority_filter_and_navigation_counts(self):
        rows=[dict(doctype='Expense Claim', name='EXP-1', title='Taxi', module='HR', views=['approvals'], priority='High', modified='1'),dict(doctype='Expense Claim', name='EXP-2', title='Meals', module='HR', views=['approvals'], priority='Low', modified='2')]
        with patch.object(api,'_user'),patch.object(api,'_rows',return_value=rows),patch.object(api,'_sources',return_value=[]):
            result=api.dashboard(view='approvals',priority='High')
            self.assertEqual(result['total'],1)
            self.assertEqual(result['data'][0]['name'],'EXP-1')
            self.assertEqual(result['counts']['all'],2)
            self.assertEqual(result['summary']['approvals'],2)

    def test_workflow_remarks_are_escaped_in_audit(self):
        d=self.doc()
        with patch.object(api,'_document',return_value=d),patch.object(api.frappe.db,'get_value'),patch.object(api,'transitions',return_value={'data':['Approve']}),patch.object(api,'apply_workflow',return_value=d):
            api.act(d.doctype,d.name,'Approve',d.modified,remarks='<script>alert(1)</script>')
            audit=d.add_comment.call_args.args[1]
            self.assertNotIn('<script>',audit)
            self.assertIn('&lt;script&gt;',audit)

    def test_overlong_remarks_rejected_before_mutation(self):
        with patch.object(api.frappe,'throw',side_effect=self.denied),patch.object(api,'apply_workflow') as apply:
            with self.assertRaises(frappe.ValidationError):api.act('Expense Claim','EXP-1','Approve','old',remarks='x'*2001)
            apply.assert_not_called()

    def test_expense_reference_summary_uses_readable_fields_and_dates(self):
        d=self.doc(employee='EMP-1',employee_name='Alice',department='Sales',total_claimed_amount=15000,remark='Client meeting',expenses=[frappe._dict(expense_date='2026-01-22',amount=7000),frappe._dict(expense_date='2026-01-20',amount=8000)])
        fields={'employee','employee_name','department','total_claimed_amount','remark','expenses'}
        summary=api._expense_summary(d,fields,{'expense_date','amount'})
        self.assertEqual([f['label'] for f in summary],['Employee','Department','Claim Amount','Expense Period','Purpose'])
        self.assertEqual(summary[0]['value'],'Alice')
        self.assertEqual(summary[3]['value'],['2026-01-20','2026-01-22'])

    def test_expense_summary_does_not_expose_unreadable_name_or_dates(self):
        d=self.doc(employee='EMP-1',employee_name='Private Name',department='Private Department',expenses=[frappe._dict(expense_date='2026-01-20')])
        summary=api._expense_summary(d,{'employee','expenses'},set())
        self.assertEqual(len(summary),1)
        self.assertEqual(summary[0]['value'],'EMP-1')

    def test_expense_table_permission_is_not_lost_by_scalar_column_helper(self):
        d=self.doc(doctype='Expense Claim',currency='PKR',total_claimed_amount=15000,expenses=[frappe._dict(expense_type='Travel',description='Taxi',amount=15000,expense_date='2026-01-20')])
        meta=MagicMock();meta.get_field.return_value=None
        meta.get_table_fields.return_value=[frappe._dict(fieldname='expenses',permlevel=0)]
        with patch.object(api,'_document',return_value=d),patch.object(api.frappe,'get_meta',return_value=meta),patch.object(api.frappe.db,'get_value',return_value=None),patch.object(api,'get_permitted_fields',side_effect=[['name','currency','total_claimed_amount'],['expense_type','description','amount','expense_date']]),patch.object(api,'_config',return_value={}),patch.object(api,'_history',return_value=[]),patch.object(api,'_attachments',return_value=[]):
            result=api.review(d.doctype,d.name)['data']
            self.assertEqual(result['tables'][0]['columns'],['expense_type','description','amount'])
            self.assertEqual(result['tables'][0]['total'],15000)
            self.assertEqual(result['summary_fields'][1]['label'],'Expense Period')

    def test_restricted_expense_table_is_not_returned(self):
        d=self.doc(doctype='Expense Claim',expenses=[frappe._dict(amount=15000)])
        d.has_permlevel_access_to.return_value=False
        meta=MagicMock();meta.get_field.return_value=None
        meta.get_table_fields.return_value=[frappe._dict(fieldname='expenses',permlevel=1)]
        with patch.object(api,'_document',return_value=d),patch.object(api.frappe,'get_meta',return_value=meta),patch.object(api.frappe.db,'get_value',return_value=None),patch.object(api,'get_permitted_fields',return_value=['name']),patch.object(api,'_config',return_value={}),patch.object(api,'_history',return_value=[]),patch.object(api,'_attachments',return_value=[]):
            result=api.review(d.doctype,d.name)['data']
            self.assertEqual(result['tables'],[])
            self.assertEqual(result['summary_fields'],[])

    def test_claim_amount_does_not_use_zero_net_payable(self):
        d=self.doc(total_claimed_amount=15000,grand_total=0)
        self.assertEqual(api._claim_amount(d,{'total_claimed_amount','grand_total'}),(15000,'Claim Amount'))
        self.assertEqual(api._claim_amount(d,{'grand_total'}),(0,'Net Payable'))
        self.assertEqual(api._claim_amount(d,set()),(None,'Claim Amount'))

    def test_cash_claim_route_uses_configured_mode_type(self):
        d=self.doc(is_paid=1,mode_of_payment='Cash',grand_total=15000)
        meta=MagicMock();meta.get_field.return_value=None
        with patch.object(api.frappe,'has_permission',return_value=True),patch.object(api.frappe,'get_cached_value',return_value='Cash'):
            source=api._claim_settlement(d,{'is_paid','mode_of_payment','grand_total'},meta)
        self.assertEqual(source['label'],'Cash')
        self.assertEqual(source['mode_of_payment'],'Cash')

    def test_payable_claim_displays_configured_account(self):
        d=self.doc(is_paid=0,payable_account='Employee Payable - TEST',grand_total=15000)
        meta=MagicMock();meta.get_field.return_value=None
        source=api._claim_settlement(d,{'is_paid','payable_account','grand_total'},meta)
        self.assertEqual(source['label'],'Payable')
        self.assertEqual(source['payable_account'],'Employee Payable - TEST')

    def test_fully_allocated_advance_is_not_shown_as_zero_claim(self):
        d=self.doc(is_paid=0,total_claimed_amount=15000,total_advance_amount=15000,grand_total=0,payable_account='Employee Payable - TEST')
        meta=MagicMock();meta.get_field.return_value=None
        source=api._claim_settlement(d,{'is_paid','total_advance_amount','grand_total','payable_account'},meta)
        self.assertEqual(source['label'],'Against Advance')
        self.assertIsNone(source['payable_account'])
        self.assertEqual(api._claim_amount(d,{'total_claimed_amount'})[0],15000)

    def test_part_advance_part_payable_and_restricted_advance_reference(self):
        d=self.doc(is_paid=0,total_advance_amount=5000,grand_total=10000,advances=[frappe._dict(employee_advance='ADV-PRIVATE',allocated_amount=5000)])
        meta=MagicMock();meta.get_field.return_value=frappe._dict(fieldtype='Table',permlevel=0)
        with patch.object(api,'get_permitted_fields',return_value=['employee_advance','allocated_amount']),patch.object(api.frappe,'has_permission',return_value=False):
            source=api._claim_settlement(d,{'is_paid','total_advance_amount','grand_total'},meta)
        self.assertEqual(source['label'],'Advance + Payable')
        self.assertEqual(source['advances'],[])

    def test_missing_settlement_permissions_do_not_infer_cash_or_payable(self):
        d=self.doc(is_paid=1,mode_of_payment='Cash',payable_account='Payable - TEST')
        meta=MagicMock();meta.get_field.return_value=None
        source=api._claim_settlement(d,{'payable_account'},meta)
        self.assertEqual(source['label'],'Not specified')

    def test_claim_employee_requester_is_recognized_with_no_configuration(self):
        d=self.doc(owner='Administrator',employee='EMP-1')
        with patch.object(api,'_config',return_value={}),patch.object(api.frappe.db,'get_value',return_value='EMP-1'):
            self.assertTrue(api._requested(d))
            self.assertEqual(api._requester_identity(d,{'employee'}),'alice@example.com')

    def test_different_employee_does_not_become_my_request(self):
        d=self.doc(owner='Administrator',employee='EMP-OTHER',employee_name='Other Employee')
        with patch.object(api,'_config',return_value={}),patch.object(api.frappe.db,'get_value',return_value=None):
            self.assertFalse(api._requested(d))
            self.assertEqual(api._requester_identity(d,{'employee','employee_name'}),'Other Employee')

    def test_explicit_empty_requester_configuration_can_disable_default(self):
        d=self.doc(owner='Administrator',employee='EMP-1')
        with patch.object(api,'_config',return_value={'requester_fields':{'Expense Claim':{}}}):
            self.assertFalse(api._requested(d))
            self.assertEqual(api._requester_identity(d,{'employee'}),'Administrator')

    def status_workflow(self):
        return frappe._dict(workflow_state_field='workflow_state',states=[frappe._dict(state='Pending',doc_status='0'),frappe._dict(state='Approved',doc_status='1'),frappe._dict(state='Rejected',doc_status='2')],transitions=[frappe._dict(state='Approved',next_state='Approved',action='Approve'),frappe._dict(state='Pending',next_state='Pending',action='Reject'),frappe._dict(state='Pending',next_state='Approved',action='Review')])

    def status_fields(self):
        return {'workflow_state','approval_status','status','grand_total','total_claimed_amount','total_sanctioned_amount','total_advance_amount','total_amount_reimbursed'}

    def test_rejected_claim_with_approved_workflow_is_not_pending_approval(self):
        d=self.doc(docstatus=1,status='Rejected',approval_status='Rejected',workflow_state='Approved',total_claimed_amount=4652,total_sanctioned_amount=0,grand_total=0,total_amount_reimbursed=0)
        wf=self.status_workflow()
        info=api._expense_status(d,wf,self.status_fields())
        self.assertTrue(info['has_conflict']);self.assertEqual(info['display_status'],'Rejected')
        self.assertEqual(info['payment_status'],'Not payable — rejected');self.assertIsNone(info['outstanding'])
        views,*_=api._document_views(d,wf,False,True,[],True,self.status_fields())
        self.assertEqual(set(views),{'rejected','all'})
        with patch.object(api,'get_transitions',return_value=[]):
            self.assertEqual(api._actions(d,wf),[])

    def test_paid_advance_claim_is_completed_even_with_stale_open_action(self):
        d=self.doc(docstatus=1,status='Paid',approval_status='Approved',workflow_state='Approved',grand_total=0,total_advance_amount=5022,total_amount_reimbursed=0)
        wf=self.status_workflow()
        info=api._expense_status(d,wf,self.status_fields())
        self.assertTrue(info['completed']);self.assertEqual(info['payment_status'],'Settled against advance')
        views,*_=api._document_views(d,wf,False,True,[],True,self.status_fields())
        self.assertIn('completed',views);self.assertNotIn('approvals',views)

    def test_approved_unpaid_claim_waits_for_payment(self):
        d=self.doc(docstatus=1,status='Unpaid',approval_status='Approved',workflow_state='Approved',grand_total=5500,total_amount_reimbursed=0)
        wf=self.status_workflow()
        info=api._expense_status(d,wf,self.status_fields())
        self.assertEqual(info['display_status'],'Approved · Unpaid');self.assertEqual(info['outstanding'],5500)
        views,*_=api._document_views(d,wf,True,False,[],False,self.status_fields())
        self.assertIn('waiting',views);self.assertNotIn('completed',views)

    def test_partial_reimbursement_keeps_only_remaining_outstanding(self):
        d=self.doc(docstatus=1,status='Unpaid',approval_status='Approved',workflow_state='Approved',grand_total=10000,total_amount_reimbursed=4000)
        info=api._expense_status(d,self.status_workflow(),self.status_fields())
        self.assertEqual(info['payment_status'],'Partly reimbursed');self.assertEqual(info['outstanding'],6000)

    def test_cancelled_claim_preserves_historical_approval_without_conflict(self):
        d=self.doc(docstatus=2,status='Cancelled',approval_status='Approved',workflow_state='Rejected')
        wf=self.status_workflow();info=api._expense_status(d,wf,self.status_fields())
        self.assertFalse(info['has_conflict']);self.assertEqual(info['display_status'],'Cancelled')
        views,*_=api._document_views(d,wf,False,True,[],False,self.status_fields())
        self.assertIn('cancelled',views);self.assertNotIn('rejected',views);self.assertNotIn('completed',views)

    def test_prepayment_flags_on_draft_do_not_make_it_paid(self):
        d=self.doc(docstatus=0,status='Draft',approval_status='Draft',workflow_state='Pending',is_paid=1,grand_total=0,total_advance_amount=24400,total_amount_reimbursed=0)
        wf=self.status_workflow();info=api._expense_status(d,wf,self.status_fields())
        self.assertFalse(info['paid']);self.assertFalse(info['completed']);self.assertTrue(info['configuration_blocked'])
        views,*_=api._document_views(d,wf,True,True,[],True,self.status_fields())
        self.assertIn('drafts',views);self.assertNotIn('waiting',views)

    def test_noop_action_is_hidden_but_real_task_or_field_update_is_retained(self):
        wf=self.status_workflow();transition=wf.transitions[0]
        d=self.doc(docstatus=1,workflow_state='Approved',approval_status='Approved')
        self.assertFalse(api._transition_has_effect(transition,wf,d))
        transition.transition_tasks='Send Receipt'
        self.assertTrue(api._transition_has_effect(transition,wf,d))
        transition.transition_tasks=None
        wf.states[1].update_field='approval_status';wf.states[1].update_value='Rejected'
        self.assertTrue(api._transition_has_effect(transition,wf,d))

    def test_submitting_draft_native_approval_requires_configured_field_update(self):
        wf=self.status_workflow();transition=wf.transitions[2]
        d=self.doc(docstatus=0,workflow_state='Pending',approval_status='Draft')
        self.assertFalse(api._transition_consistent(d,wf,transition))
        wf.states[1].update_field='approval_status';wf.states[1].update_value='Approved'
        self.assertTrue(api._transition_consistent(d,wf,transition))

    def test_status_info_does_not_return_unreadable_approval_or_amount_fields(self):
        d=self.doc(docstatus=1,workflow_state='Approved',approval_status='Rejected',status='Rejected',grand_total=0,total_claimed_amount=4652)
        info=api._expense_status(d,self.status_workflow(),{'status','workflow_state'})
        self.assertIsNone(info['approval_status']);self.assertIsNone(info['claimed']);self.assertIsNone(info['net_payable'])
        self.assertEqual(info['display_status'],'Rejected')

    def test_all_work_includes_completed_requests_and_claim_status_filter(self):
        rows=[dict(doctype='Expense Claim',name='PAID-1',module='HR',views=['requests','completed','all'],status='Paid',modified='1'),dict(doctype='Expense Claim',name='REJECTED-1',module='HR',views=['rejected','all'],status='Rejected',modified='2')]
        with patch.object(api,'_user'),patch.object(api,'_rows',return_value=rows),patch.object(api,'_sources',return_value=[]):
            self.assertEqual(api.dashboard(view='all')['total'],2)
            filtered=api.dashboard(view='all',claim_status='Rejected')
            self.assertEqual(filtered['total'],1);self.assertEqual(filtered['data'][0]['name'],'REJECTED-1')

    def test_other_doctypes_keep_their_configured_same_state_actions(self):
        d=self.doc(doctype='Custom Request',workflow_state='Approved')
        wf=self.status_workflow()
        with patch.object(api,'get_transitions',return_value=[wf.transitions[0]]),patch.object(api,'has_approval_access',return_value=True):
            self.assertEqual(api._actions(d,wf),['Approve'])
        self.assertEqual(api._workflow_notices(d,wf),[])
