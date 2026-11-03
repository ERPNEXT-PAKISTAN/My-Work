"""Non-mutating installed-site validation, run with bench execute."""
import frappe
from my_work import api


def smoke():
    previous = frappe.session.user
    try:
        frappe.set_user('Administrator')
        result = api.dashboard(page_length=5)
        assert len(result['data']) <= 5
        assert all(isinstance(result['summary'][k], int) for k in ('approvals', 'requests', 'assigned', 'waiting'))
        checked = []
        for row in result['data']:
            review = api.review(row['doctype'], row['name'])['data']
            assert review['name'] == row['name']
            assert all('file_url' not in f for f in review['attachments'])
            checked.append({'doctype': row['doctype'], 'name': row['name'], 'actions': review['actions']})
        frappe.set_user('Guest')
        try:
            api.dashboard()
        except frappe.PermissionError:
            pass
        else:
            raise AssertionError('Guest was allowed')
        return {'summary': result['summary'], 'total': result['total'], 'modules': result['modules'], 'reviewed': checked, 'guest_denied': True}
    finally:
        frappe.set_user(previous)


def audit_users():
    """Validate discovery and reviews under real enabled System Users, read-only."""
    previous = frappe.session.user
    users = frappe.get_all('User', filters={'enabled': 1, 'user_type': 'System User'}, pluck='name', limit_page_length=30)
    checked = records = denials = 0
    try:
        frappe.set_user('Administrator')
        samples = [(meta.name, frappe.get_list(meta.name, pluck='name', limit_page_length=5)) for _, meta in api._workflows()]
        for user in users:
            frappe.set_user(user)
            if 'Desk User' not in frappe.get_roles():
                continue
            rows = api._rows()
            for row in rows:
                doc = frappe.get_doc(row['doctype'], row['name'])
                assert doc.has_permission('read'), 'Unreadable result'
                if row['kind'] == 'task':
                    assert doc.allocated_to == user, 'Wrong assignee'
                if 'requests' in row['views']:
                    assert api._requested(doc), 'Wrong requester'
                if row['actions']:
                    assert set(row['actions']) == set(api.transitions(doc.doctype, doc.name)['data'])
                records += 1
            for doctype, names in samples:
                for name in names:
                    if not frappe.has_permission(doctype, 'read', doc=name):
                        try:
                            api.review(doctype, name)
                        except frappe.PermissionError:
                            denials += 1
                        else:
                            raise AssertionError('Unreadable review succeeded')
            checked += 1
        return {'users_checked': checked, 'visible_rows_checked': records, 'unauthorized_reviews_denied': denials, 'mutations_performed': 0, 'desk_page_exists': bool(frappe.db.exists('Page', 'my-work')), 'workspace_exists': bool(frappe.db.exists('Workspace', 'My Work Overview')), 'desktop_icon_exists': bool(frappe.db.exists('Desktop Icon', 'My Work'))}
    finally:
        frappe.set_user(previous)


def page_assets():
    from frappe.desk.desk_page import get
    previous = frappe.session.user
    try:
        frappe.set_user('Administrator')
        doc = get('my-work')
        assert "frappe.pages['my-work']" in doc.script
        assert 'class MyWork' in doc.script
        from frappe.desk.doctype.desktop_icon.desktop_icon import get_desktop_icons
        frappe.cache.hdel('desktop_icons', frappe.session.user)
        icons = get_desktop_icons(bootinfo=frappe._dict(workspace_sidebar_item={}))
        frappe.cache.hdel('desktop_icons', frappe.session.user)
        assert any(row.app == 'my_work' for row in icons)
        return {'page_assets_loaded': True, 'javascript_bytes': len(doc.script), 'desktop_icon_available': True}
    finally:
        frappe.set_user(previous)



def loading_performance(user=None):
    """Read-only measurements for the current or explicitly supplied Desk User."""
    from time import perf_counter
    previous=frappe.session.user
    try:
        if user: frappe.set_user(user)
        results=[]
        cases=[('default',{}),('drafts',{'view':'drafts'})]
        if frappe.db.exists('DocType','Expense Claim') and frappe.has_permission('Expense Claim','read'):
            cases.append(('expense_claim',{'doctype':'Expense Claim','days':0}))
        for label,options in cases:
            began=perf_counter()
            response=api.dashboard(**options)
            scope=response['loading']
            assert scope['candidates_checked']<=scope['record_limit']<=500
            results.append(dict(case=label,seconds=round(perf_counter()-began,3),candidates_checked=scope['candidates_checked'],visible_loaded=response['total'],limited=scope['limited']))
        return dict(results=results,mutations_performed=0)
    finally:
        frappe.set_user(previous)


def assignment_context(reference_type,reference_name):
    """Read-only check under each actual assignee; never completes assignments."""
    previous=frappe.session.user
    results=[]
    tasks=frappe.get_all('ToDo',filters={'reference_type':reference_type,'reference_name':reference_name},fields=['name','allocated_to','status'],limit_page_length=10)
    try:
        for task in tasks:
            frappe.set_user(task.allocated_to)
            if 'Desk User' not in frappe.get_roles():continue
            try:
                data=api.review('ToDo',task.name)['data']
            except frappe.PermissionError:
                results.append(dict(status=task.status,linked_readable=False));continue
            linked=data['linked_document']
            assert data['doctype']=='ToDo' and data['name']==task.name
            if linked:
                assert linked['doctype']==reference_type and linked['name']==reference_name
                assert not any(key in linked for key in ['actions','tools','activity'])
            results.append(dict(assignment_status=task.status,linked_readable=bool(linked),fact_count=len(linked['summary_fields']) if linked else 0,tables=[dict(label=t['label'],rows=len(t['rows'])) for t in linked['tables']] if linked else [],can_complete=data['can_complete'],description_editable=bool((data.get('task_description') or {}).get('editable'))))
        return dict(assignments_checked=results,mutations_performed=0)
    finally:
        frappe.set_user(previous)
