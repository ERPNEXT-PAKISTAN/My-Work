"""Personal inbox. All document discovery uses permission-filtered get_list.

Workflow metadata is configuration, never an alternative approval engine.
No response includes unrestricted document dictionaries or attachment URLs.
"""
from html import escape
from my_work.document_details import RECORD_TYPES, EMPLOYEE_TYPES, APPROVER_FIELDS
from my_work.status_labels import describe as describe_status, DECISIONS, stage_views

import frappe
from frappe import _
from frappe.model import get_permitted_fields
from frappe.model.workflow import get_transitions, has_approval_access, apply_workflow, is_transition_condition_satisfied
from frappe.utils import cint, cstr, strip_html, flt

VIEWS = {"all", "approvals", "requests", "assigned", "waiting", "drafts", "submitted", "rejected", "completed", "cancelled"}
SAFE_TYPES = {"Data", "Link", "Dynamic Link", "Select", "Date", "Datetime", "Currency", "Float", "Int", "Percent", "Check", "Small Text", "Text", "Long Text", "Text Editor", "Read Only", "Time", "Duration", "Rating"}
DEFAULT_FIELDS = ["employee", "employee_name", "department", "company", "posting_date", "expense_date", "expense_type", "description", "remarks", "approval_status", "expense_approver", "is_paid", "mode_of_payment", "payable_account", "total_amount_reimbursed", "total_advance_amount", "total_claimed_amount", "total_sanctioned_amount", "grand_total", "total", "currency", "status", "priority"]


def _user():
    if frappe.session.user == "Guest" or "Desk User" not in frappe.get_roles():
        frappe.throw(_("Desk access required"), frappe.PermissionError)
    return frappe.session.user


def _config():
    return frappe.conf.get("my_work") or {}


def _workflows():
    # Workflow configuration is intentionally read internally, never exposed verbatim.
    enabled = _config().get("enabled_doctypes")
    for name in frappe.get_all("Workflow", filters={"is_active": 1}, pluck="name"):
        wf = frappe.get_cached_doc("Workflow", name)
        meta = frappe.get_meta(wf.document_type)
        if (enabled is None or wf.document_type in enabled) and not meta.issingle and frappe.has_permission(wf.document_type, "read"):
            yield wf, meta


def _sources():
    """Active workflows take precedence; other submittable types use native flow."""
    workflows = list(_workflows())
    yield from workflows
    active = {meta.name for _, meta in workflows}
    # Include unreadable/disabled active workflows in the exclusion too: never
    # bypass a configured workflow by falling back to native submission.
    active.update(frappe.get_all("Workflow", filters={"is_active": 1}, pluck="document_type"))
    enabled = _config().get("enabled_doctypes")
    submittable = frappe.get_all("DocType", filters={"is_submittable": 1, "istable": 0, "issingle": 0, "is_virtual": 0}, pluck="name", order_by="name")
    records = frappe.get_all("DocType", filters={"name": ["in", sorted(RECORD_TYPES)], "istable": 0, "issingle": 0, "is_virtual": 0}, pluck="name")
    for name in sorted(set(submittable) | set(records)):
        if name not in active and (enabled is None or name in enabled) and frappe.has_permission(name, "read"):
            yield None, frappe.get_meta(name)


def _native_candidate_filters(meta, permitted):
    """Personal native records, not every transaction a manager can read."""
    filters = [["owner", "=", frappe.session.user]]
    for field, identity in _requester_fields(meta.name).items():
        if field not in permitted or not meta.get_field(field):
            continue
        if identity == "user":
            filters.append([field, "=", frappe.session.user])
        elif identity == "employee":
            employees = frappe.get_all("Employee", filters={"user_id": frappe.session.user}, pluck="name")
            if employees:
                filters.append([field, "in", employees])
    for field in APPROVER_FIELDS:
        df = meta.get_field(field)
        if field in permitted and df and df.fieldtype == "Link" and df.options == "User":
            filters.append([field, "=", frappe.session.user])
    return filters


def _involved(doc, meta, permitted):
    return any(field in permitted and meta.get_field(field) and meta.get_field(field).fieldtype == "Link" and meta.get_field(field).options == "User" and doc.get(field) == frappe.session.user for field in APPROVER_FIELDS)


def _native_actions(doc):
    if not frappe.get_meta(doc.doctype).is_submittable:
        return []
    status = cint(doc.docstatus)
    if status == 0 and doc.has_permission("write") and doc.has_permission("submit"):
        return ["Submit"]
    if status == 1 and doc.has_permission("cancel"):
        return ["Cancel"]
    return []


def _native_views(doc, requested, involved, actions, permitted):
    state = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(cint(doc.docstatus), "Unknown")
    info = _expense_status(doc, None, permitted) if doc.doctype == "Expense Claim" else None
    if not (requested or involved):
        return [], state, [], info
    views = ["all"] + (["requests"] if requested else [])
    if doc.doctype in RECORD_TYPES:
        return views, "Recorded", [], info
    if cint(doc.docstatus) == 2:
        views.append("cancelled")
    elif (info and info["rejected"]) or (doc.doctype in {"Leave Application", "Shift Request"} and "status" in permitted and doc.get("status") == "Rejected"):
        views.append("rejected")
    else:
        if cint(doc.docstatus) == 0:
            views.append("drafts")
            if involved and not requested and "Submit" in actions:
                views.append("approvals")
        elif info:
            if info["completed"]:
                views.append("completed")
            elif info["unpaid"]:
                views.append("waiting")
        else:
            views.append("completed")
    return views, state, [], info


