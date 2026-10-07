"""V4 activity sharing and exact V3 upgrade preservation, isolated DBs only."""
from pathlib import Path
import sqlite3
import app
import migrate
from test_app import LearnoTestCase


class ActivityTests(LearnoTestCase):
    def activity(self,c):
        sid=c.exam()['user_exam_state_id']
        status,result=c.session(sid)
        self.assertEqual(status,200)
        return result['session_id']

    def test_private_default_groups_public_and_hidden_metrics(self):
        a,b,out=self.register('activity-owner'),self.register('activity-member'),self.register('activity-outsider')
        gid=a.call('group-create',{'name':'Activity group'})[1]['id']
        b.call('group-join',{'group_id':gid});session=self.activity(a)
        private=a.call('post',{'session_id':session,'text':'Private'})[1]['post_id']
        self.assertEqual(b.state()['posts'],[])
        own=next(p for p in a.state()['posts'] if p['id']==private)
        self.assertEqual(own['audience'],'private');self.assertEqual(own['session_id'],session)
        self.assertNotIn('seconds',own)
        pid=a.call('post',{'session_id':session,'audience':'group','target_group_id':gid,'show_seconds':0})[1]['post_id']
        visible=next(p for p in b.state()['posts'] if p['id']==pid)
        for key in ('seconds','grade','session_count'):self.assertNotIn(key,visible)
        self.assertEqual(out.state()['posts'],[])
        self.assertEqual(b.call('comment',{'post_id':pid,'text':'Group reply'})[0],200)
        self.assertEqual(out.call('post',{'session_id':session,'audience':'public'})[0],400)
        self.assertEqual(a.call('post',{'session_id':session,'audience':'group','target_group_id':999999})[0],400)
        public=a.call('post',{'session_id':session,'audience':'public','show_seconds':1})[1]['post_id']
        self.assertEqual(next(p for p in out.state()['posts'] if p['id']==public)['seconds'],1800)
        self.assertEqual(out.state()['ranking'],[])
        b.call('group-leave',{'group_id':gid})
        self.assertNotIn(pid,[p['id'] for p in b.state()['posts']])
        self.assertEqual(b.call('comment',{'post_id':pid,'text':'No access'})[0],400)

    def test_independent_ranking_idempotency_and_ownership(self):
        a,b=self.register('ranking-owner'),self.register('ranking-viewer');session=self.activity(a)
        before=a.state()['sessions'][0].copy()
        pid=a.call('post',{'session_id':session,'audience':'public','show_seconds':1})[1]['post_id']
        self.assertEqual(b.state()['ranking'],[])
        self.assertEqual(b.call('session-ranking',{'session_id':session,'public':True})[0],400)
        for value in (1,'true',None):self.assertEqual(a.call('session-ranking',{'session_id':session,'public':value})[0],400)
        for _ in range(2):self.assertEqual(a.call('session-ranking',{'session_id':session,'public':True})[0],200)
        self.assertEqual(b.state()['ranking'][0]['seconds'],1800)
        a.call('post-revoke',{'post_id':pid})
        self.assertEqual(b.state()['posts'],[]);self.assertEqual(b.state()['ranking'][0]['seconds'],1800)
        pid2=a.call('post',{'session_id':session,'audience':'public'})[1]['post_id']
        a.call('session-ranking',{'session_id':session,'public':False})
        self.assertEqual(b.state()['ranking'],[])
        self.assertIn(pid2,[p['id'] for p in b.state()['posts']])
        after=a.state()['sessions'][0];self.assertEqual(before,after)

    def test_mine_filter_before_limit_and_deletion_contract(self):
        a,b=self.register('mine-owner'),self.register('mine-other');session=self.activity(a)
        own=a.call('post',{'session_id':session})[1]['post_id']
        other_session=self.activity(b)
        for _ in range(51):b.call('post',{'session_id':other_session,'audience':'public'})
        feed=a.call('feed?filter=mine')[1]
        self.assertEqual([p['id'] for p in feed['posts']],[own]);self.assertFalse(feed['has_more'])
        a.call('post-revoke',{'post_id':own})
        self.assertEqual(a.call('feed?filter=mine')[1]['posts'][0]['id'],own)
        self.assertEqual(a.state()['user_exam_states'][0]['deletion_mode'],'archived')
        unused=a.exam(title='Unused')['user_exam_state_id']
        self.assertEqual(a.personal(unused)['deletion_mode'],'deleted')

    def test_exact_v3_upgrade_legacy_publicity_and_missing_links(self):
        path=Path(self.temp.name)/'original-v3.db';migrate.migrate_database(path,target_version=3)
        db=sqlite3.connect(path);db.row_factory=sqlite3.Row
        with db:
            db.execute("INSERT INTO users(username,salt,password) VALUES('original','salt','hash')")
            db.execute("INSERT INTO sessions(user_id,subject,date,seconds,resources,location,public) VALUES(1,'Old','2026-10-06',60,'Book','Home',1)")
            db.execute("INSERT INTO posts(user_id,text,subject,title,seconds,created,audience) VALUES(1,'Legacy','Old','Lernsession',60,'old','public')")
            db.execute("INSERT INTO active(user_id,subject,started,date) VALUES(1,'Old',123,'2026-10-06')")
        before=migrate.snapshot(db);db.close()
        result=migrate.migrate_database(path);self.assertTrue(Path(result['backup']).exists())
        db=sqlite3.connect(path);db.row_factory=sqlite3.Row;migrate.verify_snapshot(db,before);migrate.check(db)
        self.assertTrue(migrate.ready(db));self.assertIsNone(db.execute('SELECT session_id FROM posts').fetchone()[0])
        self.assertEqual(db.execute('SELECT public FROM sessions').fetchone()[0],1)
        db.close();self.assertFalse(migrate.migrate_database(path)['changed'])
