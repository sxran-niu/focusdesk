/* Small native interface. Scheduling and outcome calculations live in Python. */
(() => {
  const $ = (selector, parent = document) => parent.querySelector(selector);
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clock = minutes => `${String(Math.floor(minutes / 60)).padStart(2,'0')}:${String(minutes % 60).padStart(2,'0')}`;
  const duration = minutes => minutes >= 60 ? `${Math.floor(minutes / 60)} h${minutes % 60 ? ` ${minutes % 60} min` : ''}` : `${minutes} min`;
  const localDate = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
  const categories = {study:'Study',life:'Life',rest:'Rest'};
  const priorities = {1:'Low priority',2:'Normal',3:'High priority'};
  let selectedDate = localDate(), state, route = 'today', goalId, taskFilter = 'open', modalSave, loading = false;
  let noticeTimer, requestSequence = 0, showArchived = false;
  const content = $('#page-content');
  const dialog = $('#editor');

  async function api(path, method='GET', data) {
    const response = await fetch(path, {method, headers:{'Content-Type':'application/json','X-FocusDesk-Token':$('meta[name="focusdesk-token"]').content}, body:data === undefined ? undefined : JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Unable to save. Please try again.');
    return result;
  }
  function notify(message, error=false) {
    clearTimeout(noticeTimer); const el = $('#notice'); el.textContent=message; el.classList.toggle('error',error); el.hidden=false;
    noticeTimer=setTimeout(()=>el.hidden=true,5000);
  }
  function tag(category) { return `<span class="tag ${category}">${categories[category]}</span>`; }
  function outcomePath(task) {
    const outcome=state.outcomes.find(o=>o.id===task.outcome_id);
    if (!outcome) return 'Independent task';
    const phase=state.milestones.find(m=>m.id===outcome.milestone_id);
    return `${escape(phase?.title)} / ${escape(outcome.title)}`;
  }
  function taskMeta(task) { return `${duration(task.minutes)} · ${task.due_date ? 'Due '+escape(task.due_date) : 'No deadline'}`; }
  function field(name,label,type='text',value='',extra='') {
    return `<label class="field" for="f-${name}">${label}<input id="f-${name}" name="${name}" type="${type}" value="${escape(value)}" ${extra}></label>`;
  }
  function select(name,label,options,value) {
    return `<label class="field" for="f-${name}">${label}<select id="f-${name}" name="${name}">${options.map(([v,t])=>`<option value="${escape(v)}" ${String(v)===String(value)?'selected':''}>${escape(t)}</option>`).join('')}</select></label>`;
  }
  function textarea(name,label,value='') { return `<label class="field" for="f-${name}">${label}<textarea id="f-${name}" name="${name}" maxlength="2000">${escape(value)}</textarea></label>`; }
  function openForm(title,fields,save,button='Save') {
    $('#editor-title').textContent=title;$('#editor-fields').innerHTML=fields;$('#editor-error').textContent='';$('#save-editor').textContent=button;modalSave=save;dialog.showModal();
  }
  function taskForm(id) {
    const task=state.tasks.find(t=>t.id===id) || {category:'study',minutes:60,priority:2};
    const associations=[['','Independent task — no goal link'],...state.outcomes.filter(o=>o.id===task.outcome_id||!state.goals.find(g=>g.id===state.milestones.find(m=>m.id===o.milestone_id).goal_id).archived).map(o=>{const m=state.milestones.find(m=>m.id===o.milestone_id);const g=state.goals.find(g=>g.id===m.goal_id);return [o.id,`${g.title} / ${m.title} / ${o.title}`];})];
    openForm(id?'Edit task':'New task',
      field('title','Task name','text',task.title,'required maxlength="160"')+
      `<div class="form-grid">${select('category','Category',Object.entries(categories),task.category)}${field('minutes','Estimated time (minutes)','number',task.minutes,'required min="5" max="720"')}</div>`+
      `<div class="form-grid">${field('due_date','Due date (optional)','date',task.due_date)}${select('priority','Priority',Object.entries(priorities),task.priority)}</div>`+
      select('outcome_id','Course or outcome (optional)',associations,task.outcome_id??'')+textarea('notes','Notes (optional)',task.notes),
      data=>api(id?`/api/tasks/${id}`:'/api/tasks',id?'PATCH':'POST',data));
  }
  function completeForm(id) {
    const task=state.tasks.find(t=>t.id===id);
    if(task.status==='done')return mutate(`/api/tasks/${id}/complete`,'POST',{done:false},'Task reopened');
    openForm('Record completion',`<p>${escape(task.title)}</p>`+field('actual_minutes','Actual time (minutes)','number',task.minutes,'required min="0" max="1440"')+'<p class="meta">Confirm the actual time spent. Completing a task does not change outcomes or credits.</p>',data=>api(`/api/tasks/${id}/complete`,'POST',{done:true,actual_minutes:data.actual_minutes}),'Mark complete');
  }
  function scheduleForm(id) {
    const task=state.tasks.find(t=>t.id===id);
    const gap=state.gaps.find(([a,b])=>b-a>=task.minutes);
    openForm('Schedule task',`<p>${escape(task.title)} · ${duration(task.minutes)}</p><p class="meta">${selectedDate}</p>`+field('start','Start time','time',clock(gap?.[0]??state.day.start),'required')+'<p class="meta">Existing appointments are kept. Overlapping appointments cannot be saved.</p>',data=>api(`/api/days/${selectedDate}/blocks`,'POST',{...data,task_id:id}),'Add to schedule');
  }
  function rescheduleForm(id) {
    const block=state.blocks.find(b=>b.id===id), task=state.tasks.find(t=>t.id===block.task_id);
    openForm('Reschedule task',`<p>${escape(task.title)}</p><p class="meta">Previous appointment: ${block.date} ${clock(block.start)}–${clock(block.end)}</p><div class="form-grid">`+
      field('date','Target date','date',selectedDate,'required')+field('start','Start time','time',clock(block.start),'required')+'</div><p class="meta">Choose the selected day or a later date. The original appointment stays in history; a failed save leaves it unchanged.</p>',data=>api(`/api/blocks/${id}`,'PATCH',data));
  }
  function scheduleHistory(id) {
    const changes=state.changes.filter(c=>c.entity==='schedule'&&c.entity_id===id);
    const label=raw=>{const b=JSON.parse(raw);return b?`${b.date} ${clock(b.start)}–${clock(b.end)}`:'Remove from schedule';};
    return changes.length?`<details class="history"><summary>Schedule history (${changes.length})</summary>${changes.map(c=>`<p>${escape(c.created_at)} · ${escape(label(c.old_value))} → ${escape(label(c.new_value))}</p>`).join('')}</details>`:'';
  }
  function dayForm() {
    openForm('Available hours',`<p class="meta">${selectedDate}</p><div class="form-grid">${field('start','Start time','time',clock(state.day.start),'required')}${field('end','End time','time',clock(state.day.end),'required')}</div>`,data=>api(`/api/days/${selectedDate}`,'PUT',data));
  }
  function dateToolbar(extra='') {
    return `<div class="toolbar"><div class="toolbar-group"><button class="icon-button" data-action="prev" aria-label="Previous day">‹</button><input class="date-picker" type="date" value="${selectedDate}" id="selected-date" aria-label="Selected date"><button class="icon-button" data-action="next" aria-label="Next day">›</button><button class="text-button" data-action="today">Today</button></div>${extra}</div>`;
  }
  function renderToday() {
    const blocks=[...state.blocks,...state.fixed_blocks.map(b=>({...b,fixed:true}))].filter(b=>b.date===selectedDate).sort((a,b)=>a.start-b.start);
    const tasksById=new Map(state.tasks.map(t=>[t.id,t]));
    const totals={study:0,life:0,rest:0};
    blocks.forEach(b=>totals[b.fixed?b.category:tasksById.get(b.task_id).category]+=b.end-b.start);
    const capacity=state.day.end-state.day.start;
    const used=Object.values(totals).reduce((a,b)=>a+b,0);
    const scheduled=new Set(state.blocks.map(b=>b.task_id));
    const backlog=state.tasks.filter(t=>t.status==='open'&&!scheduled.has(t.id)).sort((a,b)=>(a.due_date||'9999').localeCompare(b.due_date||'9999')||b.priority-a.priority);
    const overdue=state.tasks.filter(t=>t.status==='open'&&t.due_date&&t.due_date<selectedDate);
    let cursor=state.day.start, agenda='';
    for(const block of blocks) {
      if(block.fixed) {
        if(block.start>cursor)agenda+=`<div class="free-time">${clock(cursor)}–${clock(block.start)} · ${duration(block.start-cursor)} Free time</div>`;
        agenda+=`<article class="agenda-item"><div class="time-label">${clock(block.start)}<span>${clock(block.end)}</span></div><div class="task-block ${block.category}"><div class="task-body"><div class="task-title">${escape(block.title)}</div><p class="meta">Fixed appointment · ${categories[block.category]} · ${duration(block.end-block.start)}</p><button class="text-button" data-action="cancel-fixed" data-id="${block.id}">Cancel occurrence</button></div></div></article>`;
        cursor=block.end;continue;
      }
      const task=tasksById.get(block.task_id);
      if(block.start>cursor)agenda+=`<div class="free-time">${clock(cursor)}–${clock(block.start)} · ${duration(block.start-cursor)} Free time</div>`;
      agenda+=`<article class="agenda-item ${task.status==='done'?'done':''}"><div class="time-label">${clock(block.start)}<span>${clock(block.end)}</span></div><div class="task-block ${task.category}"><input class="check" type="checkbox" data-complete="${task.id}" ${task.status==='done'?'checked':''} aria-label="${task.status==='done'?'Reopen':'Complete'}: ${escape(task.title)}"><div class="task-body"><div class="task-title">${escape(task.title)}</div><div class="meta">${categories[task.category]} · ${duration(block.end-block.start)}${task.status==='done'?` · Actual ${duration(task.actual_minutes)}`:''}</div><div class="meta">${outcomePath(task)}</div><div class="task-controls"><button class="text-button" data-action="edit-task" data-id="${task.id}">Edit</button>${task.status==='open'?`<button class="text-button" data-action="reschedule" data-id="${block.id}">Reschedule</button>`:''}<button class="text-button" data-action="unschedule" data-id="${block.id}">Remove from schedule</button></div></div></div></article>`;
      cursor=block.end;
    }
    if(cursor<state.day.end)agenda+=`<div class="free-time">${clock(cursor)}–${clock(state.day.end)} · ${duration(state.day.end-cursor)} Free time</div>`;
    const carryover=state.carryover.map(block=>{const task=tasksById.get(block.task_id);return `<article class="backlog-item"><div class="task-title">${escape(task.title)}</div><p class="meta">Previous appointment ${block.date} ${clock(block.start)} · ${duration(task.minutes)}</p><div class="task-controls"><button class="button small" data-action="reschedule" data-id="${block.id}">Move / reschedule</button><button class="text-button" data-action="complete-task" data-id="${task.id}">Record completion</button></div>${scheduleHistory(task.id)}</article>`;}).join('');
    const list=backlog.map(task=>`<article class="backlog-item"><div class="task-title">${escape(task.title)}</div><div class="meta">${taskMeta(task)}</div><div class="backlog-actions">${tag(task.category)}<div><button class="text-button" data-action="edit-task" data-id="${task.id}">Edit</button><button class="button small" data-action="schedule" data-id="${task.id}">Schedule</button></div></div></article>`).join('');
    content.innerHTML=dateToolbar(`<button class="button" data-action="day">Available ${clock(state.day.start)}–${clock(state.day.end)} <span aria-hidden="true">⌄</span></button>`)+
      `<section class="allocation" aria-label="Daily time allocation"><div class="allocation-label"><span>Scheduled <strong>${duration(used)}</strong></span><span class="muted">Free time ${duration(capacity-used)}</span></div><div class="allocation-track" role="img" aria-label="Study ${totals.study} min, Life ${totals.life} min, Rest ${totals.rest} min, Free time ${capacity-used} min">${Object.entries(totals).map(([cat,n])=>`<span class="${cat}-fill" style="width:${n/capacity*100}%"></span>`).join('')}</div><div class="allocation-legend">${Object.entries(totals).map(([cat,n])=>`<span><i class="legend-dot ${cat}-fill"></i>${categories[cat]} ${duration(n)}</span>`).join('')}</div></section>`+
      `<div class="day-grid"><section class="panel"><div class="panel-heading"><h2>Daily schedule</h2><span class="meta">${blocks.length} appointments · ${blocks.filter(b=>!b.fixed&&tasksById.get(b.task_id).status==='done').length} completed</span></div>${blocks.length?agenda:`<div class="empty"><h3>No appointments for this day</h3><p>Give each task a specific start time.</p><button class="button" data-action="new-task">＋ New task</button></div>`}</section><aside>${carryover?`<section class="panel" style="margin-bottom:20px"><div class="panel-heading"><h2>Unfinished from earlier days</h2><span class="meta">${state.carryover.length} tasks</span></div>${carryover}</section>`:''}<section class="panel"><div class="panel-heading"><h2>Unscheduled</h2><span class="meta">${backlog.length} tasks</span></div><div class="backlog-list">${list||'<p class="empty">Every open task already has an appointment.</p>'}</div>${backlog.length?'<button class="button primary" data-action="auto" style="width:100%;margin-top:20px">Fill free time</button><p class="meta" style="margin-top:10px">Sort by deadline and priority while keeping existing appointments. Tasks that do not fit stay here.</p>':''}</section>${overdue.length?`<div class="hint warning">${overdue.length} overdue tasks. Review their deadlines and appointments.</div>`:''}</aside></div>`;
  }
  function renderTasks() {
    const tasks=state.tasks.filter(t=>taskFilter==='all'||t.status===taskFilter).slice().reverse();
    content.innerHTML=`<div class="toolbar"><div class="filter-group">${[['open','Open'],['done','Completed'],['all','All']].map(([id,title])=>`<button class="filter-button" data-action="filter" data-filter="${id}" aria-pressed="${taskFilter===id}">${title}</button>`).join('')}</div><span class="meta">Tasks: ${tasks.length}</span></div><section class="panel task-list">${tasks.map(task=>{
      const block=state.blocks.find(b=>b.task_id===task.id);
      return `<article class="task-list-row ${task.status==='done'?'done':''}"><input class="check" type="checkbox" data-complete="${task.id}" ${task.status==='done'?'checked':''} aria-label="${task.status==='done'?'Reopen':'Complete'}: ${escape(task.title)}"><div class="task-body"><div class="task-title">${escape(task.title)}</div><div class="meta">${taskMeta(task)} · ${priorities[task.priority]}</div><div class="meta">${outcomePath(task)}</div>${block?`<div class="meta">Scheduled ${block.date} ${clock(block.start)}–${clock(block.end)}</div>`:''}${task.status==='done'?`<div class="meta">Completed ${escape(task.completed_at.slice(0,10))} · Actual ${duration(task.actual_minutes)}</div>`:''}${task.notes?`<p class="meta">${escape(task.notes)}</p>`:''}${scheduleHistory(task.id)}</div><div class="task-controls">${block&&task.status==='open'?`<button class="text-button" data-action="reschedule" data-id="${block.id}">Reschedule</button>`:''}${tag(task.category)}<button class="text-button" data-action="edit-task" data-id="${task.id}">Edit</button><button class="text-button" data-action="delete-task" data-id="${task.id}">Delete</button></div></article>`;
    }).join('')||'<div class="empty"><h3>No tasks here yet</h3><p>Add one specific, achievable action.</p><button class="button" data-action="new-task">＋ New task</button></div>'}</section>`;
  }
  const weekdays=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
  function recurringForm() {
    const end=new Date(`${selectedDate}T12:00:00`);end.setDate(end.getDate()+90);
    const endDate=`${end.getFullYear()}-${String(end.getMonth()+1).padStart(2,'0')}-${String(end.getDate()).padStart(2,'0')}`;
    openForm('New recurring appointment',field('title','Appointment name','text','','required maxlength="160"')+
      `<div class="form-grid">${select('category','Category',Object.entries(categories),'study')}${select('weekday','Every week',weekdays.map((v,i)=>[i,v]),0)}</div>`+
      `<div class="form-grid">${field('start_date','Start date','date',selectedDate,'required')}${field('end_date','End date','date',endDate,'required')}</div>`+
      `<div class="form-grid">${field('start','Start time','time','09:00','required')}${field('end','End time','time','10:00','required')}</div>`+
      '<p class="meta">Choose a range of up to 366 days. Every date is checked against available hours and existing appointments. A conflict rejects the whole series. Fixed time does not award effort or credits.</p>',data=>api('/api/recurring','POST',data));
  }
  function renderCalendar() {
    const end=new Date(`${selectedDate}T12:00:00Z`);end.setUTCDate(end.getUTCDate()+6);const last=end.toISOString().slice(0,10);
    const slots=state.fixed_blocks.filter(b=>b.date>=selectedDate&&b.date<=last).sort((a,b)=>a.date.localeCompare(b.date)||a.start-b.start);
    content.innerHTML=dateToolbar('<button class="button primary" data-action="new-recurring">＋ Add recurring appointment</button>')+
      `<section class="panel"><h2>Recurring rules</h2><p class="meta">Fixed appointments appear in the daily schedule and block overlapping tasks. Cancel one occurrence or stop today and future occurrences while keeping the past.</p>${state.recurring_rules.map(r=>`<article class="task-list-row"><div class="task-body"><h3>${escape(r.title)}</h3><p class="meta">${weekdays[r.weekday]} ${clock(r.start)}–${clock(r.end)} · ${escape(r.start_date)} to ${escape(r.end_date)} · ${r.active?'Active':'Stopped'}</p></div>${r.active?`<button class="text-button" data-action="stop-recurring" data-id="${r.id}">Stop future appointments</button>`:''}</article>`).join('')||'<p class="empty">Add weekly classes, work shifts, or regular breaks.</p>'}</section>`+
      `<section class="panel" style="margin-top:20px"><div class="panel-heading"><h2>Seven days from the selected date</h2><span class="meta">${selectedDate} — ${last}</span></div>${slots.map(b=>`<article class="task-list-row"><div class="task-body"><h3>${escape(b.title)}</h3><p class="meta">${b.date} ${clock(b.start)}–${clock(b.end)}</p></div><button class="text-button" data-action="cancel-fixed" data-id="${b.id}">Cancel occurrence</button></article>`).join('')||'<p class="empty">No fixed appointments in these seven days.</p>'}</section>`;
  }
  function goalForm(id) {
    const goal=state.goals.find(g=>g.id===id)||{target:120,unit:'credits'};
    openForm(id?'Edit long-term goal':'New long-term goal',field('title','Goal name','text',goal.title,'required maxlength="160"')+
      `<div class="form-grid">${field('target','Target amount','number',goal.target,'required min="0.01" max="100000" step="0.01"')}${field('unit','Unit','text',goal.unit,'required maxlength="20"')}</div>`+
      field('target_date','Target completion date','date',goal.target_date,'required')+textarea('notes','Completion notes (optional)',goal.notes)+
      '<p class="meta">Example: finish a degree in two years with 120 credits. Add required modules, a thesis, and other conditions separately.</p>',
      async data=>{const result=await api(id?`/api/goals/${id}`:'/api/goals',id?'PATCH':'POST',data);goalId=id||result.id;showArchived=false;location.hash=`goals/${goalId}`;});
  }
  function milestoneForm(goal) {
    const phases=state.milestones.filter(m=>m.goal_id===goal.id);
    const latest=phases.slice().sort((a,b)=>b.end_date.localeCompare(a.end_date))[0];
    openForm('Add stage / semester',field('title','Stage name','text','', 'required maxlength="160"')+
      `<div class="form-grid">${field('start_date','Start date','date',latest?.end_date||state.today,'required')}${field('end_date','End date','date','','required')}</div>`+
      field('target',`Stage target (${escape(goal.unit)})`,'number','','required min="0.01" max="100000" step="0.01"'),data=>api('/api/milestones','POST',{...data,goal_id:goal.id}));
  }
  function outcomeForm(milestoneId,id) {
    const outcome=state.outcomes.find(o=>o.id===id)||{};
    const phase=state.milestones.find(m=>m.id===(milestoneId||outcome.milestone_id));
    const goal=state.goals.find(g=>g.id===phase.goal_id);
    openForm(id?'Edit course / outcome':'Add course / outcome',`<p class="meta">${escape(goal.title)} / ${escape(phase.title)}</p>`+
      (id?select('milestone_id','Stage (keep this course record)',state.milestones.filter(m=>m.goal_id===goal.id).map(m=>[m.id,m.title]),phase.id):'')+
      field('title','Course or outcome name','text',outcome.title,'required maxlength="160"')+
      field('amount',`Amount earned when confirmed (${escape(goal.unit)})`,'number',outcome.amount||6,'required min="0.01" max="100000" step="0.01"')+
      '<p class="meta">Keep one record per course. Pending amounts do not count toward confirmed progress.</p>',data=>api(id?`/api/outcomes/${id}`:'/api/outcomes',id?'PATCH':'POST',{milestone_id:phase.id,...data}));
  }
  function resultForm(id) {
    const outcome=state.outcomes.find(o=>o.id===id);
    openForm('Record outcome / result',`<p>${escape(outcome.title)}</p>`+
      select('status','Result status',[['pending','Pending / awaiting results'],['passed','Passed — amount confirmed'],['failed','Failed / not achieved']],outcome.status)+
      `<div class="form-grid">${field('result_date','Result or confirmation date','date',outcome.result_date||state.today,`max="${state.today}"`)}${field('grade','Grade (optional)','text',outcome.grade,'maxlength="40"')}</div>`+
      textarea('notes','Result notes / reflection',outcome.notes)+
      '<p class="meta">Enter a confirmed result. Saving the same result again does not add duplicate credit.</p>',data=>api(`/api/outcomes/${id}/result`,'PUT',data),'Save result');
  }
  function detailHistory(entity,id) {
    const changes=state.changes.filter(c=>c.entity===entity&&c.entity_id===id);
    const describe=raw=>{try {const values=JSON.parse(raw), labels={title:'Name',amount:'Outcome amount',milestone_id:'Stage',start_date:'Start',end_date:'End'};return Object.entries(values).map(([key,value])=>`${labels[key]||key}: ${key==='milestone_id'?(state.milestones.find(m=>m.id===value)?.title||'Previous stage'):value}`).join(', ');}catch{return raw;}};
    return changes.length?`<details class="history"><summary>Change history (${changes.length})</summary>${changes.map(c=>`<p style="overflow-wrap:anywhere">${escape(c.created_at)} · ${escape(describe(c.old_value))} → ${escape(describe(c.new_value))}</p>`).join('')}</details>`:'';
  }
  function renderGoals() {
    const visibleGoals=state.goals.filter(g=>Boolean(g.archived)===showArchived);
    const filters=`<div class="toolbar"><div class="filter-group"><button class="filter-button" data-action="goal-filter" data-archived="false" aria-pressed="${!showArchived}">Active goals</button><button class="filter-button" data-action="goal-filter" data-archived="true" aria-pressed="${showArchived}">Archived</button></div></div>`;
    const hashId=Number(location.hash.split('/')[1]);
    if(visibleGoals.some(g=>g.id===hashId))goalId=hashId;
    if(!visibleGoals.some(g=>g.id===goalId))goalId=visibleGoals[0]?.id;
    const goal=state.goals.find(g=>g.id===goalId);
    if(!goal&&showArchived){content.innerHTML=filters+'<section class="panel empty">No archived goals yet. Archive a completed goal to keep its results for reference.</section>';return;}
    if(!goal){content.innerHTML=filters+'<section class="panel empty"><h2>Give your daily actions a direction</h2><p>Create a long-term goal, then add stages and courses or outcomes.</p><button class="button primary" data-action="new-goal">＋ New goal</button></section>';return;}
    const phases=state.milestones.filter(m=>m.goal_id===goal.id);
    const requirements=state.requirements.filter(r=>r.goal_id===goal.id);
    const percent=Math.min(100,goal.earned/goal.target*100);
    const goalHistory=state.changes.filter(c=>c.entity==='goal'&&c.entity_id===goal.id);
    content.innerHTML=filters+`<div class="goal-grid"><div class="goal-options">${visibleGoals.map(g=>`<button class="goal-choice ${g.id===goal.id?'selected':''}" data-action="select-goal" data-id="${g.id}" aria-pressed="${g.id===goal.id}"><span>${escape(g.title)}</span><span class="meta">${g.earned} / ${g.target} ${escape(g.unit)}</span></button>`).join('')}</div><div class="goal-detail"><section class="panel"><div class="panel-heading"><h2>${escape(goal.title)}</h2><div class="task-controls">${goal.archived?`<button class="button small" data-action="unarchive-goal" data-id="${goal.id}">Unarchive</button>`:`<button class="text-button" data-action="edit-goal" data-id="${goal.id}">Edit goal</button>${goal.achieved?`<button class="button small" data-action="archive-goal" data-id="${goal.id}">Archive completed goal</button>`:''}`}</div></div><p class="meta">Target date ${goal.target_date}${goal.achieved?' · All configured conditions met':''}</p><div class="goal-stats"><div><div class="meta">Confirmed outcomes</div><div class="goal-number numbers">${goal.earned}<span class="meta"> / ${goal.target} ${escape(goal.unit)}</span></div></div><div><div class="meta">Pending</div><div class="goal-number numbers">${goal.pending}<span class="meta"> ${escape(goal.unit)}</span></div></div><div><div class="meta">Remaining to target</div><div class="goal-number numbers">${Math.max(0,Math.round((goal.target-goal.earned)*100)/100)}<span class="meta"> ${escape(goal.unit)}</span></div></div></div><div class="progress-track" role="progressbar" aria-label="Confirmed outcome progress" aria-valuenow="${Math.min(goal.earned,goal.target)}" aria-valuemin="0" aria-valuemax="${goal.target}"><div class="progress-fill" style="width:${percent}%"></div></div><p class="meta" style="margin-top:12px">Daily tasks track effort. Only confirmed outcomes contribute to this progress.</p>${goal.notes?`<p class="meta" style="margin-top:12px">${escape(goal.notes)}</p>`:''}${goal.planned!==goal.target?`<div class="hint warning">Stage targets total ${goal.planned} ${escape(goal.unit)}; the overall goal is ${goal.target} ${escape(goal.unit)}. Review the allocation.</div>`:''}${goalHistory.length?`<details class="history"><summary>Target change history</summary>${goalHistory.map(c=>`<p>${escape(c.created_at.slice(0,10))} · ${escape(c.old_value)} → ${escape(c.new_value)}</p>`).join('')}</details>`:''}</section><section class="panel"><div class="panel-heading"><h3>Additional conditions</h3><button class="button small" data-action="requirement" data-id="${goal.id}" ${goal.archived?'disabled':''}>＋ Add condition</button></div>${requirements.map(r=>`<label class="requirement-row"><input type="checkbox" class="check" data-requirement="${r.id}" ${goal.archived?'disabled':''} ${r.done?'checked':''}><span>${escape(r.title)}</span></label>`).join('')||'<p class="meta">Add required modules, a thesis, or any other essential conditions.</p>'}</section><div class="panel-heading" style="margin:4px 0 0"><h2>Stages and outcomes</h2><button class="button" data-action="milestone" data-id="${goal.id}" ${goal.archived?'disabled':''}>＋ Add stage</button></div>${phases.map((phase,index)=>{
      const outcomes=state.outcomes.filter(o=>o.milestone_id===phase.id);
      const changes=state.changes.filter(c=>c.entity==='milestone'&&c.entity_id===phase.id);
      const ended=phase.end_date<state.today;
      const shortage=Math.max(0,Math.round((phase.target-phase.earned)*100)/100);
      return `<details class="term" ${index===0||phase.start_date<=state.today&&phase.end_date>=state.today?'open':''}><summary><strong>${escape(phase.title)}</strong><span class="meta">${phase.start_date} — ${phase.end_date} · Confirmed ${phase.earned} / Planned ${phase.target} ${escape(goal.unit)}</span></summary><div class="term-content"><div class="term-toolbar"><button class="button small" data-action="outcome" data-id="${phase.id}" ${goal.archived?'disabled':''}>＋ Add course / outcome</button><button class="text-button" data-action="revise" data-id="${phase.id}" ${goal.archived?'disabled':''}>Edit stage</button></div>${outcomes.map(outcome=>`<article class="outcome-row"><div class="outcome-body"><div class="task-title">${escape(outcome.title)}</div><div class="meta">${outcome.amount} ${escape(goal.unit)}${outcome.grade?' · Grade '+escape(outcome.grade):''}${outcome.result_date?' · '+escape(outcome.result_date)+' Confirmed':''}</div>${outcome.notes?`<p class="meta">${escape(outcome.notes)}</p>`:''}${detailHistory('outcome_details',outcome.id)}</div><span class="tag ${outcome.status}">${{pending:'Pending',passed:'Confirmed',failed:'Failed'}[outcome.status]}</span><button class="button small" data-action="result" data-id="${outcome.id}" ${goal.archived?'disabled':''}>Record result</button><button class="text-button" data-action="edit-outcome" data-id="${outcome.id}" ${goal.archived?'disabled':''}>Edit</button></article>`).join('')||'<p class="empty">Add a course or outcome to link it to daily tasks.</p>'}${ended&&shortage?`<div class="hint warning">This stage has ended. Confirmed outcomes are ${shortage} ${escape(goal.unit)} below target${phase.pending?`; ${phase.pending} ${escape(goal.unit)} still pending`:''}. Verify results before revising the plan.</div>`:''}${outcomes.some(o=>o.status==='failed')?'<div class="hint warning">This stage has a failed outcome. Use result notes to plan a retake or next steps.</div>':''}${detailHistory('milestone_details',phase.id)}<div class="history">Original target: ${phase.original_target} ${escape(goal.unit)}${changes.length?`<details><summary>View changes (${changes.length})</summary>${changes.map(c=>`<p>${escape(c.created_at.slice(0,10))} · ${escape(c.old_value)} → ${escape(c.new_value)}</p>`).join('')}</details>`:''}</div></div></details>`;
    }).join('')||'<section class="panel empty">Break your goal into semesters, months, or other stages.</section>'}</div></div>`;
  }
  async function renderWeek() {
    const viewingDate=selectedDate;
    content.innerHTML='<p class="empty">Loading the weekly plan…</p>';
    try {
      const plan=await api(`/api/weekly-plan?date=${viewingDate}`);
      if(route!=='week'||selectedDate!==viewingDate)return;
      content.innerHTML=dateToolbar(`<span class="meta">${plan.start} — ${plan.end}</span>`)+
        `<section class="panel"><h2>Turn weekly intentions into appointments</h2><p class="meta">Set an effort target for each course, then schedule its tasks. Minutes do not convert to credits. Actual effort is recorded separately by completion date.</p><div class="hint">Time available from now in this week: ${duration(plan.remaining_free_minutes)} · Course plan gaps: ${duration(plan.unplanned_minutes)} not yet scheduled</div>${plan.unplanned_minutes>plan.remaining_free_minutes?'<p class="hint warning">The plan gaps exceed the time left in this week. Reduce targets or adjust appointments.</p>':''}</section>`+
        plan.courses.map(row=>`<section class="panel" style="margin-top:16px"><div class="panel-heading"><div><h3>${escape(row.title)}</h3><p class="meta">${escape(row.goal)} / ${escape(row.milestone)}</p></div><button class="button small" data-action="weekly-target" data-id="${row.outcome_id}" data-minutes="${row.target_minutes}">Set weekly target</button></div><div class="review-metrics"><p>Weekly plan <strong>${duration(row.target_minutes)}</strong></p><p>Scheduled <strong>${duration(row.scheduled_minutes)}</strong></p><p>Actual effort <strong>${duration(row.actual_minutes)}</strong></p></div><p class="${row.unplanned_minutes?'hint warning':'meta'}">${row.target_minutes?`${duration(row.unplanned_minutes)} still to schedule`:'No weekly target set'}</p><p class="meta">Estimated open tasks: ${duration(row.remaining_task_minutes)} (including other weeks). Link tasks to this course and schedule them in the daily planner.</p><div class="task-controls"><a class="button small" href="#tasks">View tasks</a><a class="button small" href="#today">Plan selected day</a></div></section>`).join('')+
        (plan.courses.length?'':'<section class="panel empty" style="margin-top:16px"><p>Add stages and courses under a long-term goal before setting weekly targets.</p><a class="button" href="#goals">Open long-term progress</a></section>');
    } catch(error) {if(route==='week')content.innerHTML=`<p class="empty">${escape(error.message)}</p>`;}
  }
  async function renderBackup() {
    content.innerHTML='<p class="empty">Loading backups…</p>';
    try {
      const copies=await api('/api/backups');
      if(route!=='backup')return;
      content.innerHTML=`<section class="panel"><h2>Save a complete backup</h2><p class="meta">Includes goals, courses, tasks, appointments, recurring rules, weekly targets, and history. Keep the downloaded file safe. Personal and demo spaces cannot be mixed.</p><a class="button primary" href="/api/backup" download style="margin-top:16px">Download full backup (JSON)</a></section><section class="panel" style="margin-top:20px"><h2>Restore from a backup</h2><p class="meta">Choose a FocusDesk JSON backup (up to 8 MB). After validation and confirmation, it replaces this space and saves a recovery copy of the current data. Invalid files leave current data unchanged.</p><label class="field" style="margin-top:16px">Choose a backup file<input id="backup-file" type="file" accept="application/json,.json"></label></section><section class="panel" style="margin-top:20px"><h2>Recovery copies</h2>${copies.files.map(name=>`<p style="margin-top:12px;overflow-wrap:anywhere"><a href="/api/backups/${encodeURIComponent(name)}" download>${escape(name)}</a></p>`).join('')||'<p class="meta">Automatic recovery copies appear here after a restore.</p>'}</section>`;
    } catch(error) {if(route==='backup')content.innerHTML=`<p class="empty">${escape(error.message)}</p>`;}
  }
  async function renderReview() {
    const reviewingDate=selectedDate;
    content.innerHTML='<p class="empty">Loading the weekly review…</p>';
    try {
      const report=await api(`/api/report?date=${reviewingDate}`);
      if(route!=='review'||reviewingDate!==selectedDate)return;
      const max=Math.max(60,...report.days.map(d=>d.actual));
      content.innerHTML=dateToolbar(`<span class="meta">${report.start} — ${report.end}</span>`)+
        `<div class="review-metrics"><div class="panel"><div class="meta">Completed tasks</div><div class="review-value">${report.completed}<span class="meta"></span></div></div><div class="panel"><div class="meta">Planned time</div><div class="review-value">${report.planned_minutes}<span class="meta"> min</span></div></div><div class="panel"><div class="meta">Actual effort</div><div class="review-value">${report.actual_minutes}<span class="meta"> min</span></div></div></div><section class="panel"><div class="panel-heading"><h2>Daily recorded effort</h2><span class="meta">Minutes / grouped by completion date</span></div><div class="review-bars" role="img" aria-label="${report.days.map(d=>d.date+' actual '+d.actual+' min').join(', ')}">${report.days.map(d=>`<div class="review-bar-column"><span class="numbers">${d.actual}</span><div class="review-bar" style="height:${d.actual/max*155}px"></div><span>${d.date.slice(5)}</span></div>`).join('')}</div><table class="allocation-table"><thead><tr><th>Category</th><th>Planned (min)</th><th>Actual (min)</th></tr></thead><tbody>${Object.entries(report.categories).map(([cat,n])=>`<tr><td>${categories[cat]}</td><td>${n.planned}</td><td>${n.actual}</td></tr>`).join('')}</tbody></table><p class="meta" style="margin-top:15px">Completed tasks took ${Math.abs(report.estimate_difference)} min ${report.estimate_difference>=0?'more':'less'} than estimated. Planned time uses appointment dates; actual time uses completion dates.</p></section><section class="panel" style="margin-top:20px"><div class="panel-heading"><h3>Save this weekly review</h3><div class="report-links"><a class="button" href="/api/export/md?date=${selectedDate}" download>Text report</a><a class="button" href="/api/export/csv?date=${selectedDate}" download>Schedule CSV</a><a class="button" href="/api/export/svg?date=${selectedDate}" download>Chart (SVG)</a></div></div><p class="meta">Exports stay on your computer. Long-term progress uses confirmed outcomes separately.</p></section>`;
    } catch(error) {if(route==='review')content.innerHTML=`<div class="panel empty"><p>${escape(error.message)}</p><button class="button" data-action="reload">Retry</button></div>`;}
  }
  async function load() {
    const sequence=++requestSequence;
    try {
      const result=await api(`/api/state?date=${selectedDate}`);
      if(sequence!==requestSequence)return;
      state=result;render();
    } catch(error) { content.innerHTML=`<div class="panel empty"><p>${escape(error.message)}</p><button class="button" data-action="reload">Retry</button></div>`; }
    finally {content.setAttribute('aria-busy','false');}
  }
  function render() {
    route=(location.hash.slice(1).split('/')[0]||'today');
    if(!['today','tasks','goals','week','calendar','backup','review'].includes(route))route='today';
    const titles={today:['Daily planner','DAILY PLANNER'],tasks:['Tasks','TASKS'],goals:['Long-term progress','GOALS & OUTCOMES'],backup:['Backups','BACKUP & RESTORE'],calendar:['Fixed schedule','RECURRING SCHEDULE'],week:['Weekly plan','WEEKLY PLAN'],review:['Weekly review','WEEKLY REVIEW']};
    $('#page-title').textContent=titles[route][0];$('#page-eyebrow').textContent=titles[route][1];document.title=`FocusDesk · ${titles[route][0]}`;
    document.querySelectorAll('[data-nav]').forEach(el=>{el.classList.toggle('active',el.dataset.nav===route);if(el.dataset.nav===route)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
    $('#global-add').textContent=route==='goals'?'＋ New goal':route==='calendar'?'＋ Recurring appointment':'＋ New task';
    ({today:renderToday,tasks:renderTasks,goals:renderGoals,calendar:renderCalendar,backup:renderBackup,week:renderWeek,review:renderReview}[route])();
  }
  async function mutate(path,method,data,message='Saved') {
    if(loading)return;loading=true;
    try {const result=await api(path,method,data);await load();notify(typeof message==='function'?message(result):message);}
    catch(error){notify(error.message,true);}finally{loading=false;}
  }
  content.addEventListener('click',event=>{
    const button=event.target.closest('[data-action]');if(!button)return;
    const id=Number(button.dataset.id),action=button.dataset.action;
    if(action==='new-task')taskForm();
    else if(action==='edit-task')taskForm(id);
    else if(action==='schedule')scheduleForm(id);
    else if(action==='reschedule')rescheduleForm(id);
    else if(action==='complete-task')completeForm(id);
    else if(action==='delete-task') {
      const task=state.tasks.find(t=>t.id===id);
      openForm('Delete task',`<p>Delete “${escape(task.title)}” and its appointment? Linked course outcomes will be kept.</p>`,()=>api(`/api/tasks/${id}`,'DELETE',{}),'Delete task');
    }
    else if(action==='new-recurring')recurringForm();
    else if(action==='cancel-fixed')openForm('Cancel one occurrence','<p>Remove only this occurrence. Other dates stay unchanged and the cancellation is recorded.</p>',()=>api(`/api/fixed-blocks/${id}`,'DELETE',{}),'Confirm cancellation');
    else if(action==='stop-recurring')openForm('Stop future appointments','<p>Cancel all occurrences from today onward. Past appointments and change history are kept.</p>',()=>api(`/api/recurring/${id}`,'DELETE',{}),'Stop series');
    else if(action==='filter'){taskFilter=button.dataset.filter;renderTasks();}
    else if(action==='new-goal')goalForm();
    else if(action==='edit-goal')goalForm(id);
    else if(action==='goal-filter'){showArchived=button.dataset.archived==='true';goalId=undefined;renderGoals();}
    else if(action==='archive-goal')openForm('Archive completed goal','<p>Move this goal to Archived. Courses, confirmed results, linked tasks, and history are kept. You can unarchive it later.</p>',()=>api(`/api/goals/${id}/archive`,'PUT',{archived:true}),'Archive goal');
    else if(action==='unarchive-goal')mutate(`/api/goals/${id}/archive`,'PUT',{archived:false},'Goal unarchived. Find it under Active goals.');
    else if(action==='select-goal'){goalId=id;location.hash=`goals/${id}`;}
    else if(action==='milestone')milestoneForm(state.goals.find(g=>g.id===id));
    else if(action==='outcome')outcomeForm(id);
    else if(action==='edit-outcome')outcomeForm(null,id);
    else if(action==='result')resultForm(id);
    else if(action==='revise') {
      const phase=state.milestones.find(m=>m.id===id);
      openForm('Edit stage',field('title','Stage name','text',phase.title,'required maxlength="160"')+`<div class="form-grid">${field('start_date','Start date','date',phase.start_date,'required')}${field('end_date','End date','date',phase.end_date,'required')}</div><p class="meta">Original target: ${phase.original_target}; current target: ${phase.target}. Changes are recorded.</p>`+field('target','Updated target amount','number',phase.target,'required min="0.01" max="100000" step="0.01"'),data=>api(`/api/milestones/${id}`,'PATCH',data));
    }
    else if(action==='requirement')openForm('Add completion condition',field('title','Required condition','text','','required maxlength="160"'),data=>api('/api/requirements','POST',{...data,goal_id:id}));
    else if(action==='weekly-target')openForm('Set weekly target',field('minutes','Weekly target (minutes; 0 means no target)','number',button.dataset.minutes,'required min="0" max="10080"')+'<p class="meta">Applies to the Monday–Sunday week containing the selected date. Planned time does not award credits.</p>',data=>api(`/api/weeks/${selectedDate}/outcomes/${id}`,'PUT',data));
    else if(action==='day')dayForm();
    else if(action==='unschedule')mutate(`/api/blocks/${id}`,'DELETE',{},'Appointment removed. The task is still available.');
    else if(action==='auto')mutate(`/api/days/${selectedDate}/auto-plan`,'POST',{},r=>`Scheduled: ${r.scheduled}. Still unscheduled: ${r.unplaced}.`);
    else if(action==='reload')load();
    else if(['prev','next','today'].includes(action)) {
      if(action==='today')selectedDate=localDate();
      else {const d=new Date(`${selectedDate}T12:00:00`);d.setDate(d.getDate()+(action==='next'?1:-1));selectedDate=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
      load();
    }
  });
  content.addEventListener('change',async event=>{
    if(event.target.id==='backup-file') {
      const file=event.target.files[0];if(!file)return;
      try {
        if(file.size>8*1024*1024)throw Error('Backup files must be no larger than 8 MB.');
        const backup=JSON.parse(await file.text());
        if(backup.format!=='focusdesk-backup'||backup.version!==1||!backup.tables)throw Error('This is not a supported FocusDesk backup.');
        openForm('Confirm backup restoration',`<p>File: ${escape(file.name)}</p><p class="meta">This file will replace the current space. Existing data will first be saved as a downloadable recovery copy.</p>`+field('confirm','Type RESTORE to confirm','text','','required pattern="RESTORE"'),()=>api('/api/restore','POST',{backup,confirmation:'RESTORE'}),'Restore data');
      }catch(error){notify(error.message,true);}finally{event.target.value='';}
    }
    if(event.target.id==='selected-date'&&event.target.value){selectedDate=event.target.value;load();}
    if(event.target.matches('[data-complete]')){event.target.checked=!event.target.checked;completeForm(Number(event.target.dataset.complete));}
    if(event.target.matches('[data-requirement]')){const done=event.target.checked;event.target.checked=!done;mutate(`/api/requirements/${event.target.dataset.requirement}`,'PATCH',{done});}
  });
  $('#global-add').addEventListener('click',()=>route==='goals'?goalForm():route==='calendar'?recurringForm():taskForm());
  $('#close-editor').addEventListener('click',()=>dialog.close());$('#cancel-editor').addEventListener('click',()=>dialog.close());
  $('#editor-form').addEventListener('submit',async event=>{
    event.preventDefault();const button=$('#save-editor');if(button.disabled)return;button.disabled=true;$('#editor-error').textContent='';
    try{const result=await modalSave(Object.fromEntries(new FormData(event.target)));dialog.close();await load();notify(result?.message||'Saved');}
    catch(error){$('#editor-error').textContent=error.message;}finally{button.disabled=false;}
  });
  window.addEventListener('hashchange',()=>{if(state)render();});
  load();
})();
