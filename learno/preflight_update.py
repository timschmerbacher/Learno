"""Rehearse migration on a consistent copy; original database stays read-only."""
from pathlib import Path
import json,sqlite3,tempfile
import migrate


def rehearse(path):
    path=Path(path).resolve();source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);source.row_factory=sqlite3.Row
    root=Path(__file__).parent/'data';root.mkdir(exist_ok=True)
    try:
        migrate.check(source)
        with tempfile.TemporaryDirectory(prefix='preflight-',dir=root) as scratch:
            copied=Path(scratch)/'copy.db';target=sqlite3.connect(copied);source.backup(target);target.close()
            original=sqlite3.connect(copied);original.row_factory=sqlite3.Row
            before=migrate.snapshot(original);original.close()
            migrate.migrate_database(copied)
            db=sqlite3.connect(copied);db.row_factory=sqlite3.Row
            try:
                migrate.verify_snapshot(db,before);migrate.check(db)
                return {'ok':True,'target_version':migrate.VERSION,'tables_checked':len(before),
                        'original_records':{t:len(values[1]) for t,values in before.items()}}
            finally:db.close()
    finally:source.close()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--db',required=True)
    print(json.dumps(rehearse(parser.parse_args().db),ensure_ascii=False))
