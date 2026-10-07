"""Install a verified source-only release while workers are stopped; retain all data."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,shutil,sqlite3
import migrate,feedback
from prepare_release import FILES


def install(source,target,db_path,reviewer,workers_stopped=False):
    if not workers_stopped:raise ValueError('Vor dem Update alle Worker stoppen.')
    source=Path(source).resolve();target=Path(target).resolve();db_path=Path(db_path).resolve()
    if source==target or not (target/'app.py').is_file() or not db_path.is_file():
        raise ValueError('Eine bestehende Installation und deren echte Datenbank sind erforderlich.')
    if source in db_path.parents:raise ValueError('Die Online-Datenbank darf nicht im neuen Paket liegen.')
    manifest=json.loads((source/'update-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version')!=migrate.VERSION or set(manifest.get('files',{}))!=set(FILES):
        raise ValueError('Updatepaket oder Versionsmanifest ungültig.')
    contents={}
    for name,digest in manifest['files'].items():
        file=source/name;dest=target/name
        if file.is_symlink() or source not in file.resolve().parents or target not in dest.resolve().parents:
            raise ValueError('Unsicherer Updatepfad.')
        data=file.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Quelldatei verändert: '+name)
        contents[name]=data
    original=sqlite3.connect(db_path.as_uri()+'?mode=ro',uri=True);original.row_factory=sqlite3.Row
    try:
        migrate.check(original);before=migrate.snapshot(original)
        owner=original.execute('SELECT id FROM users WHERE username=?',(reviewer,)).fetchone()
        if not owner:raise ValueError('Der gewünschte Feedbackempfänger existiert in der Online-Datenbank nicht.')
        if 'feedback_config' in before:
            current=original.execute('SELECT reviewer_user_id FROM feedback_config WHERE id=1').fetchone()
            if current and current[0]!=owner[0]:raise ValueError('Kein automatischer Wechsel des privaten Feedbackempfängers.')
    finally:original.close()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    code_backup=target.parent/'learno-code-backups'/stamp;code_backup.mkdir(parents=True,exist_ok=False)
    for name in FILES:
        old=target/name
        if old.is_file():
            copy=code_backup/name;copy.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,copy)
    migration=migrate.migrate_database(db_path)
    db=sqlite3.connect(db_path);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
    try:
        migrate.verify_snapshot(db,before);migrate.check(db)
        with db:feedback.configure(db,reviewer)
    finally:db.close()
    preserved=[]
    for name,data in contents.items():
        dest=target/name
        # Existing CSVs may contain user data; keep local moderation settings too.
        if name in ('learning_sessions.csv','blocked_words.json') and dest.exists():
            preserved.append(name);continue
        dest.parent.mkdir(parents=True,exist_ok=True)
        temporary=dest.with_name(dest.name+'.update-'+stamp)
        with temporary.open('xb') as output:output.write(data)
        os.replace(temporary,dest)
    return {'ok':True,'schema_version':migrate.VERSION,'database_backup':migration['backup'],
            'code_backup':str(code_backup),'preserved_files':preserved,'feedback_reviewer':reviewer}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',required=True);parser.add_argument('--db',required=True)
    parser.add_argument('--reviewer',required=True);parser.add_argument('--workers-stopped',action='store_true')
    args=parser.parse_args()
    print(json.dumps(install(Path(__file__).parent,args.target,args.db,args.reviewer,args.workers_stopped),ensure_ascii=False))
