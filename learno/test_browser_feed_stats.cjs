/* Additional real-browser coverage. Uses only an isolated database and profile. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'),net=require('node:net');
const {chromium}=require('playwright');
(async()=>{
 const root=__dirname,data=process.env.LEARNO_BROWSER_TEMP_ROOT||path.join(root,'data');
 fs.mkdirSync(data,{recursive:true});const dir=fs.mkdtempSync(path.join(data,'extended-browser-'));
 const python=process.env.LEARNO_TEST_PYTHON||'python',env={...process.env,PYTHONDONTWRITEBYTECODE:'1',LEARNO_DB:path.join(dir,'test.db'),TMP:dir,TEMP:dir};
 const migration=spawnSync(python,['-B',path.join(root,'migrate.py'),'--db',env.LEARNO_DB,'--workers-stopped'],{env,encoding:'utf8'});assert.equal(migration.status,0,migration.stderr);
 const port=await new Promise(r=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>r(p));});});
 const server=spawn(python,['-B',path.join(root,'app.py')],{env:{...env,LEARNO_PORT:String(port)},stdio:['ignore','ignore','pipe']});let stderr='';server.stderr.on('data',b=>stderr+=b);
 const base=`http://127.0.0.1:${port}`,failures=[],pageErrors=[];let browser;
 const state=p=>p.evaluate(async()=>await(await fetch('/api/v2/state')).json());
 async function until(p,predicate){for(let n=0;n<100;n++){const s=await state(p);if(predicate(s))return s;await new Promise(r=>setTimeout(r,50));}throw Error('State condition timed out');}
 async function rerender(p,act){const old=await p.locator('.shell').elementHandle();await act();await p.waitForFunction(el=>!el.isConnected,old);await old.dispose();}
 async function navigate(p,id){await rerender(p,async()=>{if(p.viewportSize().width<=700){if(['home','learn','exams','feed'].includes(id))await p.locator(`.mobile-nav [data-page=${id}]`).click();else{await p.locator('.mobile-nav [data-action=more]').click();await p.locator(`#modal [data-page=${id}]`).click();}}else await p.locator(`.nav [data-page=${id}]`).click();});}
 async function register(p,name){await p.goto(base);await p.locator('[data-action=auth-toggle]').click();await p.locator('[name=username]').fill(name);await p.locator('[name=password]').fill('ExamplePassword123!');await p.locator('#auth-form button[type=submit]').click();await p.locator('.shell').waitFor();}
 async function check(name,fn){try{await fn();console.log('PASS '+name);}catch(e){failures.push({name,message:e.message});console.error('FAIL '+name+': '+e.message);}}
 async function closeModal(p){if(await p.locator('#modal').isVisible())await p.locator('#modal .close').click();}
 try{
  for(let n=0;n<100;n++){try{if((await fetch(base)).ok)break;}catch{}await new Promise(r=>setTimeout(r,50));}
  process.env.TMP=dir;process.env.TEMP=dir;
  const owner=await chromium.launchPersistentContext(path.join(dir,'p'),{headless:true,executablePath:process.env.LEARNO_BROWSER_EXECUTABLE||undefined,viewport:{width:1280,height:900}});browser=owner.browser();
  const peer=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:2}),a=await owner.newPage(),b=await peer.newPage();for(const p of [a,b])p.on('pageerror',e=>pageErrors.push(e.message));
  await register(a,'extended-owner');await register(b,'extended-peer');


  async function api(p,action,data){return p.evaluate(async({action,data})=>{const st=await(await fetch('/api/v2/state')).json();const r=await fetch('/api/v2/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':st.csrf},body:JSON.stringify(data)});if(!r.ok)throw Error(await r.text());return r.json();},{action,data});}
  await check('empty statistics and optional goal',async()=>{await navigate(a,'stats');assert.equal(await a.locator('.optional-goal').getAttribute('open'),null);assert.equal(await a.locator('.column-chart.weeks .chart-column').count(),6);assert.ok((await a.locator('#content').innerText()).includes('Keine Daten im Zeitraum.'));});
  const ids=[];for(let n=0;n<8;n++){const result=await api(a,'session',{subject:'Fach '+n,date:'2026-10-07',duration_minutes:(n+1)*15,resources:'Buch',location:'Zuhause',interruptions:0});ids.push(result.session_id);}
  const gid=(await api(a,'group-create',{name:'Testgruppe'})).id;await api(b,'group-join',{group_id:gid});
  await api(a,'session-ranking',{session_id:ids[0],public:true});
  const p1=(await api(a,'post',{session_id:ids[0],audience:'group',target_group_id:gid,text:'Heute lief es gut.\nAuch mit einer Pause. '+ 'Langwort'.repeat(30),show_seconds:1})).post_id;
  const p2=(await api(a,'post',{session_id:ids[1],audience:'private',text:'Privater Entwurf als Beitrag'})).post_id;
  const root=(await api(b,'comment',{post_id:p1,text:'Gut gemacht'})).comment_id;
  const reply=(await api(a,'comment',{post_id:p1,text:'Danke',parent_comment_id:root})).comment_id;
  await api(b,'comment',{post_id:p1,text:'Gerne',parent_comment_id:reply});
  const p3=(await api(a,'post',{session_id:ids[2],audience:'public',text:'Zurückgenommener Beitrag'})).post_id;await api(a,'post-revoke',{post_id:p3});
  await api(a,'start',{subject:'Timer unverändert',date:'2026-10-07'});const started=(await state(a)).active.started;
  await check('vertical columns, global subject scale, filters and goal',async()=>{
   await navigate(a,'stats');assert.equal(await a.locator('.column-chart.subjects .chart-column').count(),8);
   const values=await a.locator('.column-chart.subjects .column-label').allTextContents();assert.equal(values[0],'Fach 7');
   const heights=await a.locator('.column-chart.subjects .column-bar').evaluateAll(es=>es.map(e=>e.getBoundingClientRect().height));assert.equal(heights[0],160);assert.equal(heights[7],20);
   assert.equal(await a.locator('.column-chart.subjects').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),6);
   const weeks=await a.locator('.column-chart.weeks .column-label').allTextContents();assert.equal(weeks.length,6);assert.equal(await a.locator('.current-week').count(),1);
   await a.locator('#filter-form [name=subject]').selectOption('Fach 0');await rerender(a,()=>a.locator('#filter-form button').click());assert.equal(await a.locator('.column-chart.subjects .chart-column').count(),1);assert.deepEqual(await a.locator('.column-chart.weeks .column-label').allTextContents(),weeks);
   await a.locator('#filter-form [name=subject]').selectOption('');await rerender(a,()=>a.locator('#filter-form button').click());
   await a.locator('.optional-goal summary').click();await a.locator('#weekly-goal-form [name=hours]').fill('1.25');await rerender(a,()=>a.locator('#weekly-goal-form button[type=submit]').click());assert.equal((await a.evaluate(async()=>await(await fetch('/api/v2/statistics')).json())).weekly_goal_minutes,75);
   await a.locator('.optional-goal summary').click();await rerender(a,()=>a.locator('[data-action=goal-disable]').click());assert.equal(await a.locator('.goal-progress').count(),0);
  });
  await check('feed prominence, visibility, keyboard menu and cancelled deletion',async()=>{
   await navigate(a,'feed');const card=a.locator(`[data-post="${p1}"].post`);assert.equal(await card.locator('.post-text').evaluate(e=>getComputedStyle(e).whiteSpace),'pre-wrap');assert.equal(await card.locator('.post-text').evaluate(e=>getComputedStyle(e).overflowWrap),'anywhere');assert.equal(await card.evaluate(e=>!!(e.querySelector('.post-text').compareDocumentPosition(e.querySelector('.post-context'))&Node.DOCUMENT_POSITION_FOLLOWING)),true);assert.ok(!(await card.innerText()).includes('Ranking'));
   await card.locator('summary').focus();await a.keyboard.press('Enter');await card.locator('[data-action=post-delete]').waitFor();let message='';a.once('dialog',async d=>{message=d.message();await d.dismiss();});await card.locator('[data-action=post-delete]').click();assert.ok(message.includes('alle zugehörigen Kommentare und Antworten endgültig löschen'));assert.ok(message.includes('weiterhin zur öffentlichen Rangliste'));assert.ok((await state(a)).own_posts.some(p=>p.id===p1));await a.keyboard.press('Escape');
   for(const id of [p2,p3]){const c=a.locator(`[data-post="${id}"].post`);assert.equal(await c.locator('[data-action=post-revoke]').count(),0);assert.equal(await c.locator('[data-action=post-delete]').count(),1);}
  });
  await check('mobile columns, menus, dialogs, drafts and timer at 320 390 700',async()=>{
   for(const width of [320,390,700]){await a.setViewportSize({width,height:844});await navigate(a,'stats');assert.equal(await a.locator('.column-chart.subjects').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),3);assert.equal(await a.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);await a.screenshot({path:path.join(data,'stats-mobile-'+width+'.png'),fullPage:false});
    await navigate(a,'feed');const c=a.locator(`[data-post="${p2}"].post`);await c.locator('.comment-form input').fill('Anderen Entwurf erhalten '+width);await navigate(a,'learn');await navigate(a,'feed');assert.equal(await c.locator('.comment-form input').inputValue(),'Anderen Entwurf erhalten '+width);
    await a.locator(`[data-post="${p1}"].post .post-menu summary`).click();const box=await a.locator(`[data-post="${p1}"] [data-action=post-delete]`).boundingBox();assert.ok(box.x>=0&&box.x+box.width<=width+1);a.once('dialog',d=>d.dismiss());await a.locator(`[data-post="${p1}"] [data-action=post-delete]`).click();await a.keyboard.press('Escape');assert.equal((await state(a)).active.started,started);assert.equal(await a.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);await a.screenshot({path:path.join(data,'feed-mobile-'+width+'.png'),fullPage:false});
   }
  });
  await check('confirmed deletion keeps other drafts, ranking and timer',async()=>{
   const other=a.locator(`[data-post="${p2}"].post`);await other.locator('.comment-form input').fill('Diesen Entwurf behalten');await a.locator(`[data-post="${p1}"].post .comment-form input`).fill('Nur diesen Entwurf löschen');await a.locator(`[data-post="${p1}"].post .post-menu summary`).click();a.once('dialog',d=>d.accept());await rerender(a,()=>a.locator(`[data-post="${p1}"] [data-action=post-delete]`).click());assert.equal(await a.locator(`[data-post="${p1}"].post`).count(),0);assert.equal(await other.locator('.comment-form input').inputValue(),'Diesen Entwurf behalten');const after=await state(a);assert.equal(after.sessions.find(s=>s.id===ids[0]).public,1);assert.equal(after.active.started,started);assert.ok(!after.comments.some(c=>c.post_id===p1));await navigate(a,'profile');assert.equal(await a.locator(`[data-action=post-revoke][data-id="${p1}"]`).count(),0);
   await navigate(a,'learn');await a.locator(`[data-action=session-details][data-id="${ids[0]}"]:visible`).first().click();assert.ok((await a.locator('#modal').innerText()).includes('Diese Lernzeit zählt zur öffentlichen Rangliste'));assert.equal((await state(a)).sessions.length,8);
  });
  if(pageErrors.length)failures.push({name:'uncaught browser errors',message:JSON.stringify(pageErrors)});
  console.log(JSON.stringify({checks:5,failures},null,2));if(failures.length)process.exitCode=1;
 }finally{
  if(browser)await browser.close();server.kill();await new Promise(r=>{if(server.exitCode!==null)r();else server.once('exit',r);});
  const resolved=path.resolve(dir);assert.ok(resolved.startsWith(path.resolve(data)+path.sep),'Unsafe cleanup');fs.rmSync(resolved,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
