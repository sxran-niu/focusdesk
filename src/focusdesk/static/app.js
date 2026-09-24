/* Small native interface. Scheduling and outcome calculations live in Python. */
(() => {
  const $ = (selector, parent = document) => parent.querySelector(selector);
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clock = minutes => `${String(Math.floor(minutes / 60)).padStart(2,'0')}:${String(minutes % 60).padStart(2,'0')}`;
  const duration = minutes => minutes >= 60 ? `${Math.floor(minutes / 60)} 小时${minutes % 60 ? ` ${minutes % 60} 分` : ''}` : `${minutes} 分钟`;
  const localDate = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
  const categories = {study:'学习',life:'生活',rest:'休息'};
  const priorities = {1:'低优先级',2:'普通',3:'高优先级'};
  let selectedDate = localDate(), state, route = 'today', goalId, taskFilter = 'open', modalSave, loading = false;
  let noticeTimer, requestSequence = 0;
  const content = $('#page-content');
  const dialog = $('#editor');

  async function api(path, method='GET', data) {
    const response = await fetch(path, {method, headers:{'Content-Type':'application/json','X-FocusDesk-Token':$('meta[name="focusdesk-token"]').content}, body:data === undefined ? undefined : JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '暂时无法保存，请稍后重试。');
    return result;
  }
  function notify(message, error=false) {
    clearTimeout(noticeTimer); const el = $('#notice'); el.textContent=message; el.classList.toggle('error',error); el.hidden=false;
    noticeTimer=setTimeout(()=>el.hidden=true,5000);
  }
  function tag(category) { return `<span class="tag ${category}">${categories[category]}</span>`; }
  function outcomePath(task) {
    const outcome=state.outcomes.find(o=>o.id===task.outcome_id);
    if (!outcome) return '独立任务';
    const phase=state.milestones.find(m=>m.id===outcome.milestone_id);
    return `${escape(phase?.title)} / ${escape(outcome.title)}`;
  }
  function taskMeta(task) { return `${duration(task.minutes)} · ${task.due_date ? escape(task.due_date)+' 截止' : '无截止日期'}`; }
  function field(name,label,type='text',value='',extra='') {
    return `<label class="field" for="f-${name}">${label}<input id="f-${name}" name="${name}" type="${type}" value="${escape(value)}" ${extra}></label>`;
  }
  function select(name,label,options,value) {
    return `<label class="field" for="f-${name}">${label}<select id="f-${name}" name="${name}">${options.map(([v,t])=>`<option value="${escape(v)}" ${String(v)===String(value)?'selected':''}>${escape(t)}</option>`).join('')}</select></label>`;
  }
  function textarea(name,label,value='') { return `<label class="field" for="f-${name}">${label}<textarea id="f-${name}" name="${name}" maxlength="2000">${escape(value)}</textarea></label>`; }
  function openForm(title,fields,save,button='保存') {
    $('#editor-title').textContent=title;$('#editor-fields').innerHTML=fields;$('#editor-error').textContent='';$('#save-editor').textContent=button;modalSave=save;dialog.showModal();
  }
  function taskForm(id) {
    const task=state.tasks.find(t=>t.id===id) || {category:'study',minutes:60,priority:2};
    const associations=[['','独立任务，不关联长期目标'],...state.outcomes.map(o=>{const m=state.milestones.find(m=>m.id===o.milestone_id);const g=state.goals.find(g=>g.id===m.goal_id);return [o.id,`${g.title} / ${m.title} / ${o.title}`];})];
    openForm(id?'编辑任务':'新建任务',
      field('title','任务名称','text',task.title,'required maxlength="160"')+
      `<div class="form-grid">${select('category','类型',Object.entries(categories),task.category)}${field('minutes','预计用时（分钟）','number',task.minutes,'required min="5" max="720"')}</div>`+
      `<div class="form-grid">${field('due_date','截止日期（可选）','date',task.due_date)}${select('priority','优先级',Object.entries(priorities),task.priority)}</div>`+
      select('outcome_id','关联课程或成果（可选）',associations,task.outcome_id??'')+textarea('notes','备注（可选）',task.notes),
      data=>api(id?`/api/tasks/${id}`:'/api/tasks',id?'PATCH':'POST',data));
  }
  function completeForm(id) {
    const task=state.tasks.find(t=>t.id===id);
    if(task.status==='done')return mutate(`/api/tasks/${id}/complete`,'POST',{done:false},'任务已恢复为待完成');
    openForm('记录完成',`<p>${escape(task.title)}</p>`+field('actual_minutes','实际用时（分钟）','number',task.minutes,'required min="0" max="1440"')+'<p class="meta">请确认实际用时。任务完成不改变课程成果或学分。</p>',data=>api(`/api/tasks/${id}/complete`,'POST',{done:true,actual_minutes:data.actual_minutes}),'确认完成');
  }
  function scheduleForm(id) {
    const task=state.tasks.find(t=>t.id===id);
    const gap=state.gaps.find(([a,b])=>b-a>=task.minutes);
    openForm('加入当日日程',`<p>${escape(task.title)} · ${duration(task.minutes)}</p><p class="meta">${selectedDate}</p>`+field('start','开始时间','time',clock(gap?.[0]??state.day.start),'required')+'<p class="meta">已有安排会被保留，重叠的时间段无法保存。</p>',data=>api(`/api/days/${selectedDate}/blocks`,'POST',{...data,task_id:id}),'加入日程');
  }
  function rescheduleForm(id) {
    const block=state.blocks.find(b=>b.id===id), task=state.tasks.find(t=>t.id===block.task_id);
    openForm('改期 / 调整时间',`<p>${escape(task.title)}</p><p class="meta">原安排：${block.date} ${clock(block.start)}–${clock(block.end)}</p><div class="form-grid">`+
      field('date','目标日期','date',selectedDate,'required')+field('start','开始时间','time',clock(block.start),'required')+'</div><p class="meta">可移到所选日期或推迟到其他日期。原安排保留在历史中，保存失败不会改变原日程。</p>',data=>api(`/api/blocks/${id}`,'PATCH',data));
  }
  function scheduleHistory(id) {
    const changes=state.changes.filter(c=>c.entity==='schedule'&&c.entity_id===id);
    const label=raw=>{const b=JSON.parse(raw);return b?`${b.date} ${clock(b.start)}–${clock(b.end)}`:'移出日程';};
    return changes.length?`<details class="history"><summary>安排历史（${changes.length}）</summary>${changes.map(c=>`<p>${escape(c.created_at)} · ${escape(label(c.old_value))} → ${escape(label(c.new_value))}</p>`).join('')}</details>`:'';
  }
  function dayForm() {
    openForm('当日可安排时间',`<p class="meta">${selectedDate}</p><div class="form-grid">${field('start','开始时间','time',clock(state.day.start),'required')}${field('end','结束时间','time',clock(state.day.end),'required')}</div>`,data=>api(`/api/days/${selectedDate}`,'PUT',data));
  }
  function dateToolbar(extra='') {
    return `<div class="toolbar"><div class="toolbar-group"><button class="icon-button" data-action="prev" aria-label="前一天">‹</button><input class="date-picker" type="date" value="${selectedDate}" id="selected-date" aria-label="查看日期"><button class="icon-button" data-action="next" aria-label="后一天">›</button><button class="text-button" data-action="today">回到今天</button></div>${extra}</div>`;
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
        if(block.start>cursor)agenda+=`<div class="free-time">${clock(cursor)}–${clock(block.start)} · ${duration(block.start-cursor)} 留白</div>`;
        agenda+=`<article class="agenda-item"><div class="time-label">${clock(block.start)}<span>${clock(block.end)}</span></div><div class="task-block ${block.category}"><div class="task-body"><div class="task-title">${escape(block.title)}</div><p class="meta">固定安排 · ${categories[block.category]} · ${duration(block.end-block.start)}</p><button class="text-button" data-action="cancel-fixed" data-id="${block.id}">取消这一次</button></div></div></article>`;
        cursor=block.end;continue;
      }
      const task=tasksById.get(block.task_id);
      if(block.start>cursor)agenda+=`<div class="free-time">${clock(cursor)}–${clock(block.start)} · ${duration(block.start-cursor)} 留白</div>`;
      agenda+=`<article class="agenda-item ${task.status==='done'?'done':''}"><div class="time-label">${clock(block.start)}<span>${clock(block.end)}</span></div><div class="task-block ${task.category}"><input class="check" type="checkbox" data-complete="${task.id}" ${task.status==='done'?'checked':''} aria-label="${task.status==='done'?'重新打开':'完成'}：${escape(task.title)}"><div class="task-body"><div class="task-title">${escape(task.title)}</div><div class="meta">${categories[task.category]} · ${duration(block.end-block.start)}${task.status==='done'?` · 实际 ${duration(task.actual_minutes)}`:''}</div><div class="meta">${outcomePath(task)}</div><div class="task-controls"><button class="text-button" data-action="edit-task" data-id="${task.id}">编辑</button>${task.status==='open'?`<button class="text-button" data-action="reschedule" data-id="${block.id}">改期 / 改时间</button>`:''}<button class="text-button" data-action="unschedule" data-id="${block.id}">移出日程</button></div></div></div></article>`;
      cursor=block.end;
    }
    if(cursor<state.day.end)agenda+=`<div class="free-time">${clock(cursor)}–${clock(state.day.end)} · ${duration(state.day.end-cursor)} 留白</div>`;
    const carryover=state.carryover.map(block=>{const task=tasksById.get(block.task_id);return `<article class="backlog-item"><div class="task-title">${escape(task.title)}</div><p class="meta">原安排 ${block.date} ${clock(block.start)} · ${duration(task.minutes)}</p><div class="task-controls"><button class="button small" data-action="reschedule" data-id="${block.id}">移到所选日 / 改期</button><button class="text-button" data-action="complete-task" data-id="${task.id}">记录完成</button></div>${scheduleHistory(task.id)}</article>`;}).join('');
    const list=backlog.map(task=>`<article class="backlog-item"><div class="task-title">${escape(task.title)}</div><div class="meta">${taskMeta(task)}</div><div class="backlog-actions">${tag(task.category)}<div><button class="text-button" data-action="edit-task" data-id="${task.id}">编辑</button><button class="button small" data-action="schedule" data-id="${task.id}">安排时间</button></div></div></article>`).join('');
    content.innerHTML=dateToolbar(`<button class="button" data-action="day">可安排 ${clock(state.day.start)}–${clock(state.day.end)} <span aria-hidden="true">⌄</span></button>`)+
      `<section class="allocation" aria-label="当日时间分配"><div class="allocation-label"><span>已安排 <strong>${duration(used)}</strong></span><span class="muted">留白 ${duration(capacity-used)}</span></div><div class="allocation-track" role="img" aria-label="学习${totals.study}分钟，生活${totals.life}分钟，休息${totals.rest}分钟，留白${capacity-used}分钟">${Object.entries(totals).map(([cat,n])=>`<span class="${cat}-fill" style="width:${n/capacity*100}%"></span>`).join('')}</div><div class="allocation-legend">${Object.entries(totals).map(([cat,n])=>`<span><i class="legend-dot ${cat}-fill"></i>${categories[cat]} ${duration(n)}</span>`).join('')}</div></section>`+
      `<div class="day-grid"><section class="panel"><div class="panel-heading"><h2>当日日程</h2><span class="meta">${blocks.length} 项 · ${blocks.filter(b=>!b.fixed&&tasksById.get(b.task_id).status==='done').length} 项已完成</span></div>${blocks.length?agenda:`<div class="empty"><h3>今天还没有安排</h3><p>给任务留出具体的开始时间。</p><button class="button" data-action="new-task">＋ 新建任务</button></div>`}</section><aside>${carryover?`<section class="panel" style="margin-bottom:20px"><div class="panel-heading"><h2>此前未完成</h2><span class="meta">${state.carryover.length} 项</span></div>${carryover}</section>`:''}<section class="panel"><div class="panel-heading"><h2>待安排</h2><span class="meta">${backlog.length} 项</span></div><div class="backlog-list">${list||'<p class="empty">所有待办都已有安排。</p>'}</div>${backlog.length?'<button class="button primary" data-action="auto" style="width:100%;margin-top:20px">填入空闲时段</button><p class="meta" style="margin-top:10px">按截止日期、优先级排列，保留现有日程。放不下的任务会留在这里。</p>':''}</section>${overdue.length?`<div class="hint warning">${overdue.length} 项任务已过截止日期，请检查是否需要调整。</div>`:''}</aside></div>`;
  }
  function renderTasks() {
    const tasks=state.tasks.filter(t=>taskFilter==='all'||t.status===taskFilter).slice().reverse();
    content.innerHTML=`<div class="toolbar"><div class="filter-group">${[['open','待完成'],['done','已完成'],['all','全部']].map(([id,title])=>`<button class="filter-button" data-action="filter" data-filter="${id}" aria-pressed="${taskFilter===id}">${title}</button>`).join('')}</div><span class="meta">${tasks.length} 项任务</span></div><section class="panel task-list">${tasks.map(task=>{
      const block=state.blocks.find(b=>b.task_id===task.id);
      return `<article class="task-list-row ${task.status==='done'?'done':''}"><input class="check" type="checkbox" data-complete="${task.id}" ${task.status==='done'?'checked':''} aria-label="${task.status==='done'?'重新打开':'完成'}：${escape(task.title)}"><div class="task-body"><div class="task-title">${escape(task.title)}</div><div class="meta">${taskMeta(task)} · ${priorities[task.priority]}</div><div class="meta">${outcomePath(task)}</div>${block?`<div class="meta">已安排 ${block.date} ${clock(block.start)}–${clock(block.end)}</div>`:''}${task.status==='done'?`<div class="meta">${escape(task.completed_at.slice(0,10))} 完成 · 实际 ${duration(task.actual_minutes)}</div>`:''}${task.notes?`<p class="meta">${escape(task.notes)}</p>`:''}${scheduleHistory(task.id)}</div><div class="task-controls">${block&&task.status==='open'?`<button class="text-button" data-action="reschedule" data-id="${block.id}">改期 / 改时间</button>`:''}${tag(task.category)}<button class="text-button" data-action="edit-task" data-id="${task.id}">编辑</button><button class="text-button" data-action="delete-task" data-id="${task.id}">删除</button></div></article>`;
    }).join('')||'<div class="empty"><h3>这里还没有任务</h3><p>把一件具体、能完成的事情记下来。</p><button class="button" data-action="new-task">＋ 新建任务</button></div>'}</section>`;
  }
  const weekdays=['周一','周二','周三','周四','周五','周六','周日'];
  function recurringForm() {
    const end=new Date(`${selectedDate}T12:00:00`);end.setDate(end.getDate()+90);
    const endDate=`${end.getFullYear()}-${String(end.getMonth()+1).padStart(2,'0')}-${String(end.getDate()).padStart(2,'0')}`;
    openForm('添加重复固定安排',field('title','安排名称','text','','required maxlength="160"')+
      `<div class="form-grid">${select('category','类型',Object.entries(categories),'study')}${select('weekday','每周',weekdays.map((v,i)=>[i,v]),0)}</div>`+
      `<div class="form-grid">${field('start_date','开始日期','date',selectedDate,'required')}${field('end_date','结束日期','date',endDate,'required')}</div>`+
      `<div class="form-grid">${field('start','开始时间','time','09:00','required')}${field('end','结束时间','time','10:00','required')}</div>`+
      '<p class="meta">最多设置 366 天。所有发生日期均检查冲突和当日可用时间；任一冲突时整组不保存。固定安排占用时间，不自动记录学习完成或学分。</p>',data=>api('/api/recurring','POST',data));
  }
  function renderCalendar() {
    const end=new Date(`${selectedDate}T12:00:00Z`);end.setUTCDate(end.getUTCDate()+6);const last=end.toISOString().slice(0,10);
    const slots=state.fixed_blocks.filter(b=>b.date>=selectedDate&&b.date<=last).sort((a,b)=>a.date.localeCompare(b.date)||a.start-b.start);
    content.innerHTML=dateToolbar('<button class="button primary" data-action="new-recurring">＋ 添加重复安排</button>')+
      `<section class="panel"><h2>重复规则</h2><p class="meta">固定时段会显示在当日日程并阻止重叠排程。取消单次不会影响其他周；停用仅取消今天及以后，过去记录保留。</p>${state.recurring_rules.map(r=>`<article class="task-list-row"><div class="task-body"><h3>${escape(r.title)}</h3><p class="meta">${weekdays[r.weekday]} ${clock(r.start)}–${clock(r.end)} · ${escape(r.start_date)} 至 ${escape(r.end_date)} · ${r.active?'已启用':'已停用'}</p></div>${r.active?`<button class="text-button" data-action="stop-recurring" data-id="${r.id}">停止后续安排</button>`:''}</article>`).join('')||'<p class="empty">添加每周课程、兼职或固定休息时间。</p>'}</section>`+
      `<section class="panel" style="margin-top:20px"><div class="panel-heading"><h2>所选日起七天</h2><span class="meta">${selectedDate} — ${last}</span></div>${slots.map(b=>`<article class="task-list-row"><div class="task-body"><h3>${escape(b.title)}</h3><p class="meta">${b.date} ${clock(b.start)}–${clock(b.end)}</p></div><button class="text-button" data-action="cancel-fixed" data-id="${b.id}">取消这一次</button></article>`).join('')||'<p class="empty">这七天没有固定安排。</p>'}</section>`;
  }
  function goalForm(id) {
    const goal=state.goals.find(g=>g.id===id)||{target:120,unit:'学分'};
    openForm(id?'编辑长期目标':'新建长期目标',field('title','目标名称','text',goal.title,'required maxlength="160"')+
      `<div class="form-grid">${field('target','成果目标数量','number',goal.target,'required min="0.01" max="100000" step="0.01"')}${field('unit','计量单位','text',goal.unit,'required maxlength="20"')}</div>`+
      field('target_date','目标完成日期','date',goal.target_date,'required')+textarea('notes','完成条件说明（可选）',goal.notes)+
      '<p class="meta">例如：两年完成硕士，目标 120 学分。必修、论文等条件可在目标中单独添加。</p>',
      async data=>{const result=await api(id?`/api/goals/${id}`:'/api/goals',id?'PATCH':'POST',data);goalId=id||result.id;location.hash=`goals/${goalId}`;});
  }
  function milestoneForm(goal) {
    const phases=state.milestones.filter(m=>m.goal_id===goal.id);
    const latest=phases.slice().sort((a,b)=>b.end_date.localeCompare(a.end_date))[0];
    openForm('添加阶段 / 学期',field('title','阶段名称','text','', 'required maxlength="160"')+
      `<div class="form-grid">${field('start_date','开始日期','date',latest?.end_date||state.today,'required')}${field('end_date','结束日期','date','','required')}</div>`+
      field('target',`本阶段计划（${escape(goal.unit)}）`,'number','','required min="0.01" max="100000" step="0.01"'),data=>api('/api/milestones','POST',{...data,goal_id:goal.id}));
  }
  function outcomeForm(milestoneId,id) {
    const outcome=state.outcomes.find(o=>o.id===id)||{};
    const phase=state.milestones.find(m=>m.id===(milestoneId||outcome.milestone_id));
    const goal=state.goals.find(g=>g.id===phase.goal_id);
    openForm(id?'编辑课程 / 成果':'添加课程 / 成果',`<p class="meta">${escape(goal.title)} / ${escape(phase.title)}</p>`+
      field('title','课程或成果名称','text',outcome.title,'required maxlength="160"')+
      field('amount',`通过后确认的数量（${escape(goal.unit)}）`,'number',outcome.amount||6,'required min="0.01" max="100000" step="0.01"')+
      '<p class="meta">同一门课程只建一条记录。尚未确认的数量不会计入目标进度。</p>',data=>api(id?`/api/outcomes/${id}`:'/api/outcomes',id?'PATCH':'POST',{...data,milestone_id:phase.id}));
  }
  function resultForm(id) {
    const outcome=state.outcomes.find(o=>o.id===id);
    openForm('记录成果 / 考核结果',`<p>${escape(outcome.title)}</p>`+
      select('status','确认状态',[['pending','待确认 / 尚未出分'],['passed','已通过，成果数量已确认'],['failed','未通过 / 本次未达成']],outcome.status)+
      `<div class="form-grid">${field('result_date','出分或确认日期','date',outcome.result_date||state.today,`max="${state.today}"`)}${field('grade','成绩（可选）','text',outcome.grade,'maxlength="40"')}</div>`+
      textarea('notes','结果说明 / 复盘',outcome.notes)+
      '<p class="meta">以实际确认结果为准。重复保存同一结果不会重复累计。</p>',data=>api(`/api/outcomes/${id}/result`,'PUT',data),'保存结果');
  }
  function renderGoals() {
    const hashId=Number(location.hash.split('/')[1]);
    if(state.goals.some(g=>g.id===hashId))goalId=hashId;
    if(!state.goals.some(g=>g.id===goalId))goalId=state.goals[0]?.id;
    const goal=state.goals.find(g=>g.id===goalId);
    if(!goal){content.innerHTML='<section class="panel empty"><h2>为日常行动设定一个方向</h2><p>先建立长期目标，再添加阶段、课程或成果。</p><button class="button primary" data-action="new-goal">＋ 新建目标</button></section>';return;}
    const phases=state.milestones.filter(m=>m.goal_id===goal.id);
    const requirements=state.requirements.filter(r=>r.goal_id===goal.id);
    const percent=Math.min(100,goal.earned/goal.target*100);
    const goalHistory=state.changes.filter(c=>c.entity==='goal'&&c.entity_id===goal.id);
    content.innerHTML=`<div class="goal-grid"><div class="goal-options">${state.goals.map(g=>`<button class="goal-choice ${g.id===goal.id?'selected':''}" data-action="select-goal" data-id="${g.id}" aria-pressed="${g.id===goal.id}"><span>${escape(g.title)}</span><span class="meta">${g.earned} / ${g.target} ${escape(g.unit)}</span></button>`).join('')}</div><div class="goal-detail"><section class="panel"><div class="panel-heading"><h2>${escape(goal.title)}</h2><button class="text-button" data-action="edit-goal" data-id="${goal.id}">编辑目标</button></div><p class="meta">目标日期 ${goal.target_date}${goal.achieved?' · 所设完成条件已满足':''}</p><div class="goal-stats"><div><div class="meta">已确认成果</div><div class="goal-number numbers">${goal.earned}<span class="meta"> / ${goal.target} ${escape(goal.unit)}</span></div></div><div><div class="meta">待确认</div><div class="goal-number numbers">${goal.pending}<span class="meta"> ${escape(goal.unit)}</span></div></div><div><div class="meta">距离数量目标</div><div class="goal-number numbers">${Math.max(0,Math.round((goal.target-goal.earned)*100)/100)}<span class="meta"> ${escape(goal.unit)}</span></div></div></div><div class="progress-track" role="progressbar" aria-label="已确认成果进度" aria-valuenow="${Math.min(goal.earned,goal.target)}" aria-valuemin="0" aria-valuemax="${goal.target}"><div class="progress-fill" style="width:${percent}%"></div></div><p class="meta" style="margin-top:12px">每日任务记录行动；只有已确认的成果计入此进度。</p>${goal.notes?`<p class="meta" style="margin-top:12px">${escape(goal.notes)}</p>`:''}${goal.planned!==goal.target?`<div class="hint warning">阶段计划合计 ${goal.planned} ${escape(goal.unit)}，总目标为 ${goal.target} ${escape(goal.unit)}，请检查阶段分配。</div>`:''}${goalHistory.length?`<details class="history"><summary>目标数量修改记录</summary>${goalHistory.map(c=>`<p>${escape(c.created_at.slice(0,10))} · ${escape(c.old_value)} → ${escape(c.new_value)}</p>`).join('')}</details>`:''}</section><section class="panel"><div class="panel-heading"><h3>其他完成条件</h3><button class="button small" data-action="requirement" data-id="${goal.id}">＋ 添加条件</button></div>${requirements.map(r=>`<label class="requirement-row"><input type="checkbox" class="check" data-requirement="${r.id}" ${r.done?'checked':''}><span>${escape(r.title)}</span></label>`).join('')||'<p class="meta">可添加必修模块、论文或其他必须满足的条件。</p>'}</section><div class="panel-heading" style="margin:4px 0 0"><h2>阶段与成果</h2><button class="button" data-action="milestone" data-id="${goal.id}">＋ 添加阶段</button></div>${phases.map((phase,index)=>{
      const outcomes=state.outcomes.filter(o=>o.milestone_id===phase.id);
      const changes=state.changes.filter(c=>c.entity==='milestone'&&c.entity_id===phase.id);
      const ended=phase.end_date<state.today;
      const shortage=Math.max(0,Math.round((phase.target-phase.earned)*100)/100);
      return `<details class="term" ${index===0||phase.start_date<=state.today&&phase.end_date>=state.today?'open':''}><summary><strong>${escape(phase.title)}</strong><span class="meta">${phase.start_date} — ${phase.end_date} · 已确认 ${phase.earned} / 计划 ${phase.target} ${escape(goal.unit)}</span></summary><div class="term-content"><div class="term-toolbar"><button class="button small" data-action="outcome" data-id="${phase.id}">＋ 添加课程 / 成果</button><button class="text-button" data-action="revise" data-id="${phase.id}">调整阶段目标</button></div>${outcomes.map(outcome=>`<article class="outcome-row"><div class="outcome-body"><div class="task-title">${escape(outcome.title)}</div><div class="meta">${outcome.amount} ${escape(goal.unit)}${outcome.grade?' · 成绩 '+escape(outcome.grade):''}${outcome.result_date?' · '+escape(outcome.result_date)+' 确认':''}</div>${outcome.notes?`<p class="meta">${escape(outcome.notes)}</p>`:''}</div><span class="tag ${outcome.status}">${{pending:'待确认',passed:'已确认',failed:'未通过'}[outcome.status]}</span><button class="button small" data-action="result" data-id="${outcome.id}">记录结果</button><button class="text-button" data-action="edit-outcome" data-id="${outcome.id}">编辑</button></article>`).join('')||'<p class="empty">添加课程或成果后，就能关联每日任务。</p>'}${ended&&shortage?`<div class="hint warning">阶段已结束，已确认成果比计划少 ${shortage} ${escape(goal.unit)}${phase.pending?`，另有 ${phase.pending} ${escape(goal.unit)}待确认`:''}。请核实结果，再考虑后续安排。</div>`:''}${outcomes.some(o=>o.status==='failed')?'<div class="hint warning">本阶段有未通过的成果，可在结果说明中记录补考或下一步安排。</div>':''}<div class="history">原计划：${phase.original_target} ${escape(goal.unit)}${changes.length?`<details><summary>查看 ${changes.length} 次调整</summary>${changes.map(c=>`<p>${escape(c.created_at.slice(0,10))} · ${escape(c.old_value)} → ${escape(c.new_value)}</p>`).join('')}</details>`:''}</div></div></details>`;
    }).join('')||'<section class="panel empty">把长期目标拆成学期、月份或其他阶段。</section>'}</div></div>`;
  }
  async function renderWeek() {
    const viewingDate=selectedDate;
    content.innerHTML='<p class="empty">正在汇总本周计划…</p>';
    try {
      const plan=await api(`/api/weekly-plan?date=${viewingDate}`);
      if(route!=='week'||selectedDate!==viewingDate)return;
      content.innerHTML=dateToolbar(`<span class="meta">${plan.start} — ${plan.end}</span>`)+
        `<section class="panel"><h2>把本周投入安排到日程</h2><p class="meta">按课程设定本周预计投入，再给关联任务安排时间。这里的分钟数不转换为学分；实际投入按完成日期单独统计。</p><div class="hint">本周尚有 ${duration(plan.free_minutes)} 空闲 · 课程计划中 ${duration(plan.unplanned_minutes)} 尚未安排</div>${plan.unplanned_minutes>plan.free_minutes?'<p class="hint warning">计划缺口超过本周剩余可用时间，请减少计划或调整日程。</p>':''}</section>`+
        plan.courses.map(row=>`<section class="panel" style="margin-top:16px"><div class="panel-heading"><div><h3>${escape(row.title)}</h3><p class="meta">${escape(row.goal)} / ${escape(row.milestone)}</p></div><button class="button small" data-action="weekly-target" data-id="${row.outcome_id}" data-minutes="${row.target_minutes}">设置本周投入</button></div><div class="review-metrics"><p>本周计划 <strong>${duration(row.target_minutes)}</strong></p><p>已安排 <strong>${duration(row.scheduled_minutes)}</strong></p><p>实际投入 <strong>${duration(row.actual_minutes)}</strong></p></div><p class="${row.unplanned_minutes?'hint warning':'meta'}">${row.target_minutes?`还有 ${duration(row.unplanned_minutes)} 尚未安排`:'尚未设置本周投入目标'}</p><p class="meta">关联的未完成任务共预计 ${duration(row.remaining_task_minutes)}（包含其他周任务）。请在任务中关联此课程，再进入当日日程安排时间。</p><div class="task-controls"><a class="button small" href="#tasks">查看任务</a><a class="button small" href="#today">安排所选日</a></div></section>`).join('')+
        (plan.courses.length?'':'<section class="panel empty" style="margin-top:16px"><p>先在长期目标中添加阶段与课程，再设定本周计划。</p><a class="button" href="#goals">打开长期进度</a></section>');
    } catch(error) {if(route==='week')content.innerHTML=`<p class="empty">${escape(error.message)}</p>`;}
  }
  async function renderReview() {
    const reviewingDate=selectedDate;
    content.innerHTML='<p class="empty">正在汇总本周记录…</p>';
    try {
      const report=await api(`/api/report?date=${reviewingDate}`);
      if(route!=='review'||reviewingDate!==selectedDate)return;
      const max=Math.max(60,...report.days.map(d=>d.actual));
      content.innerHTML=dateToolbar(`<span class="meta">${report.start} — ${report.end}</span>`)+
        `<div class="review-metrics"><div class="panel"><div class="meta">已完成任务</div><div class="review-value">${report.completed}<span class="meta"> 项</span></div></div><div class="panel"><div class="meta">计划时间</div><div class="review-value">${report.planned_minutes}<span class="meta"> 分钟</span></div></div><div class="panel"><div class="meta">实际投入</div><div class="review-value">${report.actual_minutes}<span class="meta"> 分钟</span></div></div></div><section class="panel"><div class="panel-heading"><h2>每日实际投入</h2><span class="meta">分钟 / 按完成日期归属</span></div><div class="review-bars" role="img" aria-label="${report.days.map(d=>d.date+' 实际 '+d.actual+' 分钟').join('，')}">${report.days.map(d=>`<div class="review-bar-column"><span class="numbers">${d.actual}</span><div class="review-bar" style="height:${d.actual/max*155}px"></div><span>${d.date.slice(5)}</span></div>`).join('')}</div><table class="allocation-table"><thead><tr><th>类型</th><th>计划（分钟）</th><th>实际（分钟）</th></tr></thead><tbody>${Object.entries(report.categories).map(([cat,n])=>`<tr><td>${categories[cat]}</td><td>${n.planned}</td><td>${n.actual}</td></tr>`).join('')}</tbody></table><p class="meta" style="margin-top:15px">已完成任务的实际用时比预计${report.estimate_difference>=0?'多':'少'} ${Math.abs(report.estimate_difference)} 分钟。计划按日程日期统计，实际投入按完成日期统计。</p></section><section class="panel" style="margin-top:20px"><div class="panel-heading"><h3>保存本周回顾</h3><div class="report-links"><a class="button" href="/api/export/md?date=${selectedDate}" download>文字报告</a><a class="button" href="/api/export/csv?date=${selectedDate}" download>日程 CSV</a><a class="button" href="/api/export/svg?date=${selectedDate}" download>保存图表 SVG</a></div></div><p class="meta">导出文件保留在你的电脑上，长期目标另按已确认成果统计。</p></section>`;
    } catch(error) {if(route==='review')content.innerHTML=`<div class="panel empty"><p>${escape(error.message)}</p><button class="button" data-action="reload">重试</button></div>`;}
  }
  async function load() {
    const sequence=++requestSequence;
    try {
      const result=await api(`/api/state?date=${selectedDate}`);
      if(sequence!==requestSequence)return;
      state=result;render();
    } catch(error) { content.innerHTML=`<div class="panel empty"><p>${escape(error.message)}</p><button class="button" data-action="reload">重试</button></div>`; }
    finally {content.setAttribute('aria-busy','false');}
  }
  function render() {
    route=(location.hash.slice(1).split('/')[0]||'today');
    if(!['today','tasks','goals','week','calendar','review'].includes(route))route='today';
    const titles={today:['今日安排','DAILY PLANNER'],tasks:['任务清单','TASKS'],goals:['长期进度','GOALS & OUTCOMES'],calendar:['固定课表','RECURRING SCHEDULE'],week:['本周计划','WEEKLY PLAN'],review:['每周回顾','WEEKLY REVIEW']};
    $('#page-title').textContent=titles[route][0];$('#page-eyebrow').textContent=titles[route][1];document.title=`FocusDesk · ${titles[route][0]}`;
    document.querySelectorAll('[data-nav]').forEach(el=>{el.classList.toggle('active',el.dataset.nav===route);if(el.dataset.nav===route)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
    $('#global-add').textContent=route==='goals'?'＋ 新建目标':route==='calendar'?'＋ 重复安排':'＋ 新建任务';
    ({today:renderToday,tasks:renderTasks,goals:renderGoals,calendar:renderCalendar,week:renderWeek,review:renderReview}[route])();
  }
  async function mutate(path,method,data,message='已保存') {
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
      openForm('删除任务',`<p>删除「${escape(task.title)}」及它的日程安排？关联的课程成果会保留。</p>`,()=>api(`/api/tasks/${id}`,'DELETE',{}),'确认删除');
    }
    else if(action==='new-recurring')recurringForm();
    else if(action==='cancel-fixed')openForm('取消单次固定安排','<p>仅移除这一次固定安排，其他日期保持不变，取消记录会保留。</p>',()=>api(`/api/fixed-blocks/${id}`,'DELETE',{}),'确认取消');
    else if(action==='stop-recurring')openForm('停止后续安排','<p>取消今天及以后的所有发生日期，保留过去的固定安排和变更记录。</p>',()=>api(`/api/recurring/${id}`,'DELETE',{}),'停止安排');
    else if(action==='filter'){taskFilter=button.dataset.filter;renderTasks();}
    else if(action==='new-goal')goalForm();
    else if(action==='edit-goal')goalForm(id);
    else if(action==='select-goal'){goalId=id;location.hash=`goals/${id}`;}
    else if(action==='milestone')milestoneForm(state.goals.find(g=>g.id===id));
    else if(action==='outcome')outcomeForm(id);
    else if(action==='edit-outcome')outcomeForm(null,id);
    else if(action==='result')resultForm(id);
    else if(action==='revise') {
      const phase=state.milestones.find(m=>m.id===id);
      openForm('调整阶段目标',`<p>${escape(phase.title)}</p><p class="meta">初始计划 ${phase.original_target}，目前计划 ${phase.target}。修改会保留记录。</p>`+field('target','调整后的目标数量','number',phase.target,'required min="0.01" max="100000" step="0.01"'),data=>api(`/api/milestones/${id}`,'PATCH',data));
    }
    else if(action==='requirement')openForm('添加完成条件',field('title','必须满足的条件','text','','required maxlength="160"'),data=>api('/api/requirements','POST',{...data,goal_id:id}));
    else if(action==='weekly-target')openForm('设置本周投入',field('minutes','本周计划投入（分钟，0 表示不设目标）','number',button.dataset.minutes,'required min="0" max="10080"')+'<p class="meta">保存到所选日期所在的周一至周日。计划用时不计入学分。</p>',data=>api(`/api/weeks/${selectedDate}/outcomes/${id}`,'PUT',data));
    else if(action==='day')dayForm();
    else if(action==='unschedule')mutate(`/api/blocks/${id}`,'DELETE',{},'已移出日程，任务仍保留');
    else if(action==='auto')mutate(`/api/days/${selectedDate}/auto-plan`,'POST',{},r=>`已安排 ${r.scheduled} 项，${r.unplaced} 项仍待安排`);
    else if(action==='reload')load();
    else if(['prev','next','today'].includes(action)) {
      if(action==='today')selectedDate=localDate();
      else {const d=new Date(`${selectedDate}T12:00:00`);d.setDate(d.getDate()+(action==='next'?1:-1));selectedDate=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
      load();
    }
  });
  content.addEventListener('change',event=>{
    if(event.target.id==='selected-date'&&event.target.value){selectedDate=event.target.value;load();}
    if(event.target.matches('[data-complete]')){event.target.checked=!event.target.checked;completeForm(Number(event.target.dataset.complete));}
    if(event.target.matches('[data-requirement]')){const done=event.target.checked;event.target.checked=!done;mutate(`/api/requirements/${event.target.dataset.requirement}`,'PATCH',{done});}
  });
  $('#global-add').addEventListener('click',()=>route==='goals'?goalForm():route==='calendar'?recurringForm():taskForm());
  $('#close-editor').addEventListener('click',()=>dialog.close());$('#cancel-editor').addEventListener('click',()=>dialog.close());
  $('#editor-form').addEventListener('submit',async event=>{
    event.preventDefault();const button=$('#save-editor');if(button.disabled)return;button.disabled=true;$('#editor-error').textContent='';
    try{await modalSave(Object.fromEntries(new FormData(event.target)));dialog.close();await load();notify('已保存');}
    catch(error){$('#editor-error').textContent=error.message;}finally{button.disabled=false;}
  });
  window.addEventListener('hashchange',()=>{if(state)render();});
  load();
})();
