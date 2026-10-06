/* Gemeinsame Prüfungen und Dateien. Alle Berechtigungen werden serverseitig geprüft. */
pages.groups=['Lerngruppen','user'];
let selectedGroup=null, groupSearch='';
const bytes = n => n>=1048576?`${(n/1048576).toFixed(1)} MiB`:`${Math.ceil(n/1024)} KiB`;
function difficultyField(value=3){return `<label>Deine Schwierigkeit<select name="difficulty">${[1,2,3,4,5].map(n=>`<option value="${n}" ${n===value?'selected':''}>${n}/5</option>`).join('')}</select></label>`;}
function examFields(exam={},personal=true){return `<label>Fach<input name="subject" maxlength="120" value="${esc(exam.subject||'')}" placeholder="z. B. Mathematik" required></label><label>Prüfungsbezeichnung<input name="title" maxlength="120" value="${esc(exam.title||'')}" placeholder="z. B. Zwischenprüfung" required></label><label>Prüfungsdatum<input name="exam_date" type="date" value="${esc(exam.exam_date||localDate())}" required></label>${personal?difficultyField(exam.difficulty||3):''}`;}
function enhancedForm(title,kind,body,extra={}){showModal(title,`<form id="enhanced-form" data-kind="${kind}" data-extra="${esc(JSON.stringify(extra))}">${body}<p class="error"></p><div class="modal-actions"><button type="button" class="button secondary" data-action="close">Abbrechen</button><button class="button" type="submit">Speichern</button></div></form>`);}
function startDialog(id=''){formModal('Zeit für deinen Fokus','start',`<label>Prüfung<select name="exam_id">${examOptions(id)}</select></label><button type="button" class="button soft" data-action="start-new">${icon('plus')} Neue Prüfung anlegen</button>${subjectInput()}<p class="subtle">Oder ohne Prüfung als freie Session starten. Du kannst den Timer jederzeit pausieren.</p>`,'Timer starten');}
function notices(){return (state.notices||[]).map(n=>`<div class="notice"><div>${esc(n.text)}</div><button class="text-button" data-action="notice-dismiss" data-id="${n.id}" aria-label="Hinweis gelesen">Gelesen ✓</button></div>`).join('');}
function groupsPage(){
 const all=state.groups||[],active=all.find(g=>g.id===selectedGroup&&g.joined);
 const filtered=all.filter(g=>(g.name+' '+g.description).toLowerCase().includes(groupSearch.toLowerCase()));
 return heading('Gemeinsam vorbereitet.','Offene Gruppen für eure Klasse, euren Studienzweig oder eure Lerngruppe.',button(icon('plus')+' Gruppe erstellen','group-new'))+
 `<form id="group-search-form" class="filters"><label>Gruppen suchen<input name="search" value="${esc(groupSearch)}" placeholder="Name, Schule oder Studienzweig"></label><button class="button secondary">Suchen</button></form><div class="group-grid">${filtered.map(g=>`<section class="card"><div class="row"><h2>${esc(g.name)}</h2><span class="badge">Offen</span></div><p class="compact-p">${esc(g.description)}</p><p class="meta">${g.member_count} Mitglieder · Verwaltung: ${esc(g.owner_name)}</p><div class="actions">${g.joined?button(g.id===selectedGroup?'Ausgewählt':'Gruppe öffnen','group-open',`data-id="${g.id}"`,'soft'):button('Beitreten','group-join',`data-id="${g.id}"`)}</div></section>`).join('')||`<section class="card">${empty('Keine passende Gruppe gefunden.','Erstelle eure eigene Lerngruppe.')}</section>`}</div><p class="subtle">Alle registrierten Personen können beitreten. Prüfungsunterlagen sind nach dem Beitritt sichtbar.</p>${active?groupDetail(active):''}`;
}
function groupDetail(g){const exams=state.group_exams.filter(e=>e.group_id===g.id);return `<section class="card section-space" id="group-detail"><div class="card-head"><div><p class="eyebrow">DEINE LERNGRUPPE</p><h2>${esc(g.name)}</h2></div><div class="actions">${button(icon('plus')+' Gemeinsame Prüfung','group-exam-new',`data-id="${g.id}"`)}${g.owner_id!==state.user.id?button('Verlassen','group-leave',`data-id="${g.id}"`,'secondary'):''}</div></div>${exams.map(e=>{const own=state.exams.find(p=>p.group_exam_id===e.id),edit=e.creator_id===state.user.id||g.owner_id===state.user.id;return `<article class="group-exam"><div class="row"><div class="grow"><h3>${esc(e.subject)} · ${esc(e.title)}</h3><span class="meta">${dateText(e.exam_date)} ${e.exam_date.slice(0,4)} · Angelegt von ${esc(e.creator_name)}</span></div>${own?'<span class="badge">Übernommen</span>':''}</div><div class="actions section-space">${!own?button('Zu meinen Prüfungen hinzufügen','group-adopt',`data-id="${e.id}"`,'small'):button('Meine Prüfung ansehen','go-exams','','small soft')}${button('Unterlagen','shared-files',`data-id="${e.id}"`,'small secondary')}${edit?button('Bearbeiten','group-edit',`data-id="${e.id}"`,'small secondary')+button('Löschen','group-delete',`data-id="${e.id}"`,'small danger'):''}</div></article>`;}).join('')||empty('Noch keine gemeinsamen Termine.','Jedes Mitglied kann eine Prüfung anlegen.')}<div class="hint">Du übernimmst Termine bewusst. Danach werden Terminänderungen in deiner persönlichen Liste aktualisiert und als Hinweis angezeigt. Deine Schwierigkeit, Noten und Lernzeiten bleiben persönlich.</div></section>`;}

