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
from urllib.parse import urlparse, quote, parse_qs
from contextlib import contextmanager
import v2
import insights
import feedback
from migrate import ready

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('LEARNO_DB', str(ROOT / 'data' / 'learno.db')))
PASSWORD_ROUNDS = 260000


@contextmanager
def connect():
    db = sqlite3.connect(DB.resolve().as_uri() + '?mode=rw', uri=True, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    """Read-only readiness check. Migration is deliberately never run at startup."""
    if not DB.exists():
        raise RuntimeError('Datenbank fehlt. Zuerst python migrate.py --workers-stopped ausführen.')
    with connect() as db:
        if not ready(db):
            raise RuntimeError('Migration erforderlich. App stoppen und python migrate.py --workers-stopped ausführen.')


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
        if not self.path.startswith(('/api/state','/api/v2/state')):
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
        static = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/v2.js': ('v2.js', 'text/javascript'), '/ui.js': ('ui.js', 'text/javascript')}
        if path in static:
            filename, kind = static[path]
            return self.send(200, (ROOT / 'static' / filename).read_bytes(), kind + '; charset=utf-8')
        identity = self.identity()
        if not identity:
            return self.send(401, {'error': 'Bitte anmelden.'})
        uid = identity['user_id']
        with connect() as db:
            if path in ('/api/v2/feed','/api/v2/notices','/api/v2/statistics','/api/v2/feedback'):
                db.execute('BEGIN')
                query=parse_qs(urlparse(self.path).query,keep_blank_values=True)
                try:
                    result=feedback.listing(db,uid,query) if path.endswith('/feedback') else insights.feed(db,uid,query) if path.endswith('/feed') else insights.notices(db,uid,query) if path.endswith('/notices') else insights.statistics(db,uid)
                    return self.send(200,result)
                except feedback.Forbidden as error:
                    return self.send(403,{'error':str(error)})
                except ValueError as error:
                    return self.send(400,{'error':str(error)})
            if path.startswith('/api/v2/files/') or path.startswith('/api/files/'):
                try:
                    fid=int(path.rsplit('/',1)[1])
                    if not 1<=fid<=9223372036854775807: raise ValueError('Ungültige Datei-ID.')
                    if not path.startswith('/api/v2/'):
                        old=db.execute('SELECT id FROM exam_attachments WHERE legacy_file_id=?',(fid,)).fetchone()
                        if not old: raise ValueError('Datei nicht gefunden.')
                        fid=old['id']
                    file=v2.get_file(db,fid,uid)
                    return self.send(200,file['content'],file['mime'],attachment=file['filename'])
                except (ValueError,TypeError):
                    return self.send(404,{'error':'Datei nicht gefunden oder kein Zugriff.'})
            if path in ('/api/v2/state','/api/state'):
                db.execute('BEGIN')  # Consistent snapshot across events, progress, feed and membership.
                user = dict(db.execute('SELECT id,username,reminder,reminder_on,timezone FROM users WHERE id=?', (uid,)).fetchone())
                friends = rows(db, 'SELECT f.*, a.username AS sender_name,b.username AS receiver_name\n                    FROM friendships f JOIN users a ON a.id=f.sender JOIN users b ON b.id=f.receiver\n                    WHERE sender=? OR receiver=?', (uid, uid))
                monday = date.today() - timedelta(days=date.today().weekday())
                ranking = rows(db, 'SELECT u.id,u.username,SUM(s.seconds) AS seconds FROM sessions s\n                    JOIN users u ON u.id=s.user_id WHERE s.public=1 AND s.date>=? AND s.date<=?\n                    GROUP BY u.id ORDER BY seconds DESC,u.username COLLATE NOCASE ASC LIMIT 100',
                    (monday.isoformat(), (monday + timedelta(days=6)).isoformat()))
                return self.send(200, {'user':user,'csrf':identity['csrf'],'friends':friends,
                    'ranking':ranking,'week_start':monday.isoformat(),**v2.state(db,uid,priority),**feedback.status(db,uid)})
            if path in ('/api/export','/api/v2/export'):
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
            versioned=path.startswith('/api/v2/')
            if versioned: path='/api/'+path.removeprefix('/api/v2/')
            result = {}
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
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
                action=path.removeprefix('/api/')
                if action in ('feedback','feedback-read'):
                    if not versioned:return self.send(409,{'error':'Alte Schreibschnittstelle gesperrt.'})
                    result=feedback.submit(db,uid,data,required) if action=='feedback' else feedback.mark_read(db,uid,data,integer)
                elif action in v2.ACTIONS:
                    if not versioned:
                        return self.send(409,{'error':'Bitte die V2-Oberfläche neu laden. Alte Schreibschnittstelle gesperrt.'})
                    result=v2.handle(action,db,uid,data,required,integer,iso_date,moderate)
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
        except feedback.Forbidden as error:
            self.send(403,{'error':str(error)})
        except v2.Conflict as error:
            self.send(409, {'error':str(error)})
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
