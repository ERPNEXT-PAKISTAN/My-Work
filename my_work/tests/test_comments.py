"""Native comments are independent of document actions and edit permission."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import frappe
from my_work import api


class TestComments(unittest.TestCase):
    def denied(self,message,exc=frappe.ValidationError,*args,**kwargs):
        raise exc(message)

    def test_any_saved_status_uses_native_comment_and_authenticated_actor(self):
        for status in [0,1,2]:
            doc=MagicMock(doctype='Sales Order',docstatus=status)
            doc.name='SO-TEST'
            doc.has_permission.return_value=False
            comment=SimpleNamespace(name='COMMENT-1',creation='2026-11-03',owner='alice@example.com',comment_by='Alice',content='<p>Test</p>')
            with patch.object(api,'_document',return_value=doc),patch.object(api.frappe,'session',SimpleNamespace(user='alice@example.com')),patch.object(api.frappe,'get_cached_value',return_value='Alice'),patch('frappe.desk.form.utils.add_comment',return_value=comment) as native:
                result=api.add_comment(doc.doctype,doc.name,'A & B\n<script>literal</script>')
            args=native.call_args.kwargs
            self.assertEqual(args['comment_email'],'alice@example.com');self.assertEqual(args['comment_by'],'Alice')
            self.assertIn('&amp;',args['content']);self.assertIn('&lt;script&gt;',args['content']);self.assertIn('<br>',args['content'])
            self.assertEqual(result['data']['name'],'COMMENT-1')
            doc.save.assert_not_called();doc.submit.assert_not_called();doc.cancel.assert_not_called()
            doc.check_permission.assert_not_called()  # no additional write/submit checks after _document read check

    def test_parent_read_denial_does_not_post(self):
        with patch.object(api,'_document',side_effect=frappe.PermissionError),patch('frappe.desk.form.utils.add_comment') as native:
            with self.assertRaises(frappe.PermissionError):api.add_comment('Sales Order','PRIVATE','text')
        native.assert_not_called()

    def test_empty_comment_does_not_post(self):
        with patch.object(api,'_document',return_value=SimpleNamespace()),patch.object(api.frappe,'throw',side_effect=self.denied),patch('frappe.desk.form.utils.add_comment') as native:
            with self.assertRaises(frappe.ValidationError):api.add_comment('Sales Order','TEST',' \n ')
        native.assert_not_called()

    def test_native_failure_is_not_reported_as_success(self):
        doc=SimpleNamespace(doctype='Sales Order',name='TEST')
        with patch.object(api,'_document',return_value=doc),patch.object(api.frappe,'session',SimpleNamespace(user='alice')),patch.object(api.frappe,'get_cached_value',return_value='Alice'),patch('frappe.desk.form.utils.add_comment',side_effect=frappe.PermissionError):
            with self.assertRaises(frappe.PermissionError):api.add_comment(doc.doctype,doc.name,'text')
