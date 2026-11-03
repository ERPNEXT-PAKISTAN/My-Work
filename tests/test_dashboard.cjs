// DOM unit tests only. No browser or production session is controlled.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require(process.env.MY_WORK_JSDOM || 'jsdom');
const jquery = require(path.resolve(__dirname, '../../frappe/node_modules/jquery'));
const source = fs.readFileSync(path.resolve(__dirname, '../my_work/my_work/page/my_work/my_work.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

async function setup() {
    const dom = new JSDOM('<div id="page"><div class="layout-main-section"></div></div>', {runScripts:'outside-only',url:'https://example.test/desk/my-work'});
    const w = dom.window, $ = jquery(w), calls = [];
    w.$ = $;
    w.__ = (value, args=[]) => value.replace(/\{(\d+)\}/g, (_,i) => args[i] ?? '');
    const row = {doctype:'Expense Claim',name:'TEST-001',title:'Travel <img src=x onerror=alert(1)>',requested_by:'alice@example.test',owner:'alice@example.test',module:'HR',creation:'2026-11-03 09:00:00',modified:'2026-11-03 10:00:00',remarks:'Client visit reimbursement',amount_label:'Claim Amount',settlement:{label:'Against Advance',kind:'advance',advance_amount:15000,net_payable:0,advances:[{doctype:'Employee Advance',name:'ADV-TEST-1'}]},amount:15000,currency:'PKR',state:'Pending',priority:'Medium',views:['approvals'],actions:['Approve']};
    const dashboard={data:[row],total:1,summary:{approvals:1,requests:0,assigned:0,waiting:0},counts:{all:1,approvals:1},modules:['HR'],doctypes:['Expense Claim'],request_types:['Expense Claim']};
    const review={doctype:row.doctype,name:row.name,owner:row.owner,creation:row.creation,modified:row.modified,state:'Pending',fields:[{label:'Employee',value:'Alice'}],summary_fields:[{label:'Employee',value:'Alice',icon:'user'},{label:'Department',value:'Sales',icon:'building'},{label:'Claim Amount',value:15000,fieldtype:'Currency',icon:'money'},{label:'Expense Period',value:['2026-01-20','2026-01-22'],fieldtype:'Date Range',icon:'calendar'},{label:'Purpose',value:'Client meeting',icon:'file'}],currency:'PKR',can_print:true,next_states:['Approved'],tables:[{label:'Expense Details',columns:['expense_type','description','amount'],rows:[{expense_type:'Travel',description:'Taxi',amount:15000}],total:15000}],attachments:[{name:'FILE-1',label:'receipt.pdf',private:true}],attachments_note:'Permission checked',history:[],next_roles:['Accounts Manager'],actions:['Approve'],can_complete:false};
    w.frappe={pages:{'my-work':{}},ui:{make_app_page:()=>({main:$('.layout-main-section')})},require:(_,cb)=>cb(),utils:{escape_html:v=>String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;'),debounce:fn=>fn,get_form_link:(type,name)=>`/desk/${encodeURIComponent(type)}/${encodeURIComponent(name)}`},datetime:{str_to_user:v=>v},user_info:()=>({fullname:'Alice Example'}),unscrub:v=>v.replaceAll('_',' '),call:async args=>{calls.push(args);return {message:args.method.endsWith('.dashboard')?dashboard:args.method.endsWith('.review')?{data:review}:{data:{queued:false}}};},confirm:(_,cb)=>cb(),show_alert:()=>{}};
    w.eval(source);
    const wrapper=w.document.querySelector('#page');w.frappe.pages['my-work'].on_page_load(wrapper);await tick();
    return {dom,w,$,app:wrapper.my_work,calls,row,dashboard,review};
}

test('reference layout renders real counts, tabs, document and priority',async()=>{
    const {dom,$}=await setup();
    assert.equal($('.mw-card').length,4);assert.equal($('.mw-tabs [role=tab]').length,4);
    assert.equal($('.mw-card-approvals strong').text(),'1');assert.equal($('.mw-count[data-count=all]').text(),'1');
    assert.equal($('.mw-document strong').text(),'Expense Claim');assert.equal($('.mw-priority-badge').text(),'Medium');
    assert.equal($('.mw-description img').length,0);assert.equal($('.mw-description').text(),'Client visit reimbursement');
    assert.match($('.mw-amount').text(),/Rs 15,000/);assert.equal($('.mw-settlement-badge').text(),'Against Advance');
    assert.equal($('.mw-advance-link').text(),'ADV-TEST-1');
    dom.window.close();
});

test('priority filter reaches backend and changes the active view',async()=>{
    const {dom,$,calls}=await setup();
    $('.mw-priority').val('High').trigger('change');await tick();
    assert.equal(calls.at(-1).args.priority,'High');
    $('.mw-nav-item[data-view=requests]').trigger('click');await tick();
    assert.equal($('.mw-tab.is-active').attr('data-view'),'requests');
    dom.window.close();
});

test('review has four working tabs and only configured action labels',async()=>{
    const {dom,$,app,row}=await setup();await app.review(row);
    assert.equal($('.mw-drawer [role=tab]').length,4);
    assert.equal($('.mw-action').length,1);assert.equal($('.mw-action').text(),'Approve');
    assert.match($('.mw-workflow-steps .is-current strong').text(),/Accounts Manager/);
    assert.equal($('.mw-workflow-steps .is-next strong').text(),'Approved');
    assert.equal($('.mw-detail-card dl>div').length,4);
    assert.equal($('.mw-document-remarks h3').text(),'Remarks');
    assert.equal($('.mw-document-remarks p').text(),'Client meeting');
    assert.equal($('.mw-review-top .mw-document-remarks').length,0);
    assert.ok($('[data-panel=details]').children().toArray().indexOf($('.mw-document-remarks')[0])>$('[data-panel=details]').children().toArray().indexOf($('.mw-expense-card')[0]));
    assert.equal($('.mw-field-icon').length,4);
    assert.equal($('.mw-expense-table th').length,4);
    assert.equal($('.mw-expense-table tfoot .mw-number-cell').text(),'Rs 15,000');
    assert.match($('.mw-header-tools a').first().attr('href'),/^\/printview\?/);
    $('[data-review-tab=attachments]').trigger('click');
    assert.equal($('[data-panel=attachments]').prop('hidden'),false);assert.equal($('[data-panel=details]').prop('hidden'),true);
    assert.equal($('.mw-attachment strong').text(),'receipt.pdf');
    app.close();assert.equal($('.mw-drawer').prop('hidden'),true);dom.window.close();
});

test('document actions preserve an unposted comment without consuming it as action remarks',async()=>{
    const {dom,$,app,row,calls}=await setup();await app.review(row);
    $('.mw-remarks').val('Receipt checked');$('.mw-action').trigger('click');await tick();
    const mutation=calls.find(c=>c.method.endsWith('.act'));
    assert.equal(mutation.args.remarks,undefined);assert.equal(mutation.args.modified,row.modified);
    assert.equal($('.mw-remarks').val(),'Receipt checked');assert.equal(calls.some(c=>c.method.endsWith('.add_comment')),false);
    assert.equal(mutation.args.action,'Approve');dom.window.close();
});

test('empty results show a useful state without invented rows',async()=>{
    const {dom,$,app,dashboard}=await setup();dashboard.data=[];dashboard.total=0;await app.load();
    assert.equal($('.mw-results tbody tr').length,0);assert.match($('.mw-empty h3').text(),/caught up/);dom.window.close();
});

test('drafts across all modules is the default and claim status filtering reaches the server',async()=>{
    const {dom,$,app,calls,dashboard}=await setup();
    assert.equal(app.state.view,'drafts');
    assert.equal(app.state.module,'');assert.equal(app.state.doctype,'');
    assert.equal(calls[0].args.view,'drafts');
    dashboard.statuses=['Paid','Rejected'];await app.load();
    $('.mw-claim_status').val('Rejected').trigger('change');await tick();
    assert.equal(calls.at(-1).args.claim_status,'Rejected');dom.window.close();
});

test('rejected native claim shows only its current state in list and conflict details in review',async()=>{
    const {dom,$,app,row,review}=await setup();
    const info={document_status:'Submitted',workflow_state:'Approved',approval_status:'Rejected',claim_status:'Rejected',display_status:'Rejected',payment_status:'Not payable — rejected',variant:'danger',has_conflict:true,conflicts:['Workflow State and Expense Claim Approval Status disagree.'],claimed:4652,sanctioned:0,advance_applied:0,reimbursed:0,net_payable:0,outstanding:null};
    row.status_info=info;row.status='Rejected';row.flow_mode='standard';row.views=['rejected','all'];row.actions=[];
    review.status_info=info;review.state='Approved';review.actions=[];review.next_roles=[];review.next_states=[];
    review.workflow_notices=['Approve leaves Approved unchanged.'];
    await app.load();await app.review(row);
    assert.equal($('.mw-result-status').text(),'Rejected');assert.equal($('.mw-status-conflict-label').length,0);
    assert.equal($('.mw-state-badge').text(),'Rejected');assert.equal($('.mw-action').length,0);
    assert.equal($('.mw-status-overview>div').length,4);assert.match($('.mw-status-alert').text(),/statuses conflict/);
    assert.match($('.mw-financial-overview').text(),/SanctionedRs 0/);assert.match($('.mw-financial-overview').text(),/Not payable/);
    assert.equal($('.mw-workflow-notices').length,1);dom.window.close();
});

function editableTools() {
    return {fields:[{fieldname:'approval_status',label:'Approval Status',fieldtype:'Select',options:'Draft\nApproved\nRejected\nCancelled',value:'Draft',editable:true},{fieldname:'task',label:'Task',fieldtype:'Link',options:'Task',value:'TASK-1',editable:true},{fieldname:'project',label:'Project',fieldtype:'Link',options:'Project',value:'PROJECT-1',editable:true},{fieldname:'cost_center',label:'Cost Center',fieldtype:'Link',options:'Cost Center',value:'Main - TEST',editable:true},{fieldname:'status',label:'Status',value:'Draft',editable:false}],can_assign:true,can_share:true,can_tag:true,can_attach:true,can_edit_advances:true,advances:[{row_name:'ADVANCE-ROW-1',employee_advance:'ADV-TEST-1',allocated_amount:15000,unclaimed_amount:20000,can_remove:true}],assignments:[],shares:[],tags:['Travel'],employee:'EMP-1'};
}

test('native approval selector shows schema options and save enables configured workflow action',async()=>{
    const {dom,w,$,app,row,review,calls}=await setup();
    review.tools=editableTools();review.actions=[];w.frappe.msgprint=()=>{};
    const original=w.frappe.call;
    w.frappe.call=async args=>{if(args.method.endsWith('.update_claim')){review.tools.fields[0].value=JSON.parse(args.args.fields).approval_status;review.actions=['Review'];review.modified='new-version';}return original(args);};
    await app.review(row);
    assert.equal($('.mw-native-approval option').length,4);assert.equal($('.mw-native-approval').val(),'Draft');
    assert.equal($('.mw-native-approval option[value=Cancelled]').prop('disabled'),true);
    assert.match($('.mw-claim-context').text(),/TASK-1/);assert.match($('.mw-claim-context').text(),/PROJECT-1/);assert.match($('.mw-claim-context').text(),/Main - TEST/);
    $('.mw-native-approval').val('Approved').trigger('change');assert.equal(app.claimDirty,true);
    $('.mw-save-approval').trigger('click');await tick();await tick();
    const save=calls.find(c=>c.method.endsWith('.update_claim'));assert.deepEqual(JSON.parse(save.args.fields),{approval_status:'Approved'});
    assert.equal($('.mw-action').text(),'Review');assert.equal(app.claimDirty,false);
    $('.mw-action').trigger('click');await tick();
    const action=calls.find(c=>c.method.endsWith('.act'));assert.equal(action.args.modified,'new-version');assert.equal(action.args.action,'Review');dom.window.close();
});

test('unsaved decision blocks workflow mutation and submitted claims stay read only',async()=>{
    const {dom,w,$,app,row,review,calls}=await setup();review.tools=editableTools();w.frappe.msgprint=()=>{};
    await app.review(row);$('.mw-native-approval').val('Rejected').trigger('change');
    assert.equal($('.mw-action').prop('disabled'),true);app.confirmAction(review,'Approve',row);await tick();
    assert.equal(calls.filter(c=>c.method.endsWith('.act')).length,0);
    review.tools.fields.forEach(f=>f.editable=false);review.tools.can_edit_advances=false;review.tools.advances.forEach(a=>a.can_remove=false);
    await app.review(row);assert.equal($('.mw-native-approval').prop('disabled'),true);assert.equal($('.mw-save-approval').length,0);assert.equal($('.mw-remove-advance').length,0);dom.window.close();
});

test('advance removal calls the link endpoint without deleting the advance document',async()=>{
    const {dom,$,app,row,review,calls}=await setup();review.tools=editableTools();await app.review(row);
    $('.mw-remove-advance').trigger('click');await tick();
    const request=calls.find(c=>c.method.endsWith('.remove_advance'));assert.equal(request.args.row_name,'ADVANCE-ROW-1');
    assert.equal(calls.some(c=>c.method.includes('delete_doc')),false);dom.window.close();
});

test('assign share and tag dialogs call native-tool endpoints and upload defaults private',async()=>{
    const {dom,w,$,app,row,review,calls}=await setup();review.tools=editableTools();let dialog,upload;
    w.frappe.ui.Dialog=class {constructor(opts){this.options=opts;this.$wrapper=$('<div>');dialog=this;}show(){}hide(){}get_primary_btn(){return $('<button>');}};
    w.frappe.ui.FileUploader=class {constructor(opts){upload=opts;}};
    await app.review(row);$('.mw-tool-assign').trigger('click');await dialog.options.primary_action({users:['reviewer@example.test'],priority:'High'});
    assert.equal(JSON.parse(calls.find(c=>c.method.endsWith('.assign')).args.users)[0],'reviewer@example.test');
    $('.mw-tool-share').trigger('click');await dialog.options.primary_action({user:'reader@example.test',write:0,submit:0});
    assert.equal(calls.find(c=>c.method.endsWith('.share')).args.user,'reader@example.test');
    $('.mw-tool-tags').trigger('click');await dialog.options.primary_action({tag:'Checked'});
    assert.equal(calls.find(c=>c.method.endsWith('.tag')).args.tag,'Checked');
    $('.mw-tool-attachments').trigger('click');assert.equal($('[data-panel=attachments]').prop('hidden'),false);
    $('.mw-upload').trigger('click');assert.equal(upload.make_attachments_public,false);assert.equal(upload.docname,row.name);dom.window.close();
});

test('configured automatic workflow uses action buttons without manual decision saving',async()=>{
    const {dom,$,app,row,review}=await setup();review.tools=editableTools();
    review.tools.fields[0].editable=false;review.tools.fields[0].workflow_managed=true;
    review.actions=['Approve','Reject','Return'];await app.review(row);
    assert.equal($('.mw-native-approval').prop('disabled'),true);assert.equal($('.mw-save-approval').length,0);
    assert.equal($('.mw-action').length,3);assert.match($('.mw-approval-editor .mw-note').text(),/updated automatically/);
    assert.equal($('.mw-action-success').text(),'Approve');assert.equal($('.mw-action-danger').text(),'Reject');assert.equal($('.mw-action-neutral').text(),'Return');dom.window.close();
});

test('native flow shows actual submission progress without implying mandatory cancellation',async()=>{
    const {dom,$,app,row,review,calls}=await setup();
    Object.assign(review,{flow_mode:'standard',docstatus:0,state:'Draft',next_states:['Submitted'],next_roles:[],actions:['Submit']});
    await app.review(row);
    assert.equal($('.mw-workflow-card h3').text(),'Document Flow');
    assert.equal($('.mw-workflow-steps .is-current strong').text(),'Awaiting submission');
    assert.equal($('.mw-workflow-steps .is-next strong').text(),'Submitted');
    assert.doesNotMatch($('.mw-workflow-card').text(),/Cancelled/);
    assert.equal($('.mw-review-top-reference .mw-detail-card').length,1);
    assert.equal($('.mw-review-top-reference .mw-workflow-card').length,1);
    assert.equal($('.mw-action').text(),'Submit');
    $('.mw-action').trigger('click');await tick();
    const action=calls.find(c=>c.method.endsWith('.act'));
    assert.equal(action.args.action,'Submit');
    assert.equal(action.args.modified,review.modified);
    dom.window.close();
});

test('native submitted and cancelled states keep cancellation separate',async()=>{
    const {dom,$,app,row,review}=await setup();
    Object.assign(review,{flow_mode:'standard',docstatus:1,state:'Submitted',next_states:['Cancelled'],next_roles:[],actions:['Cancel']});
    await app.review(row);
    assert.equal($('.mw-workflow-steps .is-current strong').text(),'Submission complete');
    assert.equal($('.mw-action-danger').text(),'Cancel');
    Object.assign(review,{docstatus:2,state:'Cancelled',next_states:[],actions:[]});
    await app.review(row);
    assert.equal($('.mw-workflow-steps .is-current strong').text(),'Document cancelled');
    assert.equal($('.mw-action').length,0);
    dom.window.close();
});

test('Sales Order renders only the requested item columns and total safely',async()=>{
    const {dom,$,app,row,review}=await setup();
    Object.assign(review,{doctype:'Sales Order',flow_mode:'standard',docstatus:0,state:'Draft',business_status:'Draft',actions:['Submit'],additional_fields:[{fieldname:'project',label:'Project',fieldtype:'Link',value:'PROJ-A'}],tables:[{label:'Items',compact_items:true,columns:['item_code','uom','qty','rate','amount'],column_meta:{item_code:{label:'Item Code',fieldtype:'Link'},uom:{label:'UoM',fieldtype:'Link'},qty:{label:'Qty',fieldtype:'Float'},rate:{label:'Rate',fieldtype:'Currency',options:'currency'},amount:{label:'Amount',fieldtype:'Currency',options:'currency'}},rows:[{item_code:'ITEM <script>unsafe</script>',uom:'Nos',qty:'2',rate:'100',amount:'200'}],row_details:[[]],total:200}]});
    await app.review(row);
    assert.equal($('.mw-business-table th').text(),'Item CodeUoMQtyRateAmount');
    assert.equal($('.mw-business-table .mw-row-more').length,0);
    assert.equal($('.mw-business-table script').length,0);
    assert.match($('.mw-extra-fields').text(),/PROJ-A/);
    assert.match($('.mw-business-table tfoot').text(),/TotalRs 200/);
    dom.window.close();
});

test('Employee Checkin uses saved-record display with no submit action',async()=>{
    const {dom,$,app,row,review}=await setup();
    Object.assign(review,{doctype:'Employee Checkin',flow_mode:'record',docstatus:0,state:'Recorded',actions:[],next_states:[],business_status:null});
    await app.review(row);
    assert.equal($('.mw-workflow-card h3').text(),'Record');
    assert.equal($('.mw-action').length,0);
    assert.equal($('.mw-workflow-steps .is-current strong').text(),'Saved record');
    assert.equal($('.mw-workflow-steps .is-next').length,0);
    assert.doesNotMatch($('.mw-workflow-card').text(),/Submission|Cancelled/);
    dom.window.close();
});

test('document status filter is independent from business status',async()=>{
    const {dom,$,calls}=await setup();
    $('.mw-document_status').val('Submitted').trigger('change');await tick();
    assert.equal(calls.at(-1).args.document_status,'Submitted');
    assert.equal(calls.at(-1).args.claim_status,'');
    dom.window.close();
});

test('dedicated status column shows current native state without extra status categories',async()=>{
    const {dom,$,app,row}=await setup();
    row.status_summary={key:'approved',label:'Approved',variant:'success',document_label:'Submitted',document_variant:'info',explanation:'Approval is recorded. Payment is separate.'};
    row.status='Unpaid';row.status_info={payment_status:'Awaiting payment'};
    await app.load();
    assert.match($('.mw-results thead').text(),/Status \/ Next Action/);
    assert.equal($('.mw-status-cell .mw-current-system-state').text(),'Unpaid');
    assert.equal($('.mw-status-stack').length,0);
    assert.doesNotMatch($('.mw-status-cell').text(),/Awaiting payment|No separate approval|ApprovalApproved/);
    assert.equal($('.mw-description .mw-status-pill').length,0);
    dom.window.close();
});

test('standard-flow explanation is at the end rather than above the main details',async()=>{
    const {dom,$,app,row,review}=await setup();
    review.status_summary={key:'not_approved',label:'Not approved',variant:'warning',document_label:'Draft · Not submitted',document_variant:'warning',explanation:'An approval decision has not been recorded.'};
    review.flow_mode='standard';review.docstatus=0;review.state='Draft';review.business_status='Draft';
    await app.review(row);
    assert.equal($('.mw-state-badge').text(),'Not approved');
    assert.equal($('.mw-state-badge').hasClass('mw-tone-warning'),true);
    assert.equal($('.mw-decision-banner').length,0);
    assert.match($('.mw-review-flow-note').text(),/has not been recorded/);
    assert.equal($('[data-panel=details]').children().last().hasClass('mw-review-flow-note'),true);
    assert.equal($('.mw-review-top-reference .mw-workflow-card').length,1);
    assert.equal($('.mw-flow-details').length,0);
    dom.window.close();
});

test('approval filter reaches server without changing document status filter',async()=>{
    const {dom,$,calls}=await setup();
    $('.mw-decision').val('approved').trigger('change');await tick();
    assert.equal(calls.at(-1).args.decision,'approved');
    assert.equal(calls.at(-1).args.document_status,'');
    assert.match($('.mw-status-guide').text(),/Submitted = posted/);
    dom.window.close();
});

test('loading controls bound scope and reset pagination',async()=>{
    const {dom,$,calls,app}=await setup();
    assert.equal(calls[0].args.record_limit,100);assert.equal(calls[0].args.days,30);
    app.state.start=40;
    $('.mw-record_limit').val('50').trigger('change');await tick();
    assert.equal(calls.at(-1).args.record_limit,50);assert.equal(calls.at(-1).args.start,0);
    $('.mw-to_date').val('2025-12-31').trigger('change');await tick();
    assert.equal(calls.at(-1).args.to_date,'2025-12-31');
    $('.mw-days').val('0').trigger('change');await tick();
    assert.equal(calls.at(-1).args.days,0);assert.equal(calls.at(-1).args.to_date,'');
    $('.mw-page_length').val('50').trigger('change');await tick();
    assert.equal(calls.at(-1).args.page_length,50);
    dom.window.close();
});

test('loaded-record counts clearly identify the limit and date scope',async()=>{
    const {dom,$,app,dashboard}=await setup();
    dashboard.loading={candidates_checked:100,from_date:'2026-10-05',to_date:'2026-11-03',limited:true};
    await app.load();
    assert.match($('.mw-loading-scope').text(),/100 records checked/);
    assert.match($('.mw-loading-scope').text(),/loaded records only/);
    assert.match($('.mw-loading-scope').text(),/Loading limit reached/);
    dom.window.close();
});

test('main list avoids duplicate Draft action and permits versioned native Submit',async()=>{
    const {dom,$,app,row,calls}=await setup();
    Object.assign(row,{kind:'document',docstatus:0,flow_mode:'standard',actions:['Submit']});
    await app.load();
    assert.equal($('.mw-draft-button').length,0);
    assert.equal($('.mw-main-submit').text(),'Submit');
    $('.mw-main-submit').trigger('click');await tick();
    const request=calls.find(c=>c.method.endsWith('.act'));
    assert.equal(request.args.action,'Submit');assert.equal(request.args.modified,row.modified);
    row.flow_mode='workflow';await app.load();
    assert.equal($('.mw-main-submit').length,0);
    dom.window.close();
});

test('against account and party names render safely on the main list',async()=>{
    const {dom,$,app,row}=await setup();
    row.settlement={label:'Accounts',kind:'account',accounts:[{label:'Paid From',value:'Cash <unsafe> - A'},{label:'Paid To',value:'Bank - A'}],party_label:'Customer',party:'Customer A'};
    await app.load();
    assert.equal($('.mw-against-account').length,2);
    assert.match($('.mw-against-party').text(),/Customer A/);
    assert.equal($('.mw-against-account unsafe').length,0);
    dom.window.close();
});

test('current workflow state takes precedence and no unavailable placeholders are added',async()=>{
    const {dom,$,app,row}=await setup();
    Object.assign(row,{flow_mode:'workflow',state:'Pending Manager Review',status:'Draft',actions:['Approve','Return'],next_action:'Invented next action'});
    await app.load();
    assert.equal($('.mw-current-system-state').text(),'Pending Manager Review');
    assert.equal($('.mw-status-cell .mw-next-action').text(),'Available: Approve / Return');
    assert.doesNotMatch($('.mw-status-cell').text(),/Invented|Draft|No separate|Not available/);
    row.state=null;row.actions=[];await app.load();
    assert.equal($('.mw-status-cell').text(),'');
    dom.window.close();
});

test('extra controls are collapsed so the entry table follows the main filters',async()=>{
    const {dom,$}=await setup();
    assert.equal($('.mw-more-filters').prop('open'),false);
    assert.equal($('.mw-more-filters .mw-load-controls').length,1);
    assert.equal($('.mw-more-filters .mw-decision').length,1);
    assert.equal($('.mw-more-filters .mw-status-guide').length,1);
    assert.equal($('.mw-filters .mw-search').length,1);
    assert.equal($('.mw-entry-toolbar .mw-stage-switch').length,1);
    dom.window.close();
});

test('order review shows main fields and items before secondary information, with one status',async()=>{
    const {dom,$,app,row,review}=await setup();
    const explanation='This document uses the standard Draft → Submitted flow. Submitted records have been posted; no separate approval decision is recorded.';
    Object.assign(review,{doctype:'Sales Order',flow_mode:'standard',docstatus:1,state:'Submitted',business_status:'To Deliver and Bill',actions:[],summary_fields:[{fieldname:'customer',label:'Customer',value:'Customer A'},{fieldname:'transaction_date',label:'Date',fieldtype:'Date',value:'2026-11-03'},{fieldname:'delivery_date',label:'Due Date',fieldtype:'Date',value:'2026-11-10'},{fieldname:'status',label:'Status',value:'To Deliver and Bill'},{fieldname:'company',label:'Company',value:'Company A'},{fieldname:'grand_total',label:'Total Amount',fieldtype:'Currency',value:200}],additional_fields:[],status_summary:{key:'no_separate_approval',document_label:'Submitted · Final',document_variant:'info',label:'No separate approval',variant:'muted',explanation},tables:[{fieldname:'items',label:'Items',compact_items:true,columns:['item_code','uom','qty','rate','amount'],rows:[{item_code:'ITEM-A',uom:'Nos',qty:2,rate:100,amount:200}],total:200},{fieldname:'custom_coil_production',label:'Coil Production',columns:['qty'],rows:[{qty:100}]}]});
    await app.review(row);
    assert.equal($('.mw-detail-card dt').text(),'CustomerDateDue DateStatusCompanyTotal Amount');
    assert.equal($('.mw-state-badge').length,0);
    assert.equal($('.mw-detail-card .mw-status-pill').length,1);
    assert.equal($('.mw-decision-banner').length,0);
    assert.doesNotMatch($('[data-panel=details]').text(),/Coil Production/);
    const children=$('[data-panel=details]').children().toArray();
    assert.ok(children.indexOf($('.mw-review-top-reference')[0])<children.indexOf($('.mw-expense-card')[0]));
    assert.equal(children.at(-1).textContent,explanation);
    dom.window.close();
});

test('comments are available without document actions on Draft Submitted and Cancelled',async()=>{
    const {dom,w,$,app,row,review,calls}=await setup();
    const original=w.frappe.call;
    w.frappe.call=async args=>args.method.endsWith('.add_comment')?(calls.push(args),{message:{data:{name:'COMMENT-1',creation:'2026-11-03',owner:'alice@example.test',comment_by:'Alice',content:'<p>R&amp;D<br>&lt;literal&gt;</p>'}}}):original(args);
    for(const status of [0,1,2]){
        Object.assign(review,{docstatus:status,flow_mode:'standard',actions:[],can_complete:false});
        await app.review(row);
        assert.equal($('.mw-remarks').length,1);assert.equal($('.mw-remarks').prop('disabled'),false);
        $('.mw-remarks').val('R&D\n<literal>').trigger('input');
        assert.equal($('.mw-add-comment').prop('disabled'),false);
        await app.postComment(app.currentReview.doc);
        const request=calls.filter(c=>c.method.endsWith('.add_comment')).at(-1);
        assert.equal(request.args.content,'R&D\n<literal>');assert.equal(request.args.modified,undefined);
        assert.equal($('.mw-remarks').val(),'');assert.equal($('.mw-add-comment').prop('disabled'),true);
        assert.match($('.mw-comment-history').text(),/R&D\n<literal>/);
        assert.equal($('.mw-comment-history literal').length,0);
        assert.equal($('[data-panel=activity]').prop('hidden'),false);
    }
    assert.equal(calls.some(c=>c.method.endsWith('.act')),false);
    dom.window.close();
});

test('comment posting preserves unsaved approval edits and needs no clean document state',async()=>{
    const {dom,w,$,app,row,review,calls}=await setup();
    review.tools=editableTools();await app.review(row);
    $('.mw-native-approval').val('Approved').trigger('change');
    assert.equal(app.claimDirty,true);
    const original=w.frappe.call;
    w.frappe.call=async args=>args.method.endsWith('.add_comment')?(calls.push(args),{message:{data:{name:'COMMENT-1',creation:'2026-11-03',owner:'alice',content:'<p>A note</p>'}}}):original(args);
    $('.mw-remarks').val('A note').trigger('input');
    await app.postComment(app.currentReview.doc);
    assert.equal(app.claimDirty,true);assert.equal($('.mw-native-approval').val(),'Approved');
    assert.equal(calls.filter(c=>c.method.endsWith('.add_comment')).length,1);
    dom.window.close();
});

test('Document Flow shows the recorded submitter and date, not creator or last editor',async()=>{
    const {dom,$,app,row,review}=await setup();
    Object.assign(review,{flow_mode:'standard',docstatus:1,owner:'creator@example.test',state:'Submitted',actions:[],document_events:[{action:'Submitted',actor:'approver@example.test',actor_name:'Sara Approver',creation:'2026-02-02 11:45:00',source:'Version'}]});
    await app.review(row);
    assert.equal($('.mw-workflow-steps .mw-event-actor').text(),'Submitted by Sara Approver');
    assert.match($('.mw-workflow-steps .is-current').text(),/2026-02-02 11:45:00/);
    review.docstatus=2;review.state='Cancelled';review.document_events.push({action:'Cancelled',actor_name:'Manager',actor:'manager',creation:'2026-03-03 10:00:00'});
    await app.review(row);
    assert.match($('.mw-submission-event').text(),/Submitted by Sara Approver2026-02-02 11:45:00/);
    assert.equal($('.mw-workflow-steps .mw-event-actor').text(),'Cancelled by Manager');
    dom.window.close();
});

test('assignment review shows linked expense facts and lines while completion targets the ToDo',async()=>{
    const {dom,$,app,row,review,calls}=await setup();
    Object.assign(row,{doctype:'ToDo',name:'TODO-DEMO'});
    Object.assign(review,{doctype:'ToDo',name:'TODO-DEMO',flow_mode:'record',docstatus:0,state:'Open',business_status:'Open',actions:[],can_complete:true,summary_fields:[{fieldname:'status',label:'Status',value:'Open'}],tables:[],linked_document:{doctype:'Expense Claim',name:'DEMO-EXP-1',currency:'PKR',summary_fields:[{fieldname:'employee',label:'Employee',value:'Demo Employee'},{fieldname:'total_claimed_amount',label:'Claim Amount',fieldtype:'Currency',value:15000},{fieldname:'status',label:'Entry status',value:'Unpaid'}],remark_fields:[],tables:[{label:'Expense Details',columns:['expense_type','description','amount'],rows:[{expense_type:'Travel',description:'Demo customer trip',amount:15000}],total:15000}]}});
    await app.review(row);
    assert.match($('.mw-linked-entry').text(),/Demo Employee/);
    assert.match($('.mw-linked-facts').text(),/Rs 15,000/);
    assert.match($('.mw-linked-entry .mw-expense-card').text(),/Demo customer trip/);
    assert.equal($('.mw-action').length,0);assert.equal($('.mw-complete').length,1);
    $('.mw-complete').trigger('click');await tick();
    const completed=calls.find(c=>c.method.endsWith('.complete_task'));
    assert.equal(completed.args.name,'TODO-DEMO');
    assert.equal(calls.some(c=>c.method.endsWith('.act')),false);
    dom.window.close();
});

test('assignment rows show concise source facts and reference without exposing source actions',async()=>{
    const {dom,$,app,row}=await setup();
    Object.assign(row,{doctype:'ToDo',kind:'task',name:'TODO-DEMO',reference_type:'Expense Claim',reference_name:'DEMO-EXP-1',reference_summary:{fields:[{label:'Employee',value:'Demo <Employee>'},{label:'Entry status',value:'Unpaid'}]},actions:[]});
    await app.load();
    assert.match($('.mw-assigned-facts').text(),/EmployeeDemo <Employee>/);
    assert.equal($('.mw-assigned-facts Employee').length,0);
    assert.match($('.mw-linked').text(),/DEMO-EXP-1/);
    assert.equal($('.mw-main-submit').length,0);
    dom.window.close();
});

test('assignment description saves separately and blocks completion while unsaved',async()=>{
    const {dom,w,$,app,row,review,calls}=await setup();
    Object.assign(row,{doctype:'ToDo',name:'TODO-DEMO'});
    Object.assign(review,{doctype:'ToDo',name:'TODO-DEMO',flow_mode:'record',actions:[],can_complete:true,task_description:{value:'<p>Original instruction</p>',editable:true}});
    w.frappe.msgprint=()=>{};
    await app.review(row);
    assert.equal($('.mw-task-description').val(),'Original instruction');
    $('.mw-task-description').val('Updated instruction').trigger('input');
    assert.equal($('.mw-save-task-description').prop('disabled'),false);
    assert.equal($('.mw-complete').prop('disabled'),true);
    app.confirmAction(review,null,row);await tick();
    assert.equal(calls.some(c=>c.method.endsWith('.complete_task')),false);
    $('.mw-remarks').val('Unposted comment').trigger('input');
    $('.mw-save-task-description').trigger('click');await tick();await tick();
    const save=calls.find(c=>c.method.endsWith('.update_task_description'));
    assert.equal(save.args.name,'TODO-DEMO');assert.equal(save.args.modified,row.modified);
    assert.match(save.args.description,/Updated instruction/);
    assert.equal($('.mw-remarks').val(),'Unposted comment');
    assert.equal(calls.some(c=>c.method.endsWith('.act')||c.method.endsWith('.add_comment')),false);
    dom.window.close();
});

test('assignment description uses a standalone native rich text control when available',async()=>{
    const {dom,w,$,app,row,review}=await setup();
    let options,input;
    w.frappe.ui.form={make_control:opts=>{options=opts;input=$('<textarea>').appendTo(opts.parent);return {set_value:async value=>{input.val(value);opts.df.change();},get_value:()=>input.val()};}};
    Object.assign(review,{doctype:'ToDo',name:'TODO-DEMO',actions:[],flow_mode:'record',task_description:{value:'<p><strong>Keep formatting</strong></p>',editable:true}});
    await app.review(row);
    assert.equal(options.df.fieldtype,'Text Editor');assert.equal(options.doctype,undefined);
    assert.equal(input.val(),'<p><strong>Keep formatting</strong></p>');
    assert.equal($('.mw-save-task-description').prop('disabled'),true);
    input.val('<p>Changed text</p>');options.df.change();
    assert.equal($('.mw-save-task-description').prop('disabled'),false);
    $('.mw-reset-task-description').trigger('click');await tick();
    assert.equal(input.val(),'<p><strong>Keep formatting</strong></p>');
    assert.equal($('.mw-save-task-description').prop('disabled'),true);
    dom.window.close();
});
