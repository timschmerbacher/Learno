'use strict';
/* app.js owns the single click/submit dispatchers. */
pages.groups=['Lerngruppen','user'];
let selectedGroup=null, groupSearch='';
const bytes=n=>n>=1048576?`${(n/1048576).toFixed(1)} MiB`:`${Math.ceil(n/1024)} KiB`;
const difficultyField=(v=3)=>`<label>Deine Schwierigkeit<select name="difficulty">${[1,2,3,4,5].map(n=>`<option value="${n}" ${n===v?'selected':''}>${n}/5</option>`).join('')}</select></label>`;
function examFields(e={},personal=true){return `<label>Fach<input name="subject" maxlength="120" value="${esc(e.subject||'')}" required></label><label>Prüfungsbezeichnung<input name="title" maxlength="120" value="${esc(e.title||'')}" required></label><label>Prüfungsdatum<input name="exam_date" type="date" value="${esc(e.exam_date||localDate())}" required></label>${personal?difficultyField(e.difficulty||3):''}`;}
function ownerField(){return `<label>Prüfung gehört zu<select name="group_id"><option value="">Nur mir</option>${state.groups.filter(g=>g.joined).map(g=>`<option value="${g.id}">${g.parent_id?'Untergruppe':'Hauptgruppe'}: ${esc(g.name)}</option>`).join('')}</select></label>`;}
function enhancedForm(title,kind,body,extra={}){showModal(title,`<form id="enhanced-form" data-kind="${kind}" data-extra="${esc(JSON.stringify(extra))}">${body}<p class="error"></p><div class="modal-actions"><button type="button" class="button secondary" data-action="close">Abbrechen</button><button class="button" type="submit">Speichern</button></div></form>`);}
function startDialog(id=''){formModal('Zeit für deinen Fokus','start',`<label>Prüfung<select name="user_exam_state_id">${examOptions(id)}</select></label><button type="button" class="button soft" data-action="start-new">${icon('plus')} Neue Prüfung anlegen</button>${subjectInput()}<p class="subtle">Abgeschlossene und archivierte Prüfungen werden nicht vorgeschlagen.</p>`,'Timer starten');}
function groupDetail(g){return `<section class="card section-space" id="group-detail"><div class="card-head"><h2>${esc(g.name)}</h2><div class="actions">${button('Gemeinsame Prüfung','group-exam-new',`data-id="${g.id}"`)}${!g.parent_id&&g.owner_id===state.user.id?button('Untergruppe anlegen','subgroup-new',`data-id="${g.id}"`,'secondary'):''}${g.owner_id!==state.user.id?button('Verlassen','group-leave',`data-id="${g.id}"`,'secondary'):''}</div></div>${state.exam_events.filter(e=>e.group_id===g.id).map(e=>{
 const own=state.exams.find(s=>s.exam_event_id===e.id),edit=e.creator_id===state.user.id||g.owner_id===state.user.id;
 return `<article class="group-exam"><h3>${esc(e.subject)} · ${esc(e.title)}</h3><p class="meta">${dateText(e.exam_date)} ${e.exam_date.slice(0,4)}${e.archived_at?' · Archiviert':''}</p><div class="actions">${!own&&!e.archived_at?button('Zu meinen Prüfungen hinzufügen','group-adopt',`data-id="${e.id}"`,'small'):own?button('Meine Prüfungen','go-exams','','small soft'):''}${button('Unterlagen','shared-files',`data-id="${e.id}"`,'small secondary')}${edit?e.archived_at?button('Termin wiederherstellen','event-restore',`data-id="${e.id}"`,'small'):button('Bearbeiten','group-edit',`data-id="${e.id}"`,'small secondary')+button(e.deletion_mode==='deleted'?'Endgültig löschen':'Archivieren','group-delete',`data-id="${e.id}"`,'small danger'):''}</div></article>`;
 }).join('')||empty('Keine gemeinsamen Termine.','Jedes Mitglied kann eine Prüfung anlegen.')}<div class="hint">Gemeinsame Termine werden einmal gespeichert. Noten, Schwierigkeit und Lernfortschritt bleiben persönlich.</div></section>`;}
