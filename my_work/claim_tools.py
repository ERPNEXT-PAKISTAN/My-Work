"""Native document tools for My Work. No direct financial/status DB updates."""
import math
from html import escape

import frappe
from frappe import _
from frappe.model import get_permitted_fields
from frappe.utils import cint, cstr, flt

EDIT_FIELDS = {"approval_status", "task", "project", "cost_center", "remark"}


def _state_editable(doc, workflow):
    if not workflow or frappe.session.user == "Administrator":
        return True
    state = doc.get(workflow.workflow_state_field)
    row = next((s for s in workflow.states if s.state == state), None)
    return bool(row and row.allow_edit in frappe.get_roles())


def _workflow(doc):
    name = frappe.db.get_value("Workflow", {"document_type": doc.doctype, "is_active": 1}, "name")
    return frappe.get_cached_doc("Workflow", name) if name else None


def _field_writable(doc, df):
    return bool(df and not df.read_only and (frappe.session.user == "Administrator" or not df.permlevel or doc.has_permlevel_access_to(df.fieldname, df, "write")))


def _draft_editable(doc, workflow):
    return cint(doc.docstatus) == 0 and doc.has_permission("write") and _state_editable(doc, workflow)


def _approval_managed(workflow):
    return bool(workflow and any(getattr(row,"update_field",None) == "approval_status" for row in (getattr(workflow,"states",[]) or [])))


def review_tools(doc, workflow, permitted):
    meta = frappe.get_meta(doc.doctype)
    writable = bool(doc.has_permission("write"))
    draft = bool(_draft_editable(doc, workflow))
    fields = []
    if doc.doctype == "Expense Claim":
        for name in ("approval_status", "task", "project", "cost_center", "remark", "status"):
            df = meta.get_field(name)
            if df and name in permitted:
                fields.append(dict(fieldname=name, label=df.label, fieldtype=df.fieldtype, options=df.options, value=doc.get(name), workflow_managed=bool(name == "approval_status" and _approval_managed(workflow)), editable=bool(name in EDIT_FIELDS and draft and _field_writable(doc, df) and not (workflow and workflow.workflow_state_field == name) and not (name == "approval_status" and _approval_managed(workflow)))))
    advances = []
    can_edit_advances = False
    if doc.doctype == "Expense Claim":
        from my_work.api import _readable_table
        table = meta.get_field("advances")
        can_edit_advances = bool(draft and _field_writable(doc, table))
        if _readable_table(doc, meta, "advances"):
            child_fields = set(get_permitted_fields("Expense Claim Advance", parenttype=doc.doctype))
            for row in doc.get("advances", []):
                name = row.employee_advance if "employee_advance" in child_fields else None
                readable = bool(name and frappe.has_permission("Employee Advance", "read", doc=name))
                advances.append(dict(row_name=row.name, employee_advance=name if readable else None, allocated_amount=row.allocated_amount if "allocated_amount" in child_fields else None, unclaimed_amount=row.unclaimed_amount if "unclaimed_amount" in child_fields else None, can_remove=can_edit_advances))
    assignments = frappe.get_list("ToDo", filters={"reference_type": doc.doctype, "reference_name": doc.name, "status": "Open"}, fields=["name", "allocated_to", "description", "date", "priority", "modified"], limit_page_length=50) if frappe.has_permission("ToDo", "read") else []
    can_share = bool(doc.has_permission("share") and not frappe.get_system_settings("disable_document_sharing"))
    shares = []
    if can_share:
        from frappe.share import get_users
        shares = get_users(doc.doctype, doc.name)
    return dict(date_editor=invoice_dates(doc, workflow, permitted), fields=fields, can_edit=draft, can_assign=writable, can_share=can_share, can_tag=writable, can_attach=writable, can_edit_advances=can_edit_advances, advances=advances, assignments=assignments, shares=shares, tags=[s.strip() for s in cstr(doc.get("_user_tags")).split(",") if s.strip()], employee=doc.get("employee") if "employee" in permitted else None, currency=doc.get("currency") if "currency" in permitted else None, edit_note=_("Claim fields and advance links can be edited only on a writable draft. Submitted claims require the native correction/amendment process."))


def _locked(doctype, name, modified, draft=False):
    from my_work.api import _document
    doc = _document(doctype, name)
    frappe.db.get_value(doctype, name, "modified", for_update=True)
    doc.reload()
    doc.check_permission("read")
    doc.check_permission("write")
    if cstr(doc.modified) != cstr(modified):
        frappe.throw(_("The document changed. Refresh the review panel and try again."), frappe.TimestampMismatchError)
    if draft and not _draft_editable(doc, _workflow(doc)):
        frappe.throw(_("This claim is not an editable draft in the current workflow state."), frappe.PermissionError)
    return doc


def _claim(name, modified):
    return _locked("Expense Claim", name, modified, draft=True)


def _check_field(doc, name):
    df = frappe.get_meta(doc.doctype).get_field(name)
    if not _field_writable(doc, df):
        frappe.throw(_("You cannot edit field {0}").format(name), frappe.PermissionError)
    return df


