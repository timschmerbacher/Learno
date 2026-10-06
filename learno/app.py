"""Learno: lokale Lern-App. Start: python app.py (Python 3.10+)."""
import csv
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, quote
from contextlib import contextmanager
import groups

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('LEARNO_DB', str(ROOT / 'data' / 'learno.db')))
PASSWORD_ROUNDS = 260000


@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE,
          salt TEXT NOT NULL, password TEXT NOT NULL, reminder TEXT DEFAULT '18:00',
          reminder_on INTEGER DEFAULT 0, timezone TEXT DEFAULT 'Europe/Vienna');
        CREATE TABLE IF NOT EXISTS exams (
          id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id),
          title TEXT NOT NULL, subject TEXT NOT NULL, exam_date TEXT NOT NULL,
          difficulty INTEGER NOT NULL, grade INTEGER, completed INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions (
          id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id),
          exam_id INTEGER REFERENCES exams(id), subject TEXT NOT NULL,
          date TEXT NOT NULL, seconds REAL NOT NULL, resources TEXT NOT NULL,
          location TEXT NOT NULL, interruptions INTEGER DEFAULT 0,
          public INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS active (
          user_id INTEGER PRIMARY KEY REFERENCES users(id), exam_id INTEGER REFERENCES exams(id),
          subject TEXT NOT NULL, started REAL NOT NULL, paused REAL,
          paused_total REAL DEFAULT 0, interruptions INTEGER DEFAULT 0, date TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS friendships (
          sender INTEGER REFERENCES users(id), receiver INTEGER REFERENCES users(id),
          accepted INTEGER DEFAULT 0, PRIMARY KEY(sender, receiver));
        CREATE TABLE IF NOT EXISTS posts (
          id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id),
          text TEXT NOT NULL, subject TEXT NOT NULL, title TEXT NOT NULL,
          seconds REAL NOT NULL, grade INTEGER, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS comments (
          id INTEGER PRIMARY KEY, post_id INTEGER REFERENCES posts(id),
          user_id INTEGER REFERENCES users(id), text TEXT NOT NULL, created TEXT NOT NULL);
        ''')
        groups.migrate(db)


def required(data, key, limit=120):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise ValueError(f'{key}: Bitte 1 bis {limit} Zeichen eingeben.')
    return value.strip()


def integer(data, key, minimum, maximum):
    value = data.get(key)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{key}: Ganzzahl zwischen {minimum} und {maximum} erforderlich.')
    return value


def iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Datum bitte als YYYY-MM-DD angeben.')
    date.fromisoformat(value)
    return value


def moderate(text):
    if not isinstance(text, str) or len(text) > 500:
        raise ValueError('Maximal 500 Zeichen sind erlaubt.')
    blocked = set(json.loads((ROOT / 'blocked_words.json').read_text(encoding='utf-8'))['words'])
    if set(re.findall(r'\w+', text.casefold())) & blocked:
        raise ValueError('Bitte überarbeite deinen Text. Er enthält einen nicht erlaubten Ausdruck.')
    return text.strip()


def priority(exam, minutes, today=None):
    """Die gemeinsam definierte Heuristik, keine Bewertung des Wissensstands."""
    days = (date.fromisoformat(exam['exam_date']) - (today or date.today())).days
    if days < 0 or exam['completed']:
        return None
    pressure = 6 if days <= 3 else 5 if days <= 7 else 3 if days <= 14 else 2 if days <= 30 else 1
    return {'days': days, 'score': max(1, min(10, pressure + exam['difficulty'] - min(int(minutes // 60), 3)))}


def rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql, args)]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Keine Formularinhalte oder Passwörter protokollieren.
        if not self.path.startswith('/api/state'):
            super().log_message(fmt, *args)

    def send(self, status, body, content_type='application/json; charset=utf-8', cookie=None, attachment=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        if cookie:
            if getattr(self,'scheme','http') == 'https':
                cookie += '; Secure'
            self.send_header('Set-Cookie', cookie)
        if attachment:
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(attachment,safe=''))
        self.end_headers()
        self.wfile.write(body)

    def identity(self):
        cookie = SimpleCookie()
        cookie.load(self.headers.get('Cookie', ''))
        token = cookie.get('learno')
        if token:
            with connect() as db:
                session=db.execute('SELECT * FROM auth_sessions WHERE token_hash=? AND expires>?',
                    (hashlib.sha256(token.value.encode()).hexdigest(),time.time())).fetchone()
                if session:
                    return dict(session)
        return None

    def do_GET(self):
        path = urlparse(self.path).path
        static = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/groups.js': ('groups.js', 'text/javascript')}
        if path in static:
            filename, kind = static[path]
            return self.send(200, (ROOT / 'static' / filename).read_bytes(), kind + '; charset=utf-8')
        identity = self.identity()
        if not identity:
            return self.send(401, {'error': 'Bitte anmelden.'})
        uid = identity['user_id']
        with connect() as db:
            if path.startswith('/api/files/'):
                try:
                    file=groups.get_file(db,int(path.rsplit('/',1)[1]),uid)
                    return self.send(200,file['content'],file['mime'],attachment=file['filename'])
                except (ValueError,TypeError):
                    return self.send(404,{'error':'Datei nicht gefunden oder kein Zugriff.'})
            if path == '/api/state':
                user = dict(db.execute('SELECT id,username,reminder,reminder_on,timezone FROM users WHERE id=?', (uid,)).fetchone())
                sessions = rows(db, 'SELECT * FROM sessions WHERE user_id=? ORDER BY date DESC,id DESC', (uid,))
                exams = rows(db, 'SELECT * FROM exams WHERE user_id=? ORDER BY exam_date,id', (uid,))
                for exam in exams:
                    exam['seconds'] = sum(s['seconds'] for s in sessions if s['exam_id'] == exam['id'])
                    exam['priority'] = priority(exam, exam['seconds'] / 60)
                active = db.execute('SELECT * FROM active WHERE user_id=?', (uid,)).fetchone()
                active = dict(active) if active else None
                if active:
                    active['elapsed'] = max(0, (active['paused'] or time.time()) - active['started'] - active['paused_total'])
                friends = rows(db, '''SELECT f.*, a.username AS sender_name,b.username AS receiver_name
                    FROM friendships f JOIN users a ON a.id=f.sender JOIN users b ON b.id=f.receiver
                    WHERE sender=? OR receiver=?''', (uid, uid))
                posts = rows(db, '''SELECT p.*,u.username FROM posts p JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 200''')
                comments = rows(db, '''SELECT c.*,u.username FROM comments c JOIN users u ON u.id=c.user_id
                    WHERE c.post_id IN (SELECT id FROM posts ORDER BY id DESC LIMIT 200) ORDER BY c.id''')
                monday = date.today() - timedelta(days=date.today().weekday())
                ranking = rows(db, '''SELECT u.id,u.username,SUM(s.seconds) AS seconds FROM sessions s
                    JOIN users u ON u.id=s.user_id WHERE s.public=1 AND s.date>=? AND s.date<=?
                    GROUP BY u.id ORDER BY seconds DESC,u.username COLLATE NOCASE ASC LIMIT 100''',
                    (monday.isoformat(), (monday + timedelta(days=6)).isoformat()))
                return self.send(200, {'user': user, 'csrf': identity['csrf'], 'sessions': sessions, 'exams': exams,
                    'active': active, 'friends': friends, 'posts': posts, 'comments': comments,
                    'ranking': ranking, 'week_start': monday.isoformat(), **groups.state(db,uid)})
            if path == '/api/export':
                buffer = io.StringIO(newline='')
                writer = csv.writer(buffer)
                writer.writerow(['date','duration_minutes','learning_resources','learning_location','interruptions','subject'])
                for s in db.execute('SELECT * FROM sessions WHERE user_id=? ORDER BY date,id', (uid,)):
                    writer.writerow([s['date'], int(s['seconds'] // 60), s['resources'], s['location'], s['interruptions'], s['subject']])
                return self.send(200, '\ufeff' + buffer.getvalue(), 'text/csv; charset=utf-8')
        return self.send(404, {'error': 'Nicht gefunden.'})

    def do_POST(self):
        try:
            # Nur Anfragen von der eigenen Browseroberfläche akzeptieren.
            origin = self.headers.get('Origin')
            if origin and origin != getattr(self,'scheme','http') + '://' + self.headers.get('Host', ''):
                return self.send(403, {'error': 'Fremder Ursprung ist nicht erlaubt.'})
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 7500000:
                raise ValueError('Ungültige Anfragegröße.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Ein JSON-Objekt wird erwartet.')
            path = urlparse(self.path).path
            result = {}
            with connect() as db:
                if path in ('/api/register', '/api/login'):
                    # Persistentes Limit, auch über Worker-Neustarts hinweg.
                    bucket=hashlib.sha256((self.client_address[0]+path).encode()).hexdigest()
                    cutoff=time.time()-900
                    db.execute('DELETE FROM auth_attempts WHERE created<?',(cutoff,))
                    if db.execute('SELECT COUNT(*) FROM auth_attempts WHERE bucket=?',(bucket,)).fetchone()[0]>=30:
                        return self.send(429,{'error':'Zu viele Anmeldeversuche. Bitte in 15 Minuten erneut versuchen.'})
                    db.execute('INSERT INTO auth_attempts VALUES(?,?)',(bucket,time.time()))
                    db.commit()
                    username = required(data, 'username', 30)
                    password = data.get('password', '')
                    if not re.fullmatch(r'[\w.-]{3,30}', username, re.UNICODE):
                        raise ValueError('Benutzername: 3–30 Buchstaben, Ziffern, Punkte, Bindestriche oder Unterstriche.')
                    if not isinstance(password, str) or not 12 <= len(password) <= 128:
                        raise ValueError('Das Passwort muss 12 bis 128 Zeichen enthalten.')
                    if path == '/api/register':
                        salt = secrets.token_hex(16)
                        hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), PASSWORD_ROUNDS).hex()
                        try:
                            db.execute('INSERT INTO users(username,salt,password) VALUES(?,?,?)', (username,salt,hashed))
                        except sqlite3.IntegrityError:
                            raise ValueError('Dieser Benutzername ist bereits vergeben.')
                    user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
                    if not user or not hmac.compare_digest(user['password'], hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(user['salt']), PASSWORD_ROUNDS).hex()):
                        return self.send(401, {'error': 'Benutzername oder Passwort ist falsch.'})
                    token = secrets.token_urlsafe(32)
                    db.execute('DELETE FROM auth_sessions WHERE expires<=?',(time.time(),))
                    db.execute('INSERT INTO auth_sessions VALUES(?,?,?,?)',
                        (hashlib.sha256(token.encode()).hexdigest(),user['id'],secrets.token_urlsafe(24),time.time()+86400))
                    db.commit()
                    return self.send(200, {'ok':True}, cookie=f'learno={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400')
                identity = self.identity()
                if not identity:
                    return self.send(401, {'error': 'Bitte erneut anmelden.'})
                if not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), identity['csrf']):
                    return self.send(403, {'error':'Ungültige Sitzung. Bitte die Seite neu laden.'})
                uid = identity['user_id']
                if path == '/api/logout':
                    db.execute('DELETE FROM auth_sessions WHERE token_hash=?',(identity['token_hash'],))
                    db.commit()
                    return self.send(200, {'ok':True}, cookie='learno=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                if path.removeprefix('/api/') in groups.ACTIONS:
                    # Serialize group/file mutations so quota/adoption checks are atomic.
                    db.execute('BEGIN IMMEDIATE')
                    result=groups.handle(path.removeprefix('/api/'),db,uid,data,required,integer,iso_date,self.owned)
                elif path == '/api/exam':
                    result['id']=db.execute('INSERT INTO exams(user_id,title,subject,exam_date,difficulty) VALUES(?,?,?,?,?)',
                        (uid, required(data,'title'),required(data,'subject'),iso_date(data.get('exam_date')),integer(data,'difficulty',1,5))).lastrowid
                elif path == '/api/grade':
                    exam_id = integer(data,'id',1,1000000000)
                    self.owned(db,'exams',exam_id,uid)
                    db.execute('UPDATE exams SET grade=?,completed=1 WHERE id=?', (integer(data,'grade',1,5),exam_id))
                elif path == '/api/start':
                    if db.execute('SELECT 1 FROM active WHERE user_id=?',(uid,)).fetchone():
                        raise ValueError('Es läuft bereits eine Lernsession.')
                    exam_id = data.get('exam_id') or None
                    exam = self.owned(db,'exams',exam_id,uid) if exam_id else None
                    if exam and exam['completed']:
                        raise ValueError('Diese Prüfung wurde bereits abgeschlossen.')
                    subject = exam['subject'] if exam else required(data,'subject')
                    db.execute('INSERT INTO active(user_id,exam_id,subject,started,date) VALUES(?,?,?,?,?)',
                        (uid,exam_id,subject,time.time(),iso_date(data.get('date'))))
                elif path in ('/api/pause','/api/resume','/api/stop','/api/finish','/api/discard'):
                    active = db.execute('SELECT * FROM active WHERE user_id=?',(uid,)).fetchone()
                    if not active:
                        raise ValueError('Keine laufende Lernsession vorhanden.')
                    now = time.time()
                    if path == '/api/pause' and active['paused'] is None:
                        db.execute('UPDATE active SET paused=?,interruptions=interruptions+1 WHERE user_id=?',(now,uid))
                    elif path == '/api/stop' and active['paused'] is None:
                        db.execute('UPDATE active SET paused=? WHERE user_id=?',(now,uid))
                    elif path == '/api/resume' and active['paused'] is not None:
                        db.execute('UPDATE active SET paused_total=paused_total+?,paused=NULL WHERE user_id=?',(now-active['paused'],uid))
                    elif path == '/api/finish':
                        seconds = max(0.1, round((active['paused'] or now)-active['started']-active['paused_total'],1))
                        db.execute('INSERT INTO sessions(user_id,exam_id,subject,date,seconds,resources,location,interruptions) VALUES(?,?,?,?,?,?,?,?)',
                            (uid,active['exam_id'],active['subject'],active['date'],seconds,required(data,'resources',200),required(data,'location',120),active['interruptions']))
                        db.execute('DELETE FROM active WHERE user_id=?',(uid,))
                    elif path == '/api/discard':
                        db.execute('DELETE FROM active WHERE user_id=?',(uid,))
                elif path == '/api/session':
                    exam_id = data.get('exam_id') or None
                    exam = self.owned(db,'exams',exam_id,uid) if exam_id else None
                    db.execute('INSERT INTO sessions(user_id,exam_id,subject,date,seconds,resources,location,interruptions) VALUES(?,?,?,?,?,?,?,?)',
                        (uid,exam_id,exam['subject'] if exam else required(data,'subject'),iso_date(data.get('date')),
                        integer(data,'duration_minutes',1,1440)*60,required(data,'resources',200),required(data,'location'),integer(data,'interruptions',0,1000)))
                elif path == '/api/assign':
                    sid = integer(data,'id',1,1000000000)
                    session = self.owned(db,'sessions',sid,uid)
                    exam = self.owned(db,'exams',integer(data,'exam_id',1,1000000000),uid)
                    if exam['subject'].casefold() != session['subject'].casefold():
                        raise ValueError('Lernsession und Prüfung müssen zum gleichen Fach gehören.')
                    db.execute('UPDATE sessions SET exam_id=? WHERE id=?',(exam['id'],sid))
                elif path == '/api/import':
                    content = required(data,'csv',900000).lstrip('\ufeff')
                    reader = csv.DictReader(io.StringIO(content), strict=True)
                    expected = ['date','duration_minutes','learning_resources','learning_location','interruptions','subject']
                    if reader.fieldnames != expected:
                        raise ValueError('CSV-Spalten stimmen nicht mit learning_sessions.csv überein.')
                    count = 0
                    for row in reader:
                        if None in row or any(v is None or not v.strip() for v in row.values()):
                            raise ValueError(f'CSV-Zeile {reader.line_num}: unvollständige Daten.')
                        minutes, pauses = int(row['duration_minutes']), int(row['interruptions'])
                        integer({'n':minutes},'n',1,1440)
                        integer({'n':pauses},'n',0,1000)
                        db.execute('INSERT INTO sessions(user_id,subject,date,seconds,resources,location,interruptions) VALUES(?,?,?,?,?,?,?)',
                            (uid,required(row,'subject'),iso_date(row['date']),minutes*60,required(row,'learning_resources',200),required(row,'learning_location'),pauses))
                        count += 1
                        if count > 5000:
                            raise ValueError('Maximal 5000 Zeilen pro Import.')
                    if not count:
                        raise ValueError('Die CSV-Datei enthält keine Datensätze.')
                elif path == '/api/post':
                    text = moderate(data.get('text',''))
                    grade = None
                    if data.get('session_id'):
                        s = self.owned(db,'sessions',integer(data,'session_id',1,1000000000),uid)
                        subject,title,seconds = s['subject'],'Lernsession',s['seconds']
                        db.execute('UPDATE sessions SET public=1 WHERE id=?',(s['id'],))
                    else:
                        exam = self.owned(db,'exams',integer(data,'exam_id',1,1000000000),uid)
                        if not exam['completed']:
                            raise ValueError('Bitte die Prüfung zuerst mit einer Note abschließen.')
                        subject,title,grade = exam['subject'],exam['title'],exam['grade']
                        seconds = db.execute('SELECT COALESCE(SUM(seconds),0) FROM sessions WHERE exam_id=? AND user_id=?',(exam['id'],uid)).fetchone()[0]
                        db.execute('UPDATE sessions SET public=1 WHERE exam_id=? AND user_id=?',(exam['id'],uid))
                    db.execute('INSERT INTO posts(user_id,text,subject,title,seconds,grade,created) VALUES(?,?,?,?,?,?,?)',
                        (uid,text,subject,title,seconds,grade,datetime.now(timezone.utc).isoformat()))
                elif path == '/api/comment':
                    post = db.execute('SELECT * FROM posts WHERE id=?',(integer(data,'post_id',1,1000000000),)).fetchone()
                    if not post:
                        raise ValueError('Beitrag nicht gefunden.')
                    friend = db.execute('SELECT 1 FROM friendships WHERE accepted=1 AND ((sender=? AND receiver=?) OR (sender=? AND receiver=?))',
                        (uid,post['user_id'],post['user_id'],uid)).fetchone()
                    if post['user_id'] != uid and not friend:
                        raise ValueError('Kommentare sind nur bei eigenen Beiträgen und bestätigten Freunden möglich.')
                    text = moderate(required(data,'text',500))
                    db.execute('INSERT INTO comments(post_id,user_id,text,created) VALUES(?,?,?,?)',(post['id'],uid,text,datetime.now(timezone.utc).isoformat()))
                elif path == '/api/friend':
                    other = db.execute('SELECT id FROM users WHERE username=?',(required(data,'username',30),)).fetchone()
                    if not other or other['id'] == uid:
                        raise ValueError('Kein anderer Benutzer mit diesem Namen gefunden.')
                    exists = db.execute('SELECT 1 FROM friendships WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)',
                        (uid,other['id'],other['id'],uid)).fetchone()
                    if exists:
                        raise ValueError('Freundschaft oder Anfrage besteht bereits.')
                    db.execute('INSERT INTO friendships(sender,receiver) VALUES(?,?)',(uid,other['id']))
                elif path in ('/api/accept','/api/reject'):
                    sender = integer(data,'sender',1,1000000000)
                    if path == '/api/accept':
                        db.execute('UPDATE friendships SET accepted=1 WHERE sender=? AND receiver=?',(sender,uid))
                    else:
                        db.execute('DELETE FROM friendships WHERE sender=? AND receiver=? AND accepted=0',(sender,uid))
                elif path == '/api/settings':
                    reminder = required(data,'reminder',5)
                    if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',reminder):
                        raise ValueError('Ungültige Erinnerungszeit.')
                    zone = required(data,'timezone',50)
                    if zone not in ('Europe/Vienna','UTC','Europe/London','America/New_York'):
                        raise ValueError('Bitte eine angebotene Zeitzone wählen.')
                    db.execute('UPDATE users SET reminder=?,reminder_on=?,timezone=? WHERE id=?',
                        (reminder,integer(data,'reminder_on',0,1),zone,uid))
                else:
                    return self.send(404, {'error':'Unbekannte Aktion.'})
            self.send(200, {'ok':True, **result})
        except (ValueError, TypeError, KeyError, csv.Error) as error:
            self.send(400, {'error':str(error) or 'Ungültige Eingabe.'})
        except sqlite3.Error:
            self.send(500, {'error':'Datenbankfehler. Bitte erneut versuchen.'})

    def owned(self, db, table, ident, uid):
        record = db.execute(f'SELECT * FROM {table} WHERE id=? AND user_id=?',(ident,uid)).fetchone()
        if not record:
            raise ValueError('Eintrag nicht gefunden oder kein Zugriff.')
        return record


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('LEARNO_PORT','8000'))
    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'\nLearno läuft: http://127.0.0.1:{port}\nBeenden mit Strg+C.\n', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nLearno beendet.')
    finally:
        server.server_close()