exams=function(){return heading('Ein Ziel vor Augen.','Deine Prüfungen und übernommene Gruppentermine.',button(icon('plus')+' Prüfung anlegen','create-exam'))+
`<div class="exam-cards">${state.exams.map(e=>`<section class="card exam-card"><div class="row"><span class="badge ${!e.completed?'warm':''}">${e.completed?'Abgelegt':e.priority?dayText(e.priority.days):'Termin vergangen'}</span><span class="meta">${dateText(e.exam_date)}</span></div><h2>${esc(e.subject)}</h2><p class="meta">${esc(e.title)}${e.group_exam_id?' · Gruppentermin ↻':''}</p><div class="exam-details"><div><span>Lernzeit</span><strong>${duration(e.seconds)}</strong></div><div><span>${e.completed?'Note':'Priorität'}</span><strong>${e.completed?e.grade+'/5':e.priority?e.priority.score+'/10':'–'}</strong></div><div><span>Schwierigkeit</span><strong>${e.difficulty}/5</strong></div></div><div class="actions">${e.completed?button('Ergebnis teilen','share-exam',`data-id="${e.id}"`,'small'):button('Lernen','start',`data-id="${e.id}"`,'small')}${button(e.completed?'Note ändern':'Note eintragen','grade',`data-id="${e.id}"`,'small secondary')}${button('Sessions','exam-sessions',`data-id="${e.id}"`,'small soft')}${button('Unterlagen','personal-files',`data-id="${e.id}"`,'small secondary')}${button('Bearbeiten','personal-edit',`data-id="${e.id}"`,'small secondary')}${button('Entfernen','personal-delete',`data-id="${e.id}"`,'small danger')}</div></section>`).join('')||`<section class="card full">${empty('Noch keine Prüfung geplant.','Lege eine Prüfung an oder übernimm bewusst einen Termin aus einer Lerngruppe.')}${button('Lerngruppen entdecken','go-groups','','soft')}</section>`}</div><div class="hint">Priorität = Zeitdruck + Schwierigkeit − Lernzeitabzug (1–10). Zeitdruck: bis 3 Tage = 6, bis 7 = 5, bis 14 = 3, bis 30 = 2, danach = 1. Pro voller gelernter Stunde −1, maximal −3. Vergangene und abgelegte Prüfungen erhalten keine Priorität.</div>`;};

