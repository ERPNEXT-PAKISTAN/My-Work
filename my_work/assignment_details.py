"""Readable linked-document context for a user's assignment; never applies actions."""
import frappe
from frappe.model import get_permitted_fields
from frappe.utils import cstr,strip_html


def reference_brief(task):
    doctype,name=task.get('reference_type'),task.get('reference_name')
    if not doctype or not name or doctype=='ToDo':return None
    try:
        doc=frappe.get_doc(doctype,name)
        doc.check_permission('read')
    except (frappe.PermissionError,frappe.DoesNotExistError):
        return None
    permitted=set(get_permitted_fields(doctype))
    meta=frappe.get_meta(doctype)
    from my_work.list_values import monetary_value
    if doctype=='Expense Claim':
        from my_work.api import _claim_amount
        amount,label=_claim_amount(doc,permitted)
        currency=doc.get('currency') if 'currency' in permitted else None
    else:
        amount,label,currency=monetary_value(doc,meta,permitted)
    fields=[]
    for names,label_text in [(['employee_name','employee'],'Employee'),(['customer_name','customer'],'Customer'),(['supplier_name','supplier'],'Supplier'),(['status'],'Entry status')]:
        field=next((field for field in names if field in permitted and doc.get(field)),None)
        if field:fields.append(dict(label=label_text,value=strip_html(cstr(doc.get(field)))))
    return dict(doctype=doctype,name=name,amount=amount,amount_label=label,currency=currency,fields=fields)


def reference_review(task):
    doctype,name=task.get('reference_type'),task.get('reference_name')
    if not doctype or not name or doctype=='ToDo':return None
    from my_work.api import review
    try:
        source=review(doctype,name)['data']
    except (frappe.PermissionError,frappe.DoesNotExistError):
        return None
    fields=[dict(field) for field in (source.get('summary_fields') or source['fields'])]
    current=source.get('state') if source.get('flow_mode')=='workflow' else source.get('business_status') or source.get('state')
    if current:
        fields=[field for field in fields if field.get('fieldname')!='status']
        fields.append(dict(fieldname='status',label='Entry status',fieldtype='Data',value=current))
    tables=source.get('tables') or []
    primary=[table for table in tables if table.get('compact_items') or table.get('fieldname') in {'items','accounts','references'} or table.get('label')=='Expense Details']
    # Explicit readonly subset: task completion remains attached to the ToDo.
    return dict(doctype=source['doctype'],name=source['name'],summary_fields=fields,fields=[],remark_fields=source.get('remark_fields',[]),currency=source.get('currency'),tables=primary or tables[:1])
