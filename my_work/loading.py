"""Bound document hydration; query scopes run before loading child tables."""
import frappe
from frappe import _
from frappe.model import get_permitted_fields
from frappe.utils import cint, cstr, getdate, nowdate, add_days


def settings(record_limit=100, days=30, from_date=None, to_date=None):
    limit = min(500, max(20, cint(record_limit) or 100))
    days = cint(days)
    if days not in {0, 7, 30, 90, 365}:
        frappe.throw(_("Choose a supported date range"))
    end = getdate(to_date) if to_date else getdate(nowdate())
    begin = getdate(from_date) if from_date else getdate(add_days(end, -(days-1))) if days else None
    if begin and begin > end:
        frappe.throw(_("From date must be on or before To date"))
    return dict(record_limit=limit,days=days,from_date=cstr(begin) if begin else None,to_date=cstr(end),basis="modified",limited=False,candidates_checked=0)


def filters_for(meta, permitted, scope, options):
    filters = [["modified", "<", cstr(add_days(scope['to_date'],1))]]
    if scope['from_date']:
        filters.append(["modified", ">=", scope['from_date']])
    if options.get('document_status'):
        state = options['document_status']
        if state == 'Recorded':
            if meta.is_submittable: return None
        elif not meta.is_submittable:
            return None
        else:
            filters.append(['docstatus','=',{'Draft':0,'Submitted':1,'Cancelled':2}[state]])
    for argument,field in [('priority','priority'),('claim_status','status'),('approval_status','approval_status')]:
        if options.get(argument):
            if field not in permitted or not meta.get_field(field): return None
            filters.append([field,'=',options[argument]])
    return filters


def decision_filters(meta, workflow, permitted, options):
    decision=options.get('decision')
    view=options.get('view')
    filters=[]
    if view=='assigned': return None
    if view in {'drafts','submitted','cancelled'} or view=='completed' and not workflow:
        if not meta.is_submittable: return None
        filters.append(['docstatus','=',{'drafts':0,'submitted':1,'completed':1,'cancelled':2}[view]])
    if view in {'approvals','waiting','rejected'} and meta.name=='Employee Checkin': return None
    if view=='approvals' and not workflow and not any(name in permitted and meta.get_field(name) for name in ('expense_approver','leave_approver','approver')): return None
    if not workflow and view=='waiting' and meta.name!='Expense Claim': return None
    if not workflow and view=='rejected' and meta.name not in {'Expense Claim','Leave Application','Shift Request'}: return None
    if not decision: return filters
    if decision=='cancelled':
        return filters+[['docstatus','=',2]] if meta.is_submittable else None
    if meta.is_submittable: filters.append(['docstatus','!=',2])
    approval=meta.get_field('approval_status')
    field='approval_status' if approval else 'status' if meta.name in {'Leave Application','Shift Request'} else workflow.workflow_state_field if workflow else None
    if decision=='no_separate_approval': return None if field else filters
    if decision=='unavailable': return filters if field and field not in permitted else None
    if decision=='conflict': return filters if meta.name=='Expense Claim' and workflow else None
    if not field or field not in permitted: return None
    if decision in {'approved','rejected'}:
        values=['Approved'] if decision=='approved' else ['Rejected','Request Rejected'] if workflow and field==workflow.workflow_state_field else ['Rejected']
        return filters+[[field,'in',values]]
    if decision=='not_approved':
        values=['Open','Draft','Pending','Pending Approval','Returned','Not Approved','']
        return filters+[[field,'in',values]]
    return filters


def candidates(sources, scope, options):
    from my_work.api import _native_candidate_filters
    pool = []
    for wf,meta in sources:
        if (options.get('module') and options['module'] != meta.module) or (options.get('doctype') and options['doctype'] != meta.name):
            continue
        permitted = set(get_permitted_fields(meta.name))
        filters = filters_for(meta,permitted,scope,options)
        if filters is None: continue
        decisions=decision_filters(meta,wf,permitted,options)
        if decisions is None: continue
        filters.extend(decisions)
        records = frappe.get_list(meta.name,fields=['name','modified','creation'],filters=filters,order_by='modified desc, name asc',limit_page_length=scope['record_limit']+1,**({'or_filters':_native_candidate_filters(meta,permitted)} if not wf else {}))
        pool.extend((wf,meta,row) for row in records)
    # Assignments share the same global record budget, never another full scan.
    if (not options.get('module') or options['module']=='Tasks') and (not options.get('doctype') or options['doctype']=='ToDo') and (not options.get('document_status') or options['document_status']=='Recorded') and not options.get('approval_status') and not options.get('decision') and options.get('view') not in {'approvals','requests','waiting','drafts','submitted','rejected'}:
        meta=frappe.get_meta('ToDo')
        filters=filters_for(meta,set(get_permitted_fields('ToDo')),scope,options)
        if filters is not None:
            filters.append(['allocated_to','=',frappe.session.user])
            if options.get('view') in {'assigned','completed','cancelled'}:
                filters.append(['status','=',{'assigned':'Open','completed':'Closed','cancelled':'Cancelled'}[options['view']]])
            tasks=frappe.get_list('ToDo',filters=filters,fields=['name','description','reference_type','reference_name','assigned_by','creation','modified','date','priority','status'],order_by='modified desc, name asc',limit_page_length=scope['record_limit']+1)
            pool.extend((None,None,task) for task in tasks)
    pool.sort(key=lambda entry:(cstr(entry[2].modified),entry[1].name if entry[1] else 'ToDo',entry[2].name),reverse=True)
    scope['limited']=len(pool)>scope['record_limit']
    selected=pool[:scope['record_limit']]
    scope['candidates_checked']=len(selected)
    return selected