function fileContext(examId,groupExamId){
 if(examId){const e=state.exams.find(e=>e.id===examId);if(e.group_exam_id){groupExamId=e.group_exam_id;examId=null;}}
 return {exam_id:examId||null,group_exam_id:groupExamId||null};
}
function filesModal(examId,groupExamId){const context=fileContext(examId,groupExamId),shared=!!context.group_exam_id;
 const files=state.files.filter(f=>shared?f.group_exam_id===context.group_exam_id:f.exam_id===context.exam_id);
 const e=shared?state.group_exams.find(e=>e.id===context.group_exam_id):state.exams.find(e=>e.id===context.exam_id);
 const group=shared?state.groups.find(g=>g.id===e?.group_id):null;
 showModal('Prüfungsunterlagen',`<p class="subtitle">${esc(e?.subject)} · ${esc(e?.title)}</p><div class="hint">${shared?'Nur Gruppenmitglieder können diese Dateien herunterladen. Die Gruppe ist offen für jeden registrierten Benutzer.':'Diese Dateien sind nur für dich sichtbar.'}</div><div class="file-list">${files.map(f=>`<div class="file-row"><div class="grow"><a href="/api/files/${f.id}" class="file-link">${esc(f.filename)}</a><div class="meta">${bytes(f.size)} · ${esc(f.uploader_name)} · ${new Date(f.created).toLocaleDateString('de-AT')}</div></div>${!shared||f.uploader_id===state.user.id||group?.owner_id===state.user.id?button('Löschen','file-delete',`data-id="${f.id}" data-context="${esc(JSON.stringify(context))}"`,'small secondary'):''}</div>`).join('')||empty('Noch keine Unterlagen.','Lade eure erste Zusammenfassung oder euer Übungsblatt hoch.')}</div><form id="file-form" data-context="${esc(JSON.stringify(context))}"><label>PDF oder Bild hochladen <span class="label-note">(max. 5 MiB)</span><input name="upload" type="file" accept=".pdf,.png,.jpg,.jpeg" required></label><p class="subtle">Nur Unterlagen hochladen, die du mit der Gruppe teilen darfst. Dateitypen werden geprüft; keine Viren- oder Inhaltsanalyse.</p><p class="error"></p><button type="submit" class="button">Datei hochladen</button></form>`);
}

resourceFields=function(){const locations=[...new Set(['Zuhause','Bibliothek','FH / Schule','Zug','Café',...(state.locations||[])])];return `<label>Lernort<select name="location_choice" data-location-select>${locations.map(l=>`<option>${esc(l)}</option>`).join('')}<option value="__custom__">Eigener Ort …</option></select></label><label data-custom-location hidden>Eigenen Lernort eintragen<input name="custom_location" maxlength="120" placeholder="z. B. Lernraum B2.04"></label><label>Lernhilfsmittel <span class="label-note">(Mehrfachauswahl)</span></label><div class="checks">${['Skriptum','YouTube','Mit Freunden','Übungsaufgaben'].map(r=>`<label class="check"><input type="checkbox" name="resource" value="${r}">${r}</label>`).join('')}</div><label>Weitere Lernhilfsmittel<input name="other_resource" placeholder="z. B. Karteikarten" maxlength="120"></label>`;};
document.addEventListener('change',event=>{if(event.target.matches('[data-location-select]')){const custom=event.target.closest('form').querySelector('[data-custom-location]');custom.hidden=event.target.value!=='__custom__';custom.querySelector('input').required=!custom.hidden;}});

