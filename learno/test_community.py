from datetime import date
from pathlib import Path
import sqlite3
from unittest.mock import patch
import app
import insights
import migrate
from test_app import LearnoTestCase

class CommunityTests(LearnoTestCase):
    def setup_group(self):
        a=self.register('author');b=self.register('reader');out=self.register('outsider')
        gid=a.call('group-create',{'name':'Class'})[1]['id'];b.call('group-join',{'group_id':gid})
        sid=a.exam()['user_exam_state_id'];a.change('grade',sid,grade=2)
        payload={'user_exam_state_id':sid,'audience':'group','target_group_id':gid,'show_grade':0,'show_seconds':0,'show_count':1}
        pid=a.call('post',payload)[1]['post_id']
        return a,b,out,gid,pid,payload
    def test_filter_before_pagination_and_masks(self):
        a,b,out,gid,pid,payload=self.setup_group()
        uid=a.state()['user']['id']
        with app.connect() as db:
            for i in range(210):
                db.execute("INSERT INTO posts(user_id,text,subject,title,seconds,created,audience) VALUES(?,'Public','Math','Session',60,'2026-10-06','public')",(uid,))
        status,result=b.call('feed?filter=groups')
        self.assertEqual(status,200);self.assertEqual([p['id'] for p in result['posts']],[pid])
        self.assertNotIn('grade',result['posts'][0]);self.assertNotIn('seconds',result['posts'][0])
        self.assertEqual(len(b.call('feed?filter=public')[1]['posts']),50)
        first=b.call('feed?filter=public')[1];second=b.call('feed?filter=public&before_id='+str(first['next_before_id']))[1]
        self.assertTrue(first['has_more']);self.assertFalse({p['id'] for p in first['posts']}&{p['id'] for p in second['posts']})
        self.assertEqual(out.call('feed?filter=groups&group_id='+str(gid))[0],400)
        self.assertEqual(b.call('feed?filter=unknown')[0],400)
        self.assertEqual(b.call('feed?before_id=-1')[0],400)
        self.assertEqual(b.call('feed?filter=friends')[1]['posts'],[])
        b.call('friend',{'username':'author'});a.call('accept',{'sender':b.state()['user']['id']})
        self.assertEqual(len(b.call('feed?filter=friends')[1]['posts']),50)
    def test_group_replies_same_post_and_visibility(self):
        a,b,out,gid,pid,payload=self.setup_group()
        root=b.call('comment',{'post_id':pid,'text':'Question'})[1]['comment_id']
        child=a.call('comment',{'post_id':pid,'text':'Answer','parent_comment_id':root})[1]['comment_id']
        reply=b.call('comment',{'post_id':pid,'text':'Thanks','parent_comment_id':child})
        self.assertEqual(reply[0],200)
        other=a.call('post',payload)[1]['post_id']
        self.assertEqual(b.call('comment',{'post_id':other,'text':'Wrong','parent_comment_id':root})[0],400)
        self.assertEqual(out.call('comment',{'post_id':pid,'text':'No','parent_comment_id':root})[0],400)
        self.assertEqual(b.call('comment',{'post_id':pid,'text':'x'*501,'parent_comment_id':root})[0],400)
        self.assertEqual(b.call('comment',{'post_id':pid,'text':'Scheisse','parent_comment_id':root})[0],400)
        comments=b.call('feed?filter=groups')[1]['comments']
        self.assertEqual([c['parent_comment_id'] for c in comments],[None,root,child])
        b.call('group-leave',{'group_id':gid})
        self.assertEqual(b.call('comment',{'post_id':pid,'text':'No','parent_comment_id':child})[0],400)
        self.assertEqual(b.call('feed?filter=groups')[1]['comments'],[])
        self.assertEqual(len(a.call('feed')[1]['comments']),3)
    def test_public_friendship_still_required_and_revocation(self):
        a,b,out,gid,pid,payload=self.setup_group()
        a.call('post-revoke',{'post_id':pid})
        self.assertEqual(b.call('comment',{'post_id':pid,'text':'No'})[0],400)
        self.assertEqual(b.call('feed?filter=groups')[1]['posts'],[])
        self.assertEqual(a.call('feed')[1]['posts'][0]['revoked_at'] is not None,True)
    def test_private_weekly_goal_validation_and_statistics(self):
        a=self.register('goals');b=self.register('other');uid=a.state()['user']['id']
        self.assertEqual(a.call('statistics')[1]['weekly_goal_minutes'],None)
        for goal in (True,0,16,10081,15.0):self.assertEqual(a.call('weekly-goal',{'weekly_goal_minutes':goal})[0],400)
        self.assertEqual(a.call('weekly-goal',{'weekly_goal_minutes':120})[0],200)
        with app.connect() as db:
            for d,secs in [('2026-10-05',7200),('2026-10-06',3600),('2026-10-07',6000),('2026-09-28',1800),('2026-09-29',1800),('2026-09-30',5000)]:
                db.execute('INSERT INTO sessions(user_id,subject,date,seconds,resources,location) VALUES(?,?,?,?,?,?)',(uid,'Math',d,secs,'Book','Home'))
            db.execute("INSERT INTO active(user_id,subject,started,date) VALUES(?,'Math',0,'2026-10-06')",(uid,))
            stats=insights.statistics(db,uid,date(2026,10,6))
        self.assertEqual(stats['current_seconds'],10800);self.assertEqual(stats['previous_comparable_seconds'],3600)
        self.assertEqual(stats['difference_seconds'],7200);self.assertEqual(stats['goal_percent'],100)
        self.assertEqual(stats['remaining_seconds'],0);self.assertEqual(len(stats['weeks']),6)
        self.assertIsNone(b.call('statistics')[1]['weekly_goal_minutes'])
        self.assertNotIn('weekly_goal_minutes',b.state()['user'])
        a.call('weekly-goal',{'weekly_goal_minutes':None});self.assertIsNone(a.call('statistics')[1]['goal_percent'])
    def test_notice_count_pagination_and_bulk_read_preserve_rows(self):
        a=self.register('notices');b=self.register('other');uid=a.state()['user']['id']
        with app.connect() as db:
            for i in range(125):db.execute('INSERT INTO notices(user_id,text,created) VALUES(?,?,?)',(uid,'Change '+str(i),'2026-10-06'))
        self.assertEqual(a.state()['notice_count'],125)
        page=a.call('notices')[1];self.assertEqual(len(page['notices']),50);self.assertTrue(page['has_more'])
        self.assertEqual(len(a.call('notices?before_id='+str(page['next_before_id']))[1]['notices']),50)
        self.assertEqual(b.call('notices')[1]['notice_count'],0)
        a.call('notices-read-all',{});self.assertEqual(a.state()['notice_count'],0)
        with app.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM notices WHERE user_id=?',(uid,)).fetchone()[0],125)

