"""Date corrections must preserve native accounting validation and installment identity."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import frappe
from my_work import claim_tools as tools


class TestInvoiceDates(unittest.TestCase):
    def run_save(self, schedule, editor=True, native_error=False):
        doc = MagicMock()
        doc.name = 'INV-DEMO'
        doc.modified = 'new'
        doc.due_date = '2026-11-10'
        installment = SimpleNamespace(name='ROW-DEMO', due_date='2026-01-01')
        doc.get.side_effect = lambda key: [installment] if key == 'payment_schedule' else None
        config = dict(fields=[dict(fieldname=n) for n in ('posting_date', 'due_date')], schedule=[dict(name='ROW-DEMO')])
        def denied(message, exc=frappe.ValidationError, **kw):
            raise exc(message)
        with ExitStack() as stack:
            locked = stack.enter_context(patch.object(tools, '_locked', return_value=doc))
            stack.enter_context(patch.object(tools, '_workflow', return_value=None))
            stack.enter_context(patch.object(tools, 'get_permitted_fields', return_value=[]))
            stack.enter_context(patch.object(tools, 'invoice_dates', return_value=config if editor else None))
            stack.enter_context(patch.object(frappe, 'throw', side_effect=denied))
            if native_error:
                doc.save.side_effect = frappe.ValidationError('Native credit terms validation')
            try:
                result = tools.update_invoice_dates('Sales Invoice', doc.name, 'old', {'posting_date':'2026-01-01','due_date':'2026-11-10'}, schedule)
            finally:
                self.doc = doc
            locked.assert_called_once_with('Sales Invoice', doc.name, 'old', draft=True)
        return result, installment

    def test_native_save_without_submission(self):
        result, installment = self.run_save([{'name':'ROW-DEMO','due_date':'2026-11-10'}])
        self.doc.save.assert_called_once_with()
        self.doc.submit.assert_not_called()
        self.assertEqual(str(installment.due_date), '2026-11-10')
        self.assertEqual(result['modified'], 'new')

    def test_unknown_installment_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self.run_save([{'name':'OTHER','due_date':'2026-11-10'}])
        self.doc.save.assert_not_called()

    def test_noneditable_dates_denied(self):
        with self.assertRaises(frappe.PermissionError):
            self.run_save([], editor=False)
        self.doc.save.assert_not_called()

    def test_native_validation_propagates(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'Native credit terms'):
            self.run_save([{'name':'ROW-DEMO','due_date':'2026-11-10'}], native_error=True)
        self.doc.submit.assert_not_called()
