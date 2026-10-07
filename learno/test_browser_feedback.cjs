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

  const setup=spawnSync(python,['-B',path.join(root,'feedback.py'),'--reviewer','extended-owner'],{env,encoding:'utf8'});assert.equal(setup.status,0,setup.stderr);
  await check('private author/reviewer feedback and escaped free text',async()=>{
   await navigate(b,'feedback');await b.locator('#feedback-form textarea').fill('Private feedback <script>alert(1)</script>');await b.locator('#feedback-form button[type=submit]').click();await b.locator('[data-feedback]').waitFor();assert.equal(await b.locator('[data-feedback] script').count(),0);assert.equal(await b.locator('[data-action=feedback-read]').count(),0);
   await navigate(a,'feedback');await a.locator('[data-feedback]').waitFor();assert.ok((await a.locator('[data-feedback]').innerText()).includes('Private feedback'));await rerender(a,()=>a.locator('[data-action=feedback-read]').click());assert.ok((await a.locator('[data-feedback]').innerText()).includes('Gelesen'));
   assert.equal((await state(a)).posts.length,0);assert.equal((await state(b)).posts.length,0);
   const outsider=await browser.newContext({viewport:{width:390,height:844}}),c=await outsider.newPage();await register(c,'feedback-outsider');await navigate(c,'feedback');assert.equal(await c.locator('[data-feedback]').count(),0);assert.equal(await c.locator('[data-action=feedback-filter]').count(),0);
  });
  await check('feedback draft survives navigation and rejects empty input',async()=>{
   await navigate(b,'feedback');await b.locator('#feedback-form textarea').fill('My unsent feedback');await navigate(b,'learn');await navigate(b,'feedback');assert.equal(await b.locator('#feedback-form textarea').inputValue(),'My unsent feedback');await b.locator('#feedback-form textarea').fill('');await b.locator('#feedback-form button[type=submit]').click();assert.equal(await b.locator('#feedback-form').evaluate(f=>f.checkValidity()),false);assert.equal(await b.locator('[data-feedback]').count(),1);
  });
  await check('feedback mobile layout at 320 390 and 700 pixels',async()=>{
   for(const width of [320,390,700]){
    await b.setViewportSize({width,height:844});await navigate(b,'feedback');
    assert.equal(await b.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
    const privacy=await b.locator('#feedback-form').locator('..').innerText();assert.ok(privacy.includes('nur für dich und Admins sichtbar'));assert.ok(!privacy.includes('extended-owner'));
    await b.locator('#feedback-form textarea').fill('Mobiler Bediencheck '+width);await b.locator('#feedback-form button[type=submit]').tap();await b.getByText('Mobiler Bediencheck '+width,{exact:true}).waitFor();
    assert.equal(await b.locator('#feedback-form textarea').inputValue(),'');
    await b.screenshot({path:path.join(data,'feedback-mobile-'+width+'.png'),fullPage:false});
    const nav=await b.locator('.mobile-nav').boundingBox();assert.ok(nav&&nav.width<=width+1);
    for(const id of ['home','learn','exams','feed','groups','stats','ranking','profile','feedback']){await navigate(b,id);assert.equal(await b.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Overflow '+id+' at '+width);}
   }
  });
  if(pageErrors.length)failures.push({name:'uncaught browser errors',message:JSON.stringify(pageErrors)});
  console.log(JSON.stringify({checks:3,failures},null,2));if(failures.length)process.exitCode=1;
 }finally{
  if(browser)await browser.close();server.kill();await new Promise(r=>{if(server.exitCode!==null)r();else server.once('exit',r);});
  const resolved=path.resolve(dir);assert.ok(resolved.startsWith(path.resolve(data)+path.sep),'Unsafe cleanup');fs.rmSync(resolved,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
