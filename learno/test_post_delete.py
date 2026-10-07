"""Explicit post deletion, transactional preservation and competing comments."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
import app
import migrate
import base64
import feedback
from test_app import LearnoTestCase, Client


class PostDeletionTests(LearnoTestCase):
    def setup_discussion(self):
        a,b=self.register('delete-owner'),self.register('delete-peer')
        gid=a.call('group-create',{'name':'Discussion'})[1]['id']
        b.call('group-join',{'group_id':gid})
        sid=a.exam()['user_exam_state_id'];session=a.session(sid)[1]['session_id']
        a.call('session-ranking',{'session_id':session,'public':True})
        a.change('grade',sid,grade=2)
        p=a.call('post',{'session_id':session,'audience':'group','target_group_id':gid})[1]['post_id']
        root=b.call('comment',{'post_id':p,'text':'Root'})[1]['comment_id']
        reply=a.call('comment',{'post_id':p,'text':'Reply','parent_comment_id':root})[1]['comment_id']
        b.call('comment',{'post_id':p,'text':'Nested','parent_comment_id':reply})
        return a,b,p

    def test_delete_discussion_only_preserves_all_other_business_data(self):
        a,b,p=self.setup_discussion()
        with app.connect() as db:feedback.configure(db,'delete-owner')
        self.assertEqual(b.call('feedback',{'text':'Private feedback must stay'})[0],200)
        event=a.state()['user_exam_states'][0]['exam_event_id']
        self.assertEqual(a.call('file-upload',{'exam_event_id':event,'filename':'keep.pdf',
            'content':base64.b64encode(b'%PDF-1.4\nKeep these exact bytes').decode()})[0],200)
        other=a.call('post',{'session_id':a.state()['sessions'][0]['id'],'audience':'public'})[1]['post_id']
        a.call('comment',{'post_id':other,'text':'Keep this discussion'})
        with app.connect() as db:
            before=migrate.snapshot(db)
        self.assertEqual(a.call('post-delete',{'post_id':p})[0],200)
        with app.connect() as db:
            after=migrate.snapshot(db)
            self.assertEqual(db.execute('SELECT count(*) FROM comments WHERE post_id=?',(p,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM comments WHERE post_id=?',(other,)).fetchone()[0],1)
            migrate.check(db)
        for name in before:
            if name not in ('posts','comments','auth_sessions','auth_attempts'):
                self.assertEqual(before[name],after[name],name)
        self.assertNotIn(p,[post['id'] for post in a.state()['own_posts']])
        self.assertEqual(a.state()['sessions'][0]['public'],1)

    def test_auth_csrf_ownership_and_private_revoked_legacy_posts(self):
        a,b,p=self.setup_discussion()
        self.assertEqual(b.call('post-delete',{'post_id':p})[0],400)
        self.assertEqual(Client('anonymous').call('post-delete',{'post_id':p})[0],401)
        csrf=a.csrf;a.csrf='wrong'
        self.assertEqual(a.call('post-delete',{'post_id':p})[0],403);a.csrf=csrf
        for value in (0,-1,'invalid',999999):
            self.assertEqual(a.call('post-delete',{'post_id':value})[0],400)
        session=a.state()['sessions'][0]['id']
        private=a.call('post',{'session_id':session})[1]['post_id']
        a.call('post-revoke',{'post_id':p})
        with app.connect() as db:
            legacy=db.execute("INSERT INTO posts(user_id,text,subject,title,seconds,created) VALUES(?,?,?,?,?,?)",(a.state()['user']['id'],'Legacy','Math','Old',60,'2026-01-01')).lastrowid
        for pid in (private,p,legacy):self.assertEqual(a.call('post-delete',{'post_id':pid})[0],200)
        self.assertEqual(a.call('post-delete',{'post_id':p})[0],400)

    def test_foreign_key_failure_rolls_back_entire_deletion(self):
        a,b,p=self.setup_discussion()
        other=a.call('post',{'session_id':a.state()['sessions'][0]['id']})[1]['post_id']
        with app.connect() as db:
            root=db.execute('SELECT id FROM comments WHERE post_id=? LIMIT 1',(p,)).fetchone()[0]
            # Simulate corrupt historical cross-post reference: never remove it automatically.
            db.execute('INSERT INTO comments(post_id,user_id,text,created,parent_comment_id) VALUES(?,?,?,?,?)',(other,b.state()['user']['id'],'Unexpected','2026-01-01',root))
            before=[tuple(r) for r in db.execute('SELECT * FROM comments ORDER BY id')]
        with patch('logging.exception'):
            self.assertEqual(a.call('post-delete',{'post_id':p})[0],500)
        with app.connect() as db:
            self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM comments ORDER BY id')])
            self.assertIsNotNone(db.execute('SELECT id FROM posts WHERE id=?',(p,)).fetchone())

    def test_parallel_comment_and_delete_cannot_leave_orphans(self):
        a,b,p=self.setup_discussion();barrier=Barrier(2)
        def request(client,action,data):
            barrier.wait();return client.call(action,data)[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            deletion=pool.submit(request,a,'post-delete',{'post_id':p})
            comment=pool.submit(request,b,'comment',{'post_id':p,'text':'Concurrent reply'})
            self.assertEqual(deletion.result(),200);self.assertIn(comment.result(),(200,400))
        with app.connect() as db:
            migrate.check(db)
            self.assertEqual(db.execute('SELECT count(*) FROM comments WHERE post_id=?',(p,)).fetchone()[0],0)
