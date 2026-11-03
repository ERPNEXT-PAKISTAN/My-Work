"""Document-tool tests mock native save/assignment/share boundaries; no site mutations."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import frappe
from my_work import claim_tools as tools


class TestClaimTools(unittest.TestCase):
    def setUp(self):
        for name,value in [('session',SimpleNamespace(user='approver@example.test')),('db',MagicMock())]:
            context=patch.object(frappe,name,value);context.start();self.addCleanup(context.stop)
        context=patch.object(frappe,'throw',side_effect=self.throw);context.start();self.addCleanup(context.stop)
        context=patch.object(tools,"_workflow",return_value=None);context.start();self.addCleanup(context.stop)

    def throw(self,message,exc=frappe.ValidationError,*args,**kwargs):
        raise exc(message)

    def doc(self,**kwargs):
        values=dict(doctype='Expense Claim',name='TEST-1',modified='2026-11-03 09:00:00',docstatus=0,approval_status='Draft',employee='EMP-1',company='Test Company',currency='PKR',advances=[])
        values.update(kwargs);doc=MagicMock()
        for key,value in values.items():setattr(doc,key,value)
        doc.get.side_effect=values.get
        doc.set.side_effect=lambda key,value:values.update({key:value})
        return doc

    def test_submitted_claim_is_not_editable(self):
        doc=self.doc(docstatus=1)
        self.assertFalse(tools._draft_editable(doc,None))
        with patch('my_work.api._document',return_value=doc),patch.object(tools,'_workflow',return_value=None):
            with self.assertRaises(frappe.PermissionError):tools._claim(doc.name,doc.modified)
        doc.save.assert_not_called()

    def test_stale_claim_edit_is_rejected(self):
        doc=self.doc()
        with patch('my_work.api._document',return_value=doc):
            with self.assertRaises(frappe.TimestampMismatchError):tools._locked(doc.doctype,doc.name,'old')

    def test_field_level_write_permission_is_required(self):
        doc=self.doc();doc.has_permlevel_access_to.return_value=False
        field=frappe._dict(fieldname='approval_status',permlevel=1,read_only=0)
        self.assertFalse(tools._field_writable(doc,field))

    def test_save_native_approval_uses_document_save(self):
        doc=self.doc()
        field=frappe._dict(fieldname='approval_status',fieldtype='Select',options='Draft\nApproved\nRejected\nCancelled')
        with patch.object(tools,'_claim',return_value=doc),patch.object(tools,'_check_field',return_value=field):
            tools.update_claim(doc.name,doc.modified,{'approval_status':'Approved'})
        doc.set.assert_called_once_with('approval_status','Approved');doc.save.assert_called_once()
        frappe.db.set_value.assert_not_called()

    def test_derived_status_and_unknown_fields_cannot_be_written(self):
        doc=self.doc()
        with patch.object(tools,'_claim',return_value=doc):
            with self.assertRaises(frappe.ValidationError):tools.update_claim(doc.name,doc.modified,{'status':'Paid'})
            with self.assertRaises(frappe.ValidationError):tools.update_claim(doc.name,doc.modified,{'workflow_state':'Approved'})
        doc.save.assert_not_called()

    def test_cancelled_is_not_a_draft_approval_shortcut(self):
        doc=self.doc();field=frappe._dict(fieldtype='Select',options='Draft\nApproved\nRejected\nCancelled')
        with patch.object(tools,'_claim',return_value=doc),patch.object(tools,'_check_field',return_value=field):
            with self.assertRaises(frappe.ValidationError):tools.update_claim(doc.name,doc.modified,{'approval_status':'Cancelled'})
        doc.save.assert_not_called()

    def test_rejection_with_allocated_advance_requires_explicit_removal(self):
        doc=self.doc(total_advance_amount=100)
        with patch.object(tools,'_claim',return_value=doc):
            with self.assertRaises(frappe.ValidationError):tools.update_claim(doc.name,doc.modified,{'approval_status':'Rejected'})
        doc.save.assert_not_called()

    def test_context_link_requires_target_read_permission(self):
        doc=self.doc();target=MagicMock();target.check_permission.side_effect=frappe.PermissionError
        field=frappe._dict(fieldtype='Link',options='Project')
        with patch.object(tools,'_claim',return_value=doc),patch.object(tools,'_check_field',return_value=field),patch.object(frappe,'get_doc',return_value=target):
            with self.assertRaises(frappe.PermissionError):tools.update_claim(doc.name,doc.modified,{'project':'PRIVATE-PROJECT'})
        doc.save.assert_not_called()

    def test_removing_advance_unlinks_only_selected_child_row(self):
        row=frappe._dict(name='ROW-1',employee_advance='ADV-1');doc=self.doc(advances=[row])
        with patch.object(tools,'_claim',return_value=doc),patch.object(tools,'_check_field'),patch.object(frappe,'delete_doc') as delete:
            tools.remove_advance(doc.name,doc.modified,'ROW-1')
        doc.remove.assert_called_once_with(row);doc.save.assert_called_once();delete.assert_not_called()

    def test_missing_advance_row_cannot_remove_another_link(self):
        doc=self.doc(advances=[frappe._dict(name='ROW-1')])
        with patch.object(tools,'_claim',return_value=doc),patch.object(tools,'_check_field'):
            with self.assertRaises(frappe.DoesNotExistError):tools.remove_advance(doc.name,doc.modified,'ROW-OTHER')
        doc.remove.assert_not_called();doc.save.assert_not_called()

    def test_assignment_delegates_to_native_duplicate_protection(self):
        doc=self.doc()
        with patch.object(tools,'_locked',return_value=doc),patch('frappe.desk.form.assign_to.add',return_value=[]) as add:
            tools.assign(doc.doctype,doc.name,doc.modified,['a@example.test','a@example.test'])
        self.assertEqual(add.call_args.args[0]['assign_to'],['a@example.test'])

    def test_share_delegates_to_native_permission_checks_without_ignore_flags(self):
        doc=self.doc()
        with patch('my_work.api._document',return_value=doc),patch.object(frappe,'get_system_settings',return_value=0),patch('frappe.share.add') as add:
            tools.share(doc.doctype,doc.name,doc.modified,'reader@example.test',write=1)
        args=add.call_args.kwargs
        self.assertEqual(args['read'],1);self.assertEqual(args['write'],1)
        self.assertNotIn('flags',args)

    def test_attachment_must_belong_to_selected_document(self):
        doc=self.doc();file=SimpleNamespace(attached_to_doctype='Expense Claim',attached_to_name='OTHER')
        with patch.object(tools,'_locked',return_value=doc),patch.object(frappe,'get_doc',return_value=file),patch.object(frappe,'delete_doc') as delete:
            with self.assertRaises(frappe.PermissionError):tools.remove_attachment(doc.doctype,doc.name,doc.modified,'FILE-1')
        delete.assert_not_called()

    def test_tag_mutation_checks_parent_write_boundary(self):
        with patch.object(tools,'_locked',side_effect=frappe.PermissionError),patch('frappe.desk.doctype.tag.tag.add_tag') as add:
            with self.assertRaises(frappe.PermissionError):tools.tag('Expense Claim','TEST-1','old','Tag')
        add.assert_not_called()

    def test_wrong_workflow_edit_role_cannot_edit_draft(self):
        doc=self.doc(workflow_state='Pending')
        workflow=frappe._dict(workflow_state_field='workflow_state',states=[frappe._dict(state='Pending',allow_edit='HR User')])
        with patch.object(frappe,'get_roles',return_value=['Employee']):
            self.assertFalse(tools._draft_editable(doc,workflow))

    def test_advance_allocation_uses_native_balances_and_explicit_amount(self):
        import sys
        doc=self.doc();advance=SimpleNamespace(docstatus=1,employee='EMP-1',company='Test Company',currency='PKR',check_permission=MagicMock())
        candidate=MagicMock(allocated_amount=100);candidate.as_dict.return_value={'name':'TEMP-ROW','employee_advance':'ADV-1','allocated_amount':100}
        provider=MagicMock(return_value=[candidate])
        module=SimpleNamespace(get_advances=provider)
        with patch.object(tools,'_claim',return_value=doc),patch.object(tools,'_check_field'),patch.object(tools,'_field_writable',return_value=True),patch.object(frappe,'get_meta'),patch.object(frappe,'get_doc',return_value=advance),patch.dict(sys.modules,{'hrms.hr.doctype.expense_claim.expense_claim':module}):
            tools.add_advance(doc.name,doc.modified,'ADV-1',80)
        self.assertEqual(doc.append.call_args.args[1]['allocated_amount'],80)
        self.assertNotIn('name',doc.append.call_args.args[1]);doc.save.assert_called_once();advance.check_permission.assert_called_once_with('read')

    def test_advance_allocation_over_balance_never_saves_claim(self):
        import sys
        doc=self.doc();advance=SimpleNamespace(docstatus=1,employee='EMP-1',company='Test Company',currency='PKR',check_permission=MagicMock())
        module=SimpleNamespace(get_advances=MagicMock(return_value=[SimpleNamespace(allocated_amount=50)]))
        with patch.object(tools,'_claim',return_value=doc),patch.object(tools,'_check_field'),patch.object(tools,'_field_writable',return_value=True),patch.object(frappe,'get_meta'),patch.object(frappe,'get_doc',return_value=advance),patch.dict(sys.modules,{'hrms.hr.doctype.expense_claim.expense_claim':module}):
            with self.assertRaises(frappe.ValidationError):tools.add_advance(doc.name,doc.modified,'ADV-1',100)
        doc.append.assert_not_called();doc.save.assert_not_called()

    def test_select_cannot_bypass_a_workflow_using_native_approval_as_state(self):
        doc=self.doc();workflow=SimpleNamespace(workflow_state_field='approval_status')
        with patch.object(tools,'_claim',return_value=doc),patch.object(tools,'_workflow',return_value=workflow):
            with self.assertRaises(frappe.PermissionError):tools.update_claim(doc.name,doc.modified,{'approval_status':'Approved'})
        doc.save.assert_not_called()

    def test_removing_share_uses_native_share_permission_endpoint(self):
        doc=self.doc()
        with patch('my_work.api._document',return_value=doc),patch.object(frappe,'get_system_settings',return_value=0),patch('frappe.share.set_permission') as set_permission:
            tools.share(doc.doctype,doc.name,doc.modified,'reader@example.test',remove=1)
        set_permission.assert_called_once_with(doc.doctype,doc.name,'reader@example.test','read',value=0)
