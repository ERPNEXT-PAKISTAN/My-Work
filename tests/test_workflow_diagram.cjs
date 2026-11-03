const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const esbuild=require('../../frappe/node_modules/esbuild');

test('native Frappe builder renders all workflow branches with distinct action positions',()=>{
    const filename=process.env.MY_WORK_WORKFLOW_JSON||path.join(__dirname,'fixtures/workflow-layout.json');
    const {workflow,layout}=JSON.parse(fs.readFileSync(filename));
    const source=fs.readFileSync(path.resolve(__dirname,'../../frappe/frappe/public/js/workflow_builder/utils.js'),'utf8');
    const code=esbuild.transformSync(source,{loader:'js',format:'cjs'}).code;
    const module={exports:{}};new Function('module','exports',code)(module,module.exports);
    const nodes=module.exports.get_workflow_elements(workflow,layout);
    const states=nodes.filter(node=>node.type==='state');
    const actions=nodes.filter(node=>node.type==='action');
    assert.equal(states.length,7);assert.equal(actions.length,6);assert.equal(nodes.filter(node=>node.type==='transition').length,12);
    assert.equal(new Set(actions.map(node=>`${node.position.x},${node.position.y}`)).size,6);
    for(const node of actions){assert.ok(states.some(state=>state.id===node.data.from_id));assert.ok(states.some(state=>state.id===node.data.to_id));}
});
