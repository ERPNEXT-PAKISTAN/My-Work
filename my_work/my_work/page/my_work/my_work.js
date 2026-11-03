frappe.pages['my-work'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __('My Work'), single_column: true});
    $(wrapper).addClass('my-work-page');
    frappe.require('/assets/my_work/css/my_work.css', () => { wrapper.my_work = new MyWork(page); });
};

class MyWork {
    constructor(page) {
        this.page = page;
        this.state = {view: 'drafts', search: '', module: '', doctype: '', priority: '', claim_status: '', approval_status: '', document_status: '', decision: '', record_limit: 100, days: 30, from_date: '', to_date: '', start: 0, page_length: 20, sort: 'creation', direction: 'desc'};
        this.labels = {all: __('All Work'), approvals: __('My Approvals'), requests: __('My Requests'), assigned: __('Assigned to Me'), waiting: __('Waiting on Others'), drafts: __('Draft — Not Final'), submitted: __('Submitted — Final'), rejected: __('Rejected'), completed: __('Completed'), cancelled: __('Cancelled')};
        this.icons = {all:'grid', approvals:'check', requests:'send', assigned:'clipboard', waiting:'clock', drafts:'file', submitted:'check-circle', rejected:'x', completed:'check-circle', cancelled:'x'};
        this.root = $('<div class="mw-root"></div>').appendTo(page.main);
        this.root.html(`<div class="mw-shell"><aside class="mw-sidebar" aria-label="${__('Work navigation')}"><a class="mw-home" href="/desk">${this.icon('home')}${__('Home')}</a><div class="mw-brand">${this.icon('clipboard')}<strong>${__('My Work')}</strong><button class="mw-collapse" aria-label="${__('Toggle navigation')}" aria-expanded="true">${this.icon('menu')}</button></div><nav class="mw-nav">${Object.entries(this.labels).map(([key,label]) => `<button data-view="${key}" class="mw-nav-item">${this.icon(this.icons[key])}<span class="mw-nav-label">${label}</span><span class="mw-count" data-count="${key}"></span></button>`).join('')}<div class="mw-nav-divider"></div><h3>${__('Apps')}</h3><div class="mw-modules"></div></nav></aside>
        <main class="mw-content"><header class="mw-heading"><div><h1>${__('My Work')}</h1><p>${__('Your approvals, requests, tasks and ERP work in one place.')}</p></div><div class="mw-heading-actions"><button class="mw-refresh mw-icon-button" aria-label="${__('Refresh work')}" title="${__('Refresh')}">${this.icon('refresh')}</button><button class="mw-new btn mw-primary">${this.icon('plus')}${__('New Request')}${this.icon('chevron-down')}</button></div></header><div class="mw-cards"></div><nav class="mw-stage-switch" aria-label="${__('Document submission stage')}"><button data-view="drafts">${this.icon('file')}<strong>${__('Draft — Not Final')}</strong><span data-count="drafts"></span></button><button data-view="submitted">${this.icon('check-circle')}<strong>${__('Submitted — Final')}</strong><span data-count="submitted"></span></button></nav>
        <section class="mw-inbox" aria-label="${__('Work inbox')}"><div class="mw-tabs" role="tablist" aria-label="${__('Work views')}"></div><div class="mw-filters"><label class="mw-search-field">${this.icon('search')}<input type="search" class="form-control mw-search" placeholder="${__('Search approvals…')}" aria-label="${__('Search work')}"></label><select class="form-control mw-module" aria-label="${__('Module')}"></select><select class="form-control mw-priority" aria-label="${__('Priority')}"><option value="">${__('All Priorities')}</option>${['High','Medium','Low','Urgent'].map(p => `<option>${p}</option>`).join('')}</select><select class="form-control mw-sort" aria-label="${__('Sort by')}"><option value="creation">${__('Date: Newest')}</option><option value="modified">${__('Last Activity')}</option><option value="name">${__('Document Number')}</option><option value="priority">${__('Priority: Highest')}</option></select><select class="form-control mw-doctype" aria-label="${__('Document type')}"></select><select class="form-control mw-decision" aria-label="${__('Approval decision')}"><option value="">${__('All Approval Decisions')}</option>${[['not_approved','Not approved / Pending'],['approved','Approved'],['rejected','Rejected'],['no_separate_approval','No separate approval'],['conflict','Status conflict'],['cancelled','Cancelled'],['workflow','Other workflow state'],['unavailable','Approval not visible']].map(([value,label])=>`<option value="${value}">${__(label)}</option>`).join('')}</select><select class="form-control mw-document_status" aria-label="${__('Document Status')}"><option value="">${__('All Document Statuses')}</option>${['Draft','Submitted','Cancelled','Recorded'].map(value=>`<option value="${value}">${this.esc(__(this.stageLabel(value)))}</option>`).join('')}</select><select class="form-control mw-claim_status" aria-label="${__('Business or task status')}"></select><select class="form-control mw-approval_status" aria-label="${__('Native Approval Status')}"></select></div><div class="mw-load-controls"><label>${__('Load latest')}<select class="form-control mw-record_limit" aria-label="${__('Record loading limit')}">${[50,100,200,500].map(n=>`<option value="${n}" ${n===100?'selected':''}>${n} ${__('records')}</option>`).join('')}</select></label><label>${__('Updated within')}<select class="form-control mw-days" aria-label="${__('Updated date range')}">${[[7,'Last 7 days'],[30,'Last 30 days'],[90,'Last 90 days'],[365,'Last year'],[0,'All dates']].map(([v,label])=>`<option value="${v}" ${v===30?'selected':''}>${__(label)}</option>`).join('')}</select></label><label>${__('From (updated)')}<input type="date" class="form-control mw-from_date" aria-label="${__('Updated from date')}"></label><label>${__('To (updated)')}<input type="date" class="form-control mw-to_date" aria-label="${__('Updated to date')}"></label><label>${__('Per page')}<select class="form-control mw-page_length" aria-label="${__('Rows per page')}">${[20,50,100].map(n=>`<option value="${n}">${n}</option>`).join('')}</select></label></div><p class="mw-loading-scope" aria-live="polite"></p><div class="mw-status-guide"><strong>${__('Understand statuses')}</strong><span>${__('Draft = not submitted. Approved = approval decision saved. Submitted = posted. Paid = payment completed.')}</span><span>${__('Final means submitted. Approval, payment and fulfilment are separate statuses.')}</span></div><div class="mw-view-context"><span class="mw-view-title"></span><span class="mw-total"></span></div><div class="mw-results" aria-live="polite"></div><div class="mw-pagination"><span class="mw-page-info"></span><div><button class="mw-prev mw-icon-button" aria-label="${__('Previous page')}">${this.icon('chevron-left')}</button><button class="mw-next mw-icon-button" aria-label="${__('Next page')}">${this.icon('chevron-right')}</button></div></div></section><p class="mw-footnote">${this.icon('shield')}${__('Only work you have permission to access is shown. Actions follow your configured workflow or the standard document flow.')}</p></main></div><div class="mw-overlay" hidden></div><section class="mw-drawer" role="dialog" aria-modal="true" aria-labelledby="mw-review-title" hidden></section>`);
        this.simplifyHome();
        this.root.on('click', '[data-view]', e => {this.state.view=e.currentTarget.dataset.view;if(['drafts','submitted'].includes(this.state.view)){this.state.document_status='';this.root.find('.mw-document_status').val('');}this.state.start=0;this.load();});
        this.root.on('click', '[data-module]', e => {this.state.module=e.currentTarget.dataset.module;this.state.start=0;this.load();});
        this.root.find('.mw-refresh').on('click', () => this.load());
        this.root.find('.mw-new').on('click', () => this.newRequest());
        this.root.find('.mw-collapse').on('click', e => {const collapsed=this.root.find('.mw-shell').toggleClass('mw-nav-collapsed').hasClass('mw-nav-collapsed');$(e.currentTarget).attr('aria-expanded',String(!collapsed));});
        this.root.find('.mw-search').on('input', frappe.utils.debounce(e => {this.state.search=e.target.value;this.state.start=0;this.load();},300));
        for (const key of ['module','priority','doctype','sort','claim_status','approval_status','document_status','decision','record_limit','days','from_date','to_date','page_length']) this.root.find(`.mw-${key}`).on('change', e => {this.state[key]=['record_limit','days','page_length'].includes(key)?Number(e.target.value):e.target.value;if(key==='days'){this.state.from_date='';this.state.to_date='';this.root.find('.mw-from_date,.mw-to_date').val('');}this.state.start=0;this.load();});
        this.root.find('.mw-prev').on('click', () => {this.state.start=Math.max(0,this.state.start-this.state.page_length);this.load();});
        this.root.find('.mw-next').on('click', () => {this.state.start+=this.state.page_length;this.load();});
        this.root.on('click','[data-review]',e=>{this.returnFocus=e.currentTarget;this.review(this.items[Number(e.currentTarget.dataset.review)]);});
        this.root.on('click','[data-main-submit]',e=>{e.preventDefault();this.submitFromList(this.items[Number(e.currentTarget.dataset.mainSubmit)],$(e.currentTarget));});
        this.root.find('.mw-overlay').on('click',()=>this.close());
        this.root.on('click','.mw-close',()=>this.close());
        this.root.on('click','[data-review-tab]',e=>this.reviewTab(e.currentTarget.dataset.reviewTab));
        this.root.on('keydown','[role="tablist"]',e=>{
            if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
            const tabs=$(e.currentTarget).find('[role="tab"]').toArray();let i=tabs.indexOf(document.activeElement);if(i<0)return;e.preventDefault();
            i=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[i].click();tabs[i].focus();
        });
        this.root.on('keydown','.mw-drawer',e=>{
            if(e.key==='Escape')this.close();
            if(e.key==='Tab'){const els=this.root.find('.mw-drawer').find('button,a,input,select,textarea').filter(':visible:not(:disabled)').toArray();const first=els[0],last=els[els.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
        });
        this.load();
    }
    simplifyHome(){
        const filters=this.root.find('.mw-filters');
        const advanced=$(`<details class="mw-more-filters"><summary>${__('More filters & loading')}</summary><div class="mw-more-filter-content"><div class="mw-extra-filter-grid"></div></div></details>`);
        const extra=advanced.find('.mw-extra-filter-grid');
        for(const [key,label] of [['decision','Approval decision'],['document_status','Document status'],['claim_status','Business status'],['approval_status','Native approval status']]){
            const field=filters.find(`.mw-${key}`);
            if(field.length)$('<label>').append($('<span>').text(__(label)),field).appendTo(extra);
        }
        advanced.find('.mw-more-filter-content').append(this.root.find('.mw-load-controls'));
        const help=$(`<details class="mw-status-help"><summary>${__('Status guide')}</summary></details>`);
        help.append(this.root.find('.mw-status-guide'));advanced.find('.mw-more-filter-content').append(help);
        const toolbar=$('<div class="mw-entry-toolbar"></div>');
        toolbar.append(this.root.find('.mw-stage-switch'),advanced);
        filters.after(toolbar);
        this.root.find('.mw-loading-scope').insertBefore(this.root.find('.mw-pagination'));
    }
    icon(name) {
        const paths={user:'M20 21v-2a6 6 0 0 0-6-6h-4a6 6 0 0 0-6 6v2zM16 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0',money:'M3 6h18v12H3zM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0M5 9h1M18 15h1',calendar:'M4 5h16v17H4zM8 2v6M16 2v6M4 10h16M8 14h1M12 14h1M8 18h1M12 18h1',print:'M6 9V2h12v7M6 18H3V9h18v9h-3M6 14h12v8H6zM17 11h1',home:'M3 10l9-7 9 7M5 9v12h5v-7h4v7h5V9',clipboard:'M9 5H5v16h14V5h-4M9 3h6v4H9zM8 13l3 3 5-6',grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',check:'M5 12l4 4L19 6',send:'M22 2L9 15M22 2l-7 20-6-7-7-6z',clock:'M12 7v5l4 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',file:'M14 2H5v20h14V7zM14 2v6h5M8 12h8M8 16h6',x:'M6 6l12 12M6 18L18 6','check-circle':'M8 12l3 3 5-6M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',menu:'M4 6h16M4 12h16M4 18h16',refresh:'M20 7v5h-5M4 17v-5h5M5 7a8 8 0 0 1 14-1l1 6M4 12l1 6a8 8 0 0 0 14-1',plus:'M12 5v14M5 12h14','chevron-down':'M6 9l6 6 6-6','chevron-left':'M15 6l-6 6 6 6','chevron-right':'M9 6l6 6-6 6',search:'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',shield:'M12 2l8 4v6c0 6-8 10-8 10S4 18 4 12V6zM8 12l3 3 5-6',users:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M13 3a4 4 0 0 1 0 8M22 21v-2a4 4 0 0 0-3-4M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',box:'M3 7l9-5 9 5v10l-9 5-9-5zM3 7l9 5 9-5M12 12v10',building:'M4 22V4l8-2v20M12 8h8v14M2 22h20M7 7h2M7 11h2M7 15h2M15 12h2M15 16h2',link:'M10 13l4-4M8 16l-2 2a4 4 0 0 1-6-6l4-4M16 8l2-2a4 4 0 0 1 6 6l-4 4',paperclip:'M21 11l-9 9a6 6 0 0 1-9-9L13 1a4 4 0 0 1 6 6L9 17a2 2 0 0 1-3-3l9-9',external:'M14 3h7v7M10 14L21 3M21 14v7H3V3h7',arrow:'M19 12H5M12 5l-7 7 7 7'};
        return `<svg class="mw-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]||paths.box}"/></svg>`;
    }
    esc(value){return frappe.utils.escape_html(String(value??''));}
    date(value){return value?this.esc(frappe.datetime.str_to_user(String(value).split(' ')[0])):'—';}
    person(user){return (frappe.user_info?.(user)||{}).fullname||user||__('Not available');}
    initials(user){return this.person(user).split('@')[0].split(/[\s._-]+/).filter(Boolean).slice(0,2).map(s=>s[0]).join('').toUpperCase();}
    amount(row){return this.money(row.amount,row.currency);}
    async api(method,args={}){return (await frappe.call({method:`my_work.api.${method}`,args})).message;}
    async load(){
        const sequence=this.sequence=(this.sequence||0)+1;
        this.root.find('.mw-results').attr('aria-busy','true');this.root.find('.mw-refresh').prop('disabled',true);
        try{
            const data=await this.api('dashboard',this.state);if(sequence!==this.sequence)return;
            this.items=data.data;this.requestTypes=data.request_types||[];
            const keys=['approvals','requests','assigned','waiting'];
            this.root.find('.mw-cards').html(keys.map((key,i)=>`<button data-view="${key}" class="mw-card mw-card-${key} ${this.state.view===key?'is-active':''}"><span class="mw-card-icon">${this.icon(this.icons[key])}</span><span class="mw-card-text"><strong>${data.summary[key]}</strong><span>${this.labels[key]}</span></span>${this.icon('chevron-right')}</button>`).join(''));
            this.root.find('.mw-tabs').html(keys.map(key=>`<button id="mw-tab-${key}" data-view="${key}" role="tab" aria-selected="${this.state.view===key}" tabindex="${this.state.view===key?0:-1}" class="mw-tab ${this.state.view===key?'is-active':''}">${this.labels[key]}<span>${data.summary[key]}</span></button>`).join(''));
            // Non-card views retain keyboard access to the primary inbox tabs.
            if(!keys.includes(this.state.view))this.root.find('.mw-tab').first().attr('tabindex',0);
            this.root.find('.mw-stage-switch [data-view]').each((_,el)=>$(el).toggleClass('is-active',el.dataset.view===this.state.view).attr('aria-pressed',String(el.dataset.view===this.state.view)));
            this.root.find('.mw-nav-item[data-view]').removeClass('is-active').filter(`[data-view="${this.state.view}"]`).addClass('is-active');
            this.root.find('[data-count]').each((_,el)=>{const key=el.dataset.count;$(el).text(data.counts?.[key]??data.summary[key]??'');});
            const moduleIcon=m=>/account|buy|sell/i.test(m)?'building':/hr|human/i.test(m)?'users':'box';
            this.root.find('.mw-modules').html([['',__('All Modules')],...data.modules.map(m=>[m,m])].map(([value,label])=>`<button class="mw-nav-item ${value===this.state.module?'is-active':''}" data-module="${this.esc(value)}">${this.icon(moduleIcon(label))}<span class="mw-nav-label">${this.esc(label)}</span></button>`).join(''));
            this.root.find('.mw-module').html(`<option value="">${__('All Modules')}</option>${data.modules.map(m=>`<option value="${this.esc(m)}">${this.esc(m)}</option>`).join('')}`).val(this.state.module);
            this.root.find('.mw-doctype').html(`<option value="">${__('All Document Types')}</option>${data.doctypes.map(d=>`<option value="${this.esc(d)}">${this.esc(d)}</option>`).join('')}`).val(this.state.doctype);
            this.root.find('.mw-claim_status').html(`<option value="">${__('All Business / Task Statuses')}</option>${(data.statuses||[]).map(value=>`<option value="${this.esc(value)}">${this.esc(__(value))}</option>`).join('')}`).val(this.state.claim_status);
            this.root.find('.mw-approval_status').html(`<option value="">${__('All Approval Statuses')}</option>${(data.approval_statuses||[]).map(value=>`<option value="${this.esc(value)}">${this.esc(__(value))}</option>`).join('')}`).val(this.state.approval_status);
            this.root.find('.mw-view-title').text(this.labels[this.state.view]);this.root.find('.mw-total').text(__('{0} loaded items',[data.total]));
            if(data.loading){
                const scope=data.loading;
                this.root.find('.mw-loading-scope').text(__('{0} records checked · {1} to {2} · Counts/search for loaded records only. {3}',[scope.candidates_checked,scope.from_date||__('all dates'),scope.to_date,scope.limited?__('Loading limit reached.'):'' ])).attr('title',__('Open More filters & loading to change the limit or date range.'));
                this.root.find('.mw-cards button,.mw-tab,[data-count]').attr('title',__('Count within the current loading scope'));
            }
            this.root.find('.mw-search').attr('placeholder',__('Search {0}…',[this.labels[this.state.view].toLowerCase()]));
            this.root.find('.mw-new').prop('disabled',!this.requestTypes.length).attr('title',this.requestTypes.length?__('Create a new request'):__('No documents are available for you to create'));
            this.root.find('.mw-results').html(this.items.length?this.table():`<div class="mw-empty"><span>${this.icon(this.icons[this.state.view])}</span><h3>${__('You’re all caught up')}</h3><p>${__('No work matches this view. Try another tab or change your filters.')}</p></div>`);
            this.root.find('.mw-prev').prop('disabled',!this.state.start);this.root.find('.mw-next').prop('disabled',this.state.start+this.state.page_length>=data.total);
            this.root.find('.mw-page-info').text(data.total?__('Showing {0}–{1} of {2} loaded items',[this.state.start+1,Math.min(this.state.start+this.state.page_length,data.total),data.total]):__('No items to display'));
        }catch(error){if(sequence===this.sequence)this.root.find('.mw-results').html(`<div class="mw-empty"><h3>${__('Could not load your work')}</h3><p>${__('Use Refresh to try again.')}</p></div>`);}
        finally{if(sequence===this.sequence){this.root.find('.mw-results').attr('aria-busy','false');this.root.find('.mw-refresh').prop('disabled',false);}}
    }
    table(){return `<div class="mw-table-scroll"><table class="mw-table"><thead><tr>${[__('Document'),__('Remarks / Details'),__('Requested By'),__('Amount / Value'),__('Against Account / Party'),__('Requested On'),__('Priority'),__('Status / Next Action'),__('Action')].map(t=>`<th scope="col">${t}</th>`).join('')}</tr></thead><tbody>${this.items.map((r,i)=>`<tr><td><div class="mw-document"><span class="mw-file-icon">${this.icon('file')}</span><div><strong>${this.esc(r.doctype)}</strong><span class="mw-doc-id">${this.esc(r.name)}</span></div></div></td><td><div class="mw-description" title="${this.esc(r.remarks??r.title)}">${r.remarks!=null?(this.esc(r.remarks)||`<span class="mw-muted">${__('No remarks')}</span>`):this.esc(r.title)}</div>${this.assignmentBrief(r)}${r.reference_type&&r.reference_name?`<a class="mw-linked" href="${frappe.utils.get_form_link(r.reference_type,r.reference_name)}">${this.esc(r.reference_type)} ${this.esc(r.reference_name)}</a>`:''}</td><td><div class="mw-person"><span class="mw-avatar mw-avatar-${i%4}">${this.esc(this.initials(r.requested_by))}</span><div><span>${this.esc(this.person(r.requested_by))}</span><small>${this.esc(r.module)}${r.requested_by!==r.owner?` · ${__('Created by')} ${this.esc(this.person(r.owner))}`:''}</small></div></div></td><td class="mw-amount">${this.amount(r)}${r.amount_label?`<small>${this.esc(__(r.amount_label))}</small>`:''}</td><td class="mw-settlement-cell">${this.settlementHTML(r.settlement,r.currency)}</td><td class="mw-date">${this.date(r.creation)}${r.due_date?`<small>${__('Due')}: ${this.date(r.due_date)}</small>`:''}</td><td>${r.priority?`<span class="mw-priority-badge mw-priority-${this.esc(r.priority.toLowerCase())}">${this.esc(__(r.priority))}</span>`:'<span class="mw-muted">—</span>'}</td><td class="mw-status-cell">${this.statusBadge(r)}${this.nextActionHTML(r)}</td><td><div class="mw-main-actions">${r.flow_mode==='standard'&&r.docstatus===0&&r.actions.includes('Submit')?`<button class="btn mw-main-submit" data-main-submit="${i}">${this.icon('check')}${__('Submit')}</button>`:''}<button class="mw-review-button" data-review="${i}">${__('Review')}${this.icon('chevron-right')}</button></div></td></tr>`).join('')}</tbody></table></div>`;}
    assignmentBrief(row){
        const fields=row.reference_summary?.fields||[];
        return fields.length?`<table class="mw-assigned-facts" aria-label="${__('Linked entry summary')}"><tbody>${fields.map(f=>`<tr><th>${this.esc(__(f.label))}</th><td>${this.esc(f.value)}</td></tr>`).join('')}</tbody></table>`:'';
    }
    linkedEntry(d){
        const entry=d.linked_document;if(!entry)return '';
        const fields=(entry.summary_fields||[]).filter(f=>!this.isRemarksField(f));
        return `<section class="mw-linked-entry"><div class="mw-section-heading"><h3>${__('Assigned document')}</h3>${d.business_status||d.state?`<span class="mw-linked-task-state">${__('Assignment')}: ${this.statusPill(d.business_status||d.state)}</span>`:''}<a href="${this.esc(frappe.utils.get_form_link(entry.doctype,entry.name))}">${this.esc(entry.doctype)} ${this.esc(entry.name)} ${this.icon('external')}</a></div><table class="mw-linked-facts"><tbody>${fields.map(f=>`<tr><th>${this.esc(__(f.label))}</th><td>${f.fieldtype==='Date Range'?(f.value?.length?f.value.map(value=>this.shortDate(value)).filter((value,i,array)=>i===0||value!==array[0]).join(' – '):'—'):this.tableValue(f.value,{fieldtype:f.fieldtype,options:f.options||'currency',fieldname:f.fieldname},entry.currency)}</td></tr>`).join('')}</tbody></table>${this.expenseTables(entry)}${this.reviewRemarks(entry)}</section>`;
    }
    submitFromList(row,button){
        if(!this.ensureClean()||!row||row.flow_mode!=='standard'||!row.actions.includes('Submit'))return;
        frappe.confirm(__('Submit {0}? The document will become final (submitted). Normal document validations apply.',[this.esc(row.name)]),async()=>{
            button.prop('disabled',true);
            try{await this.api('act',{doctype:row.doctype,name:row.name,action:'Submit',modified:row.modified});frappe.show_alert({message:__('Document submitted'),indicator:'green'});await this.load();}
            catch(error){button.prop('disabled',false);}
        });
    }
    newRequest(){
        if(!this.requestTypes?.length)return;
        const dialog=new frappe.ui.Dialog({title:__('New Request'),fields:[{fieldname:'request_type',label:__('Request Type'),fieldtype:'Select',options:this.requestTypes,default:this.requestTypes[0],reqd:1}],primary_action_label:__('Create Request'),primary_action:values=>{dialog.hide();frappe.new_doc(values.request_type);}});dialog.show();
    }
    async review(row){
        if(!row)return;this.claimDirty=false;this.taskDescriptionDirty=false;const token=this.reviewSequence=(this.reviewSequence||0)+1;const drawer=this.root.find('.mw-drawer');
        drawer.prop('hidden',false).html(`<header><button class="mw-close mw-icon-button" aria-label="${__('Close review')}">${this.icon('arrow')}</button><h2 id="mw-review-title">${__('Loading request…')}</h2></header><div class="mw-drawer-body"><div class="mw-loading"></div></div>`);this.root.find('.mw-overlay').prop('hidden',false);drawer.find('.mw-close').trigger('focus');
        try{
            const {data:d}=await this.api('review',{doctype:row.doctype,name:row.name});if(token!==this.reviewSequence)return;
            const history=this.timeline(d);this.currentReview={doc:d,row};
            drawer.html(`<div class="mw-review-breadcrumb"><span>${__('My Work')}</span>${this.icon('chevron-right')}<strong>${this.esc(d.doctype)} ${this.esc(d.name)}</strong></div><header><button class="mw-close mw-icon-button" aria-label="${__('Close review')}">${this.icon('arrow')}</button><h2 id="mw-review-title">${this.esc(d.doctype)} <span>${this.esc(d.name)}</span></h2>${this.reviewHeaderStatus(d,row)}<div class="mw-header-tools">${d.can_print?`<a class="mw-icon-button" href="/printview?doctype=${encodeURIComponent(d.doctype)}&name=${encodeURIComponent(d.name)}&trigger_print=1" target="_blank" rel="noopener" aria-label="${__('Print document')}" title="${__('Print document')}">${this.icon('print')}</a>`:''}<a class="mw-icon-button" href="${frappe.utils.get_form_link(d.doctype,d.name)}" aria-label="${__('Open document')}" title="${__('Open document')}">${this.icon('external')}</a></div></header>${this.documentToolbar(d)}
            <div class="mw-review-tabs" role="tablist" aria-label="${__('Review sections')}">${[['details',__('Details')],['attachments',__('Attachments ({0})',[d.attachments.length])],['history',__('Approval History')],['activity',__('Activity')]].map(([key,label])=>`<button id="mw-review-tab-${key}" role="tab" aria-selected="${key==='details'}" aria-controls="mw-review-panel-${key}" tabindex="${key==='details'?0:-1}" data-review-tab="${key}" class="${key==='details'?'is-active':''}">${label}</button>`).join('')}</div><div class="mw-drawer-body">
            <section id="mw-review-panel-details" role="tabpanel" aria-labelledby="mw-review-tab-details" class="mw-review-panel" data-panel="details">${this.reviewDetails(d,row)}</section>
            <section id="mw-review-panel-attachments" role="tabpanel" aria-labelledby="mw-review-tab-attachments" class="mw-review-panel" data-panel="attachments" hidden><div class="mw-section-heading"><h3>${__('Attachments')}</h3>${d.tools?.can_attach?`<button class="btn btn-default btn-sm mw-upload">${this.icon('plus')}${__('Upload attachment')}</button>`:''}</div>${d.attachments.length?d.attachments.map(f=>`<div class="mw-attachment"><span class="mw-file-icon">${this.icon('paperclip')}</span><span><a href="${frappe.utils.get_form_link('File',f.name)}"><strong>${this.esc(f.label)}</strong></a><small>${f.private?__('Private attachment'):__('Attachment')}</small></span>${f.can_delete&&d.tools?.can_attach?`<button class="mw-icon-button mw-remove-attachment" data-file="${this.esc(f.name)}" aria-label="${__('Remove attachment')}">${this.icon('x')}</button>`:''}</div>`).join(''):`<div class="mw-empty">${this.icon('paperclip')}<p>${__('No accessible attachments')}</p></div>`}<p class="mw-note">${this.esc(d.attachments_note)}</p></section>
            <section id="mw-review-panel-history" role="tabpanel" aria-labelledby="mw-review-tab-history" class="mw-review-panel" data-panel="history" hidden><h3>${__('Approval History')}</h3>${history}</section>
            <section id="mw-review-panel-activity" role="tabpanel" aria-labelledby="mw-review-tab-activity" class="mw-review-panel" data-panel="activity" hidden><h3>${__('Activity')}</h3><div class="mw-activity"><strong>${__('Last document update')}</strong><small>${this.esc(frappe.datetime.str_to_user(d.modified))}</small></div><div class="mw-comment-history">${this.activityList(d)}</div>${history}</section></div>
            <footer><div class="mw-comment-composer"><label class="mw-remarks-label">${d.doctype==='ToDo'?__('Assignment comment (optional)'):__('Remarks / Comment (optional)')}<textarea class="form-control mw-remarks" maxlength="10000" rows="2" placeholder="${__('Write a comment…')}" aria-label="${__('Document comment')}"></textarea></label><div class="mw-comment-controls"><button class="btn mw-primary mw-add-comment" disabled>${__('Add Comment')}</button><small>${__('Comments do not change document status.')}</small></div></div><div class="mw-action-buttons">${d.flow_mode&&d.doctype!=='Expense Claim'?`<a class="btn btn-default mw-open-native" href="${frappe.utils.get_form_link(d.doctype,d.name)}">${d.tools?.can_edit?__('Edit document'):__('Open document')}</a>`:''}${d.actions.map((a,i)=>`<button class="btn mw-action ${this.actionClass(a)}" data-action-index="${i}">${this.icon(/reject|decline|cancel/i.test(a)?'x':/return|correction/i.test(a)?'arrow':'check')}${this.esc(a)}</button>`).join('')}${d.can_complete?`<button class="btn mw-primary mw-complete">${this.icon('check')}${__('Complete Task')}</button>`:''}${!d.actions.length&&!d.can_complete?`<span class="mw-note">${__('No document actions available at this stage.')}</span>`:''}</div></footer>`);
            drawer.find('.mw-close').trigger('focus');drawer.find('.mw-action').on('click',e=>this.confirmAction(d,d.actions[Number(e.currentTarget.dataset.actionIndex)],row));drawer.find('.mw-complete').on('click',()=>this.confirmAction(d,null,row));this.bindDocumentTools(d,row);if(d.tools?.date_editor){const datesButton=$('<button class="btn btn-default mw-edit-dates"></button>').text(__('Edit Dates'));drawer.find('.mw-action-buttons').prepend(datesButton);datesButton.on('click',()=>this.editInvoiceDates(d,row));}await this.bindTaskDescription(d,row);drawer.find('.mw-remarks').on('input',()=>drawer.find('.mw-add-comment').prop('disabled',!drawer.find('.mw-remarks').val().trim()));drawer.find('.mw-add-comment').on('click',()=>this.postComment(d));
        }catch(error){if(token===this.reviewSequence)drawer.find('.mw-drawer-body').html(`<div class="mw-empty"><h3>${__('Unable to load this request')}</h3><p>${__('Close the panel and refresh your inbox to try again.')}</p></div>`);}
    }
    async postComment(doc){
        const drawer=this.root.find('.mw-drawer');
        const input=drawer.find('.mw-remarks');
        const content=String(input.val()||'').trim();if(!content)return;
        const button=drawer.find('.mw-add-comment');button.prop('disabled',true);input.prop('disabled',true);
        try{
            const result=await this.api('add_comment',{doctype:doc.doctype,name:doc.name,content});
            doc.activity=[result.data,...(doc.activity||[])];
            if(this.currentReview?.doc===doc){
                input.val('');drawer.find('.mw-comment-history').html(this.activityList(doc));this.reviewTab('activity');
            }
            frappe.show_alert({message:__('Comment added'),indicator:'green'});
        }catch(error){button.prop('disabled',false);}
        finally{input.prop('disabled',false);if(this.currentReview?.doc===doc)button.prop('disabled',!String(input.val()||'').trim());}
    }
    commentText(content){
        const template=document.createElement('template');
        template.innerHTML=String(content||'').replace(/<br\s*\/?\s*>/gi,'\n').replace(/<\/(?:p|div|li)>/gi,'\n');
        return template.content.textContent.trim();
    }
    taskDescription(d){
        const field=d.task_description;if(!field)return '';
        return `<section class="mw-task-description-section"><div class="mw-section-heading"><h3>${__('Assignment Description')}</h3>${field.editable?`<div><button class="btn mw-primary mw-save-task-description" disabled>${__('Save Description')}</button> <button class="btn btn-default mw-reset-task-description">${__('Reset')}</button></div>`:''}</div>${field.editable?'<div class="mw-task-description-editor"></div>':`<p class="mw-task-description-readonly">${this.esc(this.commentText(field.value))}</p>`}</section>`;
    }
    async bindTaskDescription(doc,row){
        if(!doc.task_description?.editable)return;
        const drawer=this.root.find('.mw-drawer');const parent=drawer.find('.mw-task-description-editor');
        let initializing=true,baseline,read,write;
        const update=()=>{
            if(initializing||this.currentReview?.doc!==doc)return;
            const value=read();this.taskDescriptionDirty=value!==baseline;
            drawer.find('.mw-save-task-description').prop('disabled',!this.taskDescriptionDirty);
            drawer.find('.mw-action,.mw-complete').prop('disabled',this.taskDescriptionDirty||this.claimDirty);
        };
        if(frappe.ui.form?.make_control){
            const editor=frappe.ui.form.make_control({parent:parent[0],df:{fieldname:'description',label:__('Description'),fieldtype:'Text Editor',reqd:1,change:update},render_input:true,only_input:true});
            read=()=>editor.get_value()||'';write=value=>editor.set_value(value);
            await write(doc.task_description.value||'');
        }else{
            const input=$('<textarea class="form-control mw-task-description" aria-label="Assignment Description" rows="4"></textarea>').appendTo(parent);
            read=()=>'<p>'+this.esc(input.val()).replaceAll('\n','<br>')+'</p>';
            write=value=>input.val(this.commentText(value));input.on('input',update);
            write(doc.task_description.value||'');
        }
        if(this.currentReview?.doc!==doc)return;
        baseline=read();initializing=false;
        drawer.find('.mw-reset-task-description').on('click',async()=>{await write(baseline);update();});
        drawer.find('.mw-save-task-description').on('click',async()=>{
            const button=drawer.find('.mw-save-task-description').prop('disabled',true);
            try{await this.api('update_task_description',{name:doc.name,modified:doc.modified,description:read()});this.taskDescriptionDirty=false;frappe.show_alert({message:__('Assignment description saved'),indicator:'green'});await this.refreshReview(doc,row);}
            catch(error){button.prop('disabled',false);}
        });
    }
    reviewHeaderStatus(d,row){
        const fields=d.summary_fields||d.fields||[];
        if(fields.some(f=>/(^|_)(status|state)$/.test(f.fieldname||'')||f.label==='Status'))return '';
        const value=this.headline(d,row);
        return value?`<span class="mw-state-badge mw-tone-${this.headlineTone(d)}">${this.esc(value)}</span>`:'';
    }
    isRemarksField(field){
        return /^(?:custom_)?remarks?$/i.test(field.fieldname||'')||['remarks','purpose'].includes(String(field.label||'').trim().toLowerCase());
    }
    reviewRemarks(d){
        const fields=[...(d.summary_fields||d.fields||[]),...(d.remark_fields||[]),...(d.additional_fields||[])].filter(f=>this.isRemarksField(f)&&String(f.value||'').trim());
        const values=[...new Set(fields.map(f=>String(f.value)))];
        return values.length?`<section class="mw-document-remarks" aria-label="${__('Document remarks')}"><h3>${__('Remarks')}</h3>${values.map(value=>`<p>${this.esc(value)}</p>`).join('')}</section>`:'';
    }
    reviewDetails(d,row){
        const tables=(d.tables||[]).filter(t=>!`${t.label||''} ${t.fieldname||''}`.toLowerCase().replaceAll('_',' ').includes('coil production'));
        let primary=tables.filter(t=>t.compact_items||['items','accounts'].includes(t.fieldname)||t.label==='Expense Details');
        if(!primary.length)primary=tables;
        const secondary=tables.filter(t=>!primary.includes(t));
        const workflow=d.flow_mode==='workflow'||!d.flow_mode;
        const approval=d.tools?.fields?.find(f=>f.fieldname==='approval_status');
        const editableApproval=approval?.editable;
        const conflict=d.status_info?.has_conflict?`<aside class="mw-status-alert" role="alert"><strong>${__('Recorded statuses conflict')}</strong><p>${__('Review the status details below before taking action.')}</p></aside>`:'';
        const statusDetails=d.status_info||workflow||approval&&!editableApproval;
        const mainFields=(d.summary_fields||d.fields||[]).filter(f=>!this.isRemarksField(f)&&!(d.doctype==='ToDo'&&d.task_description&&f.fieldname==='description'));
        const top=`<div class="mw-review-top mw-review-top-reference"><div class="mw-detail-card"><dl>${this.summaryFields({...d,summary_fields:mainFields})}</dl></div>${this.workflowCard(d,row)}</div>`;
        return `${d.linked_document?this.linkedEntry(d):top}${this.taskDescription(d)}${conflict}${this.expenseTables({...d,tables:primary})}${editableApproval?this.approvalEditor(d):''}${this.claimContext(d)}${this.advancePanel(d)}${this.financialOverview(d)}${d.settlement?`<section class="mw-review-settlement"><h3>${__('Against Account / Party')}</h3>${this.settlementHTML(d.settlement,d.currency)}</section>`:''}${secondary.length?`<details class="mw-review-secondary"><summary>${__('Additional entry details')}</summary>${this.expenseTables({...d,tables:secondary})}</details>`:''}${this.reviewRemarks(d)}${d.linked_document?`<details class="mw-review-secondary"><summary>${__('Assignment details')}</summary>${top}</details>`:''}${this.additionalFields({...d,additional_fields:(d.additional_fields||[]).filter(f=>!this.isRemarksField(f)&&!(d.doctype==='ToDo'&&d.task_description&&f.fieldname==='description'))})}${statusDetails?`<details class="mw-review-secondary mw-status-details"><summary>${__('Status details')}</summary>${approval&&!editableApproval?this.approvalEditor(d):''}${workflow?this.decisionBanner(d):''}${this.statusOverview(d)}</details>`:''}${d.status_summary?.explanation?`<p class="mw-review-flow-note">${this.esc(__(d.status_summary.explanation))}</p>`:''}`;
    }
    documentToolbar(d){
        const t=d.tools;if(!t)return '';
        return `<div class="mw-document-tools" role="toolbar" aria-label="${__('Document tools')}"><button class="mw-tool-assign" ${t.can_assign?'':'disabled'}>${this.icon('users')}${__('Assign')} ${t.assignments?.length?`(${t.assignments.length})`:''}</button><button class="mw-tool-share" ${t.can_share?'':'disabled'}>${this.icon('link')}${__('Share')}</button><button class="mw-tool-tags" ${t.can_tag?'':'disabled'}>${this.icon('file')}${__('Tags')}</button><button class="mw-tool-attachments">${this.icon('paperclip')}${__('Attachments')} (${d.attachments.length})</button></div>${t.tags?.length?`<div class="mw-tag-strip">${t.tags.map(tag=>`<span>${this.esc(tag)}</span>`).join('')}</div>`:''}`;
    }
    approvalEditor(d){
        const field=d.tools?.fields?.find(f=>f.fieldname==='approval_status');if(!field)return '';
        const options=String(field.options||'').split('\n').filter(Boolean);
        return `<section class="mw-approval-editor"><div class="mw-section-heading"><h3>${__('Approval Status')} <code>approval_status</code></h3><span class="mw-status-pill mw-tone-${this.statusTone(field.value)}">${this.esc(__(field.value==='Draft'?'Not approved (Draft)':field.value||'Not approved'))}</span></div><div class="mw-approval-controls"><select class="form-control mw-native-approval mw-status-control mw-tone-${this.statusTone(field.value)}" aria-label="${__('Select native Approval Status')}" ${field.editable?'':'disabled'}>${options.map(value=>`<option value="${this.esc(value)}" ${value===field.value?'selected':''} ${field.editable&&value==='Cancelled'?'disabled':''}>${this.esc(__(value))}</option>`).join('')}</select>${field.editable?`<button class="btn mw-primary mw-save-approval" disabled>${__('Save Approval Status')}</button><button class="btn btn-default mw-reset-approval">${__('Reset')}</button>`:''}</div><p class="mw-note">${field.workflow_managed?__('Use the available workflow action below. The native Approval Status is updated automatically.'):field.editable?__('Select the actual approval decision and save it before submitting or using an action. Saving this field does not submit the claim. Cancelled is controlled by document cancellation.'):__('Read only: native Approval Status can be changed here only on a writable draft with the required field-level permission.')}</p></section>`;
    }
    claimContext(d){
        const fields=d.tools?.fields?.filter(f=>['task','project','cost_center'].includes(f.fieldname))||[];
        if(!fields.length)return '';
        return `<section class="mw-claim-context"><div class="mw-section-heading"><h3>${__('Claim fields')}</h3>${d.tools.fields.some(f=>f.editable&&f.fieldname!=='approval_status')?`<button class="btn btn-default btn-sm mw-edit-fields">${__('Edit fields')}</button>`:''}</div><dl>${fields.map(f=>`<div><dt>${this.esc(__(f.label))}</dt><dd>${f.fieldname==='status'?this.statusPill(f.value):this.esc(f.value)||'—'}</dd></div>`).join('')}</dl><p class="mw-note">${__('Status is calculated by HRMS from document, approval and payment records.')}</p></section>`;
    }
    advancePanel(d){
        const t=d.tools;if(!t||d.doctype!=='Expense Claim')return '';
        return `<section class="mw-advance-panel"><div class="mw-section-heading"><h3>${__('Linked Employee Advances')}</h3>${t.can_edit_advances?`<button class="btn btn-default btn-sm mw-add-advance">${this.icon('plus')}${__('Add advance')}</button>`:''}</div>${t.advances.length?`<div class="mw-table-scroll"><table class="mw-table"><thead><tr><th>${__('Employee Advance')}</th><th>${__('Allocated')}</th><th>${__('Available / Unclaimed')}</th><th></th></tr></thead><tbody>${t.advances.map(a=>`<tr><td>${a.employee_advance?`<a href="${frappe.utils.get_form_link('Employee Advance',a.employee_advance)}">${this.esc(a.employee_advance)}</a>`:__('Restricted advance')}</td><td>${this.money(a.allocated_amount,d.currency)}</td><td>${this.money(a.unclaimed_amount,d.currency)}</td><td>${a.can_remove?`<button class="btn btn-default btn-sm mw-remove-advance" data-advance-row="${this.esc(a.row_name)}">${__('Remove link')}</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:`<p class="mw-note">${__('No advance links are visible.')}</p>`}<p class="mw-note">${t.can_edit_advances?__('Remove link unlinks the advance from this draft only. It does not delete the Employee Advance or its payments.'):__('Advance links on submitted or cancelled claims require the native correction/amendment process.')}</p></section>`;
    }
    activityList(d){
        return (d.activity||[]).map(a=>`<div class="mw-activity"><strong>${this.esc(this.commentText(a.content))}</strong><small>${this.esc(a.comment_by||this.person(a.owner))} · ${this.esc(frappe.datetime.str_to_user(a.creation))}</small></div>`).join('');
    }
    ensureClean(){
        if(this.taskDescriptionDirty){frappe.msgprint(__('Save or reset the assignment description before taking another action.'));return false;}
        if(!this.claimDirty)return true;
        frappe.msgprint(__('Save or reset the selected Approval Status before taking another action.'));return false;
    }
    editInvoiceDates(d,row){
        if(!this.ensureClean())return;
        const editor=d.tools.date_editor;
        const fields=editor.fields.map(f=>({fieldname:f.fieldname,fieldtype:'Date',label:f.label,default:f.value,reqd:f.fieldname!=='bill_date'}));
        fields.push({fieldtype:'HTML',options:`<p class="text-muted">${__('Saving dates does not submit the invoice. Keep the original Posting Date for an old entry unless you intend to change its accounting date. Due Date must match the latest installment. Native payment-term and accounting validations still apply.')}</p>`});
        editor.schedule.forEach((r,i)=>fields.push({fieldname:`installment_${i}`,fieldtype:'Date',label:__('Installment {0} Due Date',[r.idx]),default:r.due_date,reqd:1}));
        const dialog=new frappe.ui.Dialog({title:__('Edit Invoice Dates'),fields,primary_action_label:__('Save Dates'),primary_action:async values=>{
            const dates=Object.fromEntries(editor.fields.map(f=>[f.fieldname,values[f.fieldname]||null]));
            const schedule=editor.schedule.map((r,i)=>({name:r.name,due_date:values[`installment_${i}`]}));
            await this.tool('update_invoice_dates',{doctype:d.doctype,name:d.name,modified:d.modified,dates:JSON.stringify(dates),schedule:JSON.stringify(schedule)},dialog.get_primary_btn());
            dialog.hide();await this.refreshReview(d,row);frappe.show_alert({message:__('Dates saved. Review the invoice before submitting.'),indicator:'green'});
        }});
        dialog.show();
        editor.schedule.forEach((r,i)=>dialog.fields_dict[`installment_${i}`].df.change=()=>{const due=editor.schedule.map((_,j)=>dialog.get_value(`installment_${j}`)).filter(Boolean).sort().pop();if(due)dialog.set_value('due_date',due);});
    }
    async tool(method,args,btn){return (await frappe.call({method:`my_work.claim_tools.${method}`,args,btn})).message;}
    async refreshReview(d,row){const comment=this.root.find('.mw-remarks').val()||'';this.claimDirty=false;await this.load();await this.review(row);this.root.find('.mw-remarks').val(comment).trigger('input');}
    bindDocumentTools(d,row){
        const drawer=this.root.find('.mw-drawer'),t=d.tools;if(!t)return;
        const status=t.fields?.find(f=>f.fieldname==='approval_status');
        drawer.find('.mw-native-approval').on('change',e=>{this.claimDirty=e.target.value!==status.value;drawer.find('.mw-save-approval').prop('disabled',!this.claimDirty);drawer.find('footer .mw-action,footer .mw-complete').prop('disabled',this.claimDirty);});
        drawer.find('.mw-reset-approval').on('click',()=>{drawer.find('.mw-native-approval').val(status.value);this.claimDirty=false;drawer.find('.mw-save-approval').prop('disabled',true);drawer.find('footer .mw-action,footer .mw-complete').prop('disabled',false);});
        drawer.find('.mw-save-approval').on('click',()=>{
            const value=drawer.find('.mw-native-approval').val();
            frappe.confirm(__('Save Approval Status as {0} on {1}?',[this.esc(__(value)),this.esc(d.name)]),async()=>{await this.tool('update_claim',{name:d.name,modified:d.modified,fields:JSON.stringify({approval_status:value})},drawer.find('.mw-save-approval'));frappe.show_alert({message:__('Approval Status saved'),indicator:'green'});await this.refreshReview(d,row);});
        });
        drawer.find('.mw-tool-assign').on('click',()=>{if(this.ensureClean())this.assignDialog(d,row);});
        drawer.find('.mw-tool-share').on('click',()=>{if(this.ensureClean())this.shareDialog(d,row);});
        drawer.find('.mw-tool-tags').on('click',()=>{if(this.ensureClean())this.tagsDialog(d,row);});
        drawer.find('.mw-tool-attachments').on('click',()=>this.reviewTab('attachments'));
        drawer.find('.mw-upload').on('click',()=>{if(this.ensureClean())this.upload(d,row);});
        drawer.find('.mw-edit-fields').on('click',()=>{if(this.ensureClean())this.editFields(d,row);});
        drawer.find('.mw-add-advance').on('click',()=>{if(this.ensureClean())this.addAdvance(d,row);});
        drawer.find('.mw-remove-advance').on('click',e=>{
            if(!this.ensureClean())return;
            const rowName=e.currentTarget.dataset.advanceRow;
            frappe.confirm(__('Remove this advance link from the draft claim? The Employee Advance and its payments will be preserved.'),async()=>{await this.tool('remove_advance',{name:d.name,modified:d.modified,row_name:rowName},$(e.currentTarget));await this.refreshReview(d,row);});
        });
        drawer.find('.mw-remove-attachment').on('click',e=>{
            if(!this.ensureClean())return;
            const file=e.currentTarget.dataset.file;
            frappe.confirm(__('Remove this attachment from the document?'),async()=>{await this.tool('remove_attachment',{doctype:d.doctype,name:d.name,modified:d.modified,file_name:file},$(e.currentTarget));await this.refreshReview(d,row);this.reviewTab('attachments');});
        });
    }
    editFields(d,row){
        const fields=d.tools.fields.filter(f=>f.editable&&f.fieldname!=='approval_status');
        const dialog=new frappe.ui.Dialog({title:__('Edit Expense Claim fields'),fields:fields.map(f=>({fieldname:f.fieldname,label:__(f.label),fieldtype:f.fieldtype,options:f.options,default:f.value})),primary_action_label:__('Save changes'),primary_action:async values=>{
            const changed={};for(const f of fields)if(String(values[f.fieldname]||'')!==String(f.value||''))changed[f.fieldname]=values[f.fieldname]||null;
            if(!Object.keys(changed).length){dialog.hide();return;}
            await this.tool('update_claim',{name:d.name,modified:d.modified,fields:JSON.stringify(changed)},dialog.get_primary_btn());dialog.hide();await this.refreshReview(d,row);
        }});dialog.show();
    }
    assignDialog(d,row){
        const current=(d.tools.assignments||[]).map(a=>`${this.person(a.allocated_to)}${a.date?' · '+a.date:''}`).join(', ');
        const dialog=new frappe.ui.Dialog({title:__('Assign {0}',[d.name]),fields:[{fieldtype:'HTML',options:`<p class="text-muted">${__('Current assignments')}: ${this.esc(current)||'—'}</p>`},{fieldname:'users',fieldtype:'MultiSelectPills',label:__('Assign To'),reqd:1,get_data:txt=>frappe.db.get_link_options('User',txt,{enabled:1,user_type:'System User'})},{fieldname:'description',fieldtype:'Small Text',label:__('Description'),default:`${d.doctype} ${d.name}`},{fieldname:'date',fieldtype:'Date',label:__('Due Date')},{fieldname:'priority',fieldtype:'Select',label:__('Priority'),options:['Low','Medium','High'],default:'Medium'}],primary_action_label:__('Assign'),primary_action:async values=>{await this.tool('assign',{doctype:d.doctype,name:d.name,modified:d.modified,...values,users:JSON.stringify(values.users)},dialog.get_primary_btn());dialog.hide();await this.refreshReview(d,row);}});dialog.show();
    }
    shareDialog(d,row){
        const shares=(d.tools.shares||[]).map(s=>`<div class="mw-dialog-share"><span>${this.esc(s.user||__('Everyone'))}</span><small>${s.write?__('Read + Write'):__('Read')}${s.submit?' + '+__('Submit'):''}</small>${s.user?`<button class="btn btn-default btn-xs" data-remove-share="${this.esc(s.user)}">${__('Remove share')}</button>`:''}</div>`).join('');
        const dialog=new frappe.ui.Dialog({title:__('Share {0}',[d.name]),fields:[{fieldtype:'HTML',options:shares||`<p>${__('No explicit shares')}</p>`},{fieldname:'user',fieldtype:'Link',options:'User',label:__('User'),reqd:1,get_query:()=>({filters:{enabled:1}})},{fieldname:'write',fieldtype:'Check',label:__('Allow write'),default:0},{fieldname:'submit',fieldtype:'Check',label:__('Allow submit'),default:0},{fieldtype:'HTML',options:`<p class="text-muted">${__('Read access is included. Frappe checks your permission to grant additional rights.')}</p>`}],primary_action_label:__('Share document'),primary_action:async values=>{await this.tool('share',{doctype:d.doctype,name:d.name,modified:d.modified,...values},dialog.get_primary_btn());dialog.hide();await this.refreshReview(d,row);}});dialog.show();
        dialog.$wrapper.on('click','[data-remove-share]',e=>frappe.confirm(__('Remove this user’s explicit document share?'),async()=>{await this.tool('share',{doctype:d.doctype,name:d.name,modified:d.modified,user:e.currentTarget.dataset.removeShare,remove:1});dialog.hide();await this.refreshReview(d,row);}));
    }
    tagsDialog(d,row){
        const tags=d.tools.tags||[];
        const dialog=new frappe.ui.Dialog({title:__('Document tags'),fields:[{fieldtype:'HTML',options:`<div class="mw-dialog-tags">${tags.map(tag=>`<span>${this.esc(tag)} <button class="btn btn-default btn-xs" data-remove-tag="${this.esc(tag)}" aria-label="${__('Remove tag')}">×</button></span>`).join('')||__('No tags')}</div>`},{fieldname:'tag',fieldtype:'Data',label:__('New tag'),reqd:1}],primary_action_label:__('Add tag'),primary_action:async values=>{await this.tool('tag',{doctype:d.doctype,name:d.name,modified:d.modified,tag:values.tag},dialog.get_primary_btn());dialog.hide();await this.refreshReview(d,row);}});dialog.show();
        dialog.$wrapper.on('click','[data-remove-tag]',async e=>{await this.tool('tag',{doctype:d.doctype,name:d.name,modified:d.modified,tag:e.currentTarget.dataset.removeTag,remove:1});dialog.hide();await this.refreshReview(d,row);});
    }
    addAdvance(d,row){
        const dialog=new frappe.ui.Dialog({title:__('Link Employee Advance'),fields:[{fieldname:'employee_advance',fieldtype:'Link',options:'Employee Advance',label:__('Employee Advance'),reqd:1,get_query:()=>({filters:{docstatus:1,...(d.tools.employee?{employee:d.tools.employee}:{}),...(d.currency?{currency:d.currency}:{})}})},{fieldname:'allocated_amount',fieldtype:'Currency',label:__('Allocated amount'),reqd:1},{fieldtype:'HTML',options:`<p class="text-muted">${__('Only the draft claim link is added. Employee, company, currency and available balance are checked by the server.')}</p>`}],primary_action_label:__('Add advance link'),primary_action:async values=>{await this.tool('add_advance',{name:d.name,modified:d.modified,...values},dialog.get_primary_btn());dialog.hide();await this.refreshReview(d,row);}});dialog.show();
    }
    upload(d,row){
        const open=()=>new frappe.ui.FileUploader({doctype:d.doctype,docname:d.name,folder:'Home/Attachments',make_attachments_public:false,on_success:async()=>{await this.refreshReview(d,row);this.reviewTab('attachments');}});
        if(frappe.ui.FileUploader)open();else frappe.require('file_uploader.bundle.js',open);
    }
    statusTone(value){
        const text=String(value||'').toLowerCase();
        if(/conflict|reject|declin|absent|not payable|overdue/.test(text))return 'danger';
        if(/cancel|not available|not visible|no separate|not required/.test(text))return 'muted';
        if(/draft|pending|await|return|not approved|not posted|unpaid|partly|to deliver|to bill|open/.test(text))return 'warning';
        if(/^(approved|paid|present|completed|closed|settled against advance|fully delivered|fully billed)$/.test(text))return 'success';
        return 'info';
    }
    stageLabel(value){return value==='Draft'?'Draft · Not Final':value==='Submitted'?'Submitted · Final':value;}
    statusPill(value,tone=null){value=this.stageLabel(value);return `<span class="mw-status-pill mw-tone-${tone||this.statusTone(value)}">${this.esc(__(value||'Not available'))}</span>`;}
    headline(d,row={}){
        const summary=d.status_summary;
        return summary?(summary.key==='no_separate_approval'?summary.document_label:summary.label):(d.status_info?.display_status||d.state||row.status||'');
    }
    headlineTone(d){return d.status_summary?(d.status_summary.key==='no_separate_approval'?d.status_summary.document_variant:d.status_summary.variant):this.statusTone(d.status_info?.display_status||d.state);}
    decisionBanner(d){
        const s=d.status_summary;if(!s)return '';
        return `<section class="mw-decision-banner mw-tone-${s.variant}" aria-label="${__('Approval explained')}"><div><strong>${__('Approval')}</strong>${this.statusPill(s.label,s.variant)}${this.statusPill(s.document_label,s.document_variant)}</div><p>${this.esc(__(s.explanation))}</p></section>`;
    }
    statusBadge(row){
        const current=row.flow_mode==='workflow'?row.state:(row.status||row.state||row.document_status);
        if(!current)return '';
        const tone=row.flow_mode==='workflow'&&row.status_info?.has_conflict?'warning':this.statusTone(current);
        return `<span class="mw-current-system-state mw-result-status mw-status-pill mw-tone-${tone}" ${row.status_info?.has_conflict?`title="${__('Recorded statuses disagree; review the document details.')}"`:''}>${this.esc(__(current))}</span>`;
    }
    nextActionHTML(row){
        const actions=(row.actions||[]).filter(Boolean);
        return actions.length?`<span class="mw-next-action">${this.icon('chevron-right')}${this.esc(__('Available: {0}',[actions.map(action=>__(action)).join(' / ')]))}</span>`:'';
    }
    statusOverview(d){
        const info=d.status_info;
        if(!info)return d.flow_mode?`<section class="mw-status-overview" aria-label="${__('Recorded document statuses')}"><div><span>${__('Document')}</span><strong>${this.statusPill(d.state||'Recorded')}</strong></div>${d.business_status?`<div><span>${__('Status')}</span><strong>${this.statusPill(d.business_status)}</strong></div>`:''}<div><span>${__('Flow')}</span><strong>${d.flow_mode==='record'?__('Saved record'):d.flow_mode==='standard'?__('Standard'):__('Workflow')}</strong></div></section>`:'';
        const fields=[[__('Document stage'),info.document_status],[__('Workflow State'),info.workflow_state],[__('Approval Status'),info.approval_status],[__('Claim Status'),info.claim_status]];
        return `<section class="mw-status-overview" aria-label="${__('Recorded document statuses')}">${fields.map(([label,value])=>`<div><span>${label}</span><strong>${this.statusPill(value)}</strong></div>`).join('')}<p>${__('Payment')}: <strong>${this.statusPill(info.payment_status)}</strong></p></section>${info.has_conflict?`<aside class="mw-status-alert" role="alert"><strong>${__('Recorded statuses conflict')}</strong>${info.conflicts.map(message=>`<p>${this.esc(__(message))}</p>`).join('')}<p>${__('Standard approval actions are blocked. Review the original fields; an authorized cancellation may be available below.')}</p></aside>`:''}${d.workflow_notices?.length?`<details class="mw-workflow-notices"><summary>${__('Workflow configuration notes')}</summary>${d.workflow_notices.map(message=>`<p>${this.esc(message)}</p>`).join('')}</details>`:''}`;
    }
    financialOverview(d){
        const info=d.status_info;
        if(!info)return '';
        const amounts=[[__('Claimed'),info.claimed],[__('Sanctioned'),info.sanctioned],[__('Advance applied'),info.advance_applied],[__('Reimbursed'),info.reimbursed],[__('Net payable'),info.net_payable],[__('Outstanding'),info.outstanding]].filter(([,value])=>value!=null);
        return `<section class="mw-financial-overview"><h3>${__('Claim and payment amounts')}</h3><div>${amounts.map(([label,value])=>`<div><span>${label}</span><strong>${this.money(value,d.currency)}</strong></div>`).join('')}</div><p>${this.statusPill(info.payment_status)}</p></section>`;
    }
    settlementHTML(source,currency){
        if(!source)return '<span class="mw-muted">—</span>';
        return `<span class="mw-settlement-badge mw-settlement-${this.esc(source.kind)}">${this.esc(__(source.label))}</span>${source.configured_route?`<small>${__('Configured route')}: ${this.esc(__(source.configured_route))}</small>`:''}${(source.accounts||[]).map(a=>`<small class="mw-against-account"><strong>${this.esc(__(a.label))}:</strong> ${this.esc(a.value)}</small>`).join('')}${source.party?`<small class="mw-against-party"><strong>${this.esc(__(source.party_label||'Party'))}:</strong> ${this.esc(source.party)}</small>`:''}${source.mode_of_payment?`<small>${__('Mode')}: ${this.esc(source.mode_of_payment)}</small>`:''}${source.payable_account?`<small>${this.esc(source.payable_account)}</small>`:''}${source.advance_amount!=null&&Number(source.advance_amount)>0?`<small>${__('Advance applied')}: ${this.money(source.advance_amount,currency)}</small>`:''}${(source.advances||[]).map(a=>`<a class="mw-advance-link" href="${frappe.utils.get_form_link(a.doctype,a.name)}">${this.esc(a.name)}</a>`).join('')}${source.net_payable!=null?`<small>${__('Net payable')}: ${this.money(source.net_payable,currency)}</small>`:''}`;
    }
    money(value,currency){
        if(value==null||value==='')return '—';
        const number=Number(value);if(!Number.isFinite(number))return this.esc(value);
        return `${currency==='PKR'?'Rs':this.esc(currency||'')} ${this.esc(number.toLocaleString('en-US',{maximumFractionDigits:2}))}`.trim();
    }
    shortDate(value){
        if(!value)return '';
        const date=new Date(String(value).slice(0,10)+'T00:00:00');
        return Number.isNaN(date.getTime())?this.esc(value):this.esc(date.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}));
    }
    summaryFields(d){
        return (d.summary_fields||d.fields).map(f=>{
            const value=/(^|_)(status|state)$/.test(f.fieldname||'')?this.statusPill(f.value):f.fieldtype==='Currency'?this.money(f.value,f.options&&f.options!=='currency'?null:d.currency):f.fieldtype==='Check'?(Number(f.value)?__('Yes'):__('No')):f.fieldtype==='Date'?this.shortDate(f.value):f.fieldtype==='Date Range'?(f.value?.length?(f.value[0]===f.value[1]?this.shortDate(f.value[0]):`${this.shortDate(f.value[0])} – ${this.shortDate(f.value[1])}`):'—'):this.esc(f.value)||'—';
            const icon=f.icon||(/employee|name/i.test(f.fieldname||'')?'user':/department|company/i.test(f.fieldname||'')?'building':/status|state/i.test(f.fieldname||'')?'check-circle':f.fieldtype==='Currency'?'money':/date/i.test(f.fieldtype)?'calendar':'file');
            return `<div><dt>${this.esc(__(f.label))}</dt><dd><span class="mw-field-icon">${this.icon(icon)}</span><span class="mw-field-value ${f.fieldtype==='Currency'?'mw-field-money':''}">${value}</span></dd></div>`;
        }).join('')||`<p class="mw-note">${__('Open the document to see all permitted details.')}</p>`;
    }
    workflowCard(d,row){
        if(d.flow_mode==='standard'||d.flow_mode==='record'){
            const record=d.flow_mode==='record';
            const status=Number(d.docstatus);
            const current=record?__('Saved record'):status===0?__('Awaiting submission'):status===1?__('Submission complete'):__('Document cancelled');
            const history=d.history||[];
            const recorded=d.document_events||[];
            const submission=recorded.find(e=>e.action==='Submitted')||history.find(h=>h.comment_type==='Submitted');
            const event=status===2?(recorded.find(e=>e.action==='Cancelled')||history.find(h=>h.comment_type==='Cancelled')):submission;
            const actor=e=>e?(e.actor_name||e.comment_by||this.person(e.actor||e.owner)):'';
            const eventTime=record?d.modified:event?.creation;
            return `<aside class="mw-workflow-card"><h3>${record?__('Record'):__('Document Flow')}</h3><ol class="mw-workflow-steps"><li class="is-recorded"><span>${this.icon('check')}</span><div><strong>${__('Created by {0}',[this.esc(this.person(d.owner))])}</strong>${d.creation?`<small>${this.esc(frappe.datetime.str_to_user(d.creation))}</small>`:''}</div></li>${!record&&status===2&&submission?`<li class="is-recorded mw-submission-event"><span>${this.icon('check')}</span><div><strong>${__('Submitted by {0}',[this.esc(actor(submission))])}</strong><small>${this.esc(frappe.datetime.str_to_user(submission.creation))}</small></div></li>`:''}<li class="is-current"><span></span><div><strong>${current}</strong>${!record&&event?`<small class="mw-event-actor">${__(status===2?'Cancelled by {0}':'Submitted by {0}',[this.esc(actor(event))])}</small>`:''}${eventTime?`<small>${this.esc(frappe.datetime.str_to_user(eventTime))}</small>`:''}${!record&&status===0&&d.actions.includes('Submit')?`<small>${__('You can submit')}</small>`:''}</div></li>${!record&&status===0?`<li class="is-next"><span></span><div><strong>${__('Submitted')}</strong><small>${__('(Next)')}</small></div></li>`:''}</ol></aside>`;
        }
        const submitted=(d.document_events||[]).find(e=>e.action==='Submitted')||d.history.find(h=>h.comment_type==='Submitted');
        const actor=submitted?(submitted.actor_name||submitted.comment_by||this.person(submitted.actor||submitted.owner)):this.person(d.owner);
        const first=submitted?__('Submitted by {0}',[this.esc(actor)]):__('Created by {0}',[this.esc(actor)]);
        const time=submitted?submitted.creation:d.creation;
        const roles=d.next_roles||[];
        const pending=/pending|await|waiting/i.test(d.state||'');
        const current=pending&&roles.length?__('Pending with {0}',[this.esc(roles.join(', '))]):this.esc(d.state||row.status||__('Current state'));
        const states=d.next_states||[];
        return `<aside class="mw-workflow-card"><h3>${__('Workflow')}</h3><ol class="mw-workflow-steps"><li class="is-recorded"><span>${this.icon('check')}</span><div><strong>${first}</strong><small>${this.esc(frappe.datetime.str_to_user(time))}</small></div></li><li class="is-current"><span></span><div><strong class="mw-current-status mw-tone-${this.statusTone(d.state)}">${current}${d.actions.length?` <b>(${__('You')})</b>`:''}</strong>${!d.actions.length&&roles.length?`<small>${this.esc(roles.join(', '))}</small>`:''}</div></li>${states.length?`<li class="is-next"><span></span><div><strong>${this.esc(states.join(' / '))}</strong><small>${states.length===1?__('(Next configured state)'):__('(Possible next states)')}</small></div></li>`:''}</ol></aside>`;
    }
    additionalFields(d){
        if(!d.additional_fields?.length)return '';
        return `<details class="mw-extra-fields"><summary>${__('More document details')} (${d.additional_fields.length})</summary><dl>${this.summaryFields({fields:d.additional_fields,currency:d.currency})}</dl></details>`;
    }
    tableValue(value,meta,currency){
        if(value==null||value==='')return '—';
        if(/(^|_)(status|state)$/.test(meta?.fieldname||''))return this.statusPill(value);
        if(meta?.fieldtype==='Currency')return this.money(value,meta.options==='currency'?currency:null);
        if(meta?.fieldtype==='Check')return Number(value)?__('Yes'):__('No');
        if(meta?.fieldtype==='Date')return this.shortDate(value);
        return this.esc(value);
    }
    expenseTables(d){
        return d.tables.map(t=>{
            const metadata=t.column_meta||{};
            const numeric=c=>['Currency','Float','Int','Percent','Duration'].includes(metadata[c]?.fieldtype)||c==='amount';
            const rows=t.rows.map((r,i)=>`<tr>${t.compact_items?'':`<td>${i+1}</td>`}${t.columns.map(c=>`<td class="${numeric(c)?'mw-number-cell':''}">${metadata[c]?this.tableValue(r[c],{...metadata[c],fieldname:c},d.currency):c==='amount'?this.money(r[c],d.currency):this.esc(r[c])}</td>`).join('')}</tr>${t.row_details?.[i]?.length?`<tr class="mw-row-more"><td colspan="${t.columns.length+1}"><details><summary>${__('Row {0} details',[i+1])}</summary><dl>${this.summaryFields({fields:t.row_details[i],currency:d.currency})}</dl></details></td></tr>`:''}`).join('');
            return `<div class="mw-expense-card ${t.column_meta?'mw-business-table':''} ${t.compact_items?'mw-compact-items':''}"><h3>${this.esc(__(t.label))} ${t.column_meta?`<small>(${t.rows.length})</small>`:''}</h3><div class="mw-table-scroll"><table class="mw-table mw-expense-table"><thead><tr>${t.compact_items?'':'<th>#</th>'}${t.columns.map(c=>`<th class="${numeric(c)?'mw-number-cell':''}">${this.esc(__(metadata[c]?.label||frappe.unscrub(c)))}</th>`).join('')}</tr></thead><tbody>${rows}</tbody>${t.total!=null?`<tfoot><tr>${t.compact_items?`<td colspan="${Math.max(1,t.columns.length-1)}">${__('Total')}</td><td class="mw-number-cell">${this.money(t.total,d.currency)}</td>`:t.column_meta?`<td colspan="${t.columns.length+1}" class="mw-number-cell">${__('Total Amount')}: ${this.money(t.total,d.currency)}</td>`:`<td colspan="${t.columns.length}">${__('Total')}</td><td class="mw-number-cell">${this.money(t.total,d.currency)}</td>`}</tr></tfoot>`:''}</table></div></div>`;
        }).join('');
    }
    actionClass(action){return /reject|decline|cancel/i.test(action)?'mw-action-danger':/return|correction/i.test(action)?'mw-action-neutral':/approve|accept/i.test(action)?'mw-action-success':'mw-primary';}
    timeline(d){return `<ol class="mw-timeline"><li><strong>${__('Document created')}</strong><small>${this.esc(this.person(d.owner))} · ${this.esc(frappe.datetime.str_to_user(d.creation))}</small></li>${d.history.map(h=>`<li><strong>${this.esc(h.content.replace(/<[^>]*>/g,''))}</strong><small>${this.esc(h.comment_by||this.person(h.owner))} · ${this.esc(frappe.datetime.str_to_user(h.creation))}</small></li>`).join('')}</ol>`;}
    reviewTab(tab){this.root.find('[data-review-tab]').each((_,el)=>{$(el).toggleClass('is-active',el.dataset.reviewTab===tab).attr('aria-selected',String(el.dataset.reviewTab===tab)).attr('tabindex',el.dataset.reviewTab===tab?0:-1);});this.root.find('[data-panel]').each((_,el)=>$(el).prop('hidden',el.dataset.panel!==tab));}
    confirmAction(doc,action,row){if(!this.ensureClean())return;const pendingComment=this.root.find('.mw-remarks').val()||'';frappe.confirm(action==='Cancel'&&doc.doctype==='Expense Claim'?__('Cancel this submitted claim? Frappe will enforce linked-document checks and reverse its posted accounting/advance effects.'):action?__('Apply {0} to {1}?',[this.esc(action),this.esc(doc.name)]):__('Complete this assignment?'),async()=>{this.root.find('.mw-drawer footer button').prop('disabled',true);try{const result=await this.api(action?'act':'complete_task',action?{doctype:doc.doctype,name:doc.name,action,modified:doc.modified}:{name:doc.name,modified:doc.modified});frappe.show_alert({message:result.data.queued?__('Action queued by Frappe'):__('Work updated'),indicator:'green'});await this.load();await this.review(row);this.root.find('.mw-remarks').val(pendingComment).trigger('input');}catch(error){this.root.find('.mw-drawer footer button').prop('disabled',false);}});}
    close(){this.claimDirty=false;this.taskDescriptionDirty=false;this.reviewSequence=(this.reviewSequence||0)+1;this.root.find('.mw-drawer,.mw-overlay').prop('hidden',true);if(!this.returnFocus?.isConnected)this.root.find('.mw-refresh').trigger('focus');else this.returnFocus.focus();}
}
