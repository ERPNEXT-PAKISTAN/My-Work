"""Attribution comes from recorded transitions, not owner/last modification."""
import unittest
from unittest.mock import patch,MagicMock
import frappe
from my_work.document_events import from_versions,recorded_events,from_action_comments


class TestDocumentEvents(unittest.TestCase):
    def test_submission_actor_is_version_actor_and_unrelated_edits_are_ignored(self):
        versions=[frappe._dict(owner='creator',creation='2026-01-01',data={'changed':[['status','Draft','Draft']]}),frappe._dict(owner='submitter',creation='2026-02-02',data='{"changed":[["docstatus",0,1]]}'),frappe._dict(owner='last-editor',creation='2026-03-03',data={'changed':[['remarks','','updated']]})]
        self.assertEqual(from_versions(versions),[dict(action='Submitted',actor='submitter',creation='2026-02-02',source='Version')])

    def test_cancelled_document_preserves_submission_and_cancellation_events(self):
        versions=[frappe._dict(owner='approver',creation='t1',data={'changed':[['docstatus',0,1]]}),frappe._dict(owner='manager',creation='t2',data={'changed':[['docstatus',1,2]]})]
        self.assertEqual([event['action'] for event in from_versions(versions)],['Submitted','Cancelled'])
        self.assertEqual(from_versions([frappe._dict(data='invalid')]),[])

    def test_parent_read_is_required_before_version_query(self):
        doc=MagicMock(docstatus=1);doc.check_permission.side_effect=frappe.PermissionError
        with patch('my_work.document_events.frappe.get_all') as query:
            with self.assertRaises(frappe.PermissionError):recorded_events(doc)
        query.assert_not_called()

    def test_existing_native_action_audit_comments_supply_missing_submission_history(self):
        comments=[frappe._dict(owner='approver',creation='t1',content='My Work: updated approval_status'),frappe._dict(owner='submitter',creation='t2',content='My Work: Submit<br>Attached bill'),frappe._dict(owner='other',creation='t3',content='My Work: Submitter requested a correction')]
        self.assertEqual(from_action_comments(comments),[dict(action='Submitted',actor='submitter',creation='t2',source='My Work action history')])
