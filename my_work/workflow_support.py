"""Keep native Workflow Actions usable when an Expense Claim is resubmitted.

Runs after Frappe's wildcard workflow handler. Uses its role/transition APIs;
never changes an Expense Claim's workflow, approval or financial fields.
"""
import frappe
from frappe.model.workflow import get_workflow_name, get_transitions, has_approval_access
from frappe.workflow.doctype.workflow_action.workflow_action import (
    create_workflow_actions_for_roles,
    get_next_possible_transitions,
    update_completed_workflow_actions_using_role,
)


def _retire(action):
    action.status = 'Completed'
    # Retired configuration tasks are not represented as somebody's approval.
    action.completed_by = None
    action.completed_by_role = None
    action.save(ignore_permissions=True)
    action.add_comment('Comment','Workflow configuration/state cleanup: obsolete open task retired. No approval decision was applied to the Expense Claim.')


def synchronize(doc, method=None, configuration_migration=False):
    if doc.doctype != 'Expense Claim':
        return None
    name = get_workflow_name(doc.doctype)
    if name != 'Expense Claim':
        return None
    workflow = frappe.get_cached_doc('Workflow',name)
    # Scope this compatibility hook to the explicitly configured flow.
    if not any(row.state == 'Request Rejected' for row in workflow.states):
        return None
    state = doc.get(workflow.workflow_state_field)
    required = get_next_possible_transitions(name,state,doc)
    roles = sorted({row.allowed for row in required})
    open_actions = [frappe.get_doc('Workflow Action',n) for n in frappe.get_all('Workflow Action',filters={'reference_doctype':doc.doctype,'reference_name':doc.name,'status':'Open'},pluck='name')]
    changes = {'created':0,'updated_roles':0,'retired':0,'completed_transition':0}
    before = None if configuration_migration else doc.get_doc_before_save()
    previous_state = before.get(workflow.workflow_state_field) if before else None
    allowed_roles = set()
    if before and previous_state != state:
        allowed_roles = {t.allowed for t in get_transitions(before,workflow) if t.next_state == state and has_approval_access(frappe.session.user,before,t)}
    for action in open_actions:
        if action.workflow_state == state and roles:
            existing = sorted(row.role for row in action.permitted_roles)
            if existing != roles:
                action.set('permitted_roles',[{'role':role} for role in roles])
                action.save(ignore_permissions=True)
                changes['updated_roles'] += 1
            continue
        actor_roles = sorted({r.role for r in action.permitted_roles} & allowed_roles) if action.workflow_state == previous_state else []
        if actor_roles:
            update_completed_workflow_actions_using_role(workflow_action=[frappe._dict(name=action.name,role=actor_roles[0])])
            changes['completed_transition'] += 1
        else:
            _retire(action)
            changes['retired'] += 1
    if roles and not frappe.db.exists('Workflow Action',{'reference_doctype':doc.doctype,'reference_name':doc.name,'workflow_state':state,'status':'Open'}):
        create_workflow_actions_for_roles(roles,doc)
        changes['created'] += 1
    if any(changes.values()):
        from frappe.desk.notifications import clear_doctype_notifications
        clear_doctype_notifications('Workflow Action')
        return changes
    return None
