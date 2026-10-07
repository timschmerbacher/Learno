'use strict';
/* Presentation and read-only page data; mutations still use the shared dispatcher. */
let examView='upcoming',groupView='mine',examSearch='',examSort='date';
const discussionDrafts=new Map();
pages.feedback=['Feedback','feed'];
let feedbackData=null,feedbackFilter='all',feedbackDraft='';
let feedFilter='all',feedGroup='',feedPages=1,feedData={posts:[],comments:[],has_more:false,next_before_id:null};
let weeklyData=null,noticeData=null,feedGeneration=0;
const expandedComments=new Set(),expandedReplies=new Set(),replyTargets=new Map();
const isArchived=e=>!!(e.archived_at||e.event_archived_at);
const examBucket=e=>isArchived(e)?'archive':e.completed?'completed':'upcoming';
function groupLabel(id){const g=state.groups.find(g=>g.id===id);return g?`${g.parent_id?'Untergruppe':'Hauptgruppe'}: ${g.name}`:'Gruppe';}
function visibility(p){return p.revoked_at?'Privat · Freigabe zurückgenommen':p.audience==='private'?'Privat':p.audience==='group'?groupLabel(p.target_group_id):'Öffentlich';}
function resetPresentation(){feedbackDraft='';feedbackData=null;feedbackFilter='all';discussionDrafts.clear();examSearch='';examSort='date';examView='upcoming';groupView='mine';feedFilter='all';feedGroup='';feedPages=1;feedGeneration++;feedData={posts:[],comments:[],has_more:false,next_before_id:null};weeklyData=null;expandedComments.clear();expandedReplies.clear();replyTargets.clear();}
async function loadFeed(append=false){
 const generation=++feedGeneration;
 if(feedGroup&&!state.groups.some(g=>g.joined&&g.id===Number(feedGroup)))feedGroup='';
 const base=`feed?filter=${feedFilter}${feedFilter==='groups'&&feedGroup?'&group_id='+feedGroup:''}`;
 let posts=append?[...feedData.posts]:[],comments=append?[...feedData.comments]:[],cursor=append?feedData.next_before_id:null,result;
 const count=append?1:feedPages;
 for(let i=0;i<count;i++){
  result=await api(base+(cursor?'&before_id='+cursor:''));
  if(generation!==feedGeneration)return;
  posts.push(...result.posts);comments.push(...result.comments);cursor=result.next_before_id;
  if(!result.has_more)break;
 }
 feedData={posts,comments,has_more:result.has_more,next_before_id:cursor};
 if(append)feedPages++;
 state.posts=posts;state.comments=comments;
}
async function loadExtras(){
 if(page==='feedback')await loadFeedback();
 if(page==='feed')await loadFeed();
 if(page==='home'||page==='stats')weeklyData=await api('statistics');
}
function navButton(id,name,ico){return `<button data-page="${id}" class="${page===id?'active':''}" ${page===id?'aria-current="page"':''}>${icon(ico)}<span>${name}</span></button>`;}
function render(){
 if(!state)return auth();
 captureDiscussionDrafts();
 const extra=['groups','stats','ranking','profile','feedback'].includes(page);
 $('#app').innerHTML=`<div class="shell"><aside class="sidebar"><div class="logo">${icon('logo')}learno<span>.</span></div><small>DEIN WORKSPACE</small><nav class="nav" aria-label="Hauptnavigation">${Object.entries(pages).map(([id,[name,ico]])=>navButton(id,name,ico)).join('')}</nav><div class="side-note"><strong>Ein Schritt nach dem anderen.</strong>Jede Lernsession zählt.</div><div class="account"><div class="avatar">${initials(state.user.username)}</div><div class="account-name">${esc(state.user.username)}</div><button class="logout" data-action="logout" aria-label="Abmelden">${icon('out')}</button></div></aside><main class="main"><div class="topbar"><div class="crumb">${icon(pages[page][1])}<span>${pages[page][0]}</span></div><button class="notice-trigger" data-action="notices-open" aria-label="${state.notice_count} ungelesene Änderungen">${state.notice_count} Änderungen</button></div>${timerStrip()}<div id="content">${({home,learn,exams,stats,feed,ranking,profile,feedback:feedbackPage,groups:groupsPage}[page])()}</div><div class="footer-note">Learno · Raum für deinen Fortschritt.</div></main><nav class="mobile-nav" aria-label="Mobile Hauptnavigation">${navButton('home','Start','home')}${navButton('learn','Lernen','clock')}${navButton('exams','Prüfungen','book')}${navButton('feed','Feed','feed')}<button data-action="more" class="${extra?'active':''}" aria-haspopup="dialog">${icon('user')}<span>Mehr</span></button></nav></div>`;
 restoreDiscussionDrafts();paintBars();tick();
}
function home(){
 const today=weeklyData?.today||localDate(),daily=state.sessions.filter(s=>s.date===today).reduce((a,s)=>a+s.seconds,0),weekly=weeklyData?.current_seconds||0,next=priorities()[0];
 const focus=state.active?activeCard():`<section class="card focus next-step"><div><p class="eyebrow">DEIN NÄCHSTER SCHRITT</p><h2>${next?esc(next.subject):'Zeit für deinen Fokus.'}</h2><p>${next?esc(next.title)+' · '+dayText(next.priority.days):'Starte eine freie Lernsession oder plane deine nächste Prüfung.'}</p></div>${button(icon('play')+(next?' Jetzt lernen':' Freie Session starten'),'start',next?`data-id="${next.id}"`:'')}</section>`;
 return heading(`Dein nächster Schritt, ${esc(state.user.username)}.`,'Ein Fokus. Ein guter Anfang.',button('Nachtragen','manual','','secondary'))+focus+`<div class="metrics section-space">${metric('Heute gelernt',duration(daily),'Gespeicherte Lernzeit','clock')}${metric('Diese Woche',duration(weekly),weeklyData?.weekly_goal_minutes!==null&&weeklyData?.weekly_goal_minutes!==undefined?'Privates Ziel: '+duration(weeklyData.weekly_goal_minutes*60):'Montag bis heute','chart')}${metric('Anstehende Prüfungen',state.exams.filter(e=>examBucket(e)==='upcoming').length,'Deine Ziele','book')}</div><div class="grid"><section class="card"><div class="card-head"><h2>Zuletzt gelernt</h2><button class="text-button" data-page="learn">Alle Sessions</button></div>${sessionTable(state.sessions.slice(0,4),false)}</section><section class="card"><h2>Weitere Prüfungen</h2>${priorities().slice(next?1:0,4).map(e=>`<div class="exam-row"><div class="score">${e.priority.score}<small>/10</small></div><div class="grow"><h3>${esc(e.subject)}</h3><p class="meta">${esc(e.title)} · ${dayText(e.priority.days)}</p></div></div>`).join('')||empty('Ein Schritt nach dem anderen.','Alle Prüfungen findest du in deiner Planung.')}<button class="text-button" data-page="exams">Prüfungen ansehen</button></section></div>`;
}
function tabs(items,selected,action){return `<div class="view-tabs" role="group" aria-label="Ansicht auswählen">${items.map(([value,label])=>`<button data-action="${action}" data-view="${value}" aria-pressed="${selected===value}" class="${selected===value?'selected':''}">${label}</button>`).join('')}</div>`;}
function examActions(e){
 const archived=isArchived(e),attr=`data-id="${e.id}"`,files=e.has_group_access||state.files.some(f=>f.exam_event_id===e.exam_event_id&&f.private_owner_id===state.user.id);
 return `<details class="action-menu"><summary aria-label="Weitere Aktionen für ${esc(e.title)}">Weitere Aktionen</summary><div class="menu-items">${button(e.completed?'Note ändern':'Note eintragen','grade',attr)}${e.completed?button('Ergebnis teilen','share-exam',attr):''}${button('Sessions','exam-sessions',attr)}${files?button('Unterlagen','personal-files',attr):''}${button('Historie','exam-history',attr)}${!archived?button('Bearbeiten','personal-edit',attr)+button(e.deletion_mode==='deleted'?'Endgültig löschen':'Archivieren','personal-delete',attr,'danger'):e.archived_at?button('Wiederherstellen','personal-restore',attr):''}<button type="button" class="button menu-close" data-action="menu-close">Schließen</button></div></details>`;
}
function exams(){
 const items=[['upcoming','Anstehend'],['completed','Abgeschlossen'],['archive','Archiv']];
 const list=state.exams.filter(e=>examBucket(e)===examView&&(e.subject+' '+e.title).toLocaleLowerCase('de').includes(examSearch.toLocaleLowerCase('de'))).sort((a,b)=>examSort==='subject'?a.subject.localeCompare(b.subject,'de')||a.exam_date.localeCompare(b.exam_date):a.exam_date.localeCompare(b.exam_date)||a.subject.localeCompare(b.subject,'de'));
 return heading('Deine Prüfungen.','Planung, Ergebnisse und Historie klar getrennt.',button('Prüfung anlegen','create-exam'))+tabs(items.map(([key,label])=>[key,`${label} (${state.exams.filter(e=>examBucket(e)===key).length})`]),examView,'exam-view')+`<form id="exam-search-form" class="filters"><label>Fach oder Titel suchen<input name="search" value="${esc(examSearch)}"></label><label>Sortieren<select name="sort"><option value="date" ${examSort==='date'?'selected':''}>Termin</option><option value="subject" ${examSort==='subject'?'selected':''}>Fach</option></select></label><button type="submit" class="button secondary">Anwenden</button></form><div class="exam-cards">${list.map(e=>`<section class="card exam-card" data-exam="${e.id}"><div class="row"><span class="badge">${isArchived(e)?'Archiviert':e.completed?'Abgeschlossen':e.priority?dayText(e.priority.days):e.exam_date<(weeklyData?.today||localDate())?'Termin vergangen':'Offen'}</span><span class="meta">${esc(e.exam_date)}</span></div><h2>${esc(e.subject)}</h2><p class="meta">${esc(e.title)}</p><p class="visibility">${esc(e.group_id?groupLabel(e.group_id):'Privat')}</p><div class="exam-details"><div><span>Lernzeit</span><strong>${duration(e.seconds)}</strong></div><div><span>${e.completed?'Note':'Priorität'}</span><strong>${e.completed?e.grade+'/5':e.priority?e.priority.score+'/10':'–'}</strong></div></div><div class="actions">${button(e.startable?'Lernen':e.completed&&!isArchived(e)?'Ergebnis ansehen':'Details ansehen',e.startable?'start':'exam-details',`data-id="${e.id}"`)}${examActions(e)}</div></section>`).join('')||`<section class="card full">${empty('Keine Prüfungen in dieser Ansicht.','Deine gespeicherten Daten bleiben in den anderen Ansichten erreichbar.')}</section>`}</div>`;
}
function groupCard(g){return `<div class="group-entry"><div class="grow"><h3>${esc(g.name)}</h3><div class="visibility">${g.parent_id?'Untergruppe':'Hauptgruppe'}${g.joined?' · Mitglied':''}${g.owner_id===state.user.id?' · Verwaltung':''}</div><p class="meta">${g.member_count} Mitglieder · ${esc(g.owner_name)}</p>${g.description?`<p class="compact-p">${esc(g.description)}</p>`:''}</div>${g.joined?button('Öffnen','group-open',`data-id="${g.id}"`,'secondary'):button(g.parent_id&&!state.groups.some(p=>p.id===g.parent_id&&p.joined)?'Zuerst Hauptgruppe beitreten':'Beitreten','group-join',`data-id="${g.parent_id&&!state.groups.some(p=>p.id===g.parent_id&&p.joined)?g.parent_id:g.id}"`)}</div>`;}
function groupsPage(){
 const active=state.groups.find(g=>g.id===selectedGroup&&g.joined),query=groupSearch.toLowerCase();
 const allowed=state.groups.filter(g=>groupView==='discover'||g.joined);
 const filtered=allowed.filter(g=>(g.name+' '+g.description).toLowerCase().includes(query));
 const roots=allowed.filter(g=>!g.parent_id&&(filtered.some(x=>x.id===g.id||x.parent_id===g.id)));
 return heading('Deine Lerngruppen.','Hauptgruppen mit den passenden Untergruppen.',button('Hauptgruppe erstellen','group-new'))+tabs([['mine','Meine Gruppen'],['discover','Entdecken']],groupView,'group-view')+`<form id="group-search-form" class="filters"><label>Gruppen suchen<input name="search" value="${esc(groupSearch)}"></label><button class="button secondary">Suchen</button></form><div class="group-trees">${roots.map(g=>`<details class="group-tree" ${groupView==='mine'||query||g.joined?'open':''}><summary>${esc(g.name)} <span class="meta">Hauptgruppe${g.joined?' · Mitglied':''}</span></summary>${groupCard(g)}<div class="subgroups">${filtered.filter(c=>c.parent_id===g.id).map(groupCard).join('')}</div></details>`).join('')||empty('Keine passenden Gruppen.','Unter Entdecken kannst du weitere Gruppen suchen.')}</div>${active?groupDetail(active):''}`;
}
function commentItem(c,p,reply=false){const parent=feedData.comments.find(x=>x.id===c.parent_comment_id);return `<div class="comment ${reply?'reply':''}" data-comment="${c.id}" tabindex="-1"><div><strong>${esc(c.username)}</strong>${reply&&parent?`<button class="text-button reply-reference" data-action="comment-reference" data-id="${parent.id}" data-post="${p.id}">Antwort an ${esc(parent.username)}</button>`:''}</div><p>${esc(c.text)}</p>${p.can_comment?`<button class="text-button" data-action="reply" data-id="${c.id}" data-post="${p.id}">Antworten</button>`:''}</div>`;}
function discussion(p){
 const list=feedData.comments.filter(c=>c.post_id===p.id),map=new Map(list.map(c=>[c.id,c]));
 const rootOf=c=>{const seen=new Set();while(c.parent_comment_id&&map.has(c.parent_comment_id)&&!seen.has(c.id)){seen.add(c.id);c=map.get(c.parent_comment_id);}return c.id;};
 const roots=list.filter(c=>!c.parent_comment_id),shown=expandedComments.has(p.id)?roots:roots.slice(-3);
 const threads=shown.map(c=>{const replies=list.filter(r=>r.parent_comment_id&&rootOf(r)===c.id),visible=expandedReplies.has(c.id)?replies:replies.slice(0,2);return `<div class="comment-thread">${commentItem(c,p)}${visible.map(r=>commentItem(r,p,true)).join('')}${replies.length>visible.length?button(`${replies.length-visible.length} weitere Antworten`,'replies-more',`data-id="${c.id}"`,'small soft'):''}</div>`;}).join('');
 const target=map.get(replyTargets.get(p.id));
 return `<div class="comments" data-discussion="${p.id}">${roots.length>shown.length?button(`${roots.length-shown.length} ältere Kommentare`,'comments-more',`data-id="${p.id}"`,'small soft'):''}${threads}${p.can_comment?target?`<form class="reply-form" data-post="${p.id}" data-parent="${target.id}"><label>Antwort an ${esc(target.username)}<textarea name="text" maxlength="500" required></textarea></label><p class="error"></p><div class="actions"><button type="submit" class="button small">Antwort senden</button>${button('Abbrechen','reply-cancel',`data-id="${p.id}"`,'small secondary')}</div></form>`:`<form class="comment-form" data-post="${p.id}"><input aria-label="Kommentar zu ${esc(p.subject)}" name="text" maxlength="500" required placeholder="Kommentar schreiben"><button type="submit" class="button small secondary">Senden</button></form>`:'<p class="subtle">Du kannst diesen Beitrag lesen.</p>'}</div>`;
}
function postMenu(p){return `<details class="action-menu post-menu"><summary aria-label="Weitere Aktionen für deinen Beitrag">⋯</summary><div class="menu-items">${button('Beitrag löschen','post-delete',`data-id="${p.id}"`,'danger')}${!p.revoked_at&&p.audience!=='private'?button('Freigabe zurücknehmen','post-revoke',`data-id="${p.id}"`,'secondary'):''}${button('Schließen','menu-close','','secondary')}</div></details>`;}
function feed(){
 const descriptions={all:'Teile eine Lernsession oder ein Ergebnis.',groups:'Wähle eine andere Gruppe oder teile ein Ergebnis mit deiner Gruppe.',friends:'Bestätigte Freundschaften und sichtbare Beiträge erscheinen hier.',public:'Öffentliche Lernsessionen und bisherige öffentliche Beiträge erscheinen hier.',mine:'Hier findest du eigene Beiträge, private Momentaufnahmen und zurückgenommene Freigaben.'};
 return heading('Zusammen weiterkommen.','Deine Gruppen, Freunde und öffentliche Beiträge.',`<div class="actions">${button('Beitrag verfassen','compose')}${button('Vergleichen','compare','','secondary')}</div>`)+tabs([['all','Alle'],['groups','Meine Gruppen'],['friends','Freunde'],['public','Öffentlich'],['mine','Meine Beiträge']],feedFilter,'feed-filter')+`${feedFilter==='groups'?`<label class="feed-group-label">Gruppe<select id="feed-group"><option value="">Alle meine Gruppen</option>${state.groups.filter(g=>g.joined).map(g=>`<option value="${g.id}" ${feedGroup===String(g.id)?'selected':''}>${esc(groupLabel(g.id))}</option>`).join('')}</select></label>`:''}<div class="feed-list">${feedData.posts.map(p=>`<article class="card post" data-post="${p.id}"><header><div class="avatar">${initials(p.username)}</div><div class="grow"><h3>${esc(p.username)}</h3><span class="meta">${new Date(p.created).toLocaleString('de-AT',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}</span><span class="post-visibility">${esc(visibility(p))}</span></div>${p.user_id===state.user.id?postMenu(p):''}</header>${p.text?`<p class="post-text">${esc(p.text)}</p>`:''}<div class="post-context"><span class="meta">${p.kind==='result'?'Prüfung':'Lernsession'}</span><h2>${esc(p.subject)}</h2><p class="meta">${esc(p.title)}</p></div><div class="post-data">${p.seconds!==undefined?`<div><span>Lernzeit</span><strong>${duration(p.seconds)}</strong></div>`:''}${p.grade!==undefined&&p.grade!==null?`<div><span>Note</span><strong>${p.grade}/5</strong></div>`:''}${p.session_count!==undefined&&p.session_count!==null?`<div><span>Sessions</span><strong>${p.session_count}</strong></div>`:''}</div>${discussion(p)}</article>`).join('')||`<section class="card">${empty('Keine Beiträge in dieser Ansicht.',descriptions[feedFilter])}</section>`}${feedData.has_more?button('Weitere Beiträge laden','feed-more','','secondary'):''}</div>`;
}
function columnChart(items,kind='subjects'){
 const max=Math.max(1,...items.map(i=>i.seconds));
 return `<div class="column-chart ${kind}" role="list" aria-label="${kind==='weeks'?'Lernzeit je Kalenderwoche':'Lernzeit je Fach'}">${items.map(i=>`<div class="chart-column" role="listitem"><span class="column-value">${duration(i.seconds)}</span><div class="column-stage" aria-hidden="true"><div class="column-bar" data-height="${160*i.seconds/max}"></div></div><span class="column-label">${esc(i.label)}</span>${i.current?'<small class="current-week">Laufend</small>':''}</div>`).join('')}</div>`;
}
function stats(){
 const s=weeklyData;if(!s)return empty('Statistik wird geladen.','');
 const diff=Math.round(Math.abs(s.difference_seconds)/60);
 return heading('Dein Lernen im Blick.','Lernzeit nach Fach, Ergebnisse und Wochenentwicklung.')+filteredStats()+`<section class="card section-space weekly-panel"><div class="card-head"><h2>Letzte sechs Kalenderwochen</h2><span class="badge">Privat</span></div><p class="subtle">Wochenwerte und Vorwochenvergleich sind unabhängig vom Fach- und Datumsfilter.</p>${columnChart([...s.weeks].sort((a,b)=>a.week_start.localeCompare(b.week_start)).map(w=>({seconds:w.seconds,label:dateText(w.week_start),current:w.current})),'weeks')}<p class="week-comparison">${diff===0?'Gleich viel Lernzeit':`${diff} Minuten ${s.difference_seconds>0?'mehr':'weniger'}`} als im gleichen Zeitraum der Vorwoche.</p></section><details class="card optional-goal"><summary>Optionales Wochenziel</summary><p class="subtle">Privat und unabhängig vom Fach- und Datumsfilter. Laufende Timer zählen erst nach dem Speichern.</p><form id="weekly-goal-form" class="goal-form"><label>Freiwilliges Wochenziel in Stunden<input name="hours" type="number" min="0.25" max="168" step="0.25" value="${s.weekly_goal_minutes===null?'':s.weekly_goal_minutes/60}" placeholder="Kein Ziel"></label><button type="submit" class="button secondary">Ziel speichern</button>${button('Deaktivieren','goal-disable','','soft')}<p class="error" role="alert"></p></form>${s.weekly_goal_minutes!==null?`<div class="goal-progress"><p><strong>${duration(s.current_seconds)}</strong> von ${duration(s.weekly_goal_minutes*60)} · ${duration(s.remaining_seconds)} verbleibend</p><progress max="100" value="${s.goal_percent}" aria-label="Wochenziel erreicht"></progress></div>`:''}</details>`;
}
async function noticesModal(append=false,requireOpen=false){
 const result=await api('notices'+(append&&noticeData?.next_before_id?'?before_id='+noticeData.next_before_id:''));
 noticeData={...result,notices:append?[...noticeData.notices,...result.notices]:result.notices};state.notice_count=result.notice_count;
 const badge=$('.notice-trigger');if(badge){badge.textContent=`${result.notice_count} Änderungen`;badge.setAttribute('aria-label',`${result.notice_count} ungelesene Änderungen`);}
 if(requireOpen&&!$('#modal').open)return;
 showModal('Änderungen',`<p>${result.notice_count} ungelesene Änderungen</p>${noticeData.notices.map(n=>`<div class="notice-item"><p>${esc(n.text)}</p>${button('Gelesen','notice-read-one',`data-id="${n.id}"`,'small secondary')}</div>`).join('')||'<p>Alles gelesen.</p>'}<div class="actions">${result.has_more?button('Weitere Änderungen','notices-more','','secondary'):''}${result.notice_count?button('Alle gelesen','notices-read-all'):''}</div>`);
}
function examDetails(e){showModal(isArchived(e)?'Prüfungsdetails':'Prüfungsergebnis',`<h3>${esc(e.subject)} · ${esc(e.title)}</h3><p>${esc(e.exam_date)} · ${esc(e.group_id?groupLabel(e.group_id):'Privat')}</p><p>Lernzeit: ${duration(e.seconds)} · ${e.session_count} Sessions${e.grade!==null?' · Note '+e.grade+'/5':''}</p><div class="actions">${e.completed?button('Ergebnis teilen','share-exam',`data-id="${e.id}"`):''}${button('Sessions','exam-sessions',`data-id="${e.id}"`,'secondary')}${button('Historie','exam-history',`data-id="${e.id}"`,'secondary')}${e.archived_at?button('Wiederherstellen','personal-restore',`data-id="${e.id}"`):''}</div>`);}
async function uiAction(action,id,b){
 switch(action){
 case 'post-delete':{
  const p=(state.own_posts||[]).find(p=>p.id===id)||feedData.posts.find(p=>p.id===id);
  if(!confirm('Beitrag und alle zugehörigen Kommentare und Antworten endgültig löschen? Deine ursprüngliche Lernsession, Prüfung und Note bleiben erhalten.'+rankingWarning(p||{})))return true;
  captureDiscussionDrafts();await api('post-delete',{post_id:id});
  document.querySelector(`[data-post="${id}"].post`)?.remove();
  const prefix=`${state.user.id}:${id}:`;for(const key of discussionDrafts.keys())if(key.startsWith(prefix))discussionDrafts.delete(key);
  for(const c of feedData.comments.filter(c=>c.post_id===id))expandedReplies.delete(c.id);
  replyTargets.delete(id);expandedComments.delete(id);await refresh();toast('Beitrag endgültig gelöscht.');return true;
 }
 case 'feedback-filter':feedbackFilter=b.dataset.view;await loadFeedback();render();return true;
 case 'feedback-more':await loadFeedback(true);render();return true;
 case 'feedback-read':await api('feedback-read',{feedback_id:id});await loadFeedback();render();return true;
 case 'compose':composeDialog();return true;
 case 'share-session':composeDialog('session:'+id);return true;
 case 'session-details':sessionDetails(id);return true;
 case 'session-ranking':{const s=state.sessions.find(s=>s.id===id);await api('session-ranking',{session_id:id,public:!s.public});await refresh();sessionDetails(id);return true;}
 case 'timer-pause':case 'timer-resume':await api(action==='timer-pause'?'pause':'resume',{});await refresh();return true;
 case 'saved-done':$('#modal').close();return true;
 case 'comment-reference':{const c=feedData.comments.find(c=>c.id===id);if(c){expandedComments.add(c.post_id);expandedReplies.add(commentRoot(id));updateDiscussion(c.post_id);const target=document.querySelector(`[data-comment="${id}"]`);target?.scrollIntoView({block:'nearest'});target?.focus({preventScroll:true});}return true;}
 case 'more':showModal('Mehr',`<nav class="more-nav">${['groups','stats','ranking','profile','feedback'].map(id=>navButton(id,pages[id][0],pages[id][1])).join('')}<button data-action="logout">Abmelden</button></nav>`);return true;
 case 'menu-close':{const menu=b.closest('details');menu.open=false;menu.querySelector('summary').focus();return true;}
 case 'exam-view':examView=b.dataset.view;render();return true;
 case 'exam-details':examDetails(state.exams.find(e=>e.id===id));return true;
 case 'group-view':groupView=b.dataset.view;selectedGroup=null;render();return true;
 case 'feed-filter':feedFilter=b.dataset.view;feedGroup='';feedPages=1;replyTargets.clear();await loadFeed();render();return true;
 case 'feed-more':b.disabled=true;try{await loadFeed(true);render();}finally{b.disabled=false;}return true;
 case 'reply':replyTargets.set(Number(b.dataset.post),id);updateDiscussion(Number(b.dataset.post));document.querySelector(`.reply-form[data-post="${b.dataset.post}"] textarea`)?.focus();return true;
 case 'reply-cancel':replyTargets.delete(id);updateDiscussion(id,b);return true;
 case 'comments-more':expandedComments.add(id);updateDiscussion(id,b);return true;
 case 'replies-more':expandedReplies.add(id);updateDiscussion(feedData.comments.find(c=>c.id===id)?.post_id,b);return true;
 case 'notices-open':await noticesModal();return true;
 case 'notices-more':await noticesModal(true);return true;
 case 'notice-read-one':await api('notice-read',{notice_id:id});await noticesModal(false,true);return true;
 case 'notices-read-all':await api('notices-read-all',{});await noticesModal(false,true);return true;
 case 'goal-disable':await api('weekly-goal',{weekly_goal_minutes:null});await refresh();return true;
 default:return false;
 }
}
async function uiSubmit(form,fd,data){
 if(form.getAttribute('id')==='feedback-form'){await api('feedback',{text:data.text});feedbackDraft='';form.querySelector('[name=text]').value='';await loadFeedback();render();toast('Feedback privat gesendet.');return true;}
 if(form.getAttribute('id')==='exam-search-form'){examSearch=data.search.trim();examSort=data.sort==='subject'?'subject':'date';render();return true;}
 if(form.getAttribute('id')==='post-compose-form'){
  const [kind,rawId]=data.source.split(':'),id=Number(rawId),audience=data.target==='public'?'public':data.target?'group':'private';
  if(!['session','result'].includes(kind)||!id)throw Error('Bitte eine Session oder ein Ergebnis auswählen.');
  await api('post',{...(kind==='session'?{session_id:id}:{user_exam_state_id:id}),audience,target_group_id:audience==='group'?Number(data.target):null,text:data.text,
   show_seconds:fd.has('show_seconds')?1:0,show_grade:fd.has('show_grade')?1:0,show_count:fd.has('show_count')?1:0});
  $('#modal').close();await refresh();toast(audience==='private'?'Private Momentaufnahme gespeichert.':'Beitrag geteilt. Rankingfreigabe unverändert.');return true;
 }
 if(form.classList.contains('reply-form')||form.classList.contains('comment-form')){
  const pid=Number(form.dataset.post),parent=form.dataset.parent?Number(form.dataset.parent):null;
  const result=await api('comment',{post_id:pid,...(parent?{parent_comment_id:parent}:{}),text:data.text});
  discussionDrafts.delete(draftKey(pid,parent));form.querySelector('[name=text]').value='';
  replyTargets.delete(pid);await refresh(false);expandedComments.add(pid);
  const c=feedData.comments.find(c=>c.id===result.comment_id);if(c?.parent_comment_id)expandedReplies.add(commentRoot(c.id));
  updateDiscussion(pid);const visible=document.querySelector(`[data-comment="${result.comment_id}"]`);visible?.scrollIntoView({block:'nearest'});visible?.focus({preventScroll:true});toast('Kommentar gespeichert.');return true;
 }
 if(form.getAttribute('id')==='weekly-goal-form'){
  const minutes=data.hours===''?null:Number(data.hours)*60;
  if(minutes!==null&&(!Number.isInteger(minutes)||minutes<15||minutes>10080||minutes%15))throw Error('Bitte 0,25 bis 168 Stunden in Viertelstunden angeben.');
  await api('weekly-goal',{weekly_goal_minutes:minutes});await refresh();return true;
 }
 return false;
}
document.addEventListener('change',async event=>{
 if(event.target.id==='feed-group'){feedGroup=event.target.value;feedPages=1;try{await loadFeed();render();}catch(error){toast(error.message);}}
});
document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.action-menu[open]').forEach(m=>m.open=false);});

// Private, in-memory drafts belong to the current account and exact reply context.
function draftKey(post,parent=null){return `${state.user.id}:${post}:${parent||0}`;}
function captureDiscussionDrafts(){if(!state)return;document.querySelectorAll('.comment-form,.reply-form').forEach(f=>{const field=f.querySelector('[name=text]');if(field)discussionDrafts.set(draftKey(f.dataset.post,f.dataset.parent),field.value);});}
function restoreDiscussionDrafts(){if(!state)return;document.querySelectorAll('.comment-form,.reply-form').forEach(f=>{const field=f.querySelector('[name=text]');if(field)field.value=discussionDrafts.get(draftKey(f.dataset.post,f.dataset.parent))||'';});}
function commentRoot(id){let c=feedData.comments.find(c=>c.id===id);const seen=new Set();while(c?.parent_comment_id&&!seen.has(c.id)){seen.add(c.id);c=feedData.comments.find(x=>x.id===c.parent_comment_id);}return c?.id||id;}
function updateDiscussion(pid,trigger=null){
 captureDiscussionDrafts();const current=document.querySelector(`[data-discussion="${pid}"]`),p=feedData.posts.find(p=>p.id===pid);if(!current)return;
 if(!p){render();return;}
 const scroll=window.scrollY,action=trigger?.dataset.action,id=trigger?.dataset.id;
 current.outerHTML=discussion(p);restoreDiscussionDrafts();
 const replacement=action?document.querySelector(`[data-discussion="${pid}"] [data-action="${action}"][data-id="${id}"]`):null;
 const fallback=document.querySelector(`[data-discussion="${pid}"] [data-comment]`);
 (replacement||fallback)?.focus({preventScroll:true});window.scrollTo(0,scroll);
}
document.addEventListener('input',e=>{if(e.target.closest('#feedback-form'))feedbackDraft=e.target.value;const f=e.target.closest('.comment-form,.reply-form');if(f)discussionDrafts.set(draftKey(f.dataset.post,f.dataset.parent),e.target.value);if(e.target.closest('#post-compose-form'))composerPreview();});
function timerStrip(){const a=state.active;if(!a)return '';return `<aside class="timer-strip" aria-label="Laufende Lernsession"><div class="grow"><strong>${esc(a.subject)}</strong><span>${a.paused?'Pausiert':'Läuft'} · <span data-live-timer>00:00:00.0</span></span></div>${button(a.paused?'Fortsetzen':'Pause',a.paused?'timer-resume':'timer-pause','','small secondary')}<button class="button small" data-page="learn">Zur Session</button></aside>`;}
function sessionTable(sessions,actions=true){
 const desktop=desktopSessionTable(sessions,actions);if(!sessions.length)return desktop;
 return `<div class="desktop-sessions">${desktop}</div><div class="mobile-sessions">${sessions.map(s=>`<article class="session-card"><h3>${esc(s.subject)}</h3><p>${dateText(s.date)} ${s.date.slice(0,4)} · <strong>${duration(s.seconds)}</strong></p><p class="meta">${esc(state.exams.find(e=>e.id===s.user_exam_state_id)?.title||'Freie Lernsession')}</p><p class="meta">${esc(s.location)}</p>${actions?`<div class="actions">${button('Details','session-details',`data-id="${s.id}"`,'small secondary')}${button('Teilen','share-session',`data-id="${s.id}"`,'small soft')}</div>`:''}</article>`).join('')}</div>`;
}
function sessionDetails(id){const s=state.sessions.find(s=>s.id===id);if(!s)return;showModal('Lernsession',`<h3>${esc(s.subject)}</h3><p>${esc(s.date)} · ${duration(s.seconds)}</p><p>${esc(s.location)} · ${esc(s.resources)}</p><p>${s.interruptions} Unterbrechungen</p><p class="hint">${s.public?'Diese Lernzeit zählt zur öffentlichen Rangliste':'Diese Lernzeit zählt nicht zur öffentlichen Rangliste'}. Die Sichtbarkeit deiner Beiträge wird getrennt gesteuert.</p><div class="actions">${button(s.public?'Lernzeit aus Ranking zurücknehmen':'Lernzeit im Ranking veröffentlichen','session-ranking',`data-id="${id}"`,'secondary')}${button('Teilen','share-session',`data-id="${id}"`)}</div>`);}
function savedSession(id){const s=state.sessions.find(s=>s.id===id);if(!s)return;showModal('Session gespeichert',`<h3>${esc(s.subject)}</h3><p>${duration(s.seconds)} Lernzeit sind gespeichert. Teilen ist freiwillig.</p><div class="actions">${button('Fertig','saved-done','','secondary')}${button('Teilen','share-session',`data-id="${id}"`)}</div>`);}
function composeDialog(source='',text=''){
 const [kind,raw]=source.split(':'),id=Number(raw),item=kind==='session'?state.sessions.find(s=>s.id===id):state.exams.find(e=>e.id===id&&e.completed&&e.grade!==null);
 const options=state.sessions.map(s=>`<option value="session:${s.id}" ${source==='session:'+s.id?'selected':''}>Session: ${esc(s.subject)} · ${esc(s.date)} · ${duration(s.seconds)}</option>`).join('')+state.exams.filter(e=>e.completed&&e.grade!==null).map(e=>`<option value="result:${e.id}" ${source==='result:'+e.id?'selected':''}>Ergebnis: ${esc(e.subject)} · ${esc(e.title)}</option>`).join('');
 showModal('Beitrag verfassen',`<form id="post-compose-form"><label>Session oder Prüfungsergebnis<select name="source" id="compose-source" required><option value="">Bitte auswählen</option>${options}</select></label>${item?`<label>Sichtbarkeit<select name="target"><option value="">Privat</option>${state.groups.filter(g=>g.joined).map(g=>`<option value="${g.id}">${esc(groupLabel(g.id))}</option>`).join('')}${kind==='session'?'<option value="public">Öffentlich</option>':''}</select></label><div class="checks">${kind==='result'?'<label class="check"><input type="checkbox" name="show_grade">Note</label>':''}<label class="check"><input type="checkbox" name="show_seconds">${kind==='session'?'Lernzeit':'Gesamte Lernzeit'}</label>${kind==='result'?'<label class="check"><input type="checkbox" name="show_count">Anzahl Lernsessions</label>':''}</div>`:''}<label>Dein Beitrag<textarea name="text" maxlength="500">${esc(text)}</textarea></label><div id="composer-preview" class="hint"></div><p class="subtle">Momentaufnahme. ${kind==='session'&&item?'Ranking: '+(item.public?'Lernzeit bereits öffentlich':'Lernzeit privat')+'. ':''}Die Rankingfreigabe bleibt beim Teilen unverändert.</p><p class="error" role="alert"></p><button type="submit" class="button" ${item?'':'disabled'}>Auswahl speichern</button></form>`);composerPreview();
}
function composerPreview(){const f=$('#post-compose-form');if(!f)return;const fd=new FormData(f),[kind,raw]=String(fd.get('source')).split(':'),item=kind==='session'?state.sessions.find(s=>s.id===Number(raw)):state.exams.find(e=>e.id===Number(raw));if(!item){$('#composer-preview').textContent='Wähle deine gespeicherte Aktivität.';return;}const metrics=[];if(fd.has('show_seconds'))metrics.push(duration(item.seconds));if(fd.has('show_grade'))metrics.push('Note '+item.grade+'/5');if(fd.has('show_count'))metrics.push(item.session_count+' Sessions');$('#composer-preview').textContent='Vorschau: '+(fd.get('target')==='public'?'Öffentlich':fd.get('target')?groupLabel(Number(fd.get('target'))):'Privat')+' · '+item.subject+' · '+(metrics.join(' · ')||'Keine Kennzahlen ausgewählt');}
document.addEventListener('change',e=>{if(e.target.id==='compose-source')composeDialog(e.target.value,e.target.closest('form').querySelector('[name=text]').value);else if(e.target.closest('#post-compose-form'))composerPreview();});
function rankingStatus(p){const s=state.sessions.find(s=>s.id===p.session_id);return s?s.public?'Diese Lernzeit zählt zur öffentlichen Rangliste.':'Diese Lernzeit zählt nicht zur öffentlichen Rangliste.':'Rankingfreigaben werden separat in den Sessiondetails verwaltet. Für diesen älteren Beitrag ist keine zugehörige Session hinterlegt.';}
function rankingWarning(p){return state.sessions.some(s=>s.id===p.session_id&&s.public)?' Die Lernzeit zählt weiterhin zur öffentlichen Rangliste. Du kannst das in den Sessiondetails ändern.':'';}
function profile(){return profileBase()+`<section class="card section-space"><h2>Deine Freigaben</h2><h3 class="section-space">Aktive Beiträge und Momentaufnahmen</h3>${(state.own_posts||[]).filter(p=>!p.revoked_at).map(p=>`<div class="exam-row"><div class="grow"><strong>${esc(p.subject)}</strong><p class="meta">${esc(visibility(p))}${p.session_id?' · '+esc(rankingStatus(p)):''}</p></div>${button('Freigabe zurücknehmen','post-revoke',`data-id="${p.id}"`,'small secondary')}</div>`).join('')||'<p>Keine aktiven Beiträge.</p>'}<h3 class="section-space">Öffentliche Lernzeit im Ranking</h3>${state.sessions.filter(s=>s.public).map(s=>`<div class="exam-row"><div class="grow"><strong>${esc(s.subject)}</strong><p class="meta">${esc(s.date)} · ${duration(s.seconds)}</p></div>${button('Verwalten','session-details',`data-id="${s.id}"`,'small secondary')}</div>`).join('')||'<p>Keine Sessionlernzeit öffentlich.</p>'}<p class="subtle">Auch wenn ein Beitrag zurückgenommen wird, bleibt eine gesonderte Rankingfreigabe bestehen.</p></section>`;}

async function loadFeedback(append=false){const r=await api('feedback?filter='+feedbackFilter+(append&&feedbackData?.next_before_id?'&before_id='+feedbackData.next_before_id:''));feedbackData={...r,messages:append?[...feedbackData.messages,...r.messages]:r.messages};}
function feedbackPage(){const f=feedbackData;if(!f)return empty('Feedback wird geladen.','');return heading('Dein Feedback.','Was funktioniert gut? Was könnte einfacher sein?')+`<section class="card"><span class="badge">Privat</span><p>Dein Feedback ist nur für dich und Admins sichtbar. Es erscheint nicht im Feed oder in Gruppen.</p><form id="feedback-form"><label>Feedback verfassen<textarea name="text" maxlength="2000" required placeholder="Beschreibe deinen Wunsch oder das Problem.">${esc(feedbackDraft)}</textarea></label><p class="subtle">Bis zu 2000 Zeichen. Bitte keine Passwörter oder Zugangsdaten eingeben.</p><p class="error" role="alert"></p><button type="submit" class="button" ${f.feedback_enabled?'':'disabled'}>Privat senden</button>${f.feedback_enabled?'':'<p>Feedback ist noch nicht eingerichtet.</p>'}</form></section><section class="card section-space"><h2>${f.feedback_reviewer?'Feedback-Eingang · '+f.unread_count+' ungelesen':'Dein gesendetes Feedback'}</h2>${f.feedback_reviewer?tabs([['all','Alle'],['unread','Ungelesen']],feedbackFilter,'feedback-filter'):''}${f.messages.map(m=>`<article class="feedback-message" data-feedback="${m.id}"><div class="row"><strong>${esc(m.username)}</strong><span class="meta">${new Date(m.created).toLocaleString('de-AT')}</span><span class="badge">${m.read_at?'Gelesen':'Neu'}</span></div><p>${esc(m.text)}</p>${f.feedback_reviewer&&!m.read_at?button('Als gelesen markieren','feedback-read',`data-id="${m.id}"`,'small secondary'):''}</article>`).join('')||'<p>Hier gibt es noch keine Nachrichten.</p>'}${f.has_more?button('Weitere Nachrichten','feedback-more','','secondary'):''}</section>`;}
refresh().catch(error=>{if(error.status===401)auth();else{$('#app').innerHTML=empty('Learno konnte nicht geladen werden.','Prüfe Server und die aktuelle Migration.');}});
