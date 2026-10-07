"""V2 domain rules: shared events, private progress, archival and audience checks."""
import base64
import binascii
from pathlib import Path
import time
from migrate import now

MAX_FILE=5*1024*1024
MAX_TOTAL=200*1024*1024
ACTIONS={'group-create','group-join','group-leave','exam','group-adopt','exam-edit','event-edit',
         'exam-delete','event-delete','exam-restore','event-restore','grade','start','pause','resume',
         'stop','finish','discard','session','assign','file-upload','file-delete','file-restore',
         'notice-read','notices-read-all','weekly-goal','post','post-revoke','post-delete','comment','session-ranking'}

class Conflict(ValueError):
    pass

def rows(db,sql,args=()):
    return [dict(r) for r in db.execute(sql,args)]

def member(db,gid,uid):
    return db.execute('SELECT 1 FROM members WHERE group_id=? AND user_id=? AND left_at IS NULL',(gid,uid)).fetchone() is not None

def group(db,gid,uid):
    result=db.execute('SELECT * FROM study_groups WHERE id=?',(gid,)).fetchone()
    if not result or not member(db,gid,uid): raise ValueError('Nur Gruppenmitglieder haben Zugriff.')
    return result

def event(db,eid,uid,edit=False):
    e=db.execute('SELECT * FROM exam_events WHERE id=?',(eid,)).fetchone()
    if not e: raise ValueError('Prüfung nicht gefunden.')
    if e['group_id'] is not None:
        g=group(db,e['group_id'],uid)
        if edit and uid not in (g['owner_id'],e['creator_id']):
            raise ValueError('Nur Ersteller und Gruppenverwaltung dürfen den Termin ändern.')
    elif e['owner_user_id']!=uid:
        raise ValueError('Kein Zugriff auf diese Prüfung.')
    return e

def owned_state(db,sid,uid):
    s=db.execute('SELECT * FROM user_exam_states WHERE id=? AND user_id=?',(sid,uid)).fetchone()
    if not s: raise ValueError('Persönliche Prüfung nicht gefunden oder kein Zugriff.')
    return s

def version(record,data):
    if type(data.get('version')) is not int or data['version']!=record['version']:
        raise Conflict('Der Eintrag wurde geändert. Bitte neu laden und erneut prüfen.')

def record_event(db,eid,uid,source='edit'):
    db.execute('''INSERT INTO exam_event_history(exam_event_id,title,subject,exam_date,archived_at,version,changed_by,changed_at,source)
                  SELECT id,title,subject,exam_date,archived_at,version,?,?,? FROM exam_events WHERE id=?''',(uid,now(),source,eid))

def notify(db,eid,text):
    db.execute('''INSERT INTO notices(user_id,text,created) SELECT s.user_id,?,? FROM user_exam_states s
        JOIN exam_events e ON e.id=s.exam_event_id WHERE e.id=? AND (e.group_id IS NULL OR EXISTS(
        SELECT 1 FROM members m WHERE m.group_id=e.group_id AND m.user_id=s.user_id AND m.left_at IS NULL))''',(text,now(),eid))

def startable(db,s,e,uid):
    return (s['grade'] is None and not s['completed'] and s['archived_at'] is None and e['archived_at'] is None
            and (e['group_id'] is None or member(db,e['group_id'],uid)))

def state_used(db,s):
    sid=s['id'];eid=s['exam_event_id']
    return (s['grade'] is not None or s['completed']
        or any(db.execute(sql,(ident,)).fetchone() for sql,ident in (
            ('SELECT 1 FROM sessions WHERE user_exam_state_id=?',sid),
            ('SELECT 1 FROM active WHERE user_exam_state_id=?',sid),
            ('SELECT 1 FROM exam_grade_history WHERE user_exam_state_id=?',sid),
            ('SELECT 1 FROM posts WHERE user_exam_state_id=?',sid),
            ('SELECT 1 FROM exam_attachments WHERE exam_event_id=?',eid),
            ('SELECT 1 FROM exam_event_history WHERE exam_event_id=? AND version>1',eid))))

