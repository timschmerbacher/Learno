"""Explicit, backed-up, additive V2 migration. Run while all app workers are stopped."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import legacy_schema

VERSION = 5
SCHEMA = '''
CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, backup_path TEXT);
CREATE TABLE exam_events(
 id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, subject TEXT NOT NULL, exam_date TEXT NOT NULL,
 creator_id INTEGER NOT NULL REFERENCES users(id), owner_user_id INTEGER REFERENCES users(id),
 group_id INTEGER REFERENCES study_groups(id), archived_at TEXT, version INTEGER NOT NULL DEFAULT 1,
 legacy_exam_id INTEGER UNIQUE REFERENCES exams(id), legacy_group_exam_id INTEGER UNIQUE REFERENCES group_exams(id),
 CHECK((owner_user_id IS NULL)!=(group_id IS NULL)));
CREATE TABLE user_exam_states(
 id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
 exam_event_id INTEGER NOT NULL REFERENCES exam_events(id), difficulty INTEGER NOT NULL CHECK(difficulty BETWEEN 1 AND 5),
 grade INTEGER CHECK(grade BETWEEN 1 AND 5), completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
 archived_at TEXT, version INTEGER NOT NULL DEFAULT 1, legacy_exam_id INTEGER UNIQUE REFERENCES exams(id),
 detached_history_id INTEGER REFERENCES exam_event_history(id),
 UNIQUE(user_id,exam_event_id));
CREATE TABLE exam_event_history(
 id INTEGER PRIMARY KEY AUTOINCREMENT, exam_event_id INTEGER NOT NULL REFERENCES exam_events(id),
 title TEXT NOT NULL, subject TEXT NOT NULL, exam_date TEXT NOT NULL, archived_at TEXT,
 version INTEGER NOT NULL, changed_by INTEGER REFERENCES users(id), changed_at TEXT NOT NULL, source TEXT NOT NULL,
 UNIQUE(exam_event_id,version));
CREATE TABLE exam_grade_history(
 id INTEGER PRIMARY KEY AUTOINCREMENT, user_exam_state_id INTEGER NOT NULL REFERENCES user_exam_states(id),
 old_grade INTEGER, new_grade INTEGER, old_completed INTEGER, new_completed INTEGER NOT NULL,
 changed_by INTEGER REFERENCES users(id), changed_at TEXT, source TEXT NOT NULL);
CREATE TABLE exam_attachments(
 id INTEGER PRIMARY KEY AUTOINCREMENT, exam_event_id INTEGER NOT NULL REFERENCES exam_events(id),
 uploader_id INTEGER NOT NULL REFERENCES users(id), filename TEXT NOT NULL, mime TEXT NOT NULL,
 size INTEGER NOT NULL CHECK(size>0), content BLOB, legacy_file_id INTEGER UNIQUE REFERENCES exam_files(id),
 private_owner_id INTEGER REFERENCES users(id),
 created TEXT NOT NULL, archived_at TEXT, CHECK((content IS NULL)!=(legacy_file_id IS NULL)));
CREATE INDEX state_user ON user_exam_states(user_id,archived_at);
CREATE INDEX event_group ON exam_events(group_id,archived_at);
CREATE INDEX attachment_event ON exam_attachments(exam_event_id);
'''
ADDITIONS = {
 'study_groups': [('parent_id','INTEGER REFERENCES study_groups(id)')],
 'members': [('left_at','TEXT')],
 'sessions': [('user_exam_state_id','INTEGER REFERENCES user_exam_states(id)')],
 'active': [('user_exam_state_id','INTEGER REFERENCES user_exam_states(id)')],
 'notices': [('read_at','TEXT')],
 'posts': [('user_exam_state_id','INTEGER REFERENCES user_exam_states(id)'), ('audience','TEXT NOT NULL DEFAULT \'legacy\''),
           ('target_group_id','INTEGER REFERENCES study_groups(id)'), ('show_grade','INTEGER NOT NULL DEFAULT 1'),
           ('show_seconds','INTEGER NOT NULL DEFAULT 1'), ('show_count','INTEGER NOT NULL DEFAULT 0'),
           ('session_count','INTEGER'), ('revoked_at','TEXT')],
}

def now():
    return datetime.now(timezone.utc).isoformat()

def has_version(db, version):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
                and db.execute('SELECT 1 FROM schema_migrations WHERE version=?',(version,)).fetchone())

def ready(db):
    return has_version(db, VERSION) and {r[0] for r in db.execute('SELECT version FROM schema_migrations')}=={2,3,4,5}

def check(db):
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Datenbankprüfung fehlgeschlagen. Keine automatische Reparatur.')

def snapshot(db):
    """Exact snapshot of existing columns, including BLOBs; never printed."""
    result={}
    for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        table=row[0]
        cols=[r[1] for r in db.execute(f'PRAGMA table_info("{table}")')]
        result[table]=(cols,db.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall())
    return result

def verify_snapshot(db, before):
    for table,(cols,values) in before.items():
        names=','.join('"'+c+'"' for c in cols)
        query=f'SELECT {names} FROM "{table}"'
        args=()
        if table=='schema_migrations':
            versions=[r[cols.index('version')] for r in values]
            query+=' WHERE version IN ('+','.join('?' for _ in versions)+')'
            args=versions
        if db.execute(query+' ORDER BY rowid',args).fetchall()!=values:
            raise ValueError('Bestandsvergleich fehlgeschlagen: '+table)

def _migrate_v2(db, backup_path=None):
    """Caller holds BEGIN IMMEDIATE; no executescript/implicit commits."""
    if has_version(db, 2):
        return False
    before=snapshot(db)
    legacy_schema.initialize(db)
    for statement in SCHEMA.split(';'):
        if statement.strip(): db.execute(statement)
    for table,cols in ADDITIONS.items():
        for name,kind in cols:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
    db.execute('CREATE INDEX session_state ON sessions(user_exam_state_id,user_id)')
    db.execute('CREATE INDEX members_active ON members(user_id,group_id,left_at)')
    db.execute('CREATE INDEX post_audience ON posts(target_group_id,audience,id)')
    stamp=now()
    for e in db.execute('SELECT * FROM group_exams').fetchall():
        db.execute('INSERT INTO exam_events(title,subject,exam_date,creator_id,group_id,legacy_group_exam_id) VALUES(?,?,?,?,?,?)',
                   (e['title'],e['subject'],e['exam_date'],e['creator_id'],e['group_id'],e['id']))
    for e in db.execute('SELECT * FROM exams').fetchall():
        if e['group_exam_id'] is not None:
            event=db.execute('SELECT id FROM exam_events WHERE legacy_group_exam_id=?',(e['group_exam_id'],)).fetchone()
            if not event: raise ValueError('Ungültige Gruppenverknüpfung.')
            eid=event['id']
        else:
            eid=db.execute('INSERT INTO exam_events(title,subject,exam_date,creator_id,owner_user_id,legacy_exam_id) VALUES(?,?,?,?,?,?)',
                (e['title'],e['subject'],e['exam_date'],e['user_id'],e['user_id'],e['id'])).lastrowid
        sid=db.execute('INSERT INTO user_exam_states(user_id,exam_event_id,difficulty,grade,completed,legacy_exam_id) VALUES(?,?,?,?,?,?)',
            (e['user_id'],eid,e['difficulty'],e['grade'],e['completed'],e['id'])).lastrowid
        for table in ('sessions','active'):
            if db.execute(f'SELECT 1 FROM {table} WHERE exam_id=? AND user_id!=?',(e['id'],e['user_id'])).fetchone():
                raise ValueError('Benutzerübergreifende Prüfungszuordnung.')
            db.execute(f'UPDATE {table} SET user_exam_state_id=? WHERE exam_id=?',(sid,e['id']))
        if e['grade'] is not None or e['completed']:
            db.execute('INSERT INTO exam_grade_history(user_exam_state_id,new_grade,new_completed,source) VALUES(?,?,?,?)',
                       (sid,e['grade'],e['completed'],'migration'))
    for f in db.execute('SELECT * FROM exam_files').fetchall():
        if f['group_exam_id'] is not None:
            eid=db.execute('SELECT id FROM exam_events WHERE legacy_group_exam_id=?',(f['group_exam_id'],)).fetchone()['id']
        else:
            eid=db.execute('SELECT exam_event_id FROM user_exam_states WHERE legacy_exam_id=?',(f['exam_id'],)).fetchone()['exam_event_id']
        private_owner=db.execute('SELECT user_id FROM exams WHERE id=?',(f['exam_id'],)).fetchone()['user_id'] if f['exam_id'] is not None else None
        db.execute('INSERT INTO exam_attachments(exam_event_id,uploader_id,filename,mime,size,legacy_file_id,created,private_owner_id) VALUES(?,?,?,?,?,?,?,?)',
                   (eid,f['uploader_id'],f['filename'],f['mime'],f['size'],f['id'],f['created'],private_owner))
    db.execute('''INSERT INTO exam_event_history(exam_event_id,title,subject,exam_date,version,changed_at,source)
                  SELECT id,title,subject,exam_date,version,?,'migration' FROM exam_events''',(stamp,))
    db.execute('''UPDATE user_exam_states SET detached_history_id=(SELECT id FROM exam_event_history h
                  WHERE h.exam_event_id=user_exam_states.exam_event_id)
                  WHERE exam_event_id IN (SELECT id FROM exam_events WHERE group_id IS NOT NULL)
                  AND NOT EXISTS(SELECT 1 FROM members m JOIN exam_events e ON e.group_id=m.group_id
                  WHERE e.id=user_exam_states.exam_event_id AND m.user_id=user_exam_states.user_id AND m.left_at IS NULL)''')
    verify_snapshot(db,before)
    check(db)
    # Block the destructive legacy implementation, including old worker writes.
    for table in ('exams','group_exams','exam_files'):
        for operation in ('INSERT','UPDATE','DELETE'):
            db.execute(f'''CREATE TRIGGER protect_legacy_{table}_{operation.lower()} BEFORE {operation} ON {table}
                           BEGIN SELECT RAISE(ABORT,'Legacy data are read-only; use Learno V2'); END''')
    db.execute('''CREATE TRIGGER immutable_session_content BEFORE UPDATE OF user_id,exam_id,subject,date,seconds,resources,location,interruptions ON sessions
                  BEGIN SELECT RAISE(ABORT,'Saved learning history is immutable'); END''')
    db.execute("CREATE TRIGGER preserve_sessions BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT,'Learning sessions cannot be deleted'); END")
    db.execute('INSERT INTO schema_migrations VALUES(?,?,?)',(2,stamp,str(backup_path) if backup_path else None))
    return True

def migrate_connection(db, backup_path=None, target_version=VERSION):
    """Apply ordered steps in the caller's single transaction, retaining original values."""
    if target_version not in (2,3,4,5): raise ValueError('Unbekannte Zielversion.')
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone():
        versions={r[0] for r in db.execute('SELECT version FROM schema_migrations')}
        if versions - {2,3,4,5} or (3 in versions and 2 not in versions) or (4 in versions and not {2,3}<=versions) or (5 in versions and not {2,3,4}<=versions):
            raise ValueError('Unbekannte oder unvollständige Migrationsfolge.')
    if has_version(db,target_version): return False
    before=snapshot(db)
    _migrate_v2(db,backup_path)
    if target_version>=3 and not has_version(db,3):
        db.execute('ALTER TABLE comments ADD COLUMN parent_comment_id INTEGER REFERENCES comments(id)')
        db.execute('CREATE INDEX comment_thread ON comments(post_id,parent_comment_id,id)')
        db.execute('ALTER TABLE users ADD COLUMN weekly_goal_minutes INTEGER CHECK(weekly_goal_minutes IS NULL OR (weekly_goal_minutes BETWEEN 15 AND 10080 AND weekly_goal_minutes % 15=0))')
        db.execute('INSERT INTO schema_migrations VALUES(?,?,?)',(3,now(),str(backup_path) if backup_path else None))
    if target_version>=4 and not has_version(db,4):
        db.execute('ALTER TABLE posts ADD COLUMN session_id INTEGER REFERENCES sessions(id)')
        db.execute('CREATE INDEX post_session ON posts(session_id)')
        db.execute('INSERT INTO schema_migrations VALUES(?,?,?)',(4,now(),str(backup_path) if backup_path else None))
    if target_version>=5 and not has_version(db,5):
        db.execute('''CREATE TABLE feedback_config(id INTEGER PRIMARY KEY CHECK(id=1),
            reviewer_user_id INTEGER NOT NULL REFERENCES users(id))''')
        db.execute('''CREATE TABLE feedback_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),text TEXT NOT NULL CHECK(length(text) BETWEEN 1 AND 2000),
            created TEXT NOT NULL,read_at TEXT)''')
        db.execute('CREATE INDEX feedback_author ON feedback_messages(user_id,id)')
        db.execute("CREATE TRIGGER preserve_feedback BEFORE DELETE ON feedback_messages BEGIN SELECT RAISE(ABORT,'Feedback history cannot be deleted'); END")
        db.execute("CREATE TRIGGER immutable_feedback BEFORE UPDATE OF user_id,text,created ON feedback_messages BEGIN SELECT RAISE(ABORT,'Feedback content cannot be overwritten'); END")
        db.execute('INSERT INTO schema_migrations VALUES(?,?,?)',(5,now(),str(backup_path) if backup_path else None))
    verify_snapshot(db,before)
    check(db)
    return True

