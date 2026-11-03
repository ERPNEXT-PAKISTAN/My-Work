"""Bounded loading, date scopes and pre-hydration filtering."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import frappe
from my_work import loading, api


class TestLoading(unittest.TestCase):
    def setUp(self):
        clock=patch.object(loading,'nowdate',return_value='2026-11-03')
        clock.start();self.addCleanup(clock.stop)

    def meta(self,name,module='HR'):
        return SimpleNamespace(name=name,module=module,is_submittable=1,get_field=lambda name:None)

    def test_default_date_and_hard_limits(self):
        scope=loading.settings()
        self.assertEqual(scope['record_limit'],100)
        self.assertEqual(scope['from_date'],'2026-10-05')
        self.assertEqual(loading.settings(999999)['record_limit'],500)
        self.assertEqual(loading.settings(1)['record_limit'],20)
        self.assertIsNone(loading.settings(days=0)['from_date'])

    def test_explicit_dates_can_reach_older_history(self):
        scope=loading.settings(from_date='2025-01-01',to_date='2025-01-31')
        self.assertEqual(scope['from_date'],'2025-01-01');self.assertEqual(scope['to_date'],'2025-01-31')
        filters=loading.filters_for(self.meta('Attendance'),set(),scope,{})
        self.assertIn(['modified','<','2025-02-01'],filters)

    def test_global_budget_and_recent_order_across_types(self):
        sources=[(None,self.meta('Attendance')),(None,self.meta('Leave Application'))]
        def get_list(name,**kw):
            return [frappe._dict(name=f'{name}-{i}',modified=f'2026-11-{i+1:02d}',creation='2026-10-01') for i in range(21)]
        scope=loading.settings(20)
        with patch.object(loading,'get_permitted_fields',return_value=[]),patch.object(loading.frappe,'get_list',side_effect=get_list) as query,patch.object(api,'_native_candidate_filters',return_value=[]):
            selected=loading.candidates(sources,scope,{'module':'HR'})
        self.assertEqual(len(selected),20);self.assertTrue(scope['limited'])
        self.assertEqual(scope['candidates_checked'],20)
        self.assertEqual(selected[0][2].modified,'2026-11-21')
        self.assertTrue(all(call.kwargs['limit_page_length']==21 for call in query.call_args_list))

    def test_module_and_type_exclusion_before_query(self):
        sources=[(None,self.meta('Attendance')),(None,self.meta('Leave Application')),(None,self.meta('Sales Order','Selling'))]
        with patch.object(loading,'get_permitted_fields',return_value=[]),patch.object(loading.frappe,'get_list',return_value=[]) as query,patch.object(api,'_native_candidate_filters',return_value=[]):
            loading.candidates(sources,loading.settings(),{'module':'HR','doctype':'Attendance'})
        query.assert_called_once();self.assertEqual(query.call_args.args[0],'Attendance')

    def test_drafts_exclude_record_only_types_and_filter_before_loading(self):
        meta=self.meta('Attendance')
        self.assertEqual(loading.decision_filters(meta,None,set(),{'view':'drafts'}),[['docstatus','=',0]])
        meta.is_submittable=0
        self.assertIsNone(loading.decision_filters(meta,None,set(),{'view':'drafts'}))

    def test_approval_filter_never_treats_generic_submitted_as_approved(self):
        meta=self.meta('Sales Order')
        self.assertIsNone(loading.decision_filters(meta,None,set(),{'decision':'approved'}))
        meta.get_field=lambda name:SimpleNamespace() if name=='approval_status' else None
        self.assertIn(['approval_status','in',['Approved']],loading.decision_filters(meta,None,{'approval_status'},{'decision':'approved'}))

    def test_native_loading_skips_workflow_action_scan(self):
        with patch.object(loading,'candidates',return_value=[]),patch.object(api,'_pending_actions') as pending:
            self.assertEqual(api._rows([],loading.settings()),[])
        pending.assert_not_called()

    def test_workflow_action_query_is_scoped_to_loaded_documents(self):
        with patch.object(api.frappe,'get_list',return_value=[]) as query:
            api._pending_actions([('Expense Claim','EC-ONE')])
        filters=query.call_args.kwargs['filters']
        self.assertEqual(filters['reference_name'],['in',['EC-ONE']])
        self.assertEqual(filters['status'],'Open')
