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
    await page.getByRole('heading', {name:'Daily schedule',exact:true}).waitFor();
    assert.equal(await page.locator('html').getAttribute('lang'),'en');
    const api = (url, method='GET', data) => page.evaluate(async ({url,method,data}) => {
      const response = await fetch(url, {method,headers:{'Content-Type':'application/json','X-FocusDesk-Token':document.querySelector('meta[name="focusdesk-token"]').content},body:data===undefined?undefined:JSON.stringify(data)});
      const result=await response.json();
      if (!response.ok) throw Error(result.error);
      return result;
    }, {url,method,data});
    const today=(await api('/api/state')).today;
    const offset=(value,n)=>{const d=new Date(value+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);};
    const yesterday=offset(today,-1);
    const task=await api('/api/tasks','POST',{title:'Carryover test task',minutes:45});
    await api(`/api/days/${yesterday}/blocks`,'POST',{task_id:task.id,start:'09:00'});
    await page.reload();
    await page.getByRole('heading',{name:'Unfinished from earlier days'}).waitFor();
    await page.getByRole('button',{name:'Move / reschedule'}).click();
    await page.locator('#f-start').fill('10:00');
    const save=async()=>{await page.locator('#save-editor').click();await page.locator('#editor').waitFor({state:'hidden'});};
    await save();
    await page.locator('.agenda-item').filter({hasText:'Carryover test task'}).waitFor();
    assert.equal((await api('/api/state')).carryover.length,0);
    await page.getByRole('link',{name:'Tasks'}).click();
    await page.getByText('Schedule history (1)',{exact:true}).waitFor();
    const goal=await api('/api/goals','POST',{title:'Acceptance goal',target:6,unit:'credits',target_date:'2099-12-31'});
    const phase=await api('/api/milestones','POST',{goal_id:goal.id,title:'Acceptance semester',target:6,start_date:today,end_date:'2098-12-31'});
    const outcome=await api('/api/outcomes','POST',{milestone_id:phase.id,title:'Acceptance course',amount:6});
    await api(`/api/tasks/${task.id}`,'PATCH',{outcome_id:outcome.id});
    await page.goto(base+'/#week');
    await page.getByRole('button',{name:'Set weekly target'}).click();
    await page.locator('#f-minutes').fill('360');await save();
    await page.getByText('5 h 15 min still to schedule',{exact:true}).waitFor();
    assert.equal((await api('/api/state')).goals[0].earned,0);
    await page.goto(base+'/#calendar');
    await page.getByRole('button',{name:'＋ Add recurring appointment',exact:true}).click();
    await page.locator('#f-title').fill('Weekly class');
    await page.locator('#f-weekday').selectOption(String((new Date(today+'T12:00:00Z').getUTCDay()+6)%7));
    await page.locator('#f-end_date').fill(offset(today,14));
    await save();
    assert.equal((await api('/api/state')).fixed_blocks.length,3);
    await page.goto(base+'/#today');
    const fixed=page.locator('.agenda-item').filter({hasText:'Weekly class'});
    await fixed.waitFor();
    await fixed.getByRole('button',{name:'Cancel occurrence'}).click();await save();
    assert.equal((await api('/api/state')).fixed_blocks.length,2);
    await page.goto(base+'/#calendar');
    await page.getByRole('button',{name:'Stop future appointments'}).click();await save();
    assert.equal((await api('/api/state')).fixed_blocks.length,0);
    const secondPhase=await api('/api/milestones','POST',{goal_id:goal.id,title:'Destination semester',target:6,start_date:today,end_date:'2098-12-31'});
    await page.goto(base+'/#goals');
    await page.getByRole('button',{name:'Edit stage',exact:true}).first().click();
    await page.locator('#f-title').fill('Revised semester');
    await page.locator('#f-end_date').fill('2097-12-31');await save();
    let courseRow=page.locator('.outcome-row').filter({hasText:'Acceptance course'});
    await courseRow.getByRole('button',{name:'Edit',exact:true}).click();
    await page.locator('#f-milestone_id').selectOption(String(secondPhase.id));await save();
    assert.equal((await api('/api/state')).outcomes[0].milestone_id,secondPhase.id);
    await courseRow.getByRole('button',{name:'Record result'}).click();
    await page.locator('#f-status').selectOption('passed');await save();
    await page.getByRole('button',{name:'Archive completed goal'}).click();await save();
    await page.getByRole('button',{name:'Archived',exact:true}).click();
    await page.getByRole('button',{name:'Unarchive'}).waitFor();
    assert.equal((await api('/api/state')).goals[0].earned,6);
    await page.getByRole('button',{name:'Unarchive'}).click();
    await page.getByText('No archived goals yet. Archive a completed goal to keep its results for reference.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Active goals'}).click();
    await page.goto(base+'/#backup');
    const download=page.waitForEvent('download');
    await page.getByRole('link',{name:'Download full backup (JSON)'}).click();
    const backupPath=path.join(temp,'backup.json');await (await download).saveAs(backupPath);
    await api('/api/tasks','POST',{title:'Task added before restore'});
    await page.locator('#backup-file').setInputFiles(backupPath);
    await page.locator('#f-confirm').fill('RESTORE');await save();
    await page.getByRole('link',{name:/^before-restore-/}).waitFor();
    const restored=await api('/api/state');
    assert(!restored.tasks.some(t=>t.title==='Task added before restore'));
    assert.equal(restored.goals[0].earned,6);
    assert.equal(restored.tasks[0].outcome_id,outcome.id);
    // All four milestone flows above use this isolated test space.
    for (const width of [1440,390,320]) {
      await page.setViewportSize({width,height:1000});
      for (const route of ['today','tasks','goals','week','calendar','backup','review']) {
        await page.goto(base+'/#'+route);
        await page.locator('#page-content[aria-busy="false"]').waitFor();
        if (route==='backup') await page.getByRole('heading',{name:'Recovery copies'}).waitFor();
        if (route==='week') await page.getByRole('heading',{name:'Turn weekly intentions into appointments'}).waitFor();
        if (route==='review') await page.getByRole('heading',{name:'Daily recorded effort'}).waitFor();
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), `Overflow: ${route} at ${width}`);
        assert(!/\p{Script=Han}/u.test(await page.locator('body').innerText()), `Untranslated text: ${route}`);
      }
    }
    // Longer English form labels and feedback must also fit a narrow screen.
    await page.goto(base+'/#tasks');
    await page.locator('#page-content[aria-busy="false"]').waitFor();
    await page.locator('#global-add').click();
    assert(await page.locator('#editor').evaluate(el=>el.scrollWidth<=el.clientWidth),'Task dialog overflow');
    await page.locator('#cancel-editor').click();
    await page.goto(base+'/#calendar');
    await page.locator('#page-content[aria-busy="false"]').waitFor();
    await page.locator('#global-add').click();
    await page.locator('#f-title').fill('Invalid time check');
    await page.locator('#f-end').fill('08:00');
    await page.locator('#save-editor').click();
    await page.getByText('The end time must follow the start time. Overnight appointments are not supported.',{exact:true}).waitFor();
    assert(await page.locator('#editor').evaluate(el=>el.scrollWidth<=el.clientWidth),'Recurring dialog overflow');
    await page.locator('#cancel-editor').click();
    await page.setViewportSize({width:1440,height:1000});
    for(const route of ['today','week','calendar','goals','backup']) {
      await page.goto(base+'/#'+route);
      await page.locator('#page-content[aria-busy="false"]').waitFor();
      if(route==='week')await page.getByRole('heading',{name:'Turn weekly intentions into appointments'}).waitFor();
      if(route==='backup')await page.getByRole('heading',{name:'Recovery copies'}).waitFor();
      await page.screenshot({path:path.join(temp,route+'.png'),fullPage:true});
    }
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,temporaryDirectory:temp}));
  } finally {
    if(browser) await browser.close();
    server.kill('SIGTERM');
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
