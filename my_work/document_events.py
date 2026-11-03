"""Submission/cancellation attribution from recorded native Version events only."""
import frappe
import re
from frappe.utils import cint


def from_versions(versions):
    events=[]
    seen=set()
    for version in versions:
        try:
            data=frappe.parse_json(version.data) if isinstance(version.data,str) else version.data
        except (TypeError,ValueError):
            continue
        if not isinstance(data,dict):continue
        for change in data.get('changed',[]) or []:
            if not isinstance(change,(list,tuple)) or len(change)!=3 or change[0]!='docstatus':continue
            old,new=change[1:]
            if str(old) not in {'0','1'} or str(new) not in {'1','2'}:continue
            action='Submitted' if cint(old)==0 and cint(new)==1 else 'Cancelled' if cint(old)==1 and cint(new)==2 else None
            if not action or action in seen:continue
            seen.add(action)
            events.append(dict(action=action,actor=version.owner,creation=version.creation,source='Version'))
    return events


def from_action_comments(comments):
    """Older My Work native-action audit entries record successful submissions."""
    events=[]
    seen=set()
    for comment in comments:
        match=re.match(r"^My Work:\s*(Submit|Cancel)(?:<br\s*/?>|\r?\n|$)",comment.content or '',re.I)
        if not match:continue
        action='Submitted' if match.group(1).lower()=='submit' else 'Cancelled'
        if action in seen:continue
        seen.add(action)
        events.append(dict(action=action,actor=comment.owner,creation=comment.creation,source='My Work action history'))
    return events


def recorded_events(doc):
    # Match the native form's parent-read access boundary, without exposing diffs.
    doc.check_permission('read')
    if not cint(doc.docstatus):return []
    versions=frappe.get_all('Version',filters={'ref_doctype':doc.doctype,'docname':str(doc.name),'data':['like','%docstatus%']},fields=['owner','creation','data'],order_by='creation asc, name asc',limit_page_length=200)
    events=from_versions(versions)
    missing=({'Submitted','Cancelled'} if cint(doc.docstatus)==2 else {'Submitted'})-{event['action'] for event in events}
    if missing:
        comments=frappe.get_all('Comment',filters={'reference_doctype':doc.doctype,'reference_name':str(doc.name),'comment_type':'Comment','content':['like','My Work: %']},fields=['owner','creation','content'],order_by='creation asc, name asc',limit_page_length=200)
        events.extend(event for event in from_action_comments(comments) if event['action'] in missing)
    for event in events:
        event['actor_name']=frappe.get_cached_value('User',event['actor'],'full_name') or event['actor']
    return events
