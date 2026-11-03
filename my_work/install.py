"""Refresh module discovery before installing a newly registered bench app."""
import frappe


def prepare_modules():
    frappe.cache.delete_key("app_modules")
    frappe.setup_module_map()


def fix_workspace_route():
    """A workspace slug must not shadow the My Work Desk Page route."""
    old, new = "My Work", "My Work Overview"
    if frappe.db.exists("Workspace", old):
        workspace = frappe.get_doc("Workspace", old)
        if workspace.module != "My Work":
            frappe.throw("Cannot migrate a workspace belonging to another module")
        if frappe.db.exists("Workspace", new):
            frappe.throw("Both My Work workspace names exist; refusing to merge them")
        frappe.rename_doc("Workspace", old, new, force=True)
        workspace = frappe.get_doc("Workspace", new)
        workspace.title = workspace.label = new
        workspace.type = "Workspace"
        workspace.save()
    frappe.clear_cache()
