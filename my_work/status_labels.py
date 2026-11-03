"""Explain recorded decisions without equating submission with approval."""
from frappe.utils import cint, cstr

DECISIONS = {"approved", "not_approved", "rejected", "cancelled", "no_separate_approval", "unavailable", "workflow", "conflict"}


def describe(doc, meta, workflow, permitted, expense_info=None):
    status = cint(doc.docstatus)
    document = {0: "Draft · Not Final", 1: "Submitted · Final", 2: "Cancelled"}.get(status, "Unknown") if meta.is_submittable else "Recorded"
    document_variant = {0: "warning", 1: "info", 2: "muted"}.get(status, "muted") if meta.is_submittable else "info"
    def result(key, label, variant, explanation):
        return dict(key=key,label=label,variant=variant,explanation=explanation,document_label=document,document_variant=document_variant)
    if status == 2:
        return result("cancelled", "Cancelled", "muted", "This document is cancelled. Any earlier approval decision remains historical.")
    if expense_info and expense_info.get("has_conflict"):
        return result("conflict", "Status conflict — review required", "danger", "The recorded statuses disagree. Review the original document before taking action.")
    if meta.get_field("approval_status"):
        if "approval_status" not in permitted:
            return result("unavailable", "Approval not visible", "muted", "You do not have permission to read the approval decision.")
        decision = doc.get("approval_status")
        if decision == "Approved":
            return result("approved", "Approved", "success", "Approval is recorded. The document is still Draft and must be submitted separately." if status == 0 else "Approval is recorded. Payment or fulfilment is a separate status.")
        if decision == "Rejected":
            return result("rejected", "Rejected", "danger", "A rejection decision is recorded. This does not mean the document was cancelled.")
        if decision in {None, "", "Draft", "Pending", "Pending Approval", "Not Approved"}:
            return result("not_approved", "Not approved", "warning", "An approval decision has not been recorded. Review and save the decision, or use the configured workflow action.")
        return result("workflow", cstr(decision), "info", "This is the recorded native Approval Status.")
    if doc.doctype in {"Leave Application", "Shift Request"}:
        if "status" not in permitted:
            return result("unavailable", "Approval not visible", "muted", "You do not have permission to read the decision status.")
        decision = doc.get("status")
        if decision == "Approved":
            return result("approved", "Approved", "success", "The native approval decision is Approved. Submission is a separate step." if status == 0 else "The native approval decision is Approved.")
        if decision == "Rejected":
            return result("rejected", "Rejected", "danger", "The native approval decision is Rejected.")
        return result("not_approved", "Not approved", "warning", "The request is awaiting its native approval decision.")
    if workflow:
        if workflow.workflow_state_field not in permitted:
            return result("unavailable", "Workflow status not visible", "muted", "You do not have permission to read the workflow state.")
        state = cstr(doc.get(workflow.workflow_state_field))
        if state == "Approved":
            return result("approved", "Approved", "success", "The configured Workflow State is Approved.")
        if state in {"Rejected", "Request Rejected"}:
            return result("rejected", "Rejected", "danger", "The configured Workflow State records rejection.")
        if state in {"Draft", "Returned", "Pending", "Pending Approval"}:
            return result("not_approved", "Returned · Not approved" if state == "Returned" else "Pending approval" if state.startswith("Pending") else "Not approved", "warning", "The workflow has not recorded final approval. Use an available workflow action or wait for the responsible approver.")
        return result("workflow", state or "Workflow not started", "info", "Follow the recorded workflow state and available actions; this state is not assumed to mean approval.")
    return result("no_separate_approval", "No separate approval", "muted", "This document uses the standard Draft → Submitted flow. Submitted records have been posted; no separate approval decision is recorded." if meta.is_submittable else "This is a saved record. It does not have a separate approval or submission step.")


def stage_views(views, docstatus, submittable):
    """Submission stage is independent of approval, payment and fulfilment."""
    if not views or not submittable:
        return views
    stage = {0: "drafts", 1: "submitted"}.get(cint(docstatus))
    return list(dict.fromkeys(views + ([stage] if stage else [])))