@frappe.whitelist(methods=["POST"])
def update_claim(name, modified, fields):
    doc = _claim(name, modified)
    fields = frappe.parse_json(fields)
    if not isinstance(fields, dict) or not fields or set(fields) - EDIT_FIELDS:
        frappe.throw(_("Only Approval Status, Task, Project, Cost Center and Remarks can be edited here."))
    workflow = _workflow(doc)
    if "approval_status" in fields and _approval_managed(workflow):
        frappe.throw(_("Approval Status is managed by this workflow. Use the available workflow action."), frappe.PermissionError)
    if workflow and workflow.workflow_state_field in fields:
        frappe.throw(_("This field is controlled by Workflow. Use a configured workflow action."), frappe.PermissionError)
    if fields.get("approval_status") == "Rejected" and flt(doc.get("total_advance_amount")) > 0:
        frappe.throw(_("Remove the allocated advance links from this draft before setting Approval Status to Rejected."))
    for field, value in fields.items():
        df = _check_field(doc, field)
        if field == "approval_status":
            options = cstr(df.options).splitlines()
            if value not in options:
                frappe.throw(_("Select a configured Approval Status."))
            if value == "Cancelled":
                frappe.throw(_("Cancelled is controlled by document cancellation. Use the native Cancel action."))
        elif df.fieldtype == "Link" and value:
            frappe.get_doc(df.options, value).check_permission("read")
        if field == "remark" and len(cstr(value)) > 10000:
            frappe.throw(_("Remarks are too long."))
        doc.set(field, value)
    # HRMS validates sanctioned amounts, advances and linked accounting fields.
    # The workflow state remains unchanged; subsequent transition uses apply_workflow.
    doc.save()
    doc.add_comment("Comment", _("My Work: updated {0}").format(", ".join(sorted(fields))))
    return {"data": {"name": doc.name, "modified": doc.modified}}


@frappe.whitelist(methods=["POST"])
def remove_advance(name, modified, row_name):
    doc = _claim(name, modified)
    _check_field(doc, "advances")
    row = next((row for row in doc.get("advances", []) if row.name == row_name), None)
    if not row:
        frappe.throw(_("The advance link no longer exists."), frappe.DoesNotExistError)
    doc.remove(row)
    doc.save()
    doc.add_comment("Comment", _("My Work: removed an advance link from this draft claim; the Employee Advance was preserved."))
    return {"data": {"name": doc.name, "modified": doc.modified}}


@frappe.whitelist(methods=["POST"])
def add_advance(name, modified, employee_advance, allocated_amount):
    doc = _claim(name, modified)
    _check_field(doc, "advances")
    child_df = frappe.get_meta("Expense Claim Advance").get_field("allocated_amount")
    if not _field_writable(doc, child_df):
        frappe.throw(_("You cannot allocate advances."), frappe.PermissionError)
    advance = frappe.get_doc("Employee Advance", employee_advance)
    advance.check_permission("read")
    if cint(advance.docstatus) != 1 or advance.employee != doc.employee or advance.company != doc.company or advance.currency != doc.currency:
        frappe.throw(_("Select a submitted advance for this employee, company and currency."))
    if any(row.employee_advance == employee_advance for row in doc.get("advances", [])):
        frappe.throw(_("This advance is already linked to the claim."))
    amount = flt(allocated_amount)
    if not math.isfinite(amount) or amount <= 0:
        frappe.throw(_("Allocated amount must be greater than zero."))
    from hrms.hr.doctype.expense_claim.expense_claim import get_advances
    candidates = get_advances(doc.as_json(), employee_advance)
    available = sum(max(0, flt(row.allocated_amount)) for row in candidates)
    if amount > available:
        frappe.throw(_("Allocation exceeds this advance's available balance."))
    remaining = amount
    for candidate in candidates:
        allocated = min(remaining, max(0, flt(candidate.allocated_amount)))
        if allocated <= 0:
            continue
        values = candidate.as_dict()
        for key in ("name", "parent", "parentfield", "parenttype", "creation", "modified", "owner", "modified_by", "docstatus", "idx"):
            values.pop(key, None)
        values["allocated_amount"] = allocated
        doc.append("advances", values)
        remaining -= allocated
    doc.save()
    doc.add_comment("Comment", _("My Work: linked an Employee Advance to this draft claim."))
    return {"data": {"name": doc.name, "modified": doc.modified}}


@frappe.whitelist(methods=["POST"])
def assign(doctype, name, modified, users, description=None, date=None, priority="Medium"):
    doc = _locked(doctype, name, modified)
    users = frappe.parse_json(users)
    if not isinstance(users, list) or not users or len(users) > 20 or not all(isinstance(user, str) and user for user in users) or priority not in {"Low", "Medium", "High"}:
        frappe.throw(_("Select up to 20 assignees and a valid priority."))
    from frappe.desk.form.assign_to import add
    result = add(dict(doctype=doctype, name=name, assign_to=list(dict.fromkeys(users)), description=description or _("Review {0}").format(doc.name), date=date, priority=priority))
    return {"data": result}