class UpgradeTests(LearnoTestCase):
    def test_v2_upgrade_exact_preservation_and_idempotency(self):
        path=Path(self.temp.name)/'v2.db';migrate.migrate_database(path,target_version=2)
        db=sqlite3.connect(path);db.row_factory=sqlite3.Row
        with db:
            db.execute("INSERT INTO users(username,salt,password) VALUES('original','salt','hash')")
            db.execute("INSERT INTO posts(user_id,text,subject,title,seconds,created) VALUES(1,'Old','Math','Old',60,'original')")
            db.execute("INSERT INTO comments(post_id,user_id,text,created) VALUES(1,1,'Root','original')")
            db.execute("INSERT INTO active(user_id,subject,started,date) VALUES(1,'Math',123,'2026-10-06')")
        before=migrate.snapshot(db);db.close();result=migrate.migrate_database(path)
        self.assertTrue(Path(result['backup']).exists())
        db=sqlite3.connect(path);db.row_factory=sqlite3.Row;migrate.verify_snapshot(db,before)
        self.assertEqual(db.execute('SELECT version FROM schema_migrations ORDER BY version').fetchall()[0][0],2)
        self.assertIsNone(db.execute('SELECT parent_comment_id FROM comments').fetchone()[0]);db.close()
        self.assertFalse(migrate.migrate_database(path)['changed'])
    def test_v3_failure_rolls_back_and_startup_is_read_only(self):
        path=Path(self.temp.name)/'v2.db';migrate.migrate_database(path,target_version=2)
        db=sqlite3.connect(path);db.row_factory=sqlite3.Row;before=migrate.snapshot(db)
        with self.assertRaisesRegex(ValueError,'failure'):
            with db:
                db.execute('BEGIN IMMEDIATE')
                with patch.object(migrate,'verify_snapshot',side_effect=ValueError('failure')):migrate.migrate_connection(db)
        migrate.verify_snapshot(db,before)
        self.assertNotIn('parent_comment_id',[r[1] for r in db.execute('PRAGMA table_info(comments)')]);db.close()
        original=app.DB;app.DB=path
        try:
            data=path.read_bytes()
            with self.assertRaises(RuntimeError):app.init_db()
            self.assertEqual(path.read_bytes(),data)
        finally:app.DB=original
