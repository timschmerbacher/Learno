"""Private feedback: author plus one explicitly configured reviewer, no feed sharing."""
from migrate import now
from insights import positive


class Forbidden(ValueError):
    pass


def status(db,uid):
    reviewer=db.execute('SELECT u.id,u.username FROM feedback_config c JOIN users u ON u.id=c.reviewer_user_id WHERE c.id=1').fetchone()
    return {'feedback_enabled':reviewer is not None,'feedback_reviewer':bool(reviewer and reviewer['id']==uid),
            'feedback_recipient':reviewer['username'] if reviewer else None}


def configure(db,username):
    reviewer=db.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()
    if not reviewer:raise ValueError('Feedbackempfänger muss ein bestehendes Learno-Konto sein.')
    current=db.execute('SELECT reviewer_user_id FROM feedback_config WHERE id=1').fetchone()
    if current and current[0]!=reviewer[0]:
        raise ValueError('Feedbackempfänger ist bereits gesetzt; keine automatische Rechteübertragung.')
    db.execute('INSERT OR IGNORE INTO feedback_config(id,reviewer_user_id) VALUES(1,?)',(reviewer[0],))


def listing(db,uid,query):
    role=status(db,uid);filters=query.get('filter',['all'])
    if len(filters)!=1 or filters[0] not in ('all','unread'):raise ValueError('Ungültiger Feedbackfilter.')
    if filters[0]=='unread' and not role['feedback_reviewer']:raise Forbidden('Nur der Feedbackempfänger darf diese Übersicht öffnen.')
    sql='SELECT f.*,u.username FROM feedback_messages f JOIN users u ON u.id=f.user_id WHERE 1=1';args=[]
    if not role['feedback_reviewer']:sql+=' AND f.user_id=?';args.append(uid)
    if filters[0]=='unread':sql+=' AND f.read_at IS NULL'
    before=positive(query,'before_id')
    if before:sql+=' AND f.id<?';args.append(before)
    items=[dict(r) for r in db.execute(sql+' ORDER BY f.id DESC LIMIT 51',args)]
    has_more=len(items)>50;items=items[:50]
    unread=db.execute('SELECT count(*) FROM feedback_messages WHERE read_at IS NULL').fetchone()[0] if role['feedback_reviewer'] else None
    return {**role,'messages':items,'unread_count':unread,'has_more':has_more,'next_before_id':items[-1]['id'] if has_more else None}


def submit(db,uid,data,required):
    if not status(db,uid)['feedback_enabled']:raise ValueError('Der private Feedbackempfänger ist noch nicht eingerichtet.')
    text=required(data,'text',2000)
    return {'feedback_id':db.execute('INSERT INTO feedback_messages(user_id,text,created) VALUES(?,?,?)',(uid,text,now())).lastrowid}


def mark_read(db,uid,data,integer):
    if not status(db,uid)['feedback_reviewer']:raise Forbidden('Nur der Feedbackempfänger darf Nachrichten als gelesen markieren.')
    ident=integer(data,'feedback_id',1,1000000000)
    if not db.execute('SELECT 1 FROM feedback_messages WHERE id=?',(ident,)).fetchone():raise ValueError('Feedback nicht gefunden.')
    db.execute('UPDATE feedback_messages SET read_at=COALESCE(read_at,?) WHERE id=?',(now(),ident))
    return {}


if __name__=='__main__':
    import argparse
    import app
    parser=argparse.ArgumentParser(description='Einen vorhandenen privaten Feedbackempfänger ausdrücklich konfigurieren.')
    parser.add_argument('--reviewer',required=True)
    parser.add_argument('--db')
    args=parser.parse_args()
    if args.db:
        from pathlib import Path
        app.DB=Path(args.db)
    app.init_db()
    with app.connect() as db:
        db.execute('BEGIN IMMEDIATE');configure(db,args.reviewer)
    print('Privater Feedbackempfänger eingerichtet:',args.reviewer)
