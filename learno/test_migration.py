"""Migration tests use disposable copies, never the live DB."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import app
import legacy_schema
import migrate
import v2

class MigrationTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).parent/'data';root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='migration-test-',dir=root)
        self.path=Path(self.temp.name)/'old.db'
    def tearDown(self):
        if hasattr(self,'fixture_db'):self.fixture_db.close()
        self.temp.cleanup()
    def legacy(self):
        db=sqlite3.connect(self.path);self.fixture_db=db;db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
        with db:
            legacy_schema.initialize(db)
            for name in ('alice','bob'):
                db.execute('INSERT INTO users(username,salt,password) VALUES(?,?,?)',(name,'salt','hash'))
            db.execute("INSERT INTO study_groups VALUES(1,'Class','',1)")
            db.executemany('INSERT INTO members VALUES(1,?)',[(1,),(2,)])
            db.execute("INSERT INTO group_exams VALUES(1,1,1,'Shared','Math','2027-01-01','original')")
            db.execute("INSERT INTO exams VALUES(1,1,'Private','Java','2027-02-01',4,2,1,NULL)")
            db.execute("INSERT INTO exams VALUES(2,1,'Shared old','Math','2027-01-02',3,NULL,0,1)")
            db.execute("INSERT INTO exams VALUES(3,2,'Shared','Math','2027-01-01',5,1,1,1)")
            db.execute("INSERT INTO sessions VALUES(1,1,1,'Java original','2026-10-01',120.5,'Book','Home',2,1)")
            db.execute("INSERT INTO sessions VALUES(2,2,3,'Math','2026-10-02',3600,'Book','Library',0,0)")
            db.execute("INSERT INTO sessions VALUES(3,1,NULL,'Free','2026-10-03',1800,'Book','Home',0,0)")
            db.execute("INSERT INTO active VALUES(1,2,'Math original',1000,1100,10,2,'2026-10-03')")
            db.execute("INSERT INTO posts VALUES(1,1,'Shared intentionally','Java','Private',120.5,2,'original')")
            db.execute("INSERT INTO comments VALUES(1,1,2,'Comment','original')")
            for fid,exam,shared in ((1,1,None),(2,None,1),(3,2,None)):
                db.execute('INSERT INTO exam_files VALUES(?,?,?,?,?,?,?,?,?)',
                  (fid,exam,shared,1,'notes.pdf','application/pdf',9,b'%PDF-test','original'))
            db.execute("INSERT INTO auth_sessions VALUES('token',1,'csrf',9999999999)")
        return db
    def test_full_legacy_preservation_unique_events_and_private_files(self):
        db=self.legacy();before=migrate.snapshot(db);db.close()
        result=migrate.migrate_database(self.path);self.assertTrue(result['changed']);self.assertTrue(Path(result['backup']).exists())
        db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row
        migrate.verify_snapshot(db,before)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM exam_events').fetchone()[0],2)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM user_exam_states').fetchone()[0],3)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM exam_grade_history').fetchone()[0],2)
        self.assertEqual(db.execute('SELECT changed_at FROM exam_grade_history LIMIT 1').fetchone()[0],None)
        self.assertEqual(db.execute('SELECT user_exam_state_id FROM sessions WHERE id=3').fetchone()[0],None)
        self.assertEqual(db.execute('SELECT started,paused,paused_total FROM active').fetchone()[:],(1000,1100,10))
        fid=db.execute('SELECT id FROM exam_attachments WHERE legacy_file_id=3').fetchone()[0]
        self.assertEqual(v2.get_file(db,fid,1)['content'],b'%PDF-test')
        with self.assertRaises(ValueError):v2.get_file(db,fid,2)
        self.assertEqual(len(v2.posts_for(db,2)[0]),1);self.assertEqual(len(v2.posts_for(db,2)[1]),1)
        self.assertEqual(db.execute('SELECT SUM(seconds) FROM sessions').fetchone()[0],5520.5)
        with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM exams WHERE id=1')
        db.close()
        self.assertFalse(migrate.migrate_database(self.path)['changed'])
    def test_current_database_copy_preserved(self):
        source_path=Path(__file__).parent/'data'/'learno.db'
        if not source_path.is_file():self.skipTest('Quellpaket ohne Nutzerdaten; Online-Bestand wird separat mit preflight_update geprüft.')
        source=sqlite3.connect(source_path.resolve().as_uri()+'?mode=ro',uri=True);source.row_factory=sqlite3.Row
        before=migrate.snapshot(source);dest=sqlite3.connect(self.path);source.backup(dest);dest.close();source.close()
        migrate.migrate_database(self.path)
        db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row;migrate.verify_snapshot(db,before)
        expected=len(before['user_exam_states'][1]) if 'user_exam_states' in before else len(before['exams'][1])
        self.assertEqual(db.execute('SELECT COUNT(*) FROM user_exam_states').fetchone()[0],expected)
        db.close()
    def test_additive_transaction_rolls_back_on_failure(self):
        db=self.legacy();before=migrate.snapshot(db)
        with self.assertRaisesRegex(ValueError,'injected'):
            with db:
                db.execute('BEGIN IMMEDIATE')
                with patch.object(migrate,'verify_snapshot',side_effect=ValueError('injected')):
                    migrate.migrate_connection(db)
        self.assertFalse(migrate.ready(db));migrate.verify_snapshot(db,before)
        self.assertNotIn('user_exam_state_id',[r[1] for r in db.execute('PRAGMA table_info(sessions)')]);db.close()
    def test_startup_never_migrates(self):
        db=self.legacy();db.close();old=app.DB;app.DB=self.path
        before=self.path.read_bytes()
        try:
            with self.assertRaises(RuntimeError):app.init_db()
            self.assertEqual(self.path.read_bytes(),before)
        finally:app.DB=old
    def test_backup_checked_and_never_overwritten(self):
        db=self.legacy();db.close();result=migrate.migrate_database(self.path)
        backup=Path(result['backup']);before=backup.read_bytes()
        self.assertFalse(migrate.migrate_database(self.path)['changed'])
        self.assertEqual(backup.read_bytes(),before)
    def test_invalid_legacy_grade_aborts_without_data_changes(self):
        db=self.legacy()
        with db:db.execute('UPDATE exams SET grade=6 WHERE id=1')
        before=migrate.snapshot(db);db.close()
        with self.assertRaises(sqlite3.IntegrityError):migrate.migrate_database(self.path)
        db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row;migrate.verify_snapshot(db,before)
        self.assertFalse(migrate.ready(db));db.close()

if __name__=='__main__':unittest.main()