def _field(record, name):
    return record.get(name) if hasattr(record, "get") else getattr(record, name, None)


def _transition_has_effect(transition, wf, doc=None):
    state, target = _field(transition, "state"), _field(transition, "next_state")
    if state is None or target is None or state != target:
        return True
    if _field(transition, "transition_tasks"):
        return True
    row = next((r for r in getattr(wf, "states", []) if _field(r, "state") == target), None)
    field = _field(row, "update_field") if row else None
    if field:
        return bool(_field(row, "evaluate_as_expression") or doc is None or cstr(doc.get(field)) != cstr(_field(row, "update_value")))
    return False


def _transition_consistent(doc, wf, transition):
    if doc.doctype != "Expense Claim" or _field(transition, "next_state") is None:
        return True
    row = next((r for r in getattr(wf, "states", []) if _field(r, "state") == _field(transition, "next_state")), None)
    if not row or _field(transition, "transition_tasks") or _field(row, "evaluate_as_expression"):
        return True
    approval = doc.get("approval_status")
    if _field(row, "update_field") == "approval_status":
        approval = _field(row, "update_value")
    if cint(doc.docstatus) == 0 and cstr(_field(row, "doc_status")) == "1" and approval == "Draft":
        return False
    if cint(_field(row, "doc_status")) != 2 and (_field(transition, "next_state") == "Approved" and approval == "Rejected" or _field(transition, "next_state") == "Rejected" and approval == "Approved"):
        return False
    return True


def _effective_transitions(doc, wf):
    state = doc.get(wf.workflow_state_field)
    return [t for t in wf.transitions if t.state == state and is_transition_condition_satisfied(t, doc) and (doc.doctype != "Expense Claim" or _transition_has_effect(t, wf, doc))]


def _required_transitions(doc, wf):
    transitions = _effective_transitions(doc, wf)
    if doc.doctype != "Expense Claim":
        return transitions
    optional = {_field(row, "state") for row in wf.states if cint(_field(row, "is_optional_state"))}
    return [transition for transition in transitions if transition.next_state not in optional]


def _expense_conflicts(doc, wf):
    """Identify contradictions without rewriting any recorded business status."""
    if not wf:
        return []
    state = cstr(doc.get(wf.workflow_state_field))
    approval = doc.get("approval_status")
    status = doc.get("status")
    row = next((r for r in getattr(wf, "states", []) if _field(r, "state") == state), None)
    notices = []
    expected = _field(row, "doc_status") if row else None
    if expected is not None and cstr(expected) != "" and cint(expected) != cint(doc.docstatus):
        notices.append("Document Status does not match the configured Workflow State.")
    # A cancelled document may legitimately retain its previous approval decision.
    if cint(doc.docstatus) != 2:
        decision = _field(row, "update_value") if row and _field(row, "update_field") == "approval_status" else state
        if (decision == "Approved" and approval in {"Rejected", "Draft"}) or (decision == "Rejected" and approval == "Approved"):
            notices.append("Workflow State and Expense Claim Approval Status disagree.")
        if (status == "Rejected" and approval == "Approved") or (status in {"Paid", "Unpaid"} and approval == "Rejected"):
            notices.append("Expense Claim Status and Approval Status disagree.")
    return notices


def _workflow_notices(doc, wf):
    if not wf or doc.doctype != "Expense Claim":
        return []
    state = doc.get(wf.workflow_state_field)
    notices = []
    for transition in wf.transitions:
        if transition.state != state or not is_transition_condition_satisfied(transition, doc):
            continue
        if not _transition_has_effect(transition, wf, doc):
            notices.append(_("Configured action {0} leaves {1} unchanged and has no field update or task. It is not a new pending approval.").format(transition.action, state))
        elif not _transition_consistent(doc, wf, transition):
            notices.append(_("Configured action {0} would submit a Draft approval or create conflicting Expense Claim approval statuses. Review the native Approval Status and workflow field updates before using it.").format(transition.action))
    return notices


