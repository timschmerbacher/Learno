/* Optional real-browser regression test. npm package playwright is test-only. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const {spawn,spawnSync}=require('node:child_process');
const {chromium}=require('playwright');

(async()=>{
 const root=__dirname, data=process.env.LEARNO_BROWSER_TEMP_ROOT||path.join(root,'data');fs.mkdirSync(data,{recursive:true});
 const dir=fs.mkdtempSync(path.join(data,'browser-test-')),db=path.join(dir,'test.db');
 const python=process.env.LEARNO_TEST_PYTHON||'python';
 const env={...process.env,PYTHONDONTWRITEBYTECODE:'1',LEARNO_DB:db,TMP:dir,TEMP:dir};
 const migration=spawnSync(python,['-B',path.join(root,'migrate.py'),'--db',db,'--workers-stopped'],{env,encoding:'utf8'});
 assert.equal(migration.status,0,migration.stderr);
 const port=await new Promise(resolve=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const port=s.address().port;s.close(()=>resolve(port));});});
 const server=spawn(python,['-B',path.join(root,'app.py')],{env:{...env,LEARNO_PORT:String(port)},stdio:['ignore','pipe','pipe']});
 let serverErrors='';server.stderr.on('data',b=>serverErrors+=b);
 const base=`http://127.0.0.1:${port}`,errors=[];
 let browser;
 const state=p=>p.evaluate(async()=>await(await fetch('/api/v2/state')).json());
 const submit=p=>p.locator('#enhanced-form button[type=submit]').click();
 async function register(p,name){
  await p.goto(base);await p.locator('#auth-form').waitFor();
  await p.locator('[data-action=auth-toggle]').click();
  await p.locator('[name=username]').fill(name);await p.locator('[name=password]').fill('ExamplePassword123!');
  await p.locator('#auth-form button[type=submit]').click();await p.locator('.shell').waitFor();
 }
 async function waitState(p,fn){
  for(let i=0;i<100;i++){const s=await state(p);if(fn(s))return s;await new Promise(r=>setTimeout(r,50));}
  throw Error('Timed out waiting for state');
 }
 async function navigate(p,id){
  const previous=await p.locator('.shell').elementHandle();
  if(p.viewportSize().width<=700){
   if(['home','learn','exams','feed'].includes(id))await p.locator('.mobile-nav [data-page='+id+']').click();
   else {await p.locator('.mobile-nav [data-action=more]').click();await p.locator('#modal [data-page='+id+']').click();}
  }else await p.locator('.nav [data-page='+id+']').click();
  await p.waitForFunction(el=>!el.isConnected,previous);await previous.dispose();
 }
 async function examAction(p,sid,action){
  const e=(await state(p)).user_exam_states.find(e=>e.id===sid),view=e.archived_at||e.event_archived_at?'archive':e.completed?'completed':'upcoming';
  await p.locator(`[data-action=exam-view][data-view="${view}"]`).click();
  await p.locator(`[data-exam="${sid}"] .action-menu summary`).click();
  await p.locator(`[data-exam="${sid}"] [data-action="${action}"]`).click();
 }
 async function createExam(p,title,group=''){
  await navigate(p,'exams');await p.locator('[data-action=create-exam]').click();
  await p.locator('#enhanced-form [name=group_id]').selectOption(group);
  await p.locator('#enhanced-form [name=title]').fill(title);await p.locator('#enhanced-form [name=subject]').fill('Math');
  await submit(p);await p.locator('#modal').waitFor({state:'hidden'});
  return (await state(p)).user_exam_states.find(e=>e.title===title);
 }
 try{
  for(let i=0;i<100;i++){try{if((await fetch(base)).ok)break;}catch{}await new Promise(r=>setTimeout(r,50));}
  process.env.TMP=dir;process.env.TEMP=dir;
  const owner=await chromium.launchPersistentContext(path.join(dir,'p'),{headless:true,executablePath:process.env.LEARNO_BROWSER_EXECUTABLE||undefined,viewport:{width:390,height:844}});
  browser=owner.browser();
  const student=await browser.newContext({viewport:{width:1280,height:900}});
  const a=await owner.newPage(),b=await student.newPage();
  for(const p of [a,b])p.on('pageerror',e=>errors.push(e.message));
  await register(a,'browser-owner');await register(b,'browser-student');
  const e=await createExam(a,'Private browser exam');
  let gradeRequests=0;a.on('request',r=>{if(r.url().endsWith('/api/v2/grade'))gradeRequests++;});
  for(let grade=1;grade<=5;grade++){
   await examAction(a,e.id,'grade');
   await a.locator('#modal-form [name=grade]').selectOption(String(grade));
   await a.locator('#modal-form button[type=submit]').click();await a.locator('#modal').waitFor({state:'hidden'});
   const s=await state(a);assert.equal(s.user_exam_states.find(s=>s.id===e.id).grade,grade);
  }
  assert.equal(gradeRequests,5);assert.equal((await state(a)).grade_history.length,5);
  await navigate(a,'learn');await a.locator('[data-action=start]').click();
  assert.equal(await a.locator(`#modal-form [name=user_exam_state_id] option[value="${e.id}"]`).count(),0);
  await a.locator('[data-action=start-new]').click();await a.locator('#enhanced-form [name=title]').fill('Created at start');
  await a.locator('#enhanced-form [name=subject]').fill('Java');await submit(a);
  await a.locator('#modal-form[data-kind=start]').waitFor();
  const startExam=(await state(a)).user_exam_states.find(e=>e.title==='Created at start');
  assert.equal(await a.locator('#modal-form [name=user_exam_state_id]').inputValue(),String(startExam.id));
  assert.equal((await state(a)).active,null);
  await a.locator('#modal-form button[type=submit]').click();await a.locator('#timer').waitFor();
  await a.locator('[data-action=finish]').click();await a.locator('[data-location-select]').selectOption('__custom__');
  await a.locator('[name=custom_location]').fill('Mobile reading room');await a.locator('[name=resource]').first().check();
  await a.locator('#modal-form button[type=submit]').click();await a.locator('[data-action=saved-done]').click();await a.locator('#modal').waitFor({state:'hidden'});
  assert.equal((await state(a)).sessions[0].location,'Mobile reading room');assert.equal((await state(b)).locations.length,0);
  await navigate(a,'exams');
  a.once('dialog',d=>d.accept());await examAction(a,startExam.id,'personal-delete');
  await waitState(a,s=>s.user_exam_states.find(e=>e.id===startExam.id).archived_at);
  await examAction(a,startExam.id,'personal-restore');
  await waitState(a,s=>!s.user_exam_states.find(e=>e.id===startExam.id).archived_at);
  await navigate(a,'groups');await a.locator('[data-action=group-new]').click();
  await a.locator('#enhanced-form [name=name]').fill('Browser Main');await submit(a);await a.locator('#modal').waitFor({state:'hidden'});
  const main=(await state(a)).groups.find(g=>g.name==='Browser Main');
  await a.locator(`[data-action=subgroup-new][data-id="${main.id}"]`).click();await a.locator('#enhanced-form [name=name]').fill('Browser Child');await submit(a);await a.locator('#modal').waitFor({state:'hidden'});
  const child=(await state(a)).groups.find(g=>g.name==='Browser Child');
  await navigate(b,'groups');await b.locator('[data-action=group-view][data-view=discover]').click();await b.locator('details.group-tree > summary').click();await b.locator(`[data-action=group-join][data-id="${main.id}"]`).filter({hasText:/^Beitreten$/}).click();
  await b.locator(`[data-action=group-join][data-id="${child.id}"]`).click();
  const shared=await createExam(a,'Shared browser exam',String(child.id));
  await b.locator(`[data-action=group-open][data-id="${child.id}"]`).click();
  await b.locator(`[data-action=group-adopt][data-id="${shared.exam_event_id}"]`).click();await submit(b);await b.locator('#modal').waitFor({state:'hidden'});
  assert.equal((await state(b)).user_exam_states.length,1);assert.equal((await state(a)).exam_events.filter(e=>e.id===shared.exam_event_id).length,1);
  await examAction(a,shared.id,'personal-files');
  await a.locator('#file-form [name=upload]').setInputFiles({name:'browser.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nfixture')});
  await a.locator('#file-form button[type=submit]').click();await waitState(a,s=>s.files.length===1);
  const fid=(await state(a)).files[0].id;assert.equal((await b.request.get(base+`/api/v2/files/${fid}`)).status(),200);
  await a.locator('[data-action=close]').click();
  await examAction(a,shared.id,'grade');await a.locator('#modal-form [name=grade]').selectOption('2');
  await a.locator('#modal-form button[type=submit]').click();await a.locator('#modal').waitFor({state:'hidden'});
  await examAction(a,shared.id,'share-exam');
  assert.equal(await a.locator('#result-share-form [name=target]').inputValue(),'');
  assert.equal(await a.locator('#result-share-form input:checked').count(),0);
  await a.locator('#result-share-form [name=target]').selectOption(String(child.id));await a.locator('[name=show_count]').check();
  await a.locator('#result-share-form button[type=submit]').click();await a.locator('#modal').waitFor({state:'hidden'});
  const p=(await state(b)).posts[0];assert.equal(p.session_count,0);assert.ok(!('grade' in p));assert.ok(!('seconds' in p));
  await navigate(a,'feed');await a.locator('.post').waitFor();
  const overflow=await a.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);assert.equal(overflow,false,'Mobile document overflow');
  // Group members can discuss without a friendship, including replies to replies.
  await navigate(b,'feed');
  await b.locator(`.post[data-post="${p.id}"] .comment-form input`).fill('Eine Frage zur Prüfung');
  await b.locator(`.post[data-post="${p.id}"] .comment-form button[type=submit]`).click();
  await waitState(b,s=>s.comments.length===1);const rootComment=(await state(b)).comments[0];
  await navigate(a,'feed');await a.locator(`[data-action=reply][data-id="${rootComment.id}"]`).click();
  assert.equal(await a.locator('.reply-form textarea').inputValue(),'');
  await a.locator('.reply-form textarea').fill('Hier ist meine Antwort');await a.locator('.reply-form button[type=submit]').click();
  await waitState(a,s=>s.comments.length===2);const answer=(await state(a)).comments.find(c=>c.parent_comment_id===rootComment.id);
  await navigate(b,'feed');await b.locator(`[data-action=reply][data-id="${answer.id}"]`).click();
  assert.equal(await b.locator('.reply-form textarea').inputValue(),'');
  await b.locator('.reply-form textarea').fill('Danke für die Erklärung');await b.locator('.reply-form button[type=submit]').click();
  await waitState(b,s=>s.comments.length===3);assert.equal((await state(b)).comments[2].parent_comment_id,answer.id);
  await navigate(a,'feed');await a.locator(`[data-action=reply][data-id="${rootComment.id}"]`).click();
  await a.locator('.reply-form textarea').fill('Noch eine Ergänzung');await a.locator('.reply-form button[type=submit]').click();
  await waitState(a,s=>s.comments.length===4);await a.locator('[data-comment]').filter({hasText:'Noch eine Ergänzung'}).waitFor();
  if(await a.locator(`[data-action=replies-more][data-id="${rootComment.id}"]`).count())await a.locator(`[data-action=replies-more][data-id="${rootComment.id}"]`).click();
  assert.equal(await a.locator('[data-comment]').count(),4);
  for(let i=0;i<4;i++){
   await navigate(b,'feed');await b.locator('.comment-form input').fill('Weitere Frage '+i);
   await b.locator('.comment-form button[type=submit]').click();await waitState(b,s=>s.comments.length===5+i);
   await b.locator('[data-comment]').filter({hasText:'Weitere Frage '+i}).waitFor();
  }
  await navigate(a,'feed'); // Posting a reply now opens its thread and root discussion automatically.
  assert.equal(await a.locator('[data-comment]').count(),8);
  await navigate(a,'feed');await a.locator('[data-action=feed-filter][data-view=groups]').click();
  await a.locator('#feed-group').selectOption(String(main.id));await a.locator('.feed-list .empty').waitFor();
  await a.locator('#feed-group').selectOption(String(child.id));await a.locator('.post').waitFor();
  await navigate(a,'learn');await navigate(a,'feed');assert.equal(await a.locator('#feed-group').inputValue(),String(child.id));
  await a.locator('[data-action=feed-filter][data-view=public]').click();await a.locator('.feed-list .empty').waitFor();
  await a.locator('[data-action=feed-filter][data-view=friends]').click();await a.locator('.feed-list .empty').waitFor();
  await a.locator('[data-action=feed-filter][data-view=all]').click();await a.locator('.post').waitFor();
  // Navigation, notices and goals never pause or reset a running timer.
  await navigate(a,'learn');await a.locator('[data-action=start]').click();
  await a.locator('#modal-form [name=user_exam_state_id]').selectOption(String(startExam.id));
  await a.locator('#modal-form button[type=submit]').click();await a.locator('#timer').waitFor();
  const started=(await state(a)).active.started;
  await navigate(a,'stats');await a.locator('.optional-goal summary').click();await a.locator('#weekly-goal-form [name=hours]').fill('1.25');
  await a.locator('#weekly-goal-form button[type=submit]').click();await a.waitForFunction(()=>document.querySelector('.goal-progress'));await a.locator('.optional-goal summary').click();await a.locator('.goal-progress').waitFor();
  const stats=await a.evaluate(async()=>await(await fetch('/api/v2/statistics')).json());
  assert.equal(stats.weekly_goal_minutes,75);assert.equal(stats.current_seconds,(await state(a)).sessions.reduce((n,s)=>n+s.seconds,0));
  await a.locator('[data-action=notices-open]').click();await a.locator('[data-action=notices-read-all]').click();
  await waitState(a,s=>s.notice_count===0);await a.waitForFunction(()=>document.querySelector('.notice-trigger').textContent==='0 Änderungen');await a.locator('#modal .close').click();
  assert.equal(await a.locator('.notice-trigger').textContent(),'0 Änderungen');
  assert.equal((await state(a)).active.started,started);
  await navigate(a,'exams');a.once('dialog',d=>d.accept());await examAction(a,shared.id,'personal-delete');
  await waitState(a,s=>s.user_exam_states.find(e=>e.id===shared.id).archived_at);
  for(const width of [320,390,700]){
   await a.setViewportSize({width,height:844});await navigate(a,'exams');
   for(const view of ['upcoming','completed','archive']){
    await a.locator(`[data-action=exam-view][data-view="${view}"]`).click();
    const expected=(await state(a)).user_exam_states.filter(e=>(e.archived_at||e.event_archived_at?'archive':e.completed?'completed':'upcoming')===view).length;
    assert.equal(await a.locator('[data-exam]').count(),expected);
   }
   await a.locator('[data-action=exam-view][data-view=upcoming]').click();
   const summary=a.locator(`[data-exam="${startExam.id}"] .action-menu summary`);
   await summary.focus();await a.keyboard.press('Enter');await a.locator('.action-menu[open]').waitFor();
   const bottom=await a.locator('.action-menu[open] .menu-close').boundingBox(),nav=await a.locator('.mobile-nav').boundingBox();
   assert.ok(bottom.y+bottom.height<nav.y,'Action menu must remain above bottom navigation');
   await a.keyboard.press('Escape');assert.equal(await a.locator('.action-menu[open]').count(),0);
   for(const id of ['home','stats','groups','feed']){
    await navigate(a,id);
    assert.equal(await a.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`Overflow at ${width}px on ${id}`);
    assert.equal((await state(a)).active.started,started);
   }
   if(process.env.LEARNO_BROWSER_SCREENSHOT)await a.screenshot({path:process.env.LEARNO_BROWSER_SCREENSHOT.replace(/\.png$/,`-${width}.png`),fullPage:true});
  }
  if(process.env.LEARNO_BROWSER_SCREENSHOT)await a.screenshot({path:process.env.LEARNO_BROWSER_SCREENSHOT,fullPage:true});
  assert.deepEqual(errors,[]);console.log('Browser OK: V2 regressions, three exam views, menus, replies, filters, private goal, notices, preserved timer, 320/390/700px.');
 }finally{
  if(browser)await browser.close();server.kill();await new Promise(resolve=>{if(server.exitCode!==null)resolve();else server.once('exit',resolve);});
  const resolved=path.resolve(dir);assert.ok(resolved.startsWith(path.resolve(data)+path.sep),'Unsafe test cleanup');
  fs.rmSync(resolved,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
