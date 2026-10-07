"""Additional domain checks; every test uses an isolated temporary database."""
import base64
from datetime import date
import unittest
from unittest.mock import patch
import app
import insights
import v2
from test_app import LearnoTestCase


class ExtendedDomainTests(LearnoTestCase):
    def test_timer_arithmetic_idempotent_controls_and_finish_validation(self):
        c=self.register('timer-extra')
        for action in ('pause','resume','stop','finish','discard'):
            self.assertEqual(c.call(action,{})[0],400,action)
        with patch.object(v2.time,'time',return_value=1000):
            self.assertEqual(c.call('start',{'subject':'Math','date':'2026-10-06'})[0],200)
            self.assertEqual(c.call('resume',{})[0],200)
        with patch.object(v2.time,'time',return_value=1060):
            c.call('pause',{})
            paused=c.state()['active']
            self.assertEqual(paused['elapsed'],60)
            self.assertEqual(paused['interruptions'],1)
        with patch.object(v2.time,'time',return_value=1120):
            c.call('pause',{});c.call('stop',{})
            self.assertEqual(c.state()['active']['paused'],1060)
            self.assertEqual(c.state()['active']['interruptions'],1)
            c.call('resume',{});c.call('resume',{})
            self.assertEqual(c.state()['active']['paused_total'],60)
        with patch.object(v2.time,'time',return_value=1180):
            c.call('stop',{})
            self.assertEqual(c.state()['active']['elapsed'],120)
            before=c.state()['active']
            self.assertEqual(c.call('finish',{'resources':'','location':'Home'})[0],400)
            self.assertEqual(c.state()['active'],before)
            self.assertEqual(c.state()['sessions'],[])
        with patch.object(v2.time,'time',return_value=1300):
            self.assertEqual(c.call('finish',{'resources':'Book','location':'Home'})[0],200)
        session=c.state()['sessions'][0]
        self.assertEqual(session['seconds'],120)
        self.assertEqual(session['interruptions'],1)
        self.assertEqual(c.call('finish',{'resources':'Book','location':'Home'})[0],400)
        self.assertEqual(len(c.state()['sessions']),1)

    def test_timer_discard_is_private_and_preserves_saved_sessions(self):
        a,b=self.register('timer-owner'),self.register('timer-peer')
        sid=a.exam()['user_exam_state_id'];a.session(sid)
        saved=a.state()['sessions']
        a.call('start',{'user_exam_state_id':sid,'date':'2026-10-06'})
        b.call('start',{'subject':'Other','date':'2026-10-06'})
        peer=b.state()['active']
        self.assertEqual(a.call('discard',{})[0],200)
        self.assertIsNone(a.state()['active'])
        self.assertEqual(a.state()['sessions'],saved)
        self.assertEqual(b.state()['active']['started'],peer['started'])
        self.assertEqual(a.call('discard',{})[0],400)

    def test_manual_session_validation_atomicity_boundaries_and_ownership(self):
        a,b=self.register('manual-owner'),self.register('manual-peer')
        sid=a.exam()['user_exam_state_id']
        invalid=[{'duration_minutes':0},{'duration_minutes':1441},{'duration_minutes':True},
                 {'duration_minutes':1.5},{'interruptions':-1},{'interruptions':1001},
                 {'interruptions':False},{'resources':' '},{'resources':'x'*201},
                 {'location':' '},{'date':'2026-02-30'},{'date':'2026-2-03'}]
        for extra in invalid:
            self.assertEqual(a.session(sid,**extra)[0],400,extra)
            self.assertEqual(a.state()['sessions'],[])
        self.assertEqual(b.session(sid)[0],400)
        self.assertEqual(a.session(sid,duration_minutes=1,interruptions=0)[0],200)
        self.assertEqual(a.session(sid,duration_minutes=1440,interruptions=1000)[0],200)
        self.assertEqual(sorted(s['seconds'] for s in a.state()['sessions']),[60,86400])
        self.assertEqual(b.state()['sessions'],[])

    def test_assignment_same_subject_preserves_all_original_content(self):
        a,b=self.register('assign-owner'),self.register('assign-peer')
        sid=a.exam('Math')['user_exam_state_id'];other=a.exam('Physics')['user_exam_state_id']
        peer=b.exam('Math')['user_exam_state_id']
        self.assertEqual(a.call('session',{'subject':'mAtH','date':'2026-10-06',
            'duration_minutes':35,'interruptions':2,'resources':'Notes','location':'Park'})[0],200)
        before=a.state()['sessions'][0];session_id=before['id']
        for c,target in ((a,other),(a,peer),(b,peer)):
            self.assertEqual(c.call('assign',{'session_id':session_id,'user_exam_state_id':target})[0],400)
        self.assertEqual(a.call('assign',{'session_id':999999,'user_exam_state_id':sid})[0],400)
        self.assertEqual(a.call('assign',{'session_id':session_id,'user_exam_state_id':sid})[0],200)
        after=a.state()['sessions'][0]
        for key,value in before.items():
            if key!='user_exam_state_id':self.assertEqual(after[key],value,key)
        self.assertEqual(after['user_exam_state_id'],sid)

    def test_file_signatures_names_limits_archive_and_private_download(self):
        a,b=self.register('file-owner'),self.register('file-peer')
        eid=a.exam()['exam_event_id']
        def upload(filename,content):
            return a.call('file-upload',{'exam_event_id':eid,'filename':filename,
                'content':base64.b64encode(content).decode()})
        for filename,content in [('x.pdf',b'not pdf'),('x.png',b'%PDF-test'),('x.jpg',b'no'),
                                 ('x.pdf',b''),('../x.pdf',b'%PDF-test'),
                                 ('x\\y.pdf',b'%PDF-test'),('x\n.pdf',b'%PDF-test')]:
            self.assertEqual(upload(filename,content)[0],400,filename)
        self.assertEqual(a.state()['files'],[])
        with patch.object(v2,'MAX_FILE',16):
            self.assertEqual(upload('x.pdf',b'%PDF-'+b'x'*12)[0],400)
            result=upload('x.pdf',b'%PDF-'+b'x'*11)
            self.assertEqual(result[0],200)
        fid=result[1]['attachment_id'];content=b'%PDF-'+b'x'*11
        for action in ('file-delete','file-restore'):
            self.assertEqual(b.call(action,{'attachment_id':fid})[0],400)
        self.assertEqual(b.call(f'files/{fid}')[0],404)
        self.assertEqual(a.call(f'files/{fid}'),(200,content))
        self.assertEqual(a.last_headers['Content-Type'],'application/pdf')
        a.call('file-delete',{'attachment_id':fid})
        self.assertEqual(a.call(f'files/{fid}'),(200,content))
        with app.connect() as db:
            row=db.execute('SELECT content,archived_at FROM exam_attachments WHERE id=?',(fid,)).fetchone()
            self.assertEqual(row['content'],content);self.assertIsNotNone(row['archived_at'])
        for filename,content in [('image.PNG',b'\x89PNG\r\n\x1a\nfixture'),('photo.JPEG',b'\xff\xd8\xfffixture')]:
            self.assertEqual(upload(filename,content)[0],200)

    def test_invalid_exam_and_group_payloads_do_not_leave_partial_rows(self):
        a,b=self.register('validation-owner'),self.register('validation-peer')
        for extra in ({'difficulty':0},{'difficulty':6},{'difficulty':True},{'title':' '},
                      {'subject':' '},{'exam_date':'2026-02-30'},{'adopt':'yes'},{'group_id':True}):
            data={'title':'Test','subject':'Math','exam_date':'2026-10-06','difficulty':3,**extra}
            self.assertEqual(a.call('exam',data)[0],400,extra)
        with app.connect() as db:
            for table in ('exam_events','user_exam_states','exam_event_history'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
        for payload in ({'name':' '},{'name':'x'*101},{'name':'Group','description':'x'*501},
                        {'name':'Group','parent_id':999999}):
            self.assertEqual(a.call('group-create',payload)[0],400)
        self.assertEqual(a.state()['groups'],[])
        eid=a.exam(group_id=a.call('group-create',{'name':'Main'})[1]['id'])['exam_event_id']
        self.assertEqual(b.call('event-edit',{'exam_event_id':eid,'version':1,'title':'Other',
            'subject':'Math','exam_date':'2026-10-06'})[0],400)
        self.assertEqual(a.state()['exam_events'][0]['title'],'Test')

    def test_real_five_mebibyte_file_limit_through_wsgi(self):
        a=self.register('large-file-test');eid=a.exam()['exam_event_id']
        content=b'%PDF-'+b'x'*(5*1024*1024-5)
        payload={'exam_event_id':eid,'filename':'large.pdf','content':base64.b64encode(content).decode()}
        status,result=a.call('file-upload',payload)
        self.assertEqual(status,200)
        self.assertEqual(a.call('files/'+str(result['attachment_id'])),(200,content))
        payload['content']=base64.b64encode(content+b'x').decode()
        self.assertEqual(a.call('file-upload',payload)[0],400)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM exam_attachments').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT size FROM exam_attachments').fetchone()[0],5*1024*1024)

    def test_weekly_goal_boundaries_and_year_crossing(self):
        a,b=self.register('year-owner'),self.register('year-peer')
        uid=a.state()['user']['id']
        for value in (15,10080):
            self.assertEqual(a.call('weekly-goal',{'weekly_goal_minutes':value})[0],200)
            self.assertEqual(a.call('statistics')[1]['weekly_goal_minutes'],value)
        a.call('weekly-goal',{'weekly_goal_minutes':15})
        with app.connect() as db:
            for day,seconds in [('2025-12-22',60),('2025-12-26',120),('2025-12-27',500),
                                ('2025-12-29',300),('2026-01-02',600),('2026-01-03',999)]:
                db.execute('INSERT INTO sessions(user_id,subject,date,seconds,resources,location) VALUES(?,?,?,?,?,?)',
                    (uid,'Math',day,seconds,'Book','Home'))
            stats=insights.statistics(db,uid,date(2026,1,2))
        self.assertEqual(stats['week_start'],'2025-12-29')
        self.assertEqual(stats['current_seconds'],900)
        self.assertEqual(stats['previous_comparable_seconds'],180)
        self.assertEqual(stats['difference_seconds'],720)
        self.assertEqual(stats['remaining_seconds'],0)
        self.assertEqual(stats['goal_percent'],100)
        self.assertEqual(stats['weeks'][-2]['seconds'],680)
        self.assertEqual(sum(w['current'] for w in stats['weeks']),1)
        self.assertIsNone(b.call('statistics')[1]['weekly_goal_minutes'])


if __name__=='__main__':unittest.main()
