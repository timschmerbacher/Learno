"""Consistent SQLite backup with a unique filename; never overwrite an old backup."""
from pathlib import Path
from datetime import datetime,timezone
import json
import sqlite3
from migrate import check,snapshot,verify_snapshot


def backup_database(path):
    path=Path(path).resolve()
    source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);source.row_factory=sqlite3.Row
    try:
        check(source)
        directory=path.parent/'backups';directory.mkdir(exist_ok=True)
        target_path=directory/('learno-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.db')
        with target_path.open('xb'):pass
        target=sqlite3.connect(target_path);target.row_factory=sqlite3.Row
        try:
            source.execute('BEGIN');before=snapshot(source)
            source.backup(target);check(target)
            verify_snapshot(target,before)
        finally:target.close()
        return target_path
    finally:source.close()


if __name__=='__main__':
    import argparse,os
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=os.environ.get('LEARNO_DB',str(Path(__file__).parent/'data'/'learno.db')))
    args=parser.parse_args();print(json.dumps({'backup':str(backup_database(args.db))},ensure_ascii=False))