@frappe.whitelist(methods=["POST"])
def share(doctype, name, modified, user, write=0, submit=0, remove=0):
    from my_work.api import _document
    doc = _document(doctype, name)
    # Sharing is governed by its own native permission, independent of financial write.
    doc.check_permission("share")
    if frappe.get_system_settings("disable_document_sharing"):
        frappe.throw(_("Document sharing is disabled."), frappe.PermissionError)
    frappe.db.get_value(doctype, name, "modified", for_update=True)
    doc.reload()
    doc.check_permission("read")
    doc.check_permission("share")
    if cstr(doc.modified) != cstr(modified):
        frappe.throw(_("The document changed. Refresh and try again."), frappe.TimestampMismatchError)
    if not user or user == "Guest":
        frappe.throw(_("Select a user."))
    if cint(remove):
        from frappe.share import set_permission
        set_permission(doctype, name, user, "read", value=0)
    else:
        from frappe.share import add
        add(doctype, name, user=user, read=1, write=cint(write), submit=cint(submit))
    return {"data": {"name": name}}


@frappe.whitelist(methods=["POST"])
def tag(doctype, name, modified, tag, remove=0):
    doc = _locked(doctype, name, modified)
    tag = cstr(tag).strip()
    if not tag or len(tag) > 140 or any(c in tag for c in (",", "\n", "\r")):
        frappe.throw(_("Enter a tag of at most 140 characters without commas or newlines."))
    from frappe.desk.doctype.tag.tag import add_tag, remove_tag
    (remove_tag if cint(remove) else add_tag)(tag=tag, dt=doctype, dn=name)
    return {"data": {"name": name}}


@frappe.whitelist(methods=["POST"])
def remove_attachment(doctype, name, modified, file_name):
    doc = _locked(doctype, name, modified)
    file = frappe.get_doc("File", file_name)
    if file.attached_to_doctype != doctype or file.attached_to_name != name:
        frappe.throw(_("This attachment does not belong to the selected document."), frappe.PermissionError)
    file.check_permission("delete")
    frappe.delete_doc("File", file.name)
    doc.add_comment("Comment", _("My Work: removed attachment {0}").format(escape(cstr(file.file_name))))
    return {"data": {"name": name}}


def invoice_dates(doc, workflow, permitted):
    """Expose only writable draft invoice dates, including every payment installment."""
    if doc.doctype not in ("Sales Invoice", "Purchase Invoice") or not _draft_editable(doc, workflow):
        return None
    meta = frappe.get_meta(doc.doctype)
    names = ["posting_date", "due_date"]
    if doc.doctype == "Purchase Invoice":
        names.append("bill_date")
    if any(name not in permitted or not _field_writable(doc, meta.get_field(name)) for name in names):
        return None
    schedule = doc.get("payment_schedule") or []
    if schedule:
        table = meta.get_field("payment_schedule")
        child = frappe.get_meta(table.options)
        allowed = get_permitted_fields(table.options, parenttype=doc.doctype)
        from my_work.api import _readable_table
        if not _readable_table(doc, meta, "payment_schedule") or not _field_writable(doc, table) or "due_date" not in allowed or not _field_writable(doc, child.get_field("due_date")):
            return None
    return dict(fields=[dict(fieldname=n, label=meta.get_field(n).label, value=doc.get(n)) for n in names],
                schedule=[dict(name=r.name, idx=r.idx, due_date=r.due_date) for r in schedule])


@frappe.whitelist(methods=["POST"])
def update_invoice_dates(doctype, name, modified, dates, schedule=None):
    """Save explicitly chosen dates through the native invoice controller; never submit."""
    from frappe.utils import getdate
    doc = _locked(doctype, name, modified, draft=True)
    permitted = get_permitted_fields(doctype)
    editor = invoice_dates(doc, _workflow(doc), permitted)
    if not editor:
        frappe.throw(_("Invoice dates cannot be edited in this state."), frappe.PermissionError)
    dates = frappe.parse_json(dates)
    schedule = frappe.parse_json(schedule) if schedule else []
    expected = {f["fieldname"] for f in editor["fields"]}
    if not isinstance(dates, dict) or set(dates) != expected:
        frappe.throw(_("Refresh and provide all invoice dates."))
    for key, value in dates.items():
        if not value and key != "bill_date":
            frappe.throw(_("Posting Date and Due Date are required."))
        doc.set(key, getdate(value) if value else None)
    if not isinstance(schedule, list) or len(schedule) != len(editor["schedule"]):
        frappe.throw(_("The payment schedule changed. Refresh and try again."))
    by_name = {r.get("name"): r.get("due_date") for r in schedule if isinstance(r, dict)}
    if set(by_name) != {r["name"] for r in editor["schedule"]}:
        frappe.throw(_("The payment schedule changed. Refresh and try again."))
    for row in doc.get("payment_schedule") or []:
        if not by_name[row.name]:
            frappe.throw(_("Each installment needs a Due Date."))
        row.due_date = getdate(by_name[row.name])
    if doc.get("payment_schedule"):
        doc.set_due_date()
        if getdate(doc.due_date) != getdate(dates["due_date"]):
            frappe.throw(_("Due Date must match the latest payment installment date."))
    doc.save()
    return dict(name=doc.name, modified=doc.modified)
