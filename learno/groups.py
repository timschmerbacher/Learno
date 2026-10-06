"""Gruppen, gemeinsame Termine und zugriffsgeschützte Prüfungsunterlagen."""
import base64
import binascii
from datetime import datetime, timezone
from pathlib import Path

MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 200 * 1024 * 1024
ACTIONS = {'group-create','group-join','group-leave','group-exam','group-exam-edit',
           'group-exam-delete','group-adopt','exam-edit','exam-delete','file-upload',
           'file-delete','notice-read'}


def migrate(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS study_groups (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
      owner_id INTEGER NOT NULL REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS members (
      group_id INTEGER REFERENCES study_groups(id), user_id INTEGER REFERENCES users(id),
      PRIMARY KEY(group_id,user_id));
    CREATE TABLE IF NOT EXISTS group_exams (
      id INTEGER PRIMARY KEY, group_id INTEGER REFERENCES study_groups(id),
      creator_id INTEGER REFERENCES users(id), title TEXT NOT NULL, subject TEXT NOT NULL,
      exam_date TEXT NOT NULL, updated TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS exam_files (
      id INTEGER PRIMARY KEY, exam_id INTEGER REFERENCES exams(id),
      group_exam_id INTEGER REFERENCES group_exams(id), uploader_id INTEGER REFERENCES users(id),
      filename TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL,
      content BLOB NOT NULL, created TEXT NOT NULL,
      CHECK ((exam_id IS NULL) != (group_exam_id IS NULL)));
    CREATE TABLE IF NOT EXISTS notices (
      id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), text TEXT NOT NULL,
      created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS auth_sessions (
      token_hash TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id),
      csrf TEXT NOT NULL, expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS auth_attempts (bucket TEXT NOT NULL, created REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS auth_attempts_bucket ON auth_attempts(bucket,created);
    ''')
    if 'group_exam_id' not in {r['name'] for r in db.execute('PRAGMA table_info(exams)')}:
        db.execute('ALTER TABLE exams ADD COLUMN group_exam_id INTEGER REFERENCES group_exams(id)')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS exam_adoption ON exams(user_id,group_exam_id) WHERE group_exam_id IS NOT NULL')


def now():
    return datetime.now(timezone.utc).isoformat()


def member(db, gid, uid):
    group = db.execute('SELECT * FROM study_groups WHERE id=?',(gid,)).fetchone()
    if not group or not db.execute('SELECT 1 FROM members WHERE group_id=? AND user_id=?',(gid,uid)).fetchone():
        raise ValueError('Nur Gruppenmitglieder haben Zugriff.')
    return group


def shared(db, ident, uid, edit=False):
    exam = db.execute('SELECT * FROM group_exams WHERE id=?',(ident,)).fetchone()
    if not exam:
        raise ValueError('Gruppenprüfung nicht gefunden.')
    group = member(db,exam['group_id'],uid)
    if edit and uid not in (exam['creator_id'],group['owner_id']):
        raise ValueError('Nur Ersteller und Gruppenverwaltung dürfen diesen Termin ändern.')
    return exam,group


def notify(db, uid, text):
    db.execute('INSERT INTO notices(user_id,text,created) VALUES(?,?,?)',(uid,text,now()))


def state(db,uid):
    groups = [dict(r) for r in db.execute('''SELECT g.*,u.username AS owner_name,
       (SELECT COUNT(*) FROM members m WHERE m.group_id=g.id) AS member_count,
       EXISTS(SELECT 1 FROM members m WHERE m.group_id=g.id AND m.user_id=?) AS joined
       FROM study_groups g JOIN users u ON u.id=g.owner_id ORDER BY g.name COLLATE NOCASE,g.id''',(uid,))]
    exams = [dict(r) for r in db.execute('''SELECT e.*,u.username AS creator_name FROM group_exams e
       JOIN users u ON u.id=e.creator_id JOIN members m ON m.group_id=e.group_id
       WHERE m.user_id=? ORDER BY e.exam_date,e.id''',(uid,))]
    files = [dict(r) for r in db.execute('''SELECT f.id,f.exam_id,f.group_exam_id,f.uploader_id,f.filename,
       f.size,f.created,u.username AS uploader_name FROM exam_files f JOIN users u ON u.id=f.uploader_id
       WHERE f.exam_id IN (SELECT id FROM exams WHERE user_id=?) OR f.group_exam_id IN
       (SELECT e.id FROM group_exams e JOIN members m ON m.group_id=e.group_id WHERE m.user_id=?)
       ORDER BY f.id DESC''',(uid,uid))]
    return {'groups':groups,'group_exams':exams,'files':files,
       'notices':[dict(r) for r in db.execute('SELECT * FROM notices WHERE user_id=? ORDER BY id DESC LIMIT 100',(uid,))],
       'locations':[r[0] for r in db.execute('SELECT DISTINCT location FROM sessions WHERE user_id=? ORDER BY location',(uid,))]}


def get_file(db, ident, uid):
    file = db.execute('SELECT * FROM exam_files WHERE id=?',(ident,)).fetchone()
    if not file:
        raise ValueError('Datei nicht gefunden.')
    if file['group_exam_id']:
        shared(db,file['group_exam_id'],uid)
    elif not db.execute('SELECT 1 FROM exams WHERE id=? AND user_id=?',(file['exam_id'],uid)).fetchone():
        raise ValueError('Kein Zugriff auf diese Datei.')
    return file


def handle(action,db,uid,data,required,integer,iso_date,owned):
    ident = lambda key='id': integer(data,key,1,1000000000)
    if action == 'group-create':
        name=required(data,'name',100)
        description=data.get('description','')
        if not isinstance(description,str) or len(description)>500:
            raise ValueError('Beschreibung: maximal 500 Zeichen.')
        gid=db.execute('INSERT INTO study_groups(name,description,owner_id) VALUES(?,?,?)',(name,description.strip(),uid)).lastrowid
        db.execute('INSERT INTO members VALUES(?,?)',(gid,uid))
        return {'id':gid}
    if action == 'group-join':
        gid=ident()
        if not db.execute('SELECT 1 FROM study_groups WHERE id=?',(gid,)).fetchone():
            raise ValueError('Gruppe nicht gefunden.')
        db.execute('INSERT OR IGNORE INTO members VALUES(?,?)',(gid,uid))
    elif action == 'group-leave':
        gid=ident(); group=member(db,gid,uid)
        if group['owner_id']==uid:
            raise ValueError('Als Gruppenverwaltung kannst du deine Gruppe noch nicht verlassen.')
        db.execute('UPDATE exams SET group_exam_id=NULL WHERE user_id=? AND group_exam_id IN (SELECT id FROM group_exams WHERE group_id=?)',(uid,gid))
        db.execute('DELETE FROM members WHERE group_id=? AND user_id=?',(gid,uid))
    elif action == 'group-exam':
        gid=ident('group_id');member(db,gid,uid)
        eid=db.execute('INSERT INTO group_exams(group_id,creator_id,title,subject,exam_date,updated) VALUES(?,?,?,?,?,?)',
            (gid,uid,required(data,'title'),required(data,'subject'),iso_date(data.get('exam_date')),now())).lastrowid
        return {'id':eid}
    elif action == 'group-adopt':
        exam,_=shared(db,ident(),uid)
        difficulty=integer(data,'difficulty',1,5)
        if db.execute('SELECT 1 FROM exams WHERE user_id=? AND group_exam_id=?',(uid,exam['id'])).fetchone():
            raise ValueError('Du hast diese Prüfung bereits übernommen.')
        eid=db.execute('INSERT INTO exams(user_id,title,subject,exam_date,difficulty,group_exam_id) VALUES(?,?,?,?,?,?)',
            (uid,exam['title'],exam['subject'],exam['exam_date'],difficulty,exam['id'])).lastrowid
        return {'id':eid}
    elif action == 'group-exam-edit':
        exam,_=shared(db,ident(),uid,edit=True)
        title,subject,day=required(data,'title'),required(data,'subject'),iso_date(data.get('exam_date'))
        db.execute('UPDATE group_exams SET title=?,subject=?,exam_date=?,updated=? WHERE id=?',(title,subject,day,now(),exam['id']))
        for personal in db.execute('SELECT id,user_id FROM exams WHERE group_exam_id=?',(exam['id'],)).fetchall():
            db.execute('UPDATE exams SET title=?,subject=?,exam_date=? WHERE id=?',(title,subject,day,personal['id']))
            db.execute('UPDATE sessions SET subject=? WHERE exam_id=?',(subject,personal['id']))
            db.execute('UPDATE active SET subject=? WHERE exam_id=?',(subject,personal['id']))
            notify(db,personal['user_id'],f'Gruppenprüfung aktualisiert: {title} ({subject}), Termin {exam["exam_date"]} → {day}.')
    elif action == 'group-exam-delete':
        exam,_=shared(db,ident(),uid,edit=True)
        for personal in db.execute('SELECT user_id FROM exams WHERE group_exam_id=?',(exam['id'],)).fetchall():
            notify(db,personal['user_id'],f'Gruppenprüfung „{exam["title"]}“ wurde gelöscht. Deine persönliche Kopie bleibt ohne Synchronisation erhalten.')
        db.execute('UPDATE exams SET group_exam_id=NULL WHERE group_exam_id=?',(exam['id'],))
        db.execute('DELETE FROM exam_files WHERE group_exam_id=?',(exam['id'],))
        db.execute('DELETE FROM group_exams WHERE id=?',(exam['id'],))
    elif action == 'exam-edit':
        exam=owned(db,'exams',ident(),uid)
        difficulty=integer(data,'difficulty',1,5)
        if exam['group_exam_id']:
            # Gemeinsame Felder können nicht über die persönliche Kopie verändert werden.
            db.execute('UPDATE exams SET difficulty=? WHERE id=?',(difficulty,exam['id']))
        else:
            title,subject,day=required(data,'title'),required(data,'subject'),iso_date(data.get('exam_date'))
            db.execute('UPDATE exams SET title=?,subject=?,exam_date=?,difficulty=? WHERE id=?',(title,subject,day,difficulty,exam['id']))
            db.execute('UPDATE sessions SET subject=? WHERE exam_id=?',(subject,exam['id']))
            db.execute('UPDATE active SET subject=? WHERE exam_id=?',(subject,exam['id']))
    elif action == 'exam-delete':
        exam=owned(db,'exams',ident(),uid)
        db.execute('UPDATE sessions SET exam_id=NULL WHERE exam_id=?',(exam['id'],))
        db.execute('UPDATE active SET exam_id=NULL WHERE exam_id=?',(exam['id'],))
        db.execute('DELETE FROM exam_files WHERE exam_id=?',(exam['id'],))
        db.execute('DELETE FROM exams WHERE id=?',(exam['id'],))
    elif action == 'file-upload':
        exam_id=group_exam_id=None
        if data.get('group_exam_id'):
            group_exam_id=ident('group_exam_id');shared(db,group_exam_id,uid)
        else:
            exam_id=ident('exam_id');exam=owned(db,'exams',exam_id,uid)
            if exam['group_exam_id']:
                group_exam_id=exam['group_exam_id'];shared(db,group_exam_id,uid);exam_id=None
        filename=required(data,'filename',150)
        if '/' in filename or '\\' in filename or any(ord(c)<32 for c in filename):
            raise ValueError('Ungültiger Dateiname.')
        encoded=data.get('content')
        if not isinstance(encoded,str) or len(encoded)>MAX_FILE*4//3+4:
            raise ValueError('Dateien dürfen maximal 5 MiB groß sein.')
        try:
            content=base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error):
            raise ValueError('Dateiübertragung ungültig.')
        if not 0<len(content)<=MAX_FILE:
            raise ValueError('Dateien dürfen maximal 5 MiB groß und nicht leer sein.')
        suffix=Path(filename).suffix.lower()
        if suffix=='.pdf' and content.startswith(b'%PDF-'):
            mime='application/pdf'
        elif suffix=='.png' and content.startswith(b'\x89PNG\r\n\x1a\n'):
            mime='image/png'
        elif suffix in ('.jpg','.jpeg') and content.startswith(b'\xff\xd8\xff'):
            mime='image/jpeg'
        else:
            raise ValueError('Nur PDF, PNG und JPEG mit passendem Dateiinhalt sind erlaubt.')
        used=db.execute('SELECT COALESCE(SUM(size),0) FROM exam_files').fetchone()[0]
        if used+len(content)>MAX_TOTAL:
            raise ValueError('Der Dateispeicher der Test-App ist voll (200 MiB). Bitte Dateien entfernen.')
        fid=db.execute('INSERT INTO exam_files(exam_id,group_exam_id,uploader_id,filename,mime,size,content,created) VALUES(?,?,?,?,?,?,?,?)',
            (exam_id,group_exam_id,uid,filename,mime,len(content),content,now())).lastrowid
        return {'id':fid}
    elif action == 'file-delete':
        file=get_file(db,ident(),uid)
        if file['group_exam_id']:
            _,group=shared(db,file['group_exam_id'],uid)
            if uid not in (file['uploader_id'],group['owner_id']):
                raise ValueError('Nur hochladende Person und Gruppenverwaltung dürfen diese Datei löschen.')
        db.execute('DELETE FROM exam_files WHERE id=?',(file['id'],))
    elif action == 'notice-read':
        db.execute('DELETE FROM notices WHERE id=? AND user_id=?',(ident(),uid))
    return {}