def event_used(db,e):
    return any(db.execute(sql,(e['id'],)).fetchone() for sql in (
            'SELECT 1 FROM user_exam_states WHERE exam_event_id=?',
            'SELECT 1 FROM exam_attachments WHERE exam_event_id=?',
            'SELECT 1 FROM exam_event_history WHERE exam_event_id=? AND version>1'))

def visible_post(db,p,uid):
    if p['user_id']==uid: return True
    if p['revoked_at']: return False
    if p['audience'] in ('legacy','public'): return True
    return p['audience']=='group' and member(db,p['target_group_id'],uid) and member(db,p['target_group_id'],p['user_id'])

def can_comment(db,p,uid):
    if not visible_post(db,p,uid): return False
    if p['user_id']==uid: return True
    if p['audience']=='group': return True  # visible_post already checks both memberships.
    return bool(db.execute('SELECT 1 FROM friendships WHERE accepted=1 AND ((sender=? AND receiver=?) OR (sender=? AND receiver=?))',
                          (uid,p['user_id'],p['user_id'],uid)).fetchone())

def posts_for(db,uid,filter_name='all',group_id=None,before_id=None,limit=200):
    if filter_name not in ('all','groups','friends','public','mine'): raise ValueError('Ungültiger Feedfilter.')
    if group_id is not None:
        if filter_name!='groups': raise ValueError('Gruppenauswahl nur im Gruppenfilter.')
        group(db,group_id,uid)
    sql='''SELECT p.*,u.username FROM posts p JOIN users u ON u.id=p.user_id
                       WHERE p.user_id=? OR (p.revoked_at IS NULL AND (
                       p.audience IN ('legacy','public') OR (p.audience='group' AND EXISTS(
                       SELECT 1 FROM members m WHERE m.group_id=p.target_group_id AND m.user_id=? AND m.left_at IS NULL)
                       AND EXISTS(SELECT 1 FROM members a WHERE a.group_id=p.target_group_id AND a.user_id=p.user_id AND a.left_at IS NULL))))
                       '''
    # Parenthesize the complete visibility predicate before any filter or limit.
    where=sql.split(' WHERE ',1)[1]
    sql=sql.split(' WHERE ',1)[0]+' WHERE ('+where+')'
    args=[uid,uid]
    if filter_name=='groups':
        sql+=" AND p.audience='group' AND p.revoked_at IS NULL AND EXISTS(SELECT 1 FROM members m WHERE m.group_id=p.target_group_id AND m.user_id=? AND m.left_at IS NULL)"
        args.append(uid)
    elif filter_name=='friends':
        sql+=' AND EXISTS(SELECT 1 FROM friendships f WHERE f.accepted=1 AND ((f.sender=? AND f.receiver=p.user_id) OR (f.receiver=? AND f.sender=p.user_id)))'
        args.extend([uid,uid])
    elif filter_name=='public': sql+=" AND p.audience IN ('legacy','public') AND p.revoked_at IS NULL"
    elif filter_name=='mine': sql+=' AND p.user_id=?';args.append(uid)
    if group_id is not None:sql+=' AND p.target_group_id=?';args.append(group_id)
    if before_id is not None:sql+=' AND p.id<?';args.append(before_id)
    sql+=' ORDER BY p.id DESC LIMIT ?';args.append(limit)
    visible=rows(db,sql,args)
    for p in visible:
        p['kind']='result' if p['user_exam_state_id'] is not None or p['grade'] is not None else 'session'
        p['can_comment']=can_comment(db,p,uid)
        for name,flag in (('grade','show_grade'),('seconds','show_seconds'),('session_count','show_count')):
            if not p[flag]: p.pop(name,None)
    ids=[p['id'] for p in visible]
    comments=rows(db,f'''SELECT c.*,u.username FROM comments c JOIN users u ON u.id=c.user_id
                        WHERE c.post_id IN ({','.join('?' for _ in ids)}) ORDER BY c.id''',ids) if ids else []
    return visible,comments

