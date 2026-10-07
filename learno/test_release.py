"""Safe release packaging, unique backup and migration rehearsal on copies."""
import hashlib,json,sqlite3,zipfile
from pathlib import Path
import app,migrate
from backup import backup_database
from preflight_update import rehearse
from prepare_release import build,FILES
from install_update import install
from test_app import LearnoTestCase


class ReleaseTests(LearnoTestCase):
    def test_unique_checked_backup_and_readonly_rehearsal(self):
        c=self.register('backup-owner');sid=c.exam()['user_exam_state_id'];c.session(sid)
        before=app.DB.read_bytes();first=backup_database(app.DB);first_bytes=first.read_bytes()
        second=backup_database(app.DB);self.assertNotEqual(first,second);self.assertEqual(first.read_bytes(),first_bytes)
        result=rehearse(app.DB);self.assertTrue(result['ok']);self.assertEqual(app.DB.read_bytes(),before)
        self.assertEqual(result['original_records']['sessions'],1)
        original=sqlite3.connect(app.DB);original.row_factory=sqlite3.Row
        copy=sqlite3.connect(first);copy.row_factory=sqlite3.Row
        migrate.verify_snapshot(copy,migrate.snapshot(original));copy.close();original.close()

    def test_release_contains_only_allowlisted_sources_and_valid_hashes(self):
        package=build(Path(self.temp.name)/'release')
        with zipfile.ZipFile(package) as z:
            self.assertEqual(set(z.namelist()),{'learno/'+f for f in FILES}|{'learno/update-manifest.json'})
            manifest=json.loads(z.read('learno/update-manifest.json'))
            self.assertEqual(manifest['schema_version'],5)
            for f,digest in manifest['files'].items():self.assertEqual(hashlib.sha256(z.read('learno/'+f)).hexdigest(),digest)
            self.assertFalse(any('/data/' in f or f.endswith(('.db','.log','.env')) for f in z.namelist()))

    def test_installer_preserves_real_data_csv_and_custom_settings(self):
        root=Path(self.temp.name);target=root/'existing';target.mkdir()
        (target/'app.py').write_text('old code');(target/'wsgi.py').write_text('old WSGI')
        (target/'learning_sessions.csv').write_text('USER CSV MUST STAY')
        (target/'blocked_words.json').write_text('{"words":["custom"]}')
        path=target/'data'/'online.db';migrate.migrate_database(path,target_version=4)
        db=sqlite3.connect(path);db.row_factory=sqlite3.Row
        with db:
            db.execute("INSERT INTO users(username,salt,password) VALUES('Tim','salt','hash')")
            db.execute("INSERT INTO sessions(user_id,subject,date,seconds,resources,location) VALUES(1,'Original','2026-10-06',123,'Book','Home')")
        before=migrate.snapshot(db);db.close()
        stage=root/'stage';package=build(root/'package')
        with zipfile.ZipFile(package) as z:z.extractall(stage)
        source=stage/'learno'
        with self.assertRaises(ValueError):install(source,target,path,'Tim')
        result=install(source,target,path,'Tim',True);self.assertTrue(result['ok'])
        self.assertEqual((target/'learning_sessions.csv').read_text(),'USER CSV MUST STAY')
        self.assertEqual((target/'blocked_words.json').read_text(),'{"words":["custom"]}')
        self.assertEqual((Path(result['code_backup'])/'app.py').read_text(),'old code')
        db=sqlite3.connect(path);db.row_factory=sqlite3.Row;migrate.verify_snapshot(db,before)
        self.assertEqual(db.execute('SELECT reviewer_user_id FROM feedback_config').fetchone()[0],1);db.close()

    def test_tampered_release_and_missing_reviewer_abort_before_migration(self):
        root=Path(self.temp.name);target=root/'existing';target.mkdir();(target/'app.py').write_text('old')
        path=target/'online.db';migrate.migrate_database(path,target_version=4);before=path.read_bytes()
        package=build(root/'package');stage=root/'stage'
        with zipfile.ZipFile(package) as z:z.extractall(stage)
        with self.assertRaises(ValueError):install(stage/'learno',target,path,'missing',True)
        (stage/'learno'/'app.py').write_text('tampered')
        with self.assertRaises(ValueError):install(stage/'learno',target,path,'Tim',True)
        self.assertEqual(path.read_bytes(),before);self.assertEqual((target/'app.py').read_text(),'old')
