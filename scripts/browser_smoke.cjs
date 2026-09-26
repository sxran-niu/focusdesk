/* Optional browser acceptance test; always uses a temporary database. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');

(async () => {
  const socket = net.createServer();
  await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'focusdesk-browser-'));
  const server = spawn(process.env.FOCUSDESK_PYTHON || path.join(root, '.venv/bin/python'),
    ['-m', 'focusdesk', '--db', path.join(temp, 'test.sqlite3'), 'serve', '--port', String(port)], {cwd:root});
  let diagnostics = '';
  server.stderr.on('data', data => diagnostics += data);
  server.on('error', error => diagnostics += error.message);
  let browser;
  try {
    const base = `http://127.0.0.1:${port}`;
    let ready = false;
    for (let i=0; i<60; i++) {
      try { if ((await fetch(base+'/api/state')).ok) {ready=true;break;} } catch {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert(ready, diagnostics);
    browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_EXECUTABLE || undefined});
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base);
    await page.getByRole('heading', {name:'当日日程',exact:true}).waitFor();
    const api = (url, method='GET', data) => page.evaluate(async ({url,method,data}) => {
      const response = await fetch(url, {method,headers:{'Content-Type':'application/json','X-FocusDesk-Token':document.querySelector('meta[name="focusdesk-token"]').content},body:data===undefined?undefined:JSON.stringify(data)});
      const result=await response.json();
      if (!response.ok) throw Error(result.error);
      return result;
    }, {url,method,data});
    const today=(await api('/api/state')).today;
    const offset=(value,n)=>{const d=new Date(value+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);};
    const yesterday=offset(today,-1);
    const task=await api('/api/tasks','POST',{title:'跨日验收任务',minutes:45});
    await api(`/api/days/${yesterday}/blocks`,'POST',{task_id:task.id,start:'09:00'});
    await page.reload();
    await page.getByRole('heading',{name:'此前未完成'}).waitFor();
    await page.getByRole('button',{name:'移到所选日 / 改期'}).click();
    await page.locator('#f-start').fill('10:00');
    const save=async()=>{await page.locator('#save-editor').click();await page.locator('#editor').waitFor({state:'hidden'});};
    await save();
    await page.locator('.agenda-item').filter({hasText:'跨日验收任务'}).waitFor();
    assert.equal((await api('/api/state')).carryover.length,0);
    await page.getByRole('link',{name:'任务清单'}).click();
    await page.getByText('安排历史（1）',{exact:true}).waitFor();
    const goal=await api('/api/goals','POST',{title:'验收目标',target:6,unit:'学分',target_date:'2099-12-31'});
    const phase=await api('/api/milestones','POST',{goal_id:goal.id,title:'验收学期',target:6,start_date:today,end_date:'2098-12-31'});
    const outcome=await api('/api/outcomes','POST',{milestone_id:phase.id,title:'验收课程',amount:6});
    await api(`/api/tasks/${task.id}`,'PATCH',{outcome_id:outcome.id});
    await page.goto(base+'/#week');
    await page.getByRole('button',{name:'设置本周投入'}).click();
    await page.locator('#f-minutes').fill('360');await save();
    await page.getByText('还有 5 小时 15 分 尚未安排',{exact:true}).waitFor();
    assert.equal((await api('/api/state')).goals[0].earned,0);
    await page.goto(base+'/#calendar');
    await page.getByRole('button',{name:'＋ 添加重复安排',exact:true}).click();
    await page.locator('#f-title').fill('每周固定课');
    await page.locator('#f-weekday').selectOption(String((new Date(today+'T12:00:00Z').getUTCDay()+6)%7));
    await page.locator('#f-end_date').fill(offset(today,14));
    await save();
    assert.equal((await api('/api/state')).fixed_blocks.length,3);
    await page.goto(base+'/#today');
    const fixed=page.locator('.agenda-item').filter({hasText:'每周固定课'});
    await fixed.waitFor();
    await fixed.getByRole('button',{name:'取消这一次'}).click();await save();
    assert.equal((await api('/api/state')).fixed_blocks.length,2);
    await page.goto(base+'/#calendar');
    await page.getByRole('button',{name:'停止后续安排'}).click();await save();
    assert.equal((await api('/api/state')).fixed_blocks.length,0);
    const secondPhase=await api('/api/milestones','POST',{goal_id:goal.id,title:'迁移后的学期',target:6,start_date:today,end_date:'2098-12-31'});
    await page.goto(base+'/#goals');
    await page.getByRole('button',{name:'编辑阶段',exact:true}).first().click();
    await page.locator('#f-title').fill('调整后的学期');
    await page.locator('#f-end_date').fill('2097-12-31');await save();
    let courseRow=page.locator('.outcome-row').filter({hasText:'验收课程'});
    await courseRow.getByRole('button',{name:'编辑',exact:true}).click();
    await page.locator('#f-milestone_id').selectOption(String(secondPhase.id));await save();
    assert.equal((await api('/api/state')).outcomes[0].milestone_id,secondPhase.id);
    await courseRow.getByRole('button',{name:'记录结果'}).click();
    await page.locator('#f-status').selectOption('passed');await save();
    await page.getByRole('button',{name:'归档已完成目标'}).click();await save();
    await page.getByRole('button',{name:'已归档',exact:true}).click();
    await page.getByRole('button',{name:'取消归档'}).waitFor();
    assert.equal((await api('/api/state')).goals[0].earned,6);
    await page.getByRole('button',{name:'取消归档'}).click();
    await page.getByText('暂时没有已归档目标。完成目标后可以归档，所有成果仍会保留。',{exact:true}).waitFor();
    await page.getByRole('button',{name:'进行中的目标'}).click();
    await page.goto(base+'/#backup');
    const download=page.waitForEvent('download');
    await page.getByRole('link',{name:'下载完整备份 JSON'}).click();
    const backupPath=path.join(temp,'backup.json');await (await download).saveAs(backupPath);
    await api('/api/tasks','POST',{title:'恢复前新增任务'});
    await page.locator('#backup-file').setInputFiles(backupPath);
    await page.locator('#f-confirm').fill('恢复');await save();
    await page.getByRole('link',{name:/^before-restore-/}).waitFor();
    const restored=await api('/api/state');
    assert(!restored.tasks.some(t=>t.title==='恢复前新增任务'));
    assert.equal(restored.goals[0].earned,6);
    assert.equal(restored.tasks[0].outcome_id,outcome.id);
    // All four milestone flows above use this isolated test space.
    for (const width of [1440,390,320]) {
      await page.setViewportSize({width,height:1000});
      for (const route of ['today','tasks','goals','week','calendar','backup','review']) {
        await page.goto(base+'/#'+route);
        await page.locator('#page-content[aria-busy="false"]').waitFor();
        if (route==='backup') await page.getByRole('heading',{name:'恢复前的副本'}).waitFor();
        if (route==='week') await page.getByRole('heading',{name:'把本周投入安排到日程'}).waitFor();
        if (route==='review') await page.getByRole('heading',{name:'每日实际投入'}).waitFor();
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), `Overflow: ${route} at ${width}`);
      }
    }
    await page.setViewportSize({width:1440,height:1000});
    for(const route of ['today','week','calendar','goals','backup']) {
      await page.goto(base+'/#'+route);
      await page.locator('#page-content[aria-busy="false"]').waitFor();
      if(route==='week')await page.getByRole('heading',{name:'把本周投入安排到日程'}).waitFor();
      if(route==='backup')await page.getByRole('heading',{name:'恢复前的副本'}).waitFor();
      await page.screenshot({path:path.join(temp,route+'.png'),fullPage:true});
    }
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,temporaryDirectory:temp}));
  } finally {
    if(browser) await browser.close();
    server.kill('SIGTERM');
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
