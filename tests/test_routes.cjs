const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const app = path.resolve(__dirname, '..');

function router(workspaces) {
    const context = {frappe: {provide() {}, utils: {make_event_emitter() {}}, workspaces}, window: {addEventListener() {}}, $: () => ({on() {}})};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(app, '../frappe/frappe/public/js/frappe/router.js'), 'utf8'), context);
    return context.frappe.router;
}

test('reproduces Frappe workspace precedence over a same-name Desk Page', async () => {
    const actual = await router({'my-work': {name: 'My Work'}}).convert_to_standard_route(['my-work']);
    assert.equal(actual[0], 'Workspaces');
});

test('shipped workspace leaves dashboard route available to the Desk Page', async () => {
    const workspace = JSON.parse(fs.readFileSync(path.join(app, 'my_work/my_work/workspace/my_work_overview/my_work_overview.json')));
    assert.equal(workspace.type, 'Workspace');
    const slug = workspace.name.toLowerCase().replace(/ /g, '-');
    const routes = router({[slug]: {name: workspace.name}});
    const dashboard = await routes.convert_to_standard_route(['my-work']);
    assert.equal(dashboard.length, 1);
    assert.equal(dashboard[0], 'my-work');
    const overview = await routes.convert_to_standard_route([slug]);
    assert.equal(overview[0], 'Workspaces');
    assert.equal(overview[1], workspace.name);
});