def migrate_database(path, target_version=VERSION):
    path=Path(path).resolve()
    path.parent.mkdir(parents=True,exist_ok=True)
    existed=path.exists()
    backup=None
    if existed:
        source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        try:
            source.row_factory=sqlite3.Row
            check(source)
            if has_version(source,5) and not ready(source):
                raise ValueError('Unbekannte oder unvollständige Migrationsfolge.')
            if has_version(source,target_version): return {'changed':False,'backup':None}
            directory=path.parent/'backups';directory.mkdir(exist_ok=True)
            backup=directory/(f'learno-before-v{target_version}-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.db')
            with backup.open('xb'): pass
            target=sqlite3.connect(backup)
            try:
                source.backup(target);check(target)
            finally: target.close()
        finally: source.close()
    db=sqlite3.connect(path,timeout=15)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        db.execute('BEGIN IMMEDIATE')
        # Backup must still represent the exact source when acquiring the write lock.
        if backup:
            original=sqlite3.connect(backup);original.row_factory=sqlite3.Row
            try: verify_snapshot(db,snapshot(original))
            finally: original.close()
        changed=migrate_connection(db,backup,target_version)
        db.commit()
        return {'changed':changed,'backup':str(backup) if backup else None}
    except Exception:
        db.rollback();raise
    finally: db.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=os.environ.get('LEARNO_DB',str(Path(__file__).parent/'data'/'learno.db')))
    parser.add_argument('--workers-stopped',action='store_true',help='Confirm all local/WSGI workers are stopped')
    args=parser.parse_args()
    if not args.workers_stopped: parser.error('Stop all app workers, then pass --workers-stopped.')
    print(json.dumps(migrate_database(args.db),ensure_ascii=False))
