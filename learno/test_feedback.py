"""Feedback is private to its author and one explicitly configured account."""
from pathlib import Path
import sqlite3
import app,feedback,migrate
from test_app import LearnoTestCase


class FeedbackTests(LearnoTestCase):
    def setup_people(self):
        owner,author,other=self.register('Tim'),self.register('feedback-author'),self.register('feedback-other')
        with app.connect() as db:feedback.configure(db,'Tim')
        return owner,author,other

    def test_default_disabled_and_explicit_reviewer(self):
        c=self.register('first-account')
        self.assertFalse(c.state()['feedback_enabled']);self.assertFalse(c.state()['feedback_reviewer'])
        self.assertEqual(c.call('feedback',{'text':'Not configured'})[0],400)
        with app.connect() as db:
            with self.assertRaises(ValueError):feedback.configure(db,'missing')
            feedback.configure(db,'first-account');feedback.configure(db,'first-account')
        self.assertTrue(c.state()['feedback_reviewer'])

    def test_author_reviewer_and_outsider_privacy(self):
        owner,a,b=self.setup_people()
        ident=a.call('feedback',{'text':'Private bug report <script>alert(1)</script>'})[1]['feedback_id']
        self.assertEqual(a.call('feedback')[1]['messages'][0]['id'],ident)
        self.assertEqual(owner.call('feedback')[1]['messages'][0]['username'],'feedback-author')
        self.assertEqual(b.call('feedback')[1]['messages'],[])
        for c in (a,b,owner):
            s=c.state();self.assertNotIn('messages',s);self.assertEqual(s['posts'],[]);self.assertEqual(s['notices'],[])
        self.assertEqual(a.call('feedback?filter=unread')[0],403)
        self.assertEqual(b.call('feedback-read',{'feedback_id':ident})[0],403)
        self.assertEqual(a.call('feedback-read',{'feedback_id':ident})[0],403)
        self.assertEqual(owner.call('feedback-read',{'feedback_id':ident})[0],200)
        stamp=a.call('feedback')[1]['messages'][0]['read_at']
        owner.call('feedback-read',{'feedback_id':ident})
        self.assertEqual(a.call('feedback')[1]['messages'][0]['read_at'],stamp)
        self.assertEqual(owner.call('feedback?filter=unread')[1]['messages'],[])
        self.assertEqual(owner.call('feedback')[1]['unread_count'],0)

    def test_validation_csrf_and_content_retention(self):
        owner,a,b=self.setup_people()
        for text in ('',' ','x'*2001,None,12):self.assertEqual(a.call('feedback',{'text':text})[0],400)
        a.csrf='wrong';self.assertEqual(a.call('feedback',{'text':'No CSRF'})[0],403);a.state()
        self.assertEqual(a.call('feedback',{'text':'x'*2000})[0],200)
        with app.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM feedback_messages')
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE feedback_messages SET text='overwrite'")
            with self.assertRaises(ValueError):feedback.configure(db,'feedback-other')
        self.assertEqual(len(owner.call('feedback')[1]['messages']),1)

    def test_pagination_unread_count_and_no_forged_author(self):
        owner,a,b=self.setup_people()
        for n in range(53):a.call('feedback',{'text':'Report '+str(n),'user_id':b.state()['user']['id']})
        page=owner.call('feedback')[1];self.assertEqual(len(page['messages']),50);self.assertEqual(page['unread_count'],53)
        next_page=owner.call('feedback?before_id='+str(page['next_before_id']))[1]
        self.assertEqual(len(next_page['messages']),3)
        self.assertTrue(all(m['username']=='feedback-author' for m in page['messages']))
        self.assertEqual(b.call('feedback')[1]['messages'],[])
        self.assertEqual(a.call('feedback?filter=all&filter=unread')[0],400)

    def test_v4_upgrade_preserves_all_original_columns(self):
        path=Path(self.temp.name)/'original-v4.db';migrate.migrate_database(path,target_version=4)
        db=sqlite3.connect(path);db.row_factory=sqlite3.Row
        with db:db.execute("INSERT INTO users(username,salt,password) VALUES('Tim','salt','hash')")
        before=migrate.snapshot(db);db.close();migrate.migrate_database(path)
        db=sqlite3.connect(path);db.row_factory=sqlite3.Row
        migrate.verify_snapshot(db,before);migrate.check(db);self.assertTrue(migrate.ready(db))
        self.assertEqual(db.execute('SELECT count(*) FROM feedback_config').fetchone()[0],0)
        db.close();self.assertFalse(migrate.migrate_database(path)['changed'])
