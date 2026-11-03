app_name = "my_work"
app_title = "My Work"
app_publisher = "My Work contributors"
app_description = "Personal work and approval center"
app_email = "admin@example.com"
app_license = "MIT"
required_apps = ["frappe"]
add_to_apps_screen = [{"name": "my_work", "logo": "/assets/my_work/images/my-work.svg", "title": "My Work", "route": "/app/my-work"}]

before_install = "my_work.install.prepare_modules"

after_migrate = "my_work.install.fix_workspace_route"

# Appended after the core wildcard workflow handler, preserving recorded actors.
doc_events = {"*": {"on_update": "my_work.workflow_support.synchronize", "on_update_after_submit": "my_work.workflow_support.synchronize", "on_cancel": "my_work.workflow_support.synchronize"}}
