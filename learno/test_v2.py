import base64
from datetime import date
import itertools
import sqlite3
import threading
import unittest
from unittest.mock import patch
import app
import v2
from test_app import LearnoTestCase

class V2Tests(LearnoTestCase):
    def hierarchy(self):
        owner=self.register('owner');a=self.register('student');b=self.register('sibling');out=self.register('outsider')
        main=owner.call('group-create',{'name':'Main'})[1]['id']
        child=owner.call('group-create',{'name':'Child','parent_id':main})[1]['id']
        other=owner.call('group-create',{'name':'Other','parent_id':main})[1]['id']
        for c,gids in ((a,[main,child]),(b,[main,other])):
            for gid in gids:self.assertEqual(c.call('group-join',{'group_id':gid})[0],200)
        return owner,a,b,out,main,child,other
    def test_hierarchy_membership_and_shared_single_event(self):
        o,a,b,out,main,child,other=self.hierarchy()
        self.assertEqual(out.call('group-join',{'group_id':child})[0],400)
        self.assertEqual(a.call('group-create',{'name':'No','parent_id':main})[0],400)
        self.assertEqual(o.call('group-create',{'name':'Too deep','parent_id':child})[0],400)
        eid=a.exam(group_id=child)['exam_event_id']
        self.assertNotIn(eid,[e['id'] for e in b.state()['exam_events']])
        sid=a.call('group-adopt',{'exam_event_id':eid,'difficulty':3})[1]['user_exam_state_id']
        osid=o.call('group-adopt',{'exam_event_id':eid,'difficulty':5})[1]['user_exam_state_id']
        self.assertEqual(a.call('group-adopt',{'exam_event_id':eid,'difficulty':3})[0],400)
        self.assertEqual(a.change('grade',sid,grade=2)[0],200)
        self.assertTrue(o.personal(osid)['startable']);self.assertIsNone(o.personal(osid)['grade'])
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM exam_events').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user_exam_states').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM exams').fetchone()[0],0)
        self.assertEqual(a.call('group-leave',{'group_id':main})[0],400)
    def test_edit_never_changes_session_or_timer_and_archive_restores(self):
        c=self.register('student');r=c.exam('Java');sid=r['user_exam_state_id'];eid=r['exam_event_id']
        c.session(sid);c.call('start',{'user_exam_state_id':sid,'date':date.today().isoformat()})
        before=c.state()['sessions'][0].copy()
        self.assertEqual(c.change('exam-edit',sid,title='New',subject='Python',exam_date='2027-01-01',difficulty=2)[0],200)
        self.assertEqual(c.state()['sessions'][0],before);self.assertEqual(c.state()['active']['subject'],'Java')
        self.assertEqual(c.change('exam-delete',sid)[1]['mode'],'archived')
        self.assertEqual(c.state()['sessions'][0],before);self.assertEqual(c.state()['active']['user_exam_state_id'],sid)
        c.call('stop',{});self.assertEqual(c.call('finish',{'resources':'Book','location':'Home'})[0],200)
        self.assertEqual(c.state()['sessions'][0]['subject'],'Java')
        self.assertEqual(c.change('exam-restore',sid)[0],200);self.assertTrue(c.personal(sid)['startable'])
        unused=c.exam()['user_exam_state_id'];self.assertEqual(c.change('exam-delete',unused)[1]['mode'],'deleted')
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],2)
            with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE sessions SET subject='Changed'")
    def test_files_scope_archive_and_group_exit(self):
        o,a,b,out,main,child,other=self.hierarchy();eid=a.exam(group_id=child)['exam_event_id']
        content=b'%PDF-1.4\nfixture';upload={'exam_event_id':eid,'filename':'Übung.pdf','content':base64.b64encode(content).decode()}
        self.assertEqual(b.call('file-upload',upload)[0],400)
        fid=a.call('file-upload',upload)[1]['attachment_id']
        self.assertEqual(o.call(f'files/{fid}'),(200,content));self.assertEqual(b.call(f'files/{fid}')[0],404)
        self.assertEqual(out.call(f'files/{fid}')[0],404)
        self.assertEqual(a.call(f'files/{fid}')[0],200)
        self.assertIn("filename*=UTF-8''",a.last_headers['Content-Disposition'])
        self.assertEqual(a.call('file-upload',{**upload,'filename':'script.html'})[0],400)
        self.assertEqual(a.call('file-upload',{**upload,'content':'!'})[0],400)
        self.assertEqual(a.call('file-delete',{'attachment_id':fid})[0],200)
        self.assertEqual(a.call(f'files/{fid}'),(200,content))
        self.assertTrue(a.state()['files'][0]['archived_at'])
        self.assertEqual(a.call('file-restore',{'attachment_id':fid})[0],200)
        sid=a.call('group-adopt',{'exam_event_id':eid,'difficulty':2})[1]['user_exam_state_id']
        a.session(sid)
        self.assertEqual(a.change('exam-delete',sid)[1]['mode'],'archived')
        self.assertEqual(a.call(f'files/{fid}')[0],200)
        a.call('group-leave',{'group_id':child});self.assertEqual(a.call(f'files/{fid}')[0],404)
        self.assertEqual(a.personal(sid)['exam_event_id'],eid)
        self.assertFalse(a.personal(sid)['startable'])
        self.assertEqual(len(a.state()['sessions']),1)
    def test_event_archive_permissions_and_notice_retention(self):
        o,a,b,out,main,child,other=self.hierarchy();r=a.exam(group_id=child);eid=r['exam_event_id']
        a.call('group-adopt',{'exam_event_id':eid,'difficulty':3})
        self.assertEqual(b.call('event-delete',{'exam_event_id':eid,'version':1})[0],400)
        self.assertEqual(o.call('event-delete',{'exam_event_id':eid,'version':1})[1]['mode'],'archived')
        n=a.state()['notices'][0]['id'];self.assertEqual(a.call('notice-read',{'notice_id':n})[0],200)
        self.assertEqual(a.state()['notices'],[])
        with app.connect() as db:self.assertIsNotNone(db.execute('SELECT read_at FROM notices WHERE id=?',(n,)).fetchone()[0])
        self.assertEqual(o.call('event-restore',{'exam_event_id':eid,'version':2})[0],200)
        self.assertTrue(a.state()['user_exam_states'][0]['startable'])
    def test_all_sharing_masks_snapshot_and_no_ranking_publication(self):
        o,a,b,out,main,child,other=self.hierarchy();sid=a.exam()['user_exam_state_id'];a.session(sid);a.change('grade',sid,grade=2)
        self.assertEqual(a.state()['posts'],[]);self.assertEqual(o.state()['user_exam_states'],[])
        for flags in itertools.product((0,1),repeat=3):
            payload={'user_exam_state_id':sid,'audience':'group','target_group_id':child,'show_grade':flags[0],'show_seconds':flags[1],'show_count':flags[2]}
            self.assertEqual(a.call('post',payload)[0],200);p=o.state()['posts'][0]
            for key,flag in zip(('grade','seconds','session_count'),flags):self.assertEqual(key in p,bool(flag))
            self.assertEqual(b.state()['posts'],[]);self.assertEqual(out.state()['posts'],[])
        self.assertEqual(a.state()['ranking'],[]);self.assertEqual(a.state()['sessions'][0]['public'],0)
        a.change('grade',sid,grade=1);self.assertEqual(o.state()['posts'][0]['grade'],2)
        private={'user_exam_state_id':sid,'audience':'private','show_grade':1,'show_seconds':1,'show_count':1}
        a.call('post',private);self.assertEqual(a.state()['posts'][0]['audience'],'private')
        self.assertEqual(len(o.state()['posts']),8)
        self.assertEqual(a.call('post',{**private,'audience':'group','target_group_id':other})[0],400)
        a.call('group-leave',{'group_id':child});self.assertEqual(o.state()['posts'],[])
        a.call('group-join',{'group_id':child});self.assertEqual(o.state()['posts'],[])
    def test_audience_checked_before_comment_and_owner_can_revoke(self):
        o,a,b,out,main,child,other=self.hierarchy();sid=a.exam()['user_exam_state_id'];a.change('grade',sid,grade=2)
        p=a.call('post',{'user_exam_state_id':sid,'audience':'group','target_group_id':main,'show_grade':0,'show_seconds':0,'show_count':1})[1]['post_id']
        self.assertEqual(b.call('comment',{'post_id':p,'text':'Hi'})[0],200)
        b.call('friend',{'username':'student'});a.call('accept',{'sender':b.state()['user']['id']})
        self.assertEqual(b.call('comment',{'post_id':p,'text':'Hi'})[0],200)
        self.assertEqual(out.call('comment',{'post_id':p,'text':'Hi'})[0],400)
        self.assertEqual(b.call('post-revoke',{'post_id':p})[0],400)
        a.call('post-revoke',{'post_id':p});self.assertEqual(b.state()['posts'],[]);self.assertEqual(b.state()['comments'],[])
        self.assertEqual(len(a.state()['comments']),2)
    def test_finish_after_grade_and_restart_preserves_timer(self):
        c=self.register('timer');sid=c.exam()['user_exam_state_id'];c.call('start',{'user_exam_state_id':sid,'date':date.today().isoformat()})
        before=c.state()['active'];app.init_db();self.assertEqual(c.state()['active']['started'],before['started'])
        c.change('grade',sid,grade=3);self.assertFalse(c.personal(sid)['startable'])
        self.assertEqual(c.call('finish',{'resources':'Book','location':'Home'})[0],200)
    def test_exit_freezes_history_and_rejoin_updates_without_duplicate(self):
        o,a,b,out,main,child,other=self.hierarchy();eid=o.exam(group_id=child)['exam_event_id']
        sid=a.call('group-adopt',{'exam_event_id':eid,'difficulty':3})[1]['user_exam_state_id']
        a.session(sid);a.call('group-leave',{'group_id':child})
        o.call('event-edit',{'exam_event_id':eid,'version':1,'subject':'New subject','title':'New title','exam_date':'2027-03-01'})
        self.assertEqual(a.personal(sid)['title'],'Test')
        self.assertEqual(len(a.state()['event_history']),1)
        self.assertEqual(a.state()['exam_events'],[])
        self.assertEqual(a.state()['notices'],[])
        a.call('group-join',{'group_id':child})
        self.assertEqual(a.personal(sid)['title'],'New title');self.assertEqual(len(a.state()['user_exam_states']),1)
        self.assertEqual(a.state()['sessions'][0]['subject'],'Math')
    def test_concurrent_adoption_finish_and_grade_conflicts(self):
        o,a,b,out,main,child,other=self.hierarchy();eid=a.exam(group_id=child)['exam_event_id']
        def parallel(fn):
            barrier=threading.Barrier(2);results=[]
            def run():barrier.wait();results.append(fn())
            threads=[threading.Thread(target=run) for _ in range(2)]
            for t in threads:t.start()
            for t in threads:t.join(20);self.assertFalse(t.is_alive())
            return sorted(r[0] for r in results)
        self.assertEqual(parallel(lambda:a.call('group-adopt',{'exam_event_id':eid,'difficulty':3})),[200,400])
        sid=a.state()['user_exam_states'][0]['id'];a.call('start',{'user_exam_state_id':sid,'date':date.today().isoformat()})
        self.assertEqual(parallel(lambda:a.call('finish',{'resources':'Book','location':'Home'})),[200,400])
        self.assertEqual(len(a.state()['sessions']),1)
        self.assertEqual(parallel(lambda:a.call('grade',{'user_exam_state_id':sid,'grade':2,'version':1})),[200,409])
    def test_archive_quota_and_unused_group_event_delete(self):
        o,a,b,out,main,child,other=self.hierarchy();eid=o.exam(group_id=child)['exam_event_id']
        payload={'exam_event_id':eid,'filename':'small.pdf','content':base64.b64encode(b'%PDF-test').decode()}
        with patch.object(v2,'MAX_TOTAL',10):
            fid=o.call('file-upload',payload)[1]['attachment_id'];o.call('file-delete',{'attachment_id':fid})
            self.assertEqual(o.call('file-upload',payload)[0],400)
            self.assertEqual(o.call(f'files/{fid}')[1],b'%PDF-test')
        unused=o.exam(group_id=main)['exam_event_id']
        self.assertEqual(o.call('event-delete',{'exam_event_id':unused,'version':1})[1]['mode'],'deleted')
    def test_concurrent_session_creation_and_delete_preserve_accepted_data(self):
        c=self.register('race-user');sid=c.exam()['user_exam_state_id'];barrier=threading.Barrier(2);results={}
        def run(name,fn):barrier.wait();results[name]=fn()
        threads=[threading.Thread(target=run,args=('session',lambda:c.session(sid))),
                 threading.Thread(target=run,args=('delete',lambda:c.call('exam-delete',{'user_exam_state_id':sid,'version':1})))]
        for t in threads:t.start()
        for t in threads:t.join(20);self.assertFalse(t.is_alive())
        self.assertEqual(results['delete'][0],200)
        if results['session'][0]==200:
            self.assertEqual(results['delete'][1]['mode'],'archived')
            self.assertEqual(c.state()['sessions'][0]['user_exam_state_id'],sid)
        else:
            self.assertEqual(results['session'][0],400)
            self.assertEqual(c.state()['sessions'],[])

if __name__=='__main__':unittest.main()