def _expense_status(doc, wf, permitted):
    def value(field):
        return doc.get(field) if field in permitted else None
    document_status = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(cint(doc.docstatus), "Unknown")
    state = value(wf.workflow_state_field) if wf else None
    approval, claim = value("approval_status"), value("status")
    cancelled = cint(doc.docstatus) == 2 or claim == "Cancelled"
    rejected = not cancelled and (approval == "Rejected" or claim == "Rejected" or state == "Rejected")
    conflicts = _expense_conflicts(doc, wf)
    outgoing = _required_transitions(doc, wf) if wf else []
    configuration_blocked = bool(outgoing and not any(_transition_consistent(doc, wf, t) for t in outgoing))
    approved = approval == "Approved" or approval is None and claim in {"Paid", "Unpaid"}
    paid = cint(doc.docstatus) == 1 and claim == "Paid" and not rejected and not cancelled
    unpaid = cint(doc.docstatus) == 1 and approved and claim == "Unpaid" and not rejected and not cancelled
    net, reimbursed = value("grand_total"), value("total_amount_reimbursed")
    remaining = max(0, flt(net) - flt(reimbursed)) if net is not None and reimbursed is not None and not rejected and not cancelled else None
    if cancelled:
        display, payment, variant = "Cancelled", "Cancelled", "muted"
    elif rejected:
        display, payment, variant = "Rejected", "Not payable — rejected", "danger"
    elif paid:
        display, payment, variant = "Paid", "Paid", "success"
        if flt(value("total_advance_amount")) > 0 and net is not None and flt(net) == 0:
            payment = "Settled against advance"
    elif unpaid:
        display, payment, variant = "Approved · Unpaid", "Awaiting payment", "warning"
        if reimbursed is not None and flt(reimbursed) > 0 and remaining is not None and remaining > 0:
            payment = "Partly reimbursed"
    elif cint(doc.docstatus) == 0 and state in {"Draft", "Returned"}:
        display, payment, variant = ("Returned for correction" if state == "Returned" else "Draft"), "Not posted", "warning" if state == "Returned" else "muted"
    elif configuration_blocked:
        display, payment, variant = "Draft" if cint(doc.docstatus) == 0 else "Needs Review", "Not posted" if cint(doc.docstatus) == 0 else "Workflow setup needs review", "warning"
    elif outgoing:
        display, payment, variant = "Pending Approval", "Not posted" if cint(doc.docstatus) == 0 else "Awaiting approval", "pending"
    else:
        display, payment, variant = claim or document_status, "Not posted" if cint(doc.docstatus) == 0 else "Not determined", "muted"
    return dict(document_status=document_status, workflow_state=state, approval_status=approval, claim_status=claim, display_status=display, payment_status=payment, variant=variant, conflicts=conflicts, has_conflict=bool(conflicts), configuration_blocked=configuration_blocked, cancelled=cancelled, rejected=rejected, paid=paid, unpaid=unpaid, completed=bool(paid and not outgoing and not conflicts), outstanding=remaining, claimed=value("total_claimed_amount"), sanctioned=value("total_sanctioned_amount"), advance_applied=value("total_advance_amount"), reimbursed=reimbursed, net_payable=net)


def _document_views(doc, wf, requested, involved, actions, pending, permitted):
    if not wf:
        return _native_views(doc, requested, involved, actions, permitted)
    state, rejected, complete, roles = _state_info(doc, wf)
    info = _expense_status(doc, wf, permitted) if doc.doctype == "Expense Claim" else None
    views = ["requests"] if requested else []
    if info:
        required_labels = {transition.action for transition in _required_transitions(doc, wf) if not (state in {"Draft", "Returned"} and _field(transition, "allowed") == "Employee")}
        pending_actions = bool(set(actions) & required_labels)
        related = requested or involved or bool(pending_actions and pending)
        if not related:
            return [], state, roles, info
        if pending_actions and pending and not info["rejected"] and not info["cancelled"] and not info["has_conflict"]:
            views.append("approvals")
        if info["cancelled"]:
            views.append("cancelled")
        elif info["rejected"]:
            views.append("rejected")
        else:
            if requested and cint(doc.docstatus) == 0:
                views.append("drafts")
            if info["completed"]:
                views.append("completed")
            if not info["has_conflict"] and not info["configuration_blocked"] and (info["unpaid"] or requested and roles and not actions and not info["paid"]):
                views.append("waiting")
        # Directly assigned approvers retain access to relevant claim history,
        # even when no approval remains. This never grants document permission.
        views.append("all")
    else:
        if actions and pending and not complete and not rejected:
            views.append("approvals")
        if requested:
            if doc.docstatus == 0:
                views.append("drafts")
            if roles and not actions and not rejected:
                views.append("waiting")
            if rejected:
                views.append("rejected")
            if complete:
                views.append("completed")
        if views:
            views.append("all")
    return list(dict.fromkeys(views)), state, roles, info


def _actions(doc, wf):
    if not wf:
        return _native_actions(doc)
    if not doc.get(wf.workflow_state_field):
        return []
    transitions = get_transitions(doc, wf)
    if doc.doctype == "Expense Claim" and _expense_conflicts(doc, wf):
        cancelled = {_field(row, "state") for row in wf.states if cstr(_field(row, "doc_status")) == "2"}
        transitions = [transition for transition in transitions if transition.next_state in cancelled]
    return list(dict.fromkeys(t.action for t in transitions if has_approval_access(frappe.session.user, doc, t) and (doc.doctype != "Expense Claim" or _transition_has_effect(t, wf, doc)) and _transition_consistent(doc, wf, t)))


def _requester_fields(doctype):
    configured = _config().get("requester_fields", {})
    if doctype in configured:
        return configured[doctype]
    # HRMS Expense Claims have a standard employee requester distinct from owner.
    return {"employee": "employee"} if doctype in EMPLOYEE_TYPES else {}


def _requester_identity(doc, permitted):
    for field, identity in _requester_fields(doc.doctype).items():
        if field not in permitted or not doc.get(field):
            continue
        if identity == "user":
            return doc.get(field)
        if identity == "employee":
            employee = doc.get(field)
            if frappe.db.get_value("Employee", {"name": employee, "user_id": frappe.session.user}, "name"):
                return frappe.session.user
            # The readable claim already contains its employee name/ID. Do not
            # expose another employee's User identity through an unrestricted lookup.
            return (doc.get("employee_name") if "employee_name" in permitted else None) or employee
    return doc.owner


