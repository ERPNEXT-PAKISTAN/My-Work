"""Metadata-driven, permission-filtered business details for the review panel."""
import frappe
from frappe.model import get_permitted_fields
from frappe.utils import cstr, flt, strip_html

RECORD_TYPES = {"Employee Checkin"}
EMPLOYEE_TYPES = RECORD_TYPES | {"Expense Claim", "Employee Advance", "Attendance", "Attendance Request", "Leave Application", "Leave Allocation", "Leave Encashment", "Compensatory Leave Request", "Shift Request", "Shift Assignment", "Shift Schedule Assignment", "Salary Slip", "Additional Salary", "Retention Bonus", "Employee Incentive", "Employee Benefit Application", "Employee Benefit Claim", "Travel Request", "Overtime Slip", "Employee Transfer", "Employee Promotion", "Employee Separation", "Employee Onboarding"}
APPROVER_FIELDS = ("expense_approver", "leave_approver", "approver")
SUMMARY_FIELDS = ["customer", "customer_name", "supplier", "supplier_name", "party_type", "party", "employee", "employee_name", "department", "company", "transaction_date", "posting_date", "delivery_date", "schedule_date", "attendance_date", "time", "log_type", "from_date", "to_date", "start_date", "end_date", "leave_type", "total_leave_days", "leave_balance", "new_leaves_allocated", "total_leaves_allocated", "reason", "explanation", "status", "shift", "shift_type", "working_hours", "in_time", "out_time", "late_entry", "early_exit", "attendance", "skip_auto_attendance", "leave_application", "leave_approver", "approver", "currency", "total_qty", "total", "grand_total", "paid_amount", "outstanding_amount", "per_delivered", "per_billed", "project", "task", "cost_center", "remarks", "description"]
ITEM_COLUMNS = ["item_code", "uom", "qty", "rate", "amount"]


ORDER_TYPES = {"Sales Order", "Purchase Order"}


def excluded_detail(df):
    text=" ".join(cstr(df.get(key)) for key in ('fieldname','label','options')).lower().replace('_',' ').replace('-',' ')
    return 'coil production' in text


def order_header(doc, meta, permitted, safe_types):
    fields=[]
    profile=[('Customer' if doc.doctype=='Sales Order' else 'Supplier',['customer'] if doc.doctype=='Sales Order' else ['supplier']),('Date',['transaction_date','posting_date']),('Due Date',['delivery_date'] if doc.doctype=='Sales Order' else ['schedule_date']),('Status',['status']),('Company',['company']),('Total Amount',['grand_total','total_amount','total'])]
    for label,names in profile:
        for name in names:
            df=meta.get_field(name)
            if df and name in permitted and df.fieldtype in safe_types and not df.hidden:
                value=scalar(df,doc.get(name));value['label']=label;fields.append(value);break
    return fields, []


def scalar(df, value):
    return dict(fieldname=df.fieldname, label=df.label or df.fieldname, fieldtype=df.fieldtype, options=df.options, value=strip_html(cstr(value)) if value is not None else "")


def header_details(doc, meta, permitted, safe_types, configured=None):
    if doc.get("doctype") in ORDER_TYPES and configured is None:
        return order_header(doc,meta,permitted,safe_types)
    item_table = any(df.fieldname == "items" and df.fieldtype in {"Table", "Table MultiSelect"} for df in meta.fields)
    item_fields = set(ITEM_COLUMNS) | {"total_qty"}
    eligible = [df for df in meta.fields if not (item_table and df.fieldname in item_fields) and not excluded_detail(df) and df.fieldname in permitted and df.fieldtype in safe_types and not df.hidden and doc.get(df.fieldname) not in (None, "")]
    by_name = {df.fieldname: df for df in eligible}
    preferred = configured if configured is not None else SUMMARY_FIELDS + [df.fieldname for df in eligible if df.in_list_view]
    names = list(dict.fromkeys(name for name in preferred if name in by_name))
    if not names and configured is None:
        names = [df.fieldname for df in eligible[:10]]
    fields = [scalar(by_name[name], doc.get(name)) for name in names]
    extra = [scalar(df, doc.get(df.fieldname)) for df in eligible if df.fieldname not in names]
    return fields, extra


def child_tables(doc, meta, safe_types):
    """Parent table and child field permissions both apply, including permlevels."""
    from my_work.api import _readable_table
    result = []
    for table in meta.get_table_fields():
        if excluded_detail(table) or table.hidden or not doc.get(table.fieldname) or not _readable_table(doc, meta, table.fieldname):
            continue
        child = frappe.get_meta(table.options)
        permitted = set(get_permitted_fields(child.name, parenttype=doc.doctype))
        eligible = [df for df in child.fields if df.fieldname in permitted and df.fieldtype in safe_types and not df.hidden and not excluded_detail(df)]
        if not eligible:
            continue
        by_name = {df.fieldname: df for df in eligible}
        compact_items = table.fieldname == "items" or "item_code" in by_name
        preferred = ITEM_COLUMNS if compact_items else []
        names = [name for name in preferred if name in by_name] if compact_items else list(dict.fromkeys(df.fieldname for df in eligible if df.in_list_view))[:12]
        if compact_items and not names:
            continue
        if not names:
            names = [df.fieldname for df in eligible[:8]]
        rows, details = [], []
        for row in doc.get(table.fieldname):
            rows.append({name: strip_html(cstr(row.get(name))) if row.get(name) is not None else "" for name in names})
            details.append([] if compact_items else [scalar(df, row.get(df.fieldname)) for df in eligible if df.fieldname not in names and row.get(df.fieldname) not in (None, "")])
        result.append(dict(compact_items=compact_items, fieldname=table.fieldname, label=table.label or table.fieldname, columns=names, column_meta={name: dict(label=({"item_code": "Item Code", "uom": "UoM", "qty": "Qty", "rate": "Rate", "amount": "Amount"}.get(name) if compact_items else by_name[name].label), fieldtype=by_name[name].fieldtype, options=by_name[name].options) for name in names}, rows=rows, row_details=details, total=sum(flt(row.get("amount")) for row in doc.get(table.fieldname)) if "amount" in names else None))
    return result
