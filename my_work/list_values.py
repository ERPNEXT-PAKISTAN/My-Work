"""Readable native monetary totals and configured against accounts for list rows."""
import frappe
from frappe.model import get_permitted_fields
from frappe.utils import cstr

AMOUNTS = {
    'Employee Advance': ['advance_amount'],
    'Journal Entry': ['total_debit'],
    'Stock Entry': ['total_amount','total_incoming_value','total_outgoing_value'],
    'Stock Reconciliation': ['difference_amount'],
    'Salary Slip': ['net_pay','rounded_total','gross_pay'],
    'Bank Transaction': ['deposit','withdrawal'],
}
ACCOUNT_FIELDS = [('advance_account','Advance Account'),('debit_to','Receivable Account'),('credit_to','Payable Account'),('paid_from','Paid From'),('paid_to','Paid To'),('payable_account','Payable Account'),('cash_bank_account','Cash / Bank Account'),('bank_account','Bank Account'),('expense_account','Expense Account'),('difference_account','Difference Account'),('account','Account'),('against_account','Against Account')]


def currency_for(doc, permitted, df):
    option=cstr(df.options) if df else 'currency'
    if not option: option='currency'
    if ':' not in option:
        return doc.get(option) if option in permitted else None
    if option=='Company:company:default_currency' and 'company' in permitted and doc.get('company') and frappe.has_permission('Company','read',doc=doc.get('company')) and 'default_currency' in get_permitted_fields('Company'):
        return frappe.get_cached_value('Company',doc.get('company'),'default_currency')
    return None


def monetary_value(doc, meta, permitted):
    names=AMOUNTS.get(doc.doctype,['grand_total','total_amount','total','amount','net_total'])
    if doc.doctype=='Payment Entry':
        names=['received_amount'] if 'payment_type' in permitted and doc.get('payment_type')=='Receive' else ['paid_amount']
    if doc.doctype=='Bank Transaction':
        names=[name for name in names if name in permitted and doc.get(name)] or names
    for name in names:
        if name not in permitted or doc.get(name) is None: continue
        df=meta.get_field(name)
        return doc.get(name), (df.label if df else name.replace('_',' ').title()), currency_for(doc,permitted,df)
    return None,None,None


def against_accounts(doc, meta, permitted):
    from my_work.api import _readable_table
    accounts=[]
    seen=set()
    for name,label in ACCOUNT_FIELDS:
        if name in permitted and doc.get(name):
            value=cstr(doc.get(name))
            if value not in seen:
                seen.add(value);accounts.append(dict(label=label,value=value))
    for table_name in ['accounts','items']:
        table=meta.get_field(table_name)
        if not table or not _readable_table(doc,meta,table_name) or not doc.get(table_name): continue
        child=set(get_permitted_fields(table.options,parenttype=doc.doctype))
        fields=[('account','Account')] if table_name=='accounts' else [('expense_account','Item Expense Account'),('income_account','Item Income Account'),('difference_account','Item Difference Account')]
        for row in doc.get(table_name):
            for field,label in fields:
                value=row.get(field) if field in child else None
                if value and value not in seen:
                    seen.add(value);accounts.append(dict(label=label,value=cstr(value)))
    party=next(((field,doc.get(field)) for field in ['customer','supplier','party','employee'] if field in permitted and doc.get(field)),None)
    if not accounts and not party: return None
    return dict(label='Accounts' if accounts else 'Against '+party[0].title(),kind='account' if accounts else 'party',accounts=accounts,party_label=party[0].replace('_',' ').title() if party else None,party=party[1] if party else None)
