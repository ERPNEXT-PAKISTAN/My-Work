"""Native monetary/account values without fabricated ledger data."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import frappe
from my_work import list_values


class TestListValues(unittest.TestCase):
    def meta(self,fields):
        return SimpleNamespace(get_field=lambda name:frappe._dict(fieldname=name,label=name.replace('_',' ').title(),options=fields[name],fieldtype='Table' if name=='accounts' else 'Currency') if name in fields else None)

    def test_advance_uses_advance_amount(self):
        doc=frappe._dict(doctype='Employee Advance',advance_amount=25000,paid_amount=0,currency='PKR')
        amount,label,currency=list_values.monetary_value(doc,self.meta({'advance_amount':'currency'}),{'advance_amount','currency'})
        self.assertEqual((amount,currency),(25000,'PKR'))

    def test_receipt_uses_receiving_account_currency(self):
        doc=frappe._dict(doctype='Payment Entry',payment_type='Receive',paid_amount=100,received_amount=28000,paid_from_account_currency='USD',paid_to_account_currency='PKR')
        result=list_values.monetary_value(doc,self.meta({'received_amount':'paid_to_account_currency'}),set(doc))
        self.assertEqual(result[0],28000);self.assertEqual(result[2],'PKR')

    def test_zero_total_is_preserved_and_restricted_amount_is_omitted(self):
        doc=frappe._dict(doctype='Sales Order',grand_total=0,total=500,currency='PKR')
        self.assertEqual(list_values.monetary_value(doc,self.meta({'grand_total':'currency'}),set(doc))[0],0)
        self.assertIsNone(list_values.monetary_value(doc,self.meta({}),{'currency'})[0])

    def test_account_fields_require_read_permission(self):
        doc=frappe._dict(doctype='Sales Invoice',debit_to='Debtors - A',cash_bank_account='PRIVATE')
        result=list_values.against_accounts(doc,self.meta({}),{'debit_to'})
        self.assertEqual(result['accounts'],[{'label':'Receivable Account','value':'Debtors - A'}])
        self.assertNotIn('PRIVATE',str(result))

    def test_orders_show_actual_party_without_inventing_ledger_account(self):
        doc=frappe._dict(doctype='Sales Order',customer='Customer A')
        result=list_values.against_accounts(doc,self.meta({}),{'customer'})
        self.assertEqual(result['accounts'],[]);self.assertEqual(result['party'],'Customer A')

    def test_journal_accounts_obey_child_field_permissions(self):
        doc=frappe._dict(doctype='Journal Entry',accounts=[frappe._dict(account='Cash - A'),frappe._dict(account='Debtors - A')])
        with patch('my_work.api._readable_table',return_value=True),patch.object(list_values,'get_permitted_fields',return_value=['account']):
            result=list_values.against_accounts(doc,self.meta({'accounts':'Journal Entry Account'}),set())
            self.assertEqual(len(result['accounts']),2)
        with patch('my_work.api._readable_table',return_value=True),patch.object(list_values,'get_permitted_fields',return_value=[]):
            self.assertIsNone(list_values.against_accounts(doc,self.meta({'accounts':'Journal Entry Account'}),set()))
