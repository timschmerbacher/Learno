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

  const api=async(p,action,payload)=>{const csrf=(await state(p)).csrf;const r=await p.request.post(base+'/api/v2/'+action,{headers:{'X-CSRF-Token':csrf},data:payload});assert.equal(r.status(),200,await r.text());return r.json();};
  const today=new Date().toLocaleDateString('sv-SE');
  const main=await api(a,'group-create',{name:'Activity Main'}),child=await api(a,'group-create',{name:'Activity Child',parent_id:main.id});
  await api(b,'group-join',{group_id:main.id});await api(b,'group-join',{group_id:child.id});
  await api(b,'friend',{username:'extended-owner'});await api(a,'accept',{sender:(await state(b)).user.id});
  const e1=await api(a,'exam',{title:'Zebra exam',subject:'Math',exam_date:today,difficulty:3}),e2=await api(a,'exam',{title:'Alpha exam',subject:'Biology',exam_date:today,difficulty:3});
  const s1=await api(a,'session',{user_exam_state_id:e1.user_exam_state_id,date:today,duration_minutes:30,resources:'Book',location:'Home',interruptions:0});
  const p1=await api(a,'post',{session_id:s1.session_id,audience:'public',text:'Discussion one'}),p2=await api(a,'post',{session_id:s1.session_id,audience:'public',text:'Discussion two'});
  const roots=[];for(let n=0;n<5;n++)roots.push((await api(b,'comment',{post_id:p1.post_id,text:'Root '+n})).comment_id);
  let parent=roots[0];for(let n=0;n<3;n++){parent=(await api(b,'comment',{post_id:p1.post_id,parent_comment_id:parent,text:'Reply '+n})).comment_id;}
  await check('draft retention, targeted discussion updates, errors and response references',async()=>{
   await navigate(a,'feed');const box=a.locator(`[data-post="${p1.post_id}"] .comment-form input`),other=a.locator(`[data-post="${p2.post_id}"] .comment-form input`);
   await box.fill('My root draft');await other.fill('Other draft');const otherNode=await other.elementHandle();
   await a.locator(`[data-action=comments-more][data-id="${p1.post_id}"]`).click();assert.equal(await box.inputValue(),'My root draft');assert.equal(await otherNode.evaluate(el=>el.isConnected),true);await otherNode.dispose();
   await a.locator(`[data-action=reply][data-id="${roots[0]}"]`).click();await a.locator('.reply-form textarea').fill('scheisse');
   await a.locator(`[data-action=replies-more][data-id="${roots[0]}"]`).click();assert.equal(await a.locator('.reply-form textarea').inputValue(),'scheisse');
   await a.locator('.reply-form button[type=submit]').click();await a.locator('.reply-form .error').filter({hasText:'überarbeite'}).waitFor();assert.equal(await a.locator('.reply-form textarea').inputValue(),'scheisse');
   await navigate(a,'learn');await navigate(a,'feed');assert.equal(await a.locator('.reply-form textarea').inputValue(),'scheisse');assert.equal(await other.inputValue(),'Other draft');
   await a.locator('.reply-form textarea').fill('A retained answer');await a.locator('.reply-form button[type=submit]').click();await a.locator('[data-comment]').filter({hasText:'A retained answer'}).waitFor();assert.equal(await box.inputValue(),'My root draft');assert.equal(await other.inputValue(),'Other draft');
   await a.locator('.reply-reference').first().click();assert.equal(await a.evaluate(()=>document.activeElement.hasAttribute('data-comment')),true);
  });
  await check('composer private default, group visibility and independent ranking',async()=>{
   await a.locator('[data-action=compose]').click();await a.locator('#compose-source').selectOption('session:'+s1.session_id);
   assert.equal(await a.locator('#post-compose-form [name=target]').inputValue(),'');assert.equal(await a.locator('#post-compose-form input:checked').count(),0);
   assert.equal(await a.locator('#modal').getAttribute('aria-labelledby'),'dialog-title');await a.locator('#post-compose-form textarea').fill('Only my group');await a.locator('#post-compose-form [name=target]').selectOption(String(child.id));await a.locator('#post-compose-form button[type=submit]').click();await a.locator('#modal').waitFor({state:'hidden'});
   const own=(await state(a)).own_posts.find(p=>p.text==='Only my group');assert.equal(own.audience,'group');assert.ok(!('seconds'in own));assert.equal((await state(a)).ranking.length,0);
   await navigate(a,'learn');await a.locator(`[data-action=session-details][data-id="${s1.session_id}"]:visible`).click();await a.locator('#modal [data-action=session-ranking]').click();await a.locator('#modal').getByText('Diese Lernzeit zählt zur öffentlichen Rangliste',{exact:false}).waitFor();await closeModal(a);
   await navigate(a,'feed');await a.locator('[data-action=feed-filter][data-view=mine]').click();await a.locator('[data-action=feed-filter][data-view=mine].selected').waitFor();await a.locator(`[data-post="${own.id}"] .post-menu summary`).click();a.once('dialog',d=>d.accept());await a.locator(`[data-post="${own.id}"] [data-action=post-revoke]`).click();await until(a,s=>s.own_posts.find(p=>p.id===own.id).revoked_at);await navigate(a,'profile');await a.getByText('Öffentliche Lernzeit im Ranking',{exact:true}).waitFor();assert.equal((await state(a)).ranking[0].seconds,1800);
  });
  await check('exam search/sort, concrete deletion labels and compact timer',async()=>{
   await api(a,'start',{user_exam_state_id:e1.user_exam_state_id,date:today});await api(a,'weekly-goal',{weekly_goal_minutes:60});await navigate(a,'home');const started=(await state(a)).active.started;
   assert.ok((await a.locator('.metrics').innerText()).includes('Privates Ziel: 1 Std. 0 Min.'));await a.locator('.timer-strip [data-action=timer-pause]').click();await a.locator('.timer-strip [data-action=timer-resume]').waitFor();await a.locator('.timer-strip [data-action=timer-resume]').click();await a.locator('.timer-strip [data-action=timer-pause]').waitFor();
   await navigate(a,'exams');await a.locator('#exam-search-form [name=search]').fill('Zebra');await a.locator('#exam-search-form button').click();assert.equal(await a.locator('[data-exam]').count(),1);await a.locator('.action-menu summary').click();assert.equal(await a.locator('.menu-items').getByText('Archivieren',{exact:true}).count(),1);await a.locator('[data-action=menu-close]').click();
   await a.locator('#exam-search-form [name=search]').fill('');await a.locator('#exam-search-form [name=sort]').selectOption('subject');await a.locator('#exam-search-form button').click();assert.equal(await a.locator('[data-exam]').first().getAttribute('data-exam'),String(e2.user_exam_state_id));
   assert.equal((await state(a)).active.started,started);
  });
  await check('result composer remains private or group only',async()=>{
   const personal=(await state(a)).user_exam_states.find(e=>e.id===e2.user_exam_state_id);await api(a,'grade',{user_exam_state_id:personal.id,version:personal.version,grade:2});await navigate(a,'feed');await a.locator('[data-action=compose]').click();await a.locator('#compose-source').selectOption('result:'+personal.id);
   assert.equal(await a.locator('#post-compose-form option[value=public]').count(),0);assert.equal(await a.locator('#post-compose-form input:checked').count(),0);await a.locator('#post-compose-form [name=target]').selectOption(String(child.id));await a.locator('#post-compose-form [name=show_grade]').check();await a.locator('#post-compose-form textarea').fill('Result snapshot');await a.locator('#post-compose-form button[type=submit]').click();await a.locator('#modal').waitFor({state:'hidden'});assert.equal((await state(b)).posts.find(p=>p.text==='Result snapshot').grade,2);
  });
  await check('saved session confirmation and mobile session cards',async()=>{
   await navigate(a,'learn');await a.locator('[data-action=finish]').click();await a.locator('#modal-form [name=resource]').first().check();await a.locator('#modal-form button[type=submit]').click();await a.locator('[data-action=saved-done]').waitFor();assert.equal((await state(a)).active,null);await a.locator('[data-action=saved-done]').click();
   for(const width of [320,390,700]){await a.setViewportSize({width,height:844});for(const view of ['learn','feed','exams','profile']){await navigate(a,view);assert.equal(await a.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,view+' '+width);}await navigate(a,'learn');assert.equal(await a.locator('.mobile-sessions').isVisible(),true);assert.equal(await a.locator('.desktop-sessions').isVisible(),false);if(process.env.LEARNO_BROWSER_SCREENSHOT)await a.screenshot({path:process.env.LEARNO_BROWSER_SCREENSHOT.replace(/\.png$/,`-${width}.png`),fullPage:true});}
  });
  await check('logout clears all private discussion drafts',async()=>{
   await navigate(a,'feed');await a.locator('[data-action=feed-filter][data-view=all]').click();await a.locator('[data-action=feed-filter][data-view=all].selected').waitFor();const draft=a.locator(`[data-post="${p2.post_id}"] .comment-form input`);await draft.fill('Account private draft');await a.locator('.mobile-nav [data-action=more]').click();await a.locator('#modal [data-action=logout]').click();await a.locator('#auth-form').waitFor();await closeModal(a);
   await a.locator('#auth-form [name=username]').fill('extended-owner');await a.locator('#auth-form [name=password]').fill('ExamplePassword123!');await a.locator('#auth-form button[type=submit]').click();await a.locator('.shell').waitFor();await navigate(a,'feed');assert.equal(await draft.inputValue(),'');
  });
  if(pageErrors.length)failures.push({name:'uncaught browser errors',message:JSON.stringify(pageErrors)});
  console.log(JSON.stringify({checks:6,failures},null,2));if(failures.length)process.exitCode=1;
 }finally{
  if(browser)await browser.close();server.kill();await new Promise(r=>{if(server.exitCode!==null)r();else server.once('exit',r);});
  const resolved=path.resolve(dir);assert.ok(resolved.startsWith(path.resolve(data)+path.sep),'Unsafe cleanup');fs.rmSync(resolved,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