def attachment(db,fid,uid,manage=False):
    f=db.execute('SELECT * FROM exam_attachments WHERE id=?',(fid,)).fetchone()
    if not f: raise ValueError('Datei nicht gefunden.')
    if f['private_owner_id'] is not None:
        if f['private_owner_id']!=uid: raise ValueError('Private historische Datei.')
        return f
    e=event(db,f['exam_event_id'],uid)
    if manage and e['group_id'] is not None:
        g=group(db,e['group_id'],uid)
        if uid not in (g['owner_id'],f['uploader_id']): raise ValueError('Nur hochladende Person und Gruppenverwaltung dürfen die Datei verwalten.')
    return f

def get_file(db,fid,uid):
    f=dict(attachment(db,fid,uid))
    if f['legacy_file_id'] is not None:
        f['content']=db.execute('SELECT content FROM exam_files WHERE id=?',(f['legacy_file_id'],)).fetchone()['content']
    return f

def state(db,uid,priority):
    groups=rows(db,'''SELECT g.*,u.username AS owner_name,
        (SELECT COUNT(*) FROM members m WHERE m.group_id=g.id AND m.left_at IS NULL) AS member_count,
        EXISTS(SELECT 1 FROM members m WHERE m.group_id=g.id AND m.user_id=? AND m.left_at IS NULL) AS joined
        FROM study_groups g JOIN users u ON u.id=g.owner_id ORDER BY COALESCE(g.parent_id,g.id),g.parent_id,g.name''',(uid,))
    events=rows(db,'''SELECT e.*,u.username AS creator_name FROM exam_events e JOIN users u ON u.id=e.creator_id
        WHERE e.owner_user_id=? OR EXISTS(SELECT 1 FROM members m WHERE m.group_id=e.group_id AND m.user_id=? AND m.left_at IS NULL)
        ORDER BY e.exam_date,e.id''',(uid,uid))
    for e in events:e['deletion_mode']='archived' if event_used(db,e) else 'deleted'
    personal=rows(db,'''SELECT s.*,e.title,e.subject,e.exam_date,e.group_id,e.archived_at AS event_archived_at,
        e.version AS event_version,COALESCE(a.seconds,0) AS seconds,COALESCE(a.session_count,0) AS session_count
        FROM user_exam_states s JOIN exam_events e ON e.id=s.exam_event_id
        LEFT JOIN (SELECT user_exam_state_id,SUM(seconds) AS seconds,COUNT(*) AS session_count FROM sessions
        WHERE user_id=? GROUP BY user_exam_state_id) a ON a.user_exam_state_id=s.id WHERE s.user_id=? ORDER BY e.exam_date,s.id''',(uid,uid))
    for s in personal:
        e=db.execute('SELECT * FROM exam_events WHERE id=?',(s['exam_event_id'],)).fetchone()
        if s['detached_history_id'] is not None:
            h=db.execute('SELECT * FROM exam_event_history WHERE id=?',(s['detached_history_id'],)).fetchone()
            for key in ('title','subject','exam_date'):s[key]=h[key]
            s['event_archived_at']=h['archived_at'];s['event_version']=h['version']
        s['startable']=startable(db,s,e,uid)
        s['priority']=priority(s,s['seconds']/60) if s['startable'] else None
        s['has_group_access']=e['group_id'] is None or member(db,e['group_id'],uid)
        s['deletion_mode']='archived' if state_used(db,s) or e['group_id'] is not None else 'deleted'
    files=rows(db,'''SELECT f.id,f.exam_event_id,f.uploader_id,f.filename,f.mime,f.size,f.created,f.archived_at,f.private_owner_id,u.username AS uploader_name
        FROM exam_attachments f JOIN users u ON u.id=f.uploader_id JOIN exam_events e ON e.id=f.exam_event_id
        WHERE f.private_owner_id=? OR (f.private_owner_id IS NULL AND (e.owner_user_id=? OR EXISTS(
        SELECT 1 FROM members m WHERE m.group_id=e.group_id AND m.user_id=? AND m.left_at IS NULL)))
        ORDER BY f.id DESC''',(uid,uid,uid))
    posts,comments=posts_for(db,uid)
    active=db.execute('SELECT * FROM active WHERE user_id=?',(uid,)).fetchone()
    active=dict(active) if active else None
    if active: active['elapsed']=max(0,(active['paused'] if active['paused'] is not None else time.time())-active['started']-active['paused_total'])
    return {'api_version':2,'groups':groups,'exam_events':events,'user_exam_states':personal,
        'sessions':rows(db,'SELECT * FROM sessions WHERE user_id=? ORDER BY date DESC,id DESC',(uid,)),
        'active':active,'files':files,'posts':posts,'comments':comments,
        'own_posts':posts_for(db,uid,'mine',limit=1000000000)[0],
        'notices':rows(db,'SELECT * FROM notices WHERE user_id=? AND read_at IS NULL ORDER BY id DESC LIMIT 100',(uid,)),
        'notice_count':db.execute('SELECT COUNT(*) FROM notices WHERE user_id=? AND read_at IS NULL',(uid,)).fetchone()[0],
        'locations':[r[0] for r in db.execute('SELECT DISTINCT location FROM sessions WHERE user_id=? ORDER BY location',(uid,))],
        'grade_history':rows(db,'''SELECT h.* FROM exam_grade_history h JOIN user_exam_states s ON s.id=h.user_exam_state_id WHERE s.user_id=? ORDER BY h.id''',(uid,)),
        'event_history':rows(db,'''SELECT h.* FROM exam_event_history h WHERE EXISTS
        (SELECT 1 FROM user_exam_states s WHERE s.user_id=? AND s.exam_event_id=h.exam_event_id
        AND (s.detached_history_id IS NULL OR h.id<=s.detached_history_id)) OR h.exam_event_id IN
        (SELECT e.id FROM exam_events e JOIN members m ON m.group_id=e.group_id WHERE m.user_id=? AND m.left_at IS NULL) ORDER BY h.id''',(uid,uid))}

