"""Business detail visibility and HR discovery tests without database mutations."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import frappe
from my_work import api, document_details as details


def field(name, kind="Data", **kwargs):
    return frappe._dict(fieldname=name,fieldtype=kind,label=name.replace('_',' ').title(),hidden=0,permlevel=0,options=None,in_list_view=0,**kwargs)


class TestDocumentDetails(unittest.TestCase):
    def setUp(self):
        clock = patch("my_work.loading.nowdate", return_value="2026-11-03")
        clock.start(); self.addCleanup(clock.stop)

    def test_header_keeps_business_fields_and_filters_hidden_or_restricted(self):
        fields=[field('customer'),field('grand_total','Currency'),field('secret'),field('hidden_value'),field('custom_note')]
        fields[3].hidden=1
        doc=frappe._dict(customer='Customer A',grand_total=250,secret='private',hidden_value='hidden',custom_note='<b>Safe</b>')
        main,extra=details.header_details(doc,SimpleNamespace(fields=fields),{'customer','grand_total','hidden_value','custom_note'},api.SAFE_TYPES)
        self.assertEqual([f['fieldname'] for f in main],['customer','grand_total'])
        self.assertEqual(extra[0]['value'],'Safe')
        self.assertNotIn('secret',str(main+extra));self.assertNotIn('hidden_value',str(main+extra))

    def test_items_show_only_requested_columns_without_extra_details(self):
        fields=[field('item_code'),field('uom'),field('qty','Float'),field('rate','Currency'),field('amount','Currency'),field('project','Link'),field('secret'),field('hidden_value')]
        fields[-1].hidden=1
        child=SimpleNamespace(name='Sales Order Item',fields=fields)
        table=field('items','Table');table.options=child.name
        meta=SimpleNamespace(get_table_fields=lambda:[table])
        doc=frappe._dict(doctype='Sales Order',items=[frappe._dict(item_code='ITEM-A',uom='Nos',qty=2,rate=100,amount=200,project='PROJ-A',secret='PRIVATE',hidden_value='HIDDEN')])
        with patch.object(api,'_readable_table',return_value=True),patch.object(details.frappe,'get_meta',return_value=child),patch.object(details,'get_permitted_fields',return_value=['item_code','uom','qty','rate','amount','project','hidden_value']):
            result=details.child_tables(doc,meta,api.SAFE_TYPES)[0]
        self.assertEqual(result['columns'],['item_code','uom','qty','rate','amount'])
        self.assertEqual(result['rows'][0]['qty'],'2');self.assertEqual(result['total'],200)
        self.assertEqual(result['row_details'],[[]]);self.assertTrue(result['compact_items'])
        self.assertNotIn('PROJ-A',str(result));self.assertEqual(result['column_meta']['uom']['label'],'UoM')
        self.assertNotIn('PRIVATE',str(result));self.assertNotIn('HIDDEN',str(result))
        self.assertEqual(result['column_meta']['qty']['fieldtype'],'Float')

    def test_restricted_parent_table_is_not_read(self):
        table=field('items','Table');table.options='Sales Order Item'
        doc=frappe._dict(doctype='Sales Order',items=[frappe._dict(item_code='PRIVATE')])
        with patch.object(api,'_readable_table',return_value=False),patch.object(details.frappe,'get_meta') as get_meta:
            self.assertEqual(details.child_tables(doc,SimpleNamespace(get_table_fields=lambda:[table]),api.SAFE_TYPES),[])
            get_meta.assert_not_called()

    def test_hr_created_records_belong_to_employee_requester(self):
        for doctype in ['Employee Checkin','Attendance','Leave Application','Attendance Request','Employee Advance','Shift Assignment']:
            doc=frappe._dict(doctype=doctype,owner='Administrator',employee='EMP-A')
            with patch.object(api,'_config',return_value={}),patch.object(api.frappe,'session',SimpleNamespace(user='employee@example.com')),patch.object(api.frappe,'db',MagicMock()) as db:
                db.get_value.return_value='EMP-A'
                self.assertTrue(api._requested(doc),doctype)
                db.get_value.assert_called_with('Employee',{'name':'EMP-A','user_id':'employee@example.com'},'name')

    def test_checkin_is_recorded_and_never_draft_or_submitted(self):
        doc=frappe._dict(doctype='Employee Checkin',owner='Administrator',docstatus=0,log_type='IN')
        views,state,*_=api._native_views(doc,True,False,[],{'log_type'})
        self.assertEqual(set(views),{'all','requests'});self.assertEqual(state,'Recorded')
        with patch.object(api.frappe,'get_meta',return_value=SimpleNamespace(is_submittable=0)):
            self.assertEqual(api._native_actions(doc),[])
        self.assertEqual(api._state_info(doc,None)[0],'Recorded')

    def test_rejected_native_leave_does_not_appear_completed(self):
        doc=frappe._dict(doctype='Leave Application',docstatus=1,status='Rejected')
        views,*_=api._native_views(doc,True,True,['Cancel'],{'status'})
        self.assertIn('rejected',views);self.assertNotIn('completed',views)

    def test_document_status_filter_separates_posting_from_business_status(self):
        rows=[dict(doctype='Sales Order',name='SO-1',module='Selling',views=['all','requests'],document_status='Draft',status='Draft',modified='1'),dict(doctype='Sales Order',name='SO-2',module='Selling',views=['all','requests'],document_status='Submitted',status='To Deliver and Bill',modified='2')]
        with patch.object(api,'_user'),patch.object(api,'_rows',return_value=rows),patch.object(api,'_sources',return_value=[]),patch.object(api,'_approval_status_options',return_value=[]):
            result=api.dashboard(document_status='Submitted')
            self.assertEqual(result['total'],1);self.assertEqual(result['data'][0]['name'],'SO-2')

    def test_checkin_source_is_included_without_a_workflow(self):
        def query(doctype,**kwargs):
            if doctype=='Workflow': return []
            return ['Sales Order'] if kwargs['filters'].get('is_submittable') else ['Employee Checkin']
        with patch.object(api,'_workflows',return_value=[]),patch.object(api.frappe,'get_all',side_effect=query),patch.object(api,'_config',return_value={}),patch.object(api.frappe,'has_permission',return_value=True),patch.object(api.frappe,'get_meta',side_effect=lambda name:SimpleNamespace(name=name)):
            self.assertEqual([m.name for _,m in api._sources()],['Employee Checkin','Sales Order'])

    def test_order_header_uses_only_main_fields_without_qty_or_extra_settings(self):
        fields=[field('customer','Link'),field('transaction_date','Date'),field('delivery_date','Date'),field('status','Select'),field('company','Link'),field('grand_total','Currency'),field('total_qty','Float'),field('custom_coil_production','Table')]
        by_name={f.fieldname:f for f in fields}
        doc=frappe._dict(doctype='Sales Order',customer='Customer A',transaction_date='2026-11-03',delivery_date='2026-11-10',status='Draft',company='Company A',grand_total=200,total_qty=2)
        main,extra=details.header_details(doc,SimpleNamespace(fields=fields,get_field=by_name.get),set(by_name),api.SAFE_TYPES)
        self.assertEqual([f['label'] for f in main],['Customer','Date','Due Date','Status','Company','Total Amount'])
        self.assertEqual(extra,[])
        self.assertNotIn('total_qty',[f['fieldname'] for f in main])
        restricted,_=details.header_details(doc,SimpleNamespace(fields=fields,get_field=by_name.get),{'customer','grand_total'},api.SAFE_TYPES)
        self.assertEqual([f['label'] for f in restricted],['Customer','Total Amount'])

    def test_coil_production_section_is_excluded_from_review_without_schema_changes(self):
        table=field('custom_coil_production','Table');table.label='Coil Production';table.options='Coil Production Line'
        doc=frappe._dict(doctype='Sales Order',custom_coil_production=[frappe._dict(qty=10)])
        with patch.object(details.frappe,'get_meta') as get_meta:
            self.assertEqual(details.child_tables(doc,SimpleNamespace(get_table_fields=lambda:[table]),api.SAFE_TYPES),[])
            get_meta.assert_not_called()
        self.assertEqual(doc.custom_coil_production[0].qty,10)
