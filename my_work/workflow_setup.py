"""Explicit administrator-run Expense Claim workflow setup. Never an install hook."""
import json
import os
from pathlib import Path

import frappe
from frappe.utils import cstr, now_datetime

WORKFLOW = "Expense Claim"


def definition():
    def state(name, status, editor, decision=None, optional=0):
        return dict(state=name, doc_status=str(status), allow_edit=editor, update_field="approval_status" if decision else None, update_value=decision, is_optional_state=optional, avoid_status_override=1)
    def transition(source, action, target, role):
        return dict(state=source, action=action, next_state=target, allowed=role, allow_self_approval=1)
    result = dict(states=[state("Draft",0,"Employee","Draft"),state("Pending",0,"Expense Approver","Draft"),state("Approved",1,"Expense Approver","Approved"),state("Request Rejected",0,"Expense Approver","Rejected"),state("Returned",0,"Employee","Draft"),state("Cancelled",2,"Expense Approver","Cancelled",1),state("Rejected",2,"Expense Approver",None,1)],transitions=[transition("Draft","Submit for Approval","Pending","Employee"),transition("Pending","Approve","Approved","Expense Approver"),transition("Pending","Reject","Request Rejected","Expense Approver"),transition("Pending","Return","Returned","Expense Approver"),transition("Returned","Resubmit","Pending","Employee"),transition("Approved","Cancel","Cancelled","Expense Approver")])


    for index,row in enumerate(result['states'],1):
        row['workflow_builder_id']=str(index)
    for index,row in enumerate(result['transitions'],1):
        row['workflow_builder_id']='action-'+str(index)
    return result


def diagram(data):
    state_positions={'Draft':(50,120),'Pending':(650,120),'Approved':(1250,120),'Request Rejected':(1250,500),'Returned':(1250,880),'Cancelled':(1850,120),'Rejected':(1850,500)}
    action_positions={'Submit for Approval':(350,140),'Approve':(950,140),'Reject':(950,520),'Return':(950,900),'Resubmit':(350,1100),'Cancel':(1550,140)}
    ids={row['state']:row['workflow_builder_id'] for row in data['states']}
    result=[]
    for row in data['states']:
        x,y=state_positions[row['state']]
        result.append(dict(id=ids[row['state']],type='state',position=dict(x=x,y=y),data={}))
    for row in data['transitions']:
        x,y=action_positions[row['action']]
        result.append(dict(id=row['workflow_builder_id'],type='action',position=dict(x=x,y=y),data=dict(from_id=ids[row['state']],to_id=ids[row['next_state']])))
    return result


def _claims():
    return frappe.get_all("Expense Claim", fields=["name","docstatus","workflow_state","approval_status","status","modified","total_claimed_amount","total_sanctioned_amount","grand_total","total_advance_amount","total_amount_reimbursed"], order_by="name")


def preview():
    frappe.only_for("System Manager")
    wf = frappe.get_doc("Workflow", WORKFLOW)
    return {"name":wf.name,"modified":cstr(wf.modified),"current":json.loads(wf.as_json()),"proposed":definition(),"claims":_claims()}