def handle(action,db,uid,data,required,integer,iso_date,moderate):
    ident=lambda key:integer(data,key,1,1000000000)
    result={}
    if action=='group-create':
        parent=data.get('parent_id')
        if parent is not None:
            parent=ident('parent_id');g=group(db,parent,uid)
            if g['parent_id'] is not None or g['owner_id']!=uid:
                raise ValueError('Nur die Hauptgruppenverwaltung darf Untergruppen anlegen.')
        description=data.get('description','')
        if not isinstance(description,str) or len(description)>500: raise ValueError('Beschreibung: maximal 500 Zeichen.')
        gid=db.execute('INSERT INTO study_groups(name,description,owner_id,parent_id) VALUES(?,?,?,?)',
            (required(data,'name',100),description.strip(),uid,parent)).lastrowid
        db.execute('INSERT INTO members(group_id,user_id) VALUES(?,?)',(gid,uid))
        result={'id':gid}
    elif action=='group-join':
        gid=ident('group_id');g=db.execute('SELECT * FROM study_groups WHERE id=?',(gid,)).fetchone()
        if not g: raise ValueError('Gruppe nicht gefunden.')
        if g['parent_id'] is not None and not member(db,g['parent_id'],uid): raise ValueError('Bitte zuerst der Hauptgruppe beitreten.')
        db.execute('INSERT INTO members(group_id,user_id) VALUES(?,?) ON CONFLICT(group_id,user_id) DO UPDATE SET left_at=NULL',(gid,uid))
        db.execute('UPDATE user_exam_states SET detached_history_id=NULL WHERE user_id=? AND exam_event_id IN (SELECT id FROM exam_events WHERE group_id=?)',(uid,gid))
    elif action=='group-leave':
        gid=ident('group_id');g=group(db,gid,uid)
        if g['owner_id']==uid: raise ValueError('Die Gruppenverwaltung kann ihre Gruppe nicht verlassen.')
        if db.execute('''SELECT 1 FROM members m JOIN study_groups g ON g.id=m.group_id
                         WHERE g.parent_id=? AND m.user_id=? AND m.left_at IS NULL''',(gid,uid)).fetchone():
            raise ValueError('Bitte zuerst die Untergruppen verlassen.')
        db.execute('''UPDATE user_exam_states SET detached_history_id=(SELECT h.id FROM exam_event_history h
            WHERE h.exam_event_id=user_exam_states.exam_event_id ORDER BY h.version DESC LIMIT 1)
            WHERE user_id=? AND exam_event_id IN (SELECT id FROM exam_events WHERE group_id=?)''',(uid,gid))
        db.execute('UPDATE members SET left_at=? WHERE group_id=? AND user_id=?',(now(),gid,uid))
        db.execute("UPDATE posts SET revoked_at=? WHERE user_id=? AND target_group_id=? AND audience='group' AND revoked_at IS NULL",(now(),uid,gid))
    elif action=='exam':
        gid=data.get('group_id')
        if gid is not None: gid=ident('group_id');group(db,gid,uid)
        eid=db.execute('INSERT INTO exam_events(title,subject,exam_date,creator_id,owner_user_id,group_id) VALUES(?,?,?,?,?,?)',
            (required(data,'title'),required(data,'subject'),iso_date(data.get('exam_date')),uid,None if gid else uid,gid)).lastrowid
        record_event(db,eid,uid,'create')
        if 'adopt' in data and type(data['adopt']) is not bool: raise ValueError('adopt muss ein Wahrheitswert sein.')
        if gid is None or data.get('adopt',False):
            sid=db.execute('INSERT INTO user_exam_states(user_id,exam_event_id,difficulty) VALUES(?,?,?)',
                (uid,eid,integer(data,'difficulty',1,5))).lastrowid
            result['user_exam_state_id']=sid
        result['exam_event_id']=eid
    elif action=='group-adopt':
        e=event(db,ident('exam_event_id'),uid)
        if e['archived_at']: raise ValueError('Dieser Termin ist archiviert.')
        if e['group_id'] is None: raise ValueError('Keine Gruppenprüfung.')
        old=db.execute('SELECT * FROM user_exam_states WHERE user_id=? AND exam_event_id=?',(uid,e['id'])).fetchone()
        if old:
            if old['archived_at']: raise ValueError('Die Prüfung ist bereits im Archiv. Bitte wiederherstellen.')
            raise ValueError('Diese Prüfung wurde bereits übernommen.')
        result['user_exam_state_id']=db.execute('INSERT INTO user_exam_states(user_id,exam_event_id,difficulty) VALUES(?,?,?)',
            (uid,e['id'],integer(data,'difficulty',1,5))).lastrowid
    elif action in ('exam-edit','grade','exam-delete','exam-restore'):
        s=owned_state(db,ident('user_exam_state_id'),uid);version(s,data)
        e=db.execute('SELECT * FROM exam_events WHERE id=?',(s['exam_event_id'],)).fetchone()
        if action=='grade':
            grade=integer(data,'grade',1,5)
            if grade!=s['grade'] or not s['completed']:
                db.execute('INSERT INTO exam_grade_history(user_exam_state_id,old_grade,new_grade,old_completed,new_completed,changed_by,changed_at,source) VALUES(?,?,?,?,1,?,?,?)',
                    (s['id'],s['grade'],grade,s['completed'],uid,now(),'edit'))
                db.execute('UPDATE user_exam_states SET grade=?,completed=1,version=version+1 WHERE id=?',(grade,s['id']))
        elif action=='exam-edit':
            difficulty=integer(data,'difficulty',1,5)
            if e['owner_user_id']==uid:
                version(e,{'version':data.get('event_version')})
                edit_event(db,e,uid,data,required,iso_date)
            db.execute('UPDATE user_exam_states SET difficulty=?,version=version+1 WHERE id=?',(difficulty,s['id']))
        elif action=='exam-delete':
            if state_used(db,s) or e['group_id'] is not None:
                db.execute('UPDATE user_exam_states SET archived_at=?,version=version+1 WHERE id=?',(now(),s['id']))
                if e['owner_user_id']==uid and e['archived_at'] is None: archive_event(db,e,uid)
                result['mode']='archived'
            else:
                db.execute('DELETE FROM user_exam_states WHERE id=?',(s['id'],))
                db.execute('DELETE FROM exam_event_history WHERE exam_event_id=?',(e['id'],))
                db.execute('DELETE FROM exam_events WHERE id=?',(e['id'],));result['mode']='deleted'
        else:
            db.execute('UPDATE user_exam_states SET archived_at=NULL,version=version+1 WHERE id=?',(s['id'],))
            if e['owner_user_id']==uid and e['archived_at'] is not None: archive_event(db,e,uid,restore=True)
    elif action in ('event-edit','event-delete','event-restore'):
        e=event(db,ident('exam_event_id'),uid,edit=True);version(e,data)
        if action=='event-edit': edit_event(db,e,uid,data,required,iso_date)
        elif action=='event-restore': archive_event(db,e,uid,restore=True)
        elif event_used(db,e): archive_event(db,e,uid);result['mode']='archived'
        else:
            db.execute('DELETE FROM exam_event_history WHERE exam_event_id=?',(e['id'],))
            db.execute('DELETE FROM exam_events WHERE id=?',(e['id'],));result['mode']='deleted'
    elif action=='start':
        if db.execute('SELECT 1 FROM active WHERE user_id=?',(uid,)).fetchone(): raise ValueError('Es läuft bereits eine Lernsession.')
        sid=data.get('user_exam_state_id')
        if sid is not None:
            sid=ident('user_exam_state_id');s=owned_state(db,sid,uid);e=event(db,s['exam_event_id'],uid)
            if not startable(db,s,e,uid): raise ValueError('Diese Prüfung ist abgeschlossen oder archiviert.')
            subject=e['subject']
        else: subject=required(data,'subject')
        db.execute('INSERT INTO active(user_id,user_exam_state_id,subject,started,date) VALUES(?,?,?,?,?)',
            (uid,sid,subject,time.time(),iso_date(data.get('date'))))
    elif action in ('pause','resume','stop','finish','discard'):
        a=db.execute('SELECT * FROM active WHERE user_id=?',(uid,)).fetchone()
        if not a: raise ValueError('Keine laufende Lernsession vorhanden.')
        stamp=time.time()
        if action=='pause' and a['paused'] is None:
            db.execute('UPDATE active SET paused=?,interruptions=interruptions+1 WHERE user_id=?',(stamp,uid))
        elif action=='stop' and a['paused'] is None: db.execute('UPDATE active SET paused=? WHERE user_id=?',(stamp,uid))
        elif action=='resume' and a['paused'] is not None:
            db.execute('UPDATE active SET paused_total=paused_total+?,paused=NULL WHERE user_id=?',(stamp-a['paused'],uid))
        elif action=='finish':
            seconds=max(.1,round((a['paused'] if a['paused'] is not None else stamp)-a['started']-a['paused_total'],1))
            result['session_id']=db.execute('INSERT INTO sessions(user_id,exam_id,user_exam_state_id,subject,date,seconds,resources,location,interruptions) VALUES(?,?,?,?,?,?,?,?,?)',
                (uid,a['exam_id'],a['user_exam_state_id'],a['subject'],a['date'],seconds,required(data,'resources',200),required(data,'location'),a['interruptions'])).lastrowid
            db.execute('DELETE FROM active WHERE user_id=?',(uid,))
        elif action=='discard': db.execute('DELETE FROM active WHERE user_id=?',(uid,))
    elif action=='session':
        sid=data.get('user_exam_state_id')
        if sid is not None:
            sid=ident('user_exam_state_id');s=owned_state(db,sid,uid);e=event(db,s['exam_event_id'],uid);subject=e['subject']
        else: subject=required(data,'subject')
        result['session_id']=db.execute('INSERT INTO sessions(user_id,user_exam_state_id,subject,date,seconds,resources,location,interruptions) VALUES(?,?,?,?,?,?,?,?)',
            (uid,sid,subject,iso_date(data.get('date')),integer(data,'duration_minutes',1,1440)*60,
             required(data,'resources',200),required(data,'location'),integer(data,'interruptions',0,1000))).lastrowid
    elif action=='assign':
        session=db.execute('SELECT * FROM sessions WHERE id=? AND user_id=?',(ident('session_id'),uid)).fetchone()
        s=owned_state(db,ident('user_exam_state_id'),uid);e=event(db,s['exam_event_id'],uid)
        if not session or session['subject'].casefold()!=e['subject'].casefold(): raise ValueError('Session und Prüfung müssen zum gleichen Fach gehören.')
        db.execute('UPDATE sessions SET user_exam_state_id=? WHERE id=?',(s['id'],session['id']))
    elif action=='file-upload':
        e=event(db,ident('exam_event_id'),uid)
        if e['archived_at']: raise ValueError('Bitte zuerst den Termin wiederherstellen.')
        filename=required(data,'filename',150)
        if '/' in filename or '\\' in filename or any(ord(c)<32 for c in filename): raise ValueError('Ungültiger Dateiname.')
        encoded=data.get('content')
        if not isinstance(encoded,str) or len(encoded)>MAX_FILE*4//3+4: raise ValueError('Maximal 5 MiB pro Datei.')
        try: content=base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error): raise ValueError('Dateiübertragung ungültig.')
        if not 0<len(content)<=MAX_FILE: raise ValueError('Datei muss 1 Byte bis 5 MiB groß sein.')
        suffix=Path(filename).suffix.lower()
        if suffix=='.pdf' and content.startswith(b'%PDF-'): mime='application/pdf'
        elif suffix=='.png' and content.startswith(b'\x89PNG\r\n\x1a\n'): mime='image/png'
        elif suffix in ('.jpg','.jpeg') and content.startswith(b'\xff\xd8\xff'): mime='image/jpeg'
        else: raise ValueError('Nur PDF, PNG und JPEG mit passendem Inhalt.')
        if db.execute('SELECT COALESCE(SUM(size),0) FROM exam_attachments').fetchone()[0]+len(content)>MAX_TOTAL:
            raise ValueError('Dateispeicher voll (200 MiB inklusive Archiv).')
        result['attachment_id']=db.execute('INSERT INTO exam_attachments(exam_event_id,uploader_id,filename,mime,size,content,created) VALUES(?,?,?,?,?,?,?)',
            (e['id'],uid,filename,mime,len(content),content,now())).lastrowid
    elif action in ('file-delete','file-restore'):
        f=attachment(db,ident('attachment_id'),uid,manage=True)
        db.execute('UPDATE exam_attachments SET archived_at=? WHERE id=?',(now() if action=='file-delete' else None,f['id']))
    elif action=='notice-read':
        db.execute('UPDATE notices SET read_at=? WHERE id=? AND user_id=?',(now(),ident('notice_id'),uid))
    elif action=='notices-read-all':
        db.execute('UPDATE notices SET read_at=? WHERE user_id=? AND read_at IS NULL',(now(),uid))
    elif action=='weekly-goal':
        minutes=data.get('weekly_goal_minutes')
        if minutes is not None:
            minutes=integer(data,'weekly_goal_minutes',15,10080)
            if minutes % 15: raise ValueError('Bitte Viertelstunden wählen.')
        db.execute('UPDATE users SET weekly_goal_minutes=? WHERE id=?',(minutes,uid))
    elif action=='session-ranking':
        sid=ident('session_id')
        if type(data.get('public')) is not bool: raise ValueError('public muss ein Wahrheitswert sein.')
        if not db.execute('SELECT 1 FROM sessions WHERE id=? AND user_id=?',(sid,uid)).fetchone():
            raise ValueError('Session nicht gefunden oder kein Zugriff.')
        db.execute('UPDATE sessions SET public=? WHERE id=?',(int(data['public']),sid))
    elif action=='post':
        text=moderate(data.get('text',''))
        if data.get('session_id') is not None:
            s=db.execute('SELECT * FROM sessions WHERE id=? AND user_id=?',(ident('session_id'),uid)).fetchone()
            if not s: raise ValueError('Session nicht gefunden.')
            audience=data.get('audience','private')
            if audience not in ('private','group','public'): raise ValueError('Ungültige Sichtbarkeit.')
            gid=ident('target_group_id') if audience=='group' else None
            if gid: group(db,gid,uid)
            show=integer(data,'show_seconds',0,1) if 'show_seconds' in data else 0
            result['post_id']=db.execute('''INSERT INTO posts(user_id,text,subject,title,seconds,created,audience,target_group_id,
                show_grade,show_seconds,show_count,session_id) VALUES(?,?,?,'Lernsession',?,?,?,?,0,?,0,?)''',
                (uid,text,s['subject'],s['seconds'],now(),audience,gid,show,s['id'])).lastrowid
        else:
            s=owned_state(db,ident('user_exam_state_id'),uid)
            if not s['completed'] or s['grade'] is None: raise ValueError('Bitte zuerst eine Note eintragen.')
            audience=data.get('audience','private')
            if audience not in ('private','group'): raise ValueError('Ungültige Sichtbarkeit.')
            gid=ident('target_group_id') if audience=='group' else None
            if gid: group(db,gid,uid)
            flags=[integer(data,k,0,1) for k in ('show_grade','show_seconds','show_count')]
            e=db.execute('SELECT * FROM exam_events WHERE id=?',(s['exam_event_id'],)).fetchone()
            if s['detached_history_id'] is not None:
                e=db.execute('SELECT * FROM exam_event_history WHERE id=?',(s['detached_history_id'],)).fetchone()
            total,count=db.execute('SELECT COALESCE(SUM(seconds),0),COUNT(*) FROM sessions WHERE user_exam_state_id=? AND user_id=?',(s['id'],uid)).fetchone()
            result['post_id']=db.execute('''INSERT INTO posts(user_id,text,subject,title,seconds,grade,created,user_exam_state_id,audience,target_group_id,show_grade,show_seconds,show_count,session_count)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(uid,text,e['subject'],e['title'],total,s['grade'],now(),s['id'],audience,gid,*flags,count)).lastrowid
    elif action=='post-delete':
        pid=ident('post_id')
        if not db.execute('SELECT 1 FROM posts WHERE id=? AND user_id=?',(pid,uid)).fetchone():
            raise ValueError('Beitrag nicht gefunden.')
        # Delete the entire discussion in one statement, including self-referencing replies.
        # Unexpected cross-post references fail the transaction instead of removing other data.
        db.execute('DELETE FROM comments WHERE post_id=?',(pid,))
        db.execute('DELETE FROM posts WHERE id=? AND user_id=?',(pid,uid))
    elif action=='post-revoke':
        if not db.execute('SELECT 1 FROM posts WHERE id=? AND user_id=?',(ident('post_id'),uid)).fetchone(): raise ValueError('Beitrag nicht gefunden.')
        db.execute('UPDATE posts SET revoked_at=? WHERE id=?',(now(),data['post_id']))
    elif action=='comment':
        p=db.execute('SELECT * FROM posts WHERE id=?',(ident('post_id'),)).fetchone()
        if not p or not can_comment(db,p,uid): raise ValueError('Beitrag nicht gefunden oder keine Kommentierberechtigung.')
        parent=data.get('parent_comment_id')
        if parent is not None:
            parent=ident('parent_comment_id')
            if not db.execute('SELECT 1 FROM comments WHERE id=? AND post_id=?',(parent,p['id'])).fetchone():
                raise ValueError('Bezugskommentar gehört nicht zu diesem Beitrag.')
        result['comment_id']=db.execute('INSERT INTO comments(post_id,user_id,text,created,parent_comment_id) VALUES(?,?,?,?,?)',
            (p['id'],uid,moderate(required(data,'text',500)),now(),parent)).lastrowid
    return result

def edit_event(db,e,uid,data,required,iso_date):
    if e['archived_at']: raise ValueError('Bitte zuerst den Termin wiederherstellen.')
    values=(required(data,'title'),required(data,'subject'),iso_date(data.get('exam_date')))
    if values==(e['title'],e['subject'],e['exam_date']): return
    db.execute('UPDATE exam_events SET title=?,subject=?,exam_date=?,version=version+1 WHERE id=?',(*values,e['id']))
    record_event(db,e['id'],uid)
    notify(db,e['id'],f'Prüfung aktualisiert: {values[0]} ({values[1]}), Termin {values[2]}. Deine Lernhistorie bleibt unverändert.')

def archive_event(db,e,uid,restore=False):
    db.execute('UPDATE exam_events SET archived_at=?,version=version+1 WHERE id=?',(None if restore else now(),e['id']))
    record_event(db,e['id'],uid,'restore' if restore else 'archive')
    notify(db,e['id'],f'Prüfung {"wiederhergestellt" if restore else "archiviert"}: {e["title"]}. Daten und Unterlagen bleiben erhalten.')