def _requested(doc):
    user = frappe.session.user
    if doc.owner == user:
        return True
    mapping = _requester_fields(doc.doctype)
    # Use the standard Expense Claim employee link or explicit configured mappings.
    for field, identity in mapping.items():
        if identity == "user" and doc.get(field) == user:
            return True
        if identity == "employee" and doc.get(field) and frappe.db.get_value("Employee", {"name": doc.get(field), "user_id": user}, "name"):
            return True
    return False


def _state_info(doc, wf):
    if not wf:
        if doc.doctype in RECORD_TYPES:
            return "Recorded", False, False, []
        if doc.doctype == "ToDo":
            return doc.get("status"), False, doc.get("status") == "Closed", []
        status = cint(doc.docstatus)
        return {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(status), status == 2, status == 1, []
    state = doc.get(wf.workflow_state_field)
    outgoing = _required_transitions(doc, wf)
    state_row = next((s for s in wf.states if s.state == state), None)
    style = frappe.db.get_value("Workflow State", state, "style") if state else None
    rejected = style == "Danger" or doc.docstatus == 2
    complete = bool(state and not outgoing and not rejected)
    # Expose configured roles only on documents the user can read; never guess users.
    next_roles = sorted({t.allowed for t in outgoing})
    return state, rejected, complete, next_roles


def _pending_actions(references=None):
    filters = {"status": "Open"}
    if references is not None:
        if not references:
            return set()
        filters.update(reference_doctype=["in", sorted({doctype for doctype, _ in references})], reference_name=["in", sorted({name for _, name in references})])
    pending = set()
    start = 0
    while True:
        batch = frappe.get_list("Workflow Action", filters=filters, fields=["reference_doctype", "reference_name", "workflow_state"], limit_start=start, limit_page_length=200)
        pending.update((r.reference_doctype, r.reference_name, r.workflow_state) for r in batch)
        if len(batch) < 200:
            return pending
        start += len(batch)


def _claim_amount(doc, permitted):
    # grand_total is the net sanctioned/taxed amount less allocated advances,
    # not the amount being claimed by the employee.
    for field, label in (("total_claimed_amount", "Claim Amount"), ("grand_total", "Net Payable")):
        if field in permitted and doc.get(field) is not None:
            return doc.get(field), label
    return None, "Claim Amount"


def _readable_table(doc, meta, fieldname):
    df = meta.get_field(fieldname)
    return bool(df and df.fieldtype in {"Table", "Table MultiSelect"} and (frappe.session.user == "Administrator" or not df.permlevel or doc.has_permlevel_access_to(fieldname, df, "read")))


def _claim_settlement(doc, permitted, meta=None):
    """Configured claim settlement route, not proof that money was disbursed."""
    def value(field):
        return doc.get(field) if field in permitted else None
    meta = meta or frappe.get_meta(doc.doctype)
    net = value("grand_total")
    allocated = value("total_advance_amount")
    advances = []
    if _readable_table(doc, meta, "advances"):
        child = set(get_permitted_fields("Expense Claim Advance", parenttype=doc.doctype))
        if allocated is None and "allocated_amount" in child:
            allocated = sum(flt(row.get("allocated_amount")) for row in doc.get("advances", []))
        for row in doc.get("advances", []):
            name = row.get("employee_advance") if "employee_advance" in child else None
            if name and frappe.has_permission("Employee Advance", "read", doc=name):
                advances.append({"doctype": "Employee Advance", "name": name})
    mode = value("mode_of_payment")
    paid = value("is_paid")
    account = value("payable_account")
    method_type = None
    direct = paid is not None and cint(paid) == 1
    if direct and mode and frappe.has_permission("Mode of Payment", "read", doc=mode):
        method_type = frappe.get_cached_value("Mode of Payment", mode, "type")
    base = (method_type if method_type in {"Cash", "Bank"} else "Direct Payment") if direct else ("Payable" if paid is not None and not cint(paid) else "Not specified")
    if flt(allocated) > 0:
        label = "Advance + " + base if net is not None and flt(net) > 0 else "Against Advance"
        kind = "advance"
    else:
        label, kind = base, base.lower().replace(" ", "-")
    configured_route = label
    if cint(doc.docstatus) == 2:
        label, kind = "Cancelled", "cancelled"
    elif "status" in permitted and doc.get("status") == "Rejected" or "approval_status" in permitted and doc.get("approval_status") == "Rejected":
        label, kind = "Not payable (Rejected)", "rejected"
    return {"label": label, "kind": kind, "configured_route": configured_route if configured_route != label else None, "mode_of_payment": mode if direct else None, "payable_account": account if base == "Payable" and (not flt(allocated) or net is not None and flt(net) > 0) else None, "advance_amount": allocated, "advances": advances, "net_payable": net}


def _next_action(doc, info, actions, wf=None):
    if not wf and doc.doctype in RECORD_TYPES:
        return "Open record for attendance details"
    if not wf and doc.doctype == "Leave Application" and cint(doc.docstatus) == 0 and doc.get("status") not in {"Approved", "Rejected"}:
        return "Open Leave Application → select Approved or Rejected → Submit"
    if not wf and cint(doc.docstatus) == 0:
        if doc.doctype == "Expense Claim" and doc.get("approval_status") not in {"Approved", "Rejected"}:
            return "Select Approval Status → Save → Submit" if doc.has_permission("write") else "Await an authorized Approval Status decision"
        return "Available: Submit" if "Submit" in actions else "Open document to edit the draft"
    if info:
        if info["has_conflict"]:
            return "Review the status conflict in Expense Claim"
        if info["configuration_blocked"]:
            from my_work.claim_tools import _draft_editable, _field_writable
            field = frappe.get_meta(doc.doctype).get_field("approval_status")
            if _draft_editable(doc, wf) and _field_writable(doc, field):
                return "Select Approval Status → Save → Workflow action"
            return "Await an authorized Approval Status decision"
        if info["cancelled"]:
            return "No action — cancelled"
        if info["rejected"]:
            return "Review the rejection decision"
        if info["unpaid"]:
            return "Open Expense Claim for payment / reimbursement"
        if info["paid"]:
            return "No action — settled"
        if actions:
            return "Available: " + " / ".join(actions)
        if info["display_status"] == "Pending Approval":
            return "Waiting for approval"
        if info["display_status"] == "Returned for correction":
            return "Correct the claim and resubmit"
        if cint(doc.docstatus) == 0:
            return "Review the draft claim"
    return "Available: " + " / ".join(actions) if actions else "Open document"


def _rows(sources=None, scope=None, options=None):
    from my_work.loading import settings, candidates
    scope = scope if scope is not None else settings()
    sources = list(sources if sources is not None else _sources())
    selected = candidates(sources, scope, options or {})
    workflow_references = [(meta.name, candidate.name) for wf, meta, candidate in selected if wf]
    pending = _pending_actions(workflow_references) if workflow_references else set()
    rows = []
    for wf, meta, candidate in selected:
        if meta is None:
            task = candidate
            linked = bool(task.reference_type and task.reference_name)
            if linked and not frappe.has_permission(task.reference_type, "read", doc=task.reference_name):
                continue
            rows.append(dict(doctype="ToDo", name=task.name, module="Tasks", title=strip_html(task.description or ""), owner=task.assigned_by, requested_by=task.assigned_by, creation=task.creation, modified=task.modified, due_date=task.date, priority=task.priority, status=task.status, state=task.status, actions=[], views=["assigned"] if task.status == "Open" else (["completed"] if task.status == "Closed" else ["cancelled"]), kind="task", document_status="Recorded", reference_type=task.reference_type, reference_name=task.reference_name))
            continue
        permitted = set(get_permitted_fields(meta.name))
        try:
            doc = frappe.get_doc(meta.name, candidate.name)
            doc.check_permission("read")
            actions = _actions(doc, wf)
            requested = _requested(doc)
            involved = _involved(doc, meta, permitted)
            has_pending = bool(wf and (doc.doctype, doc.name, doc.get(wf.workflow_state_field)) in pending)
            views, state, next_roles, status_info = _document_views(doc, wf, requested, involved, actions, has_pending, permitted)
            views = stage_views(views, doc.docstatus, meta.is_submittable)
            if not views:
                continue
            def value(field):
                return doc.get(field) if field in permitted else None
            title = value(meta.title_field) if meta.title_field else None
            from my_work.list_values import monetary_value, against_accounts
            amount, amount_label, row_currency = monetary_value(doc, meta, permitted)
            remarks, settlement = None, against_accounts(doc, meta, permitted) if doc.doctype != "Expense Claim" else None
            if doc.doctype == "Expense Claim":
                amount, amount_label = _claim_amount(doc, permitted)
                row_currency = value("currency")
                remarks = strip_html(cstr(value("remark"))) if "remark" in permitted else None
                settlement = _claim_settlement(doc, permitted, meta)
            rows.append(dict(doctype=doc.doctype, name=doc.name, module=meta.module, title=strip_html(cstr(title or value("description") or doc.name))[:240], owner=doc.owner, requested_by=_requester_identity(doc, permitted), creation=doc.creation, modified=doc.modified, flow_mode="workflow" if wf else "record" if meta.name in RECORD_TYPES else "standard", docstatus=cint(doc.docstatus), document_status={0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(cint(doc.docstatus)) if meta.is_submittable else "Recorded", state=state if not wf or wf.workflow_state_field in permitted else None, status=value("status"), status_info=status_info, status_summary=describe_status(doc, meta, wf, permitted, status_info), display_status=status_info["display_status"] if status_info else state, next_action=_next_action(doc, status_info, actions, wf), remarks=remarks, amount=amount, amount_label=amount_label, settlement=settlement, payment_type=settlement["label"] if settlement else None, currency=row_currency, priority=value("priority"), actions=actions, next_roles=next_roles, views=views, kind="document"))
        except (frappe.PermissionError, frappe.DoesNotExistError):
            continue
    return rows


def _approval_status_options():
    if not frappe.db.exists("DocType", "Expense Claim") or not frappe.has_permission("Expense Claim", "read"):
        return []
    if "approval_status" not in get_permitted_fields("Expense Claim"):
        return []
    return [value for value in cstr(frappe.get_meta("Expense Claim").get_field("approval_status").options).splitlines() if value]


@frappe.whitelist()
def dashboard(view="all", search="", module=None, doctype=None, start=0, page_length=20, sort="modified", direction="desc", priority=None, claim_status=None, approval_status=None, document_status=None, decision=None, record_limit=100, days=30, from_date=None, to_date=None):
    _user()
    if view not in VIEWS or sort not in {"modified", "creation", "name", "priority"} or direction not in {"asc", "desc"}:
        frappe.throw(_("Invalid filter"))
    if document_status and document_status not in {"Draft", "Submitted", "Cancelled", "Recorded"}:
        frappe.throw(_("Invalid document status"))
    if decision and decision not in DECISIONS:
        frappe.throw(_("Invalid approval filter"))
    start = max(0, cint(start))
    page_length = min(100, max(1, cint(page_length)))
    sources = list(_sources())
    from my_work.loading import settings
    scope = settings(record_limit, days, from_date, to_date)
    rows = _rows(sources, scope, dict(view=view,module=module,doctype=doctype,priority=priority,claim_status=claim_status,approval_status=approval_status,document_status=document_status,decision=decision))
    summary = {key: sum(key in r["views"] for r in rows) for key in ("approvals", "requests", "assigned", "waiting")}
    modules = sorted({r["module"] for r in rows} | {meta.module for _, meta in sources})
    doctypes = sorted({r["doctype"] for r in rows} | {meta.name for _, meta in sources})
    query = cstr(search).casefold().strip()
    filtered = [r for r in rows if (view == "all" and bool(r["views"]) or view in r["views"]) and (not module or r["module"] == module) and (not doctype or r["doctype"] == doctype) and (not priority or r.get("priority") == priority) and (not decision or (r.get("status_summary") or {}).get("key") == decision) and (not document_status or r.get("document_status") == document_status) and (not claim_status or r.get("status") == claim_status) and (not approval_status or (r.get("status_info") or {}).get("approval_status") == approval_status) and (not query or query in " ".join(cstr(r.get(f)) for f in ("name", "title", "remarks", "doctype", "owner", "state", "display_status", "payment_type")).casefold())]
    filtered.sort(key=lambda r: (({"Low": 1, "Medium": 2, "High": 3, "Urgent": 4}.get(r.get("priority"), 0) if sort == "priority" else cstr(r.get(sort))), r["doctype"], r["name"]), reverse=direction == "desc")
    return {"data": filtered[start:start + page_length], "loading": scope, "total": len(filtered), "start": start, "page_length": page_length, "summary": summary, "modules": modules, "doctypes": doctypes, "statuses": sorted({r["status"] for r in rows if r.get("status")}), "approval_statuses": _approval_status_options(), "counts": {key: sum(key in r["views"] for r in rows) for key in VIEWS if key != "all"} | {"all": sum(bool(r["views"]) for r in rows)}, "request_types": sorted({meta.name for _, meta in sources if frappe.has_permission(meta.name, "create")})}


def _document(doctype, name):
    _user()
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    if doctype == "ToDo" and doc.allocated_to != frappe.session.user:
        frappe.throw(_("Only your own assignments are available"), frappe.PermissionError)
    return doc


def _history(doc):
    # Parent read permission is mandatory. System-generated Workflow comments are
    # existing recorded history; no inferred or reconstructed decisions.
    return frappe.get_all("Comment", filters={"reference_doctype": doc.doctype, "reference_name": doc.name, "comment_type": ["in", ["Workflow", "Submitted", "Cancelled"]]}, fields=["name", "creation", "comment_by", "owner", "content", "comment_type"], order_by="creation asc, name asc")


def _attachments(doc):
    files = frappe.get_list("File", filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name}, fields=["name", "file_name", "is_private"], limit_page_length=100)
    return [dict(name=f.name, label=f.file_name, private=bool(f.is_private), can_delete=bool(doc.has_permission("write") and frappe.has_permission("File", "delete", doc=f.name))) for f in files if frappe.has_permission("File", "read", doc=f.name)]


def _expense_summary(doc, permitted, child_fields):
    """Reference-layout fields derived only from permission-readable claim data."""
    summary = []
    def add(name, label, value, fieldtype="Data", icon="file"):
        summary.append(dict(fieldname=name, label=label, value=value, fieldtype=fieldtype, icon=icon))
    if "employee" in permitted:
        employee = doc.get("employee_name") if "employee_name" in permitted else None
        add("employee", "Employee", employee or doc.get("employee") or "", icon="user")
    if "department" in permitted:
        add("department", "Department", doc.get("department") or "", icon="building")
    if "total_claimed_amount" in permitted:
        add("total_claimed_amount", "Claim Amount", doc.get("total_claimed_amount"), "Currency", "money")
    if "expenses" in permitted and "expense_date" in child_fields:
        dates = sorted(cstr(row.get("expense_date")) for row in doc.get("expenses", []) if row.get("expense_date"))
        add("expense_period", "Expense Period", [dates[0], dates[-1]] if dates else [], "Date Range", "calendar")
    if "remark" in permitted:
        purpose = doc.get("remark")
        if not purpose and "expenses" in permitted and "description" in child_fields:
            purpose = "; ".join(dict.fromkeys(strip_html(cstr(row.get("description"))) for row in doc.get("expenses", []) if row.get("description")))
        add("remark", "Purpose", strip_html(cstr(purpose)), icon="file")
    if "total_sanctioned_amount" in permitted and doc.get("total_sanctioned_amount") and doc.get("total_sanctioned_amount") != doc.get("total_claimed_amount"):
        add("total_sanctioned_amount", "Sanctioned Amount", doc.get("total_sanctioned_amount"), "Currency", "money")
    return summary


def _tools(doc, wf, permitted):
    from my_work.claim_tools import review_tools
    return review_tools(doc, wf, permitted)


@frappe.whitelist()
def review(doctype, name):
    doc = _document(doctype, name)
    meta = frappe.get_meta(doctype)
    wf_name = frappe.db.get_value("Workflow", {"document_type": doctype, "is_active": 1}, "name")
    wf = frappe.get_cached_doc("Workflow", wf_name) if wf_name else None
    # Scalar-field helpers omit Table fields. Check table permlevels explicitly
    # after the parent document read permission has already been enforced.
    permitted = set(get_permitted_fields(doctype))
    permitted.update(df.fieldname for df in meta.get_table_fields() if frappe.session.user == "Administrator" or not df.permlevel or doc.has_permlevel_access_to(df.fieldname, df, "read"))
    fields = []
    selected = _config().get("display_fields", {}).get(doctype, DEFAULT_FIELDS)
    for fieldname in selected:
        df = meta.get_field(fieldname)
        if df and fieldname in permitted and df.fieldtype in SAFE_TYPES and not df.hidden:
            value = doc.get(fieldname)
            fields.append({"fieldname": fieldname, "label": df.label, "fieldtype": df.fieldtype, "value": strip_html(cstr(value)) if value is not None else ""})
    remark_fields = [dict(fieldname=df.fieldname, label=df.label, fieldtype=df.fieldtype, value=strip_html(cstr(doc.get(df.fieldname)))) for df in meta.fields if df.fieldname in permitted and not df.hidden and df.fieldtype in SAFE_TYPES and (df.fieldname in {"remark", "remarks", "custom_remark", "custom_remarks"} or cstr(df.label).strip().lower() in {"remarks", "purpose"}) and doc.get(df.fieldname)]
    additional_fields = []
    if doctype != "Expense Claim":
        from my_work.document_details import header_details
        fields, additional_fields = header_details(doc, meta, permitted, SAFE_TYPES, _config().get("display_fields", {}).get(doctype))
    tables = []
    child_fields = set()
    if doctype == "Expense Claim" and "expenses" in permitted:
        child_meta = frappe.get_meta("Expense Claim Detail")
        child_fields = set(get_permitted_fields(child_meta.name, parenttype=doctype))
        columns = [f for f in ("expense_type", "description", "amount") if f in child_fields]
        tables = [{"label": "Expense Details", "columns": columns, "rows": [{f: strip_html(cstr(row.get(f))) for f in columns} for row in doc.get("expenses", [])], "total": sum(flt(row.get("amount")) for row in doc.get("expenses", [])) if "amount" in columns else None}]
    if doctype != "Expense Claim":
        from my_work.document_details import child_tables
        tables = child_tables(doc, meta, SAFE_TYPES)
    from my_work.document_events import recorded_events
    return {"data": {"document_events": recorded_events(doc), "doctype": doc.doctype, "name": doc.name, "owner": doc.owner, "creation": doc.creation, "modified": doc.modified, "state": doc.get(wf.workflow_state_field) if wf and wf.workflow_state_field in permitted else (_state_info(doc, None)[0] if not wf else None), "flow_mode": "workflow" if wf else "standard" if meta.is_submittable else "record", "is_submittable": bool(meta.is_submittable), "business_status": doc.get("status") if "status" in permitted else None, "additional_fields": additional_fields, "remark_fields": remark_fields, "docstatus": cint(doc.docstatus), "fields": fields, "tools": _tools(doc, wf, permitted), "summary_fields": _expense_summary(doc, permitted, child_fields) if doctype == "Expense Claim" and not _config().get("display_fields", {}).get(doctype) else fields, "currency": doc.get("currency") if "currency" in permitted else None, "next_states": sorted({t.next_state for t in _required_transitions(doc, wf)}) if wf else [] if not meta.is_submittable else (["Submitted"] if cint(doc.docstatus) == 0 else ["Cancelled"] if cint(doc.docstatus) == 1 else []), "status_info": _expense_status(doc, wf, permitted) if doctype == "Expense Claim" else None, "status_summary": describe_status(doc, meta, wf, permitted, _expense_status(doc, wf, permitted) if doctype == "Expense Claim" else None), "workflow_notices": _workflow_notices(doc, wf), "can_print": bool(doc.has_permission("print")), "settlement": _claim_settlement(doc, permitted, meta) if doctype == "Expense Claim" else None, "tables": tables, "actions": _actions(doc, wf), "history": _history(doc), "next_roles": _state_info(doc, wf)[3] if wf else [], "activity": frappe.get_all("Comment", filters={"reference_doctype": doc.doctype, "reference_name": doc.name, "comment_type": "Comment"}, fields=["creation", "owner", "comment_by", "content"], order_by="creation desc", limit_page_length=50), "can_complete": doctype == "ToDo" and doc.status == "Open", "attachments": _attachments(doc), "attachments_note": _("Attachments open through Frappe with normal file permissions.")}}


@frappe.whitelist()
def history(doctype, name):
    return {"data": _history(_document(doctype, name))}


@frappe.whitelist()
def transitions(doctype, name):
    return {"data": review(doctype, name)["data"]["actions"]}


@frappe.whitelist(methods=["POST"])
def add_comment(doctype, name, content):
    """Same native read-permission policy, independently of status/actions."""
    doc = _document(doctype, name)
    content = cstr(content).strip()
    if not content:
        frappe.throw(_("Enter a comment before posting"))
    if len(content) > 10000:
        frappe.throw(_("Comments must be 10,000 characters or fewer"))
    from frappe.desk.form.utils import add_comment as native_add_comment
    user = frappe.session.user
    comment = native_add_comment(
        reference_doctype=doc.doctype,
        reference_name=doc.name,
        content="<p>" + escape(content).replace("\n", "<br>") + "</p>",
        comment_email=user,
        comment_by=frappe.get_cached_value("User", user, "full_name") or user,
    )
    return {"data": {"name": comment.name, "creation": comment.creation, "owner": comment.owner, "comment_by": comment.comment_by, "content": comment.content}}


@frappe.whitelist(methods=["POST"])
def act(doctype, name, action, modified, remarks=None):
    remarks = cstr(remarks).strip()
    if len(remarks) > 2000:
        frappe.throw(_("Remarks must be 2,000 characters or fewer"))
    doc = _document(doctype, name)
    # Lock the document for the transaction before comparing the client's version.
    frappe.db.get_value(doctype, name, "modified", for_update=True)
    doc.reload()
    doc.check_permission("read")
    if cstr(doc.modified) != cstr(modified):
        frappe.throw(_("This document changed. Refresh and review it again."), frappe.TimestampMismatchError)
    if action not in transitions(doctype, name)["data"]:
        frappe.throw(_("This action is no longer allowed"), frappe.PermissionError)
    from my_work.claim_tools import _workflow
    workflow = _workflow(doc)
    if workflow:
        result = apply_workflow(doc.as_json(), action)
    else:
        # A fresh configuration check and native permission checks are mandatory.
        # Document methods retain all business validations, accounting hooks,
        # linked-document restrictions, and standard Submitted/Cancelled history.
        if action not in _native_actions(doc):
            frappe.throw(_("This standard action is no longer allowed"), frappe.PermissionError)
        doc.check_permission("submit" if action == "Submit" else "cancel")
        result = doc.submit() if action == "Submit" else doc.cancel()
        result.add_comment("Comment", _("My Work: {0}").format(escape(action)) + ("<br>" + escape(remarks) if remarks else ""))
        return {"data": {"name": result.name, "modified": result.modified, "queued": False}}
    # Supported workflow API records its own Workflow comment; add source audit.
    if result is None:
        doc.add_comment("Workflow", _("My Work: queued {0}").format(escape(action)) + ("<br>" + escape(remarks) if remarks else ""))
        return {"data": {"name": doc.name, "modified": doc.modified, "queued": True}}
    result.add_comment("Workflow", _("My Work: {0}").format(escape(action)) + ("<br>" + escape(remarks) if remarks else ""))
    return {"data": {"name": result.name, "modified": result.modified, "queued": False}}


@frappe.whitelist(methods=["POST"])
def complete_task(name, modified):
    doc = _document("ToDo", name)
    frappe.db.get_value("ToDo", name, "modified", for_update=True)
    doc.reload()
    if doc.allocated_to != frappe.session.user:
        frappe.throw(_("Assignment is no longer yours"), frappe.PermissionError)
    if cstr(doc.modified) != cstr(modified) or doc.status != "Open":
        frappe.throw(_("Assignment changed. Refresh and try again."), frappe.TimestampMismatchError)
    if doc.reference_type and doc.reference_name:
        from frappe.desk.form.assign_to import set_status
        frappe.get_doc(doc.reference_type, doc.reference_name).check_permission("read")
        set_status(doc.reference_type, doc.reference_name, todo=doc.name, assign_to=frappe.session.user, status="Closed")
    else:
        doc.check_permission("write")
        doc.status = "Closed"
        doc.save()
    return {"data": {"name": doc.name, "status": "Closed"}}


def _list(view, filters):
    filters = frappe.parse_json(filters) if filters else {}
    allowed = {"search", "module", "doctype", "start", "page_length", "sort", "direction", "priority", "claim_status", "approval_status", "document_status", "decision", "record_limit", "days", "from_date", "to_date"}
    return dashboard(view=view, **{key: value for key, value in filters.items() if key in allowed})


@frappe.whitelist()
def dashboard_summary():
    result = dashboard(page_length=1)
    return {"data": result["summary"], "loading": result["loading"]}


@frappe.whitelist()
def approval_list(filters=None):
    return _list("approvals", filters)


@frappe.whitelist()
def request_list(filters=None):
    return _list("requests", filters)


@frappe.whitelist()
def assigned_tasks(filters=None):
    return _list("assigned", filters)


@frappe.whitelist()
def waiting_on_others(filters=None):
    return _list("waiting", filters)
