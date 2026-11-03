"""Assignment text updates remain native saves with ownership/version guards."""
import unittest
from unittest.mock import MagicMock,patch
from types import SimpleNamespace
import frappe
from my_work import api


class TestTaskDescription(unittest.TestCase):
    def denied(self,message,exc=frappe.ValidationError,*args,**kwargs):raise exc(message)

    def doc(self):
        doc=MagicMock();doc.name='TODO-DEMO';doc.allocated_to='assignee@example.test';doc.status='Closed';doc.modified='new-version'
        return doc

    def test_save_description_preserves_task_status_and_uses_versioned_lock(self):
        doc=self.doc()
        with patch('my_work.claim_tools._locked',return_value=doc) as locked,patch('my_work.claim_tools._field_writable',return_value=True),patch.object(api.frappe,'get_meta'),patch.object(api.frappe,'session',SimpleNamespace(user=doc.allocated_to)),patch.object(api,'apply_workflow') as workflow:
            result=api.update_task_description(doc.name,'old-version','<p>Updated instruction</p><script>bad()</script>')
        locked.assert_called_once_with('ToDo',doc.name,'old-version',draft=True)
        self.assertIn('Updated instruction',doc.description);self.assertNotIn('<script>',doc.description)
        self.assertEqual(doc.status,'Closed');doc.save.assert_called_once_with();doc.submit.assert_not_called();workflow.assert_not_called()
        self.assertEqual(result['data']['modified'],'new-version')

    def test_reassigned_task_cannot_be_updated_after_lock(self):
        doc=self.doc()
        with patch('my_work.claim_tools._locked',return_value=doc),patch.object(api.frappe,'session',SimpleNamespace(user='other@example.test')),patch.object(api.frappe,'throw',side_effect=self.denied):
            with self.assertRaises(frappe.PermissionError):api.update_task_description(doc.name,'version','text')
        doc.save.assert_not_called()

    def test_readonly_description_cannot_be_saved(self):
        doc=self.doc()
        with patch('my_work.claim_tools._locked',return_value=doc),patch('my_work.claim_tools._field_writable',return_value=False),patch.object(api.frappe,'get_meta'),patch.object(api.frappe,'session',SimpleNamespace(user=doc.allocated_to)),patch.object(api.frappe,'throw',side_effect=self.denied):
            with self.assertRaises(frappe.PermissionError):api.update_task_description(doc.name,'version','text')
        doc.save.assert_not_called()

    def test_empty_required_description_is_rejected(self):
        doc=self.doc()
        with patch('my_work.claim_tools._locked',return_value=doc),patch('my_work.claim_tools._field_writable',return_value=True),patch.object(api.frappe,'get_meta'),patch.object(api.frappe,'session',SimpleNamespace(user=doc.allocated_to)),patch.object(api.frappe,'throw',side_effect=self.denied):
            with self.assertRaises(frappe.ValidationError):api.update_task_description(doc.name,'version','<p><br></p>')
        doc.save.assert_not_called()