def configure(expected_modified):
    frappe.only_for("System Manager")
    wf = frappe.get_doc("Workflow", WORKFLOW)
    wf.check_permission("write")
    frappe.db.get_value("Workflow", wf.name, "modified", for_update=True)
    wf.reload()
    if cstr(wf.modified) != expected_modified:
        frappe.throw("The workflow changed after inspection. Inspect it again before applying setup.",frappe.TimestampMismatchError)
    if wf.document_type != "Expense Claim" or wf.workflow_state_field != "workflow_state":
        frappe.throw("Unexpected workflow target or state field; refusing to replace it.")
    claims = _claims()
    if any(not row.workflow_state for row in claims):
        frappe.throw("Some existing claims have no workflow state. Resolve them before this setup.")
    proposed = definition()
    statuses = {s['state']:s['doc_status'] for s in proposed['states']}
    if any(statuses.get(row.workflow_state) != str(row.docstatus) for row in claims):
        frappe.throw("An existing claim would not match the preserved workflow states. No configuration was changed.")
    actions = [frappe.get_doc('Workflow Action', name).as_dict() for name in frappe.get_all('Workflow Action', filters={'reference_doctype':'Expense Claim'}, pluck='name')]
    backup_dir = Path(frappe.get_site_path('private','backups'))
    backup_dir.mkdir(parents=True,exist_ok=True)
    path = backup_dir / (now_datetime().strftime('%Y%m%d-%H%M%S')+'-expense-claim-workflow-before.json')
    path.write_text(frappe.as_json({'workflow':wf.as_dict(),'workflow_actions':actions,'claims_snapshot':claims}),encoding='utf-8')
    os.chmod(path,0o600)
    for name,style in [('Draft','Primary'),('Request Rejected','Danger'),('Returned','Warning'),('Cancelled','Inverse')]:
        if not frappe.db.exists('Workflow State',name):
            frappe.get_doc({'doctype':'Workflow State','workflow_state_name':name,'style':style}).insert()
    for name in ['Submit for Approval','Approve','Reject','Return','Resubmit','Cancel']:
        if not frappe.db.exists('Workflow Action Master',name):
            frappe.get_doc({'doctype':'Workflow Action Master','workflow_action_name':name}).insert()
    wf.set('states',proposed['states'])
    wf.set('transitions',proposed['transitions'])
    wf.workflow_data = frappe.as_json(diagram(proposed))
    wf.save()
    wf.add_comment('Comment','My Work: configured native Approval Status updates for Approve/Reject/Return/Resubmit/Cancel. Historical cancelled Rejected state retained. Self-approval setting retained from the previous workflow.')
    frappe.clear_cache(doctype='Expense Claim')
    from my_work.workflow_support import synchronize
    task_changes = []
    for row in claims:
        changed = synchronize(frappe.get_doc('Expense Claim',row.name), configuration_migration=True)
        if changed:
            task_changes.append({'name':row.name,**changed})
    if frappe.as_json(_claims()) != frappe.as_json(claims):
        frappe.db.rollback()
        frappe.clear_cache()
        frappe.throw('Claim source values changed unexpectedly. Workflow setup was rolled back.')
    after_path = path.with_name(path.name.replace('-before.json','-after.json'))
    after_path.write_text(wf.as_json(),encoding='utf-8')
    os.chmod(after_path,0o600)
    frappe.db.commit()
    frappe.clear_cache()
    return {'workflow':wf.name,'backup':str(path),'after':str(after_path),'states':proposed['states'],'transitions':proposed['transitions'],'claims_preserved':len(claims),'workflow_task_changes':task_changes,'send_email_alert':wf.send_email_alert,'override_status':wf.override_status}


def validate_configuration(user=None):
    """Read-only verification of metadata, role access and synthetic Pending actions."""
    previous=frappe.session.user
    try:
        wf=frappe.get_doc('Workflow',WORKFLOW)
        wf.validate_docstatus()
        definitions=definition()
        for row in definitions['states']:
            saved=next(s for s in wf.states if s.state==row['state'])
            assert all(cstr(saved.get(key))==cstr(value) for key,value in row.items() if key!='doctype')
        meta=frappe.get_meta('Expense Claim')
        level=meta.get_field('approval_status').permlevel
        assert any(p.role=='Expense Approver' and p.permlevel==level and p.write for p in meta.permissions)
        handlers=frappe.get_doc_hooks()['*']['on_update']
        native='frappe.workflow.doctype.workflow_action.workflow_action.process_workflow_actions'
        support='my_work.workflow_support.synchronize'
        assert handlers.index(support)>handlers.index(native)
        frappe.set_user(user or previous)
        source=frappe.get_list('Expense Claim',fields=['name'],limit_page_length=1)[0]
        doc=frappe.get_doc('Expense Claim',source.name)
        original=frappe.db.get_value('Expense Claim',doc.name,['modified','workflow_state','approval_status','docstatus'],as_dict=True)
        doc.docstatus=0
        doc.workflow_state='Pending'
        doc.approval_status='Draft'
        doc.status='Draft'
        from my_work.api import _actions,_expense_status
        from my_work.claim_tools import _approval_managed
        actions=_actions(doc,wf)
        assert set(actions)=={'Approve','Reject','Return'}
        doc.workflow_state='Draft'
        draft_actions=_actions(doc,wf)
        assert draft_actions==['Submit for Approval']
        assert _approval_managed(wf)
        after=frappe.db.get_value('Expense Claim',doc.name,['modified','workflow_state','approval_status','docstatus'],as_dict=True)
        assert original==after
        return {'workflow_active':bool(wf.is_active),'native_approval_field_managed':True,'approver_pending_actions_preview':actions,'requester_draft_actions_preview':draft_actions,'expense_approver_field_write_permission':True,'core_docstatus_validation_passed':True,'resubmission_hook_after_core':True,'existing_claim_unchanged_by_preview':True,'open_workflow_actions':frappe.db.count('Workflow Action',{'reference_doctype':'Expense Claim','status':'Open'}),'mutations_performed':0}
    finally:
        frappe.set_user(previous)