document.addEventListener('click',async event=>{
 const b=event.target.closest('[data-action]');if(!b)return;const action=b.dataset.action,id=Number(b.dataset.id);
 try{
  if(action==='go-groups'||action==='go-exams'){page=action==='go-groups'?'groups':'exams';await refresh();return;}
  if(action==='group-new'){enhancedForm('Neue Lerngruppe','group-create','<label>Gruppenname<input name="name" maxlength="100" placeholder="z. B. BWI – 1. Semester" required></label><label>Beschreibung<textarea name="description" maxlength="500" placeholder="Schule, Hochschule oder Schwerpunkt"></textarea></label><p class="subtle">Jeder registrierte Benutzer kann direkt beitreten.</p>');return;}
  if(action==='group-open'){selectedGroup=id;render();$('#group-detail')?.scrollIntoView({behavior:'smooth',block:'start'});return;}
  if(action==='group-join'){await api('group-join',{id});selectedGroup=id;await refresh();toast('Du bist jetzt Mitglied.');return;}
  if(action==='group-leave'){if(!confirm('Gruppe verlassen? Deine Prüfungen bleiben als persönliche Kopien erhalten. Zugriff auf Gruppendateien und Terminsynchronisation enden.'))return;await api('group-leave',{id});selectedGroup=null;await refresh();return;}
  if(action==='group-exam-new'){enhancedForm('Gemeinsame Prüfung anlegen','group-exam',examFields({},false),{group_id:id});return;}
  if(action==='group-adopt'){enhancedForm('Prüfung bewusst übernehmen','group-adopt',`<p class="subtitle">Der Termin bleibt mit der Gruppe verbunden. Lernzeit und Note gehören nur dir.</p>${difficultyField()}`,{id});return;}
  if(action==='group-edit'){const e=state.group_exams.find(e=>e.id===id);enhancedForm('Gemeinsamen Termin bearbeiten','group-exam-edit',examFields(e,false)+'<p class="subtle">Änderungen werden bei allen übernommenen Prüfungen aktualisiert.</p>',{id});return;}
  if(action==='group-delete'){if(!confirm('Gemeinsame Prüfung und ihre Gruppendateien löschen? Bereits übernommene persönliche Prüfungen bleiben ohne Synchronisation erhalten.'))return;await api('group-exam-delete',{id});await refresh();toast('Gruppenprüfung gelöscht.');return;}
  if(action==='personal-delete'){if(!confirm('Prüfung aus deiner Liste entfernen? Deine Lernsessions bleiben erhalten. Nur private Prüfungsdateien werden mitgelöscht; Gruppentermine und Gruppendateien bleiben bestehen.'))return;await api('exam-delete',{id});await refresh();return;}
  if(action==='personal-edit'){const e=state.exams.find(e=>e.id===id);enhancedForm('Meine Prüfung bearbeiten','exam-edit',e.group_exam_id?'<p class="hint">Datum und Bezeichnung kommen aus der Gruppe. Deine Schwierigkeit kannst du hier ändern.</p>'+difficultyField(e.difficulty):examFields(e),{id});return;}
  if(action==='create-exam'||action==='start-new'){enhancedForm('Neue Prüfung anlegen','exam',examFields(),{return_to_start:action==='start-new'});return;}
  if(action==='shared-files'){filesModal(null,id);return;}
  if(action==='personal-files'){filesModal(id,null);return;}
  if(action==='file-delete'){if(!confirm('Diese Datei endgültig löschen?'))return;const c=JSON.parse(b.dataset.context);await api('file-delete',{id});await refresh(false);filesModal(c.exam_id,c.group_exam_id);return;}
  if(action==='notice-dismiss'){await api('notice-read',{id});await refresh(false);b.closest('.notice').remove();return;}
 }catch(error){toast(error.message);}
});
document.addEventListener('submit',async event=>{
 const form=event.target;if(!['enhanced-form','group-search-form','file-form'].includes(form.id))return;
 event.preventDefault();const fd=new FormData(form),data=Object.fromEntries(fd.entries());const button=form.querySelector('[type=submit]');if(button)button.disabled=true;
 try{
  if(form.id==='group-search-form'){groupSearch=data.search;render();return;}
  if(form.id==='file-form'){
   const file=fd.get('upload');if(!file.size||file.size>5*1024*1024)throw Error('Bitte eine Datei bis 5 MiB auswählen.');
   const content=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(Error('Datei konnte nicht gelesen werden.'));r.readAsDataURL(file);});
   const context=JSON.parse(form.dataset.context);await api('file-upload',{...context,filename:file.name,content});await refresh(false);filesModal(context.exam_id,context.group_exam_id);toast('Datei hochgeladen.');return;
  }
  const extra=JSON.parse(form.dataset.extra),kind=form.dataset.kind;
  if(data.difficulty)data.difficulty=Number(data.difficulty);
  const result=await api(kind,{...data,...extra});await refresh(false);
  if(kind==='group-create')selectedGroup=result.id;
  if(kind==='exam'&&extra.return_to_start){startDialog(result.id);return;}
  $('#modal').close();render();toast(kind==='group-adopt'?'Prüfung übernommen.':'Gespeichert.');
 }catch(error){form.querySelector('.error').textContent=error.message;}finally{if(button)button.disabled=false;}
});

// Start erst nach Laden aller Ansichten.
refresh().catch(error=>{if(error.status===401)auth();else{$('#app').innerHTML=empty('Learno konnte nicht geladen werden.','Prüfe, ob python app.py noch läuft, und lade die Seite neu.');}});