function resourceFields(){const places=[...new Set(['Zuhause','Bibliothek','FH / Schule','Zug','Café',...state.locations])];return `<label>Lernort<select name="location_choice" data-location-select>${places.map(l=>`<option>${esc(l)}</option>`).join('')}<option value="__custom__">Eigener Ort …</option></select></label><label data-custom-location hidden>Eigener Lernort<input name="custom_location" maxlength="120"></label><label>Lernhilfsmittel</label><div class="checks">${['Skriptum','YouTube','Mit Freunden','Übungsaufgaben'].map(r=>`<label class="check"><input type="checkbox" name="resource" value="${r}">${r}</label>`).join('')}</div><label>Weitere Hilfsmittel<input name="other_resource" maxlength="120"></label>`;}
document.addEventListener('change',event=>{
 if(event.target.matches('[data-location-select]')){const c=event.target.closest('form').querySelector('[data-custom-location]');c.hidden=event.target.value!=='__custom__';c.querySelector('input').required=!c.hidden;}
 if(event.target.closest('#result-share-form'))sharePreview();
});
function filesModal(eid,archive=false){
 const e=state.exam_events.find(e=>e.id===eid)||state.exams.find(e=>e.exam_event_id===eid),g=state.groups.find(g=>g.id===e?.group_id),files=state.files.filter(f=>f.exam_event_id===eid&&!!f.archived_at===archive);
 showModal('Prüfungsunterlagen',`<p class="subtitle">${esc(e?.subject)} · ${esc(e?.title)}</p><div class="hint">${esc(g?groupLabel(g.id):'Privat')} Dateien bleiben auch im Archiv gespeichert.</div>${button(archive?'Aktive Dateien':'Dateiarchiv','file-archive',`data-event="${eid}" data-archive="${archive?'0':'1'}"`,'secondary section-space')}<div class="file-list">${files.map(f=>`<div class="file-row"><div class="grow"><a href="/api/v2/files/${f.id}" class="file-link">${esc(f.filename)}</a><div class="meta">${bytes(f.size)} · ${esc(f.private_owner_id? 'Privat':g?groupLabel(g.id):'Privat')}${f.archived_at?' · Dateiarchiv':''}</div></div>${f.private_owner_id===state.user.id||!g||g.owner_id===state.user.id||f.uploader_id===state.user.id?button(f.archived_at?'Wiederherstellen':'Archivieren',f.archived_at?'file-restore':'file-delete',`data-id="${f.id}" data-event="${eid}"`,'small secondary'):''}</div>`).join('')||empty('Noch keine Unterlagen.','PDF, PNG oder JPEG hochladen.')}</div>${!archive&&!e?.archived_at&&e?.has_group_access!==false?`<form id="file-form" data-event="${eid}"><label>Datei bis 5 MiB<input name="upload" type="file" accept=".pdf,.png,.jpg,.jpeg" required></label><p class="error"></p><button type="submit" class="button">Hochladen</button></form>`:''}`);
}
function shareDialog(s){showModal('Ergebnis bewusst teilen',`<form id="result-share-form" data-state="${s.id}"><p>${esc(s.subject)} · ${esc(s.title)}</p><label>Sichtbarkeit<select name="target"><option value="">Privat</option>${state.groups.filter(g=>g.joined).map(g=>`<option value="${g.id}">${g.parent_id?'Untergruppe':'Hauptgruppe'}: ${esc(g.name)}</option>`).join('')}</select></label><div class="checks">${[['show_grade','Note'],['show_seconds','Gesamte Lernzeit'],['show_count','Anzahl Lernsessions']].map(([k,label])=>`<label class="check"><input type="checkbox" name="${k}">${label}</label>`).join('')}</div><label>Text<textarea name="text" maxlength="500"></textarea></label><div id="share-preview" class="hint"></div><p class="subtle">Momentaufnahme. Spätere Änderungen werden nicht automatisch geteilt. Keine Veröffentlichung im globalen Ranking.</p><p class="error"></p><button type="submit" class="button">Auswahl speichern</button></form>`);sharePreview();}
function sharePreview(){const f=$('#result-share-form');if(!f)return;const s=state.exams.find(s=>s.id===Number(f.dataset.state)),fd=new FormData(f),v=[];if(fd.has('show_grade'))v.push('Note '+s.grade+'/5');if(fd.has('show_seconds'))v.push(duration(s.seconds));if(fd.has('show_count'))v.push(s.session_count+' Lernsessions');$('#share-preview').textContent='Vorschau: '+(fd.get('target')?groupLabel(Number(fd.get('target'))):'Privat')+' · '+(v.join(' · ')||'Keine Kennzahlen ausgewählt');}
async function groupAction(action,id,b){
 const own=()=>state.exams.find(s=>s.id===id),ev=()=>state.exam_events.find(e=>e.id===id);
 switch(action){
 case 'go-groups':case 'go-exams':page=action==='go-groups'?'groups':'exams';await refresh();return true;
 case 'toggle-archive':examView=examView==='archive'?'upcoming':'archive';render();return true;
 case 'group-new':case 'subgroup-new':enhancedForm(action==='group-new'?'Hauptgruppe erstellen':'Untergruppe erstellen','group-create','<label>Name<input name="name" maxlength="100" required></label><label>Beschreibung<textarea name="description" maxlength="500"></textarea></label>',{parent_id:action==='subgroup-new'?id:null});return true;
 case 'group-open':selectedGroup=id;await refresh();$('#group-detail')?.scrollIntoView({behavior:'smooth'});return true;
 case 'group-join':await api('group-join',{group_id:id});selectedGroup=id;await refresh();return true;
 case 'group-leave':if(confirm('Gruppe verlassen? Eigene Historie bleibt erhalten; Gruppenzugriff und Freigaben enden.')){await api('group-leave',{group_id:id});selectedGroup=null;await refresh();}return true;
 case 'group-exam-new':enhancedForm('Gemeinsame Prüfung','exam',examFields({},false),{group_id:id});return true;
 case 'group-adopt':enhancedForm('Prüfung übernehmen','group-adopt',difficultyField(),{exam_event_id:id});return true;
 case 'group-edit':enhancedForm('Termin bearbeiten','event-edit',examFields(ev(),false),{exam_event_id:id,version:ev().version});return true;
 case 'group-delete':if(confirm('Unbenutzten Termin löschen, sonst archivieren? Historische Daten bleiben erhalten.')){await api('event-delete',{exam_event_id:id,version:ev().version});await refresh();}return true;
 case 'event-restore':await api('event-restore',{exam_event_id:id,version:ev().version});await refresh();return true;
 case 'personal-delete':if(confirm('Unbenutzte persönliche Prüfung löschen, sonst archivieren? Daten bleiben erhalten.')){const r=await api('exam-delete',{user_exam_state_id:id,version:own().version});await refresh();toast(r.mode==='deleted'?'Unbenutzte Prüfung gelöscht.':'Prüfung archiviert.');}return true;
 case 'personal-restore':await api('exam-restore',{user_exam_state_id:id,version:own().version});await refresh();return true;
 case 'personal-edit':{const e=own();enhancedForm('Meine Prüfung bearbeiten','exam-edit',e.group_id?difficultyField(e.difficulty):examFields(e),{user_exam_state_id:id,version:e.version,event_version:e.event_version});return true;}
 case 'create-exam':case 'start-new':enhancedForm('Neue Prüfung','exam',ownerField()+examFields(),{adopt:true,return_to_start:action==='start-new'});return true;
 case 'shared-files':filesModal(id);return true;
 case 'personal-files':filesModal(own().exam_event_id);return true;
 case 'file-archive':filesModal(Number(b.dataset.event),b.dataset.archive==='1');return true;
 case 'file-delete':case 'file-restore':await api(action,{attachment_id:id});await refresh(false);filesModal(Number(b.dataset.event));return true;
 case 'notice-dismiss':await api('notice-read',{notice_id:id});await refresh();return true;
 case 'share-exam':shareDialog(own());return true;
 case 'post-revoke':if(confirm('Freigabe zurücknehmen? Der gespeicherte Beitrag bleibt für dich erhalten.'+rankingWarning((state.own_posts||state.posts).find(p=>p.id===id)||{}))){await api('post-revoke',{post_id:id});await refresh();}return true;
 case 'exam-history':{const e=own(),grades=state.grade_history.filter(h=>h.user_exam_state_id===id),events=state.event_history.filter(h=>h.exam_event_id===e.exam_event_id);showModal('Prüfungshistorie',`<h3>Noten</h3>${grades.map(h=>`<p>${h.changed_at?new Date(h.changed_at).toLocaleString('de-AT'):'Übernommener Ausgangsstand'}: ${h.old_grade??'–'} → ${h.new_grade??'–'}</p>`).join('')||'<p>Keine Note eingetragen.</p>'}<h3>Termine</h3>${events.map(h=>`<p>${esc(h.title)} · ${esc(h.subject)} · ${esc(h.exam_date)}${h.archived_at?' · Archiviert':''}</p>`).join('')}`);return true;}
 default:return false;
 }
}
async function groupSubmit(form,fd,data){
 const id=form.getAttribute('id');
 if(id==='group-search-form'){groupSearch=data.search;render();return true;}
 if(id==='file-form'){
  const file=fd.get('upload');if(!file.size||file.size>5*1024*1024)throw Error('Bitte eine Datei bis 5 MiB auswählen.');
  const content=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(Error('Datei konnte nicht gelesen werden.'));r.readAsDataURL(file);});
  const eid=Number(form.dataset.event);await api('file-upload',{exam_event_id:eid,filename:file.name,content});await refresh(false);filesModal(eid);return true;
 }
 if(id==='result-share-form'){
  const gid=data.target?Number(data.target):null;
  await api('post',{user_exam_state_id:Number(form.dataset.state),audience:gid?'group':'private',target_group_id:gid,text:data.text,show_grade:fd.has('show_grade')?1:0,show_seconds:fd.has('show_seconds')?1:0,show_count:fd.has('show_count')?1:0});
  $('#modal').close();await refresh();toast(gid?'Momentaufnahme geteilt.':'Private Momentaufnahme gespeichert.');return true;
 }
 if(id!=='enhanced-form')return false;
 const extra=JSON.parse(form.dataset.extra),kind=form.dataset.kind;
 if('difficulty' in data)data.difficulty=Number(data.difficulty);
 if('group_id' in data)data.group_id=data.group_id?Number(data.group_id):null;
 const result=await api(kind,{...data,...extra});await refresh(false);
 if(kind==='exam'||kind==='group-adopt')examView='upcoming';
 if(kind==='group-create'){selectedGroup=result.id;groupView='mine';}
 if(kind==='exam'&&extra.return_to_start){$('#modal').close();startDialog(result.user_exam_state_id);return true;}
 $('#modal').close();render();toast('Gespeichert.');return true;
}
