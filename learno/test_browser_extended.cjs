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
  const peer=await browser.newContext({viewport:{width:390,height:844}}),a=await owner.newPage(),b=await peer.newPage();for(const p of [a,b])p.on('pageerror',e=>pageErrors.push(e.message));
  await register(a,'extended-owner');await register(b,'extended-peer');
  await check('profile settings and persisted timezone',async()=>{
   await navigate(a,'profile');await a.locator('#settings-form [name=reminder_on]').check();await a.locator('#settings-form [name=reminder]').fill('19:45');await a.locator('#settings-form [name=timezone]').selectOption('Europe/London');
   await rerender(a,()=>a.locator('#settings-form button').click());const s=await state(a);assert.equal(s.user.reminder,'19:45');assert.equal(s.user.timezone,'Europe/London');assert.equal(s.user.reminder_on,1);
   await a.reload();await a.locator('.shell').waitFor();await navigate(a,'profile');assert.equal(await a.locator('#settings-form [name=reminder]').inputValue(),'19:45');
  });
  await check('friend request rejection, acceptance and missing-user error',async()=>{
   await navigate(a,'profile');await a.locator('#friend-form input').fill('extended-peer');await rerender(a,()=>a.locator('#friend-form button').click());
   await navigate(b,'profile');await rerender(b,()=>b.locator('[data-action=reject]').click());assert.equal((await state(b)).friends.length,0);
   await navigate(a,'profile');await a.locator('#friend-form input').fill('extended-peer');await rerender(a,()=>a.locator('#friend-form button').click());
   await navigate(b,'profile');await rerender(b,()=>b.locator('[data-action=accept]').click());assert.equal((await state(b)).friends[0].accepted,1);
   await a.locator('#friend-form input').fill('missing-user-xyz');await a.locator('#friend-form button').click();await a.waitForFunction(()=>document.querySelector('#toast').classList.contains('visible')&&document.querySelector('#toast').textContent.includes('gefunden'));assert.equal((await state(a)).friends.length,1);
  });
  const today=new Date().toLocaleDateString('sv-SE'),header='date,duration_minutes,learning_resources,learning_location,interruptions,subject\n';
  const csv=header+`${today},30,Book,Home,0,Mathematik\n${today},45,Notes,Library,1,Physik\n`;
  await check('CSV browser import, invalid import atomicity and export download',async()=>{
   await navigate(a,'profile');await a.locator('#import-form input').setInputFiles({name:'sessions.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});await rerender(a,()=>a.locator('#import-form button').click());assert.equal((await state(a)).sessions.length,2);assert.equal((await state(b)).sessions.length,0);
   const dl=a.waitForEvent('download');await a.locator('[data-action=export]').click();const file=await dl,contents=fs.readFileSync(await file.path(),'utf8').replace(/^\uFEFF/,'');assert.equal(file.suggestedFilename(),'learning_sessions.csv');assert.ok(contents.includes('Mathematik'));assert.ok(contents.includes(',45,Notes,Library,1,Physik'));
   await a.locator('#import-form input').setInputFiles({name:'invalid.csv',mimeType:'text/csv',buffer:Buffer.from(csv+`${today},-2,Book,Home,0,Invalid\n`)});const invalid=a.waitForResponse(r=>r.url().endsWith('/api/v2/import')&&r.request().method()==='POST');await a.locator('#import-form button').click();const response=await invalid;assert.equal(response.status(),400);const error=(await response.json()).error;await a.waitForFunction(message=>document.querySelector('#toast').textContent===message,error);assert.equal((await state(a)).sessions.length,2);
  });
  await check('statistic subject/date filters independent of weekly totals',async()=>{
   await navigate(a,'stats');await a.locator('#filter-form [name=subject]').selectOption('Mathematik');await a.locator('#filter-form button').click();
   assert.equal(await a.locator('.metrics .metric-value').first().textContent(),'30 Min.');assert.equal(await a.locator('.metrics .metric-value').nth(1).textContent(),'1');
   await a.locator('#filter-form [name=from]').fill('2099-01-01');await a.locator('#filter-form button').click();assert.equal(await a.locator('.metrics .metric-value').first().textContent(),'0 Min.');
   const stats=await a.evaluate(async()=>await(await fetch('/api/v2/statistics')).json());assert.equal(stats.current_seconds,4500);
  });
  await check('private sessions excluded from ranking, repeated publication counted once',async()=>{
   await navigate(a,'ranking');assert.equal((await state(a)).ranking.length,0);await navigate(a,'learn');const sid=(await state(a)).sessions.find(s=>s.subject==='Mathematik').id;
   for(let n=0;n<2;n++){await a.locator(`[data-action=share-session][data-id="${sid}"]:visible`).click();await a.locator('#post-compose-form [name=target]').selectOption('public');await a.locator('#post-compose-form textarea').fill('Frei verfasster Beitrag '+n);await a.locator('#post-compose-form button[type=submit]').click();await a.locator('#modal').waitFor({state:'hidden'});await until(a,s=>s.posts.length===n+1);await navigate(a,'learn');}
   assert.equal((await state(a)).ranking.length,0);await a.locator(`[data-action=session-details][data-id="${sid}"]:visible`).click();await a.locator('#modal [data-action=session-ranking]').click();await closeModal(a);await navigate(a,'ranking');const s=await state(a);assert.equal(s.ranking.length,1);assert.equal(s.ranking[0].seconds,1800);assert.ok((await a.locator('.rank-me').textContent()).includes('30 Min.'));
   await navigate(b,'feed');assert.equal(await b.locator('.comment-form').count(),2);
  });
  await check('start/manual cancellation and running timer reload/pause/resume',async()=>{
   await navigate(a,'learn');const count=(await state(a)).sessions.length;await a.locator('[data-action=manual]').click();await a.locator('#modal-form [name=subject]').fill('Cancelled');await a.locator('#modal-form [data-action=close]').click();assert.equal((await state(a)).sessions.length,count);
   await a.locator('[data-action=start]').click();await a.locator('#modal-form [name=subject]').fill('Reload subject');await a.locator('#modal-form [data-action=close]').click();assert.equal((await state(a)).active,null);
   await a.locator('[data-action=start]').click();await a.locator('#modal-form [name=subject]').fill('Reload subject');await a.locator('#modal-form button[type=submit]').click();await a.locator('#timer').waitFor();const started=(await state(a)).active.started;
   await a.reload();await a.locator('#timer').waitFor();assert.equal((await state(a)).active.started,started);
   await rerender(a,()=>a.locator('[data-action=pause]').click());assert.ok((await state(a)).active.paused);await a.reload();await a.locator('#timer').waitFor();assert.ok((await state(a)).active.paused);
   await rerender(a,()=>a.locator('[data-action=resume]').click());assert.equal((await state(a)).active.paused,null);assert.equal((await state(a)).active.started,started);
  });
  await check('desktop/mobile exam dialog cancellation, keyboard menu and invalid form',async()=>{
   for(const width of [1280,390,320]){await closeModal(a);await a.setViewportSize({width,height:900});await navigate(a,'exams');const count=(await state(a)).exam_events.length;await a.locator('[data-action=create-exam]').click();await a.locator('#enhanced-form [name=title]').fill('Do not save');await a.keyboard.press('Escape');await a.locator('#modal').waitFor({state:'hidden'});assert.equal((await state(a)).exam_events.length,count);
    await a.locator('[data-action=create-exam]').click();await a.locator('#enhanced-form button[type=submit]').click();assert.equal(await a.locator('#enhanced-form').evaluate(el=>el.checkValidity()),false);assert.equal((await state(a)).exam_events.length,count);await closeModal(a);}
   await a.locator('[data-action=create-exam]').click();await a.locator('#enhanced-form [name=title]').fill('Keyboard menu');await a.locator('#enhanced-form [name=subject]').fill('Math');await a.locator('#enhanced-form button[type=submit]').click();await a.locator('#modal').waitFor({state:'hidden'});await until(a,s=>s.exam_events.length===1);await navigate(a,'exams');
   const summary=a.locator('.action-menu summary');await summary.focus();await a.keyboard.press('Enter');await a.locator('.action-menu[open]').waitFor();await a.locator('.menu-close').click();assert.equal(await a.locator('.action-menu[open]').count(),0);assert.equal(await summary.evaluate(el=>el===document.activeElement),true);
  });
  await check('logout clears feed filters and login restores active timer',async()=>{
   await closeModal(a);await navigate(a,'feed');await a.locator('[data-action=feed-filter][data-view=friends]').click();await a.locator('[data-action=feed-filter][data-view=friends].selected').waitFor();const started=(await state(a)).active.started;
   await a.locator('.mobile-nav [data-action=more]').click();await a.locator('#modal [data-action=logout]').click();await a.locator('#auth-form').waitFor();await closeModal(a);
   await a.locator('#auth-form [name=username]').fill('extended-owner');await a.locator('#auth-form [name=password]').fill('ExamplePassword123!');await a.locator('#auth-form button').click();await a.locator('.shell').waitFor();assert.equal((await state(a)).active.started,started);await navigate(a,'feed');assert.equal(await a.locator('[data-action=feed-filter].selected').getAttribute('data-view'),'all');
  });
  if(pageErrors.length)failures.push({name:'uncaught browser errors',message:JSON.stringify(pageErrors)});
  console.log(JSON.stringify({checks:8,failures},null,2));if(failures.length)process.exitCode=1;
 }finally{
  if(browser)await browser.close();server.kill();await new Promise(r=>{if(server.exitCode!==null)r();else server.once('exit',r);});
  const resolved=path.resolve(dir);assert.ok(resolved.startsWith(path.resolve(data)+path.sep),'Unsafe cleanup');fs.rmSync(resolved,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
