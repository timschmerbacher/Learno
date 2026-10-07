"""WSGI integration tests against a fresh temporary V2 DB per test."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from datetime import date, timedelta
from http.cookies import SimpleCookie
import app
from migrate import migrate_database

class Client:
    def __init__(self, name):
        self.name=name; self.csrf=''; self.cookies=SimpleCookie()
    def call(self,path,data=None,legacy=False):
        import wsgi
        raw=json.dumps(data).encode() if data is not None else b''
        environ={'PATH_INFO':('/api/' if legacy else '/api/v2/')+path,
          'REQUEST_METHOD':'POST' if data is not None else 'GET','wsgi.url_scheme':'https',
          'wsgi.input':io.BytesIO(raw),'CONTENT_LENGTH':str(len(raw)),'CONTENT_TYPE':'application/json',
          'HTTP_HOST':'learno.test','HTTP_ORIGIN':'https://learno.test','HTTP_COOKIE':self.cookies.output(header='',sep=';').strip(),
          'HTTP_X_CSRF_TOKEN':self.csrf,'REMOTE_ADDR':self.name}
        result={}
        def response(status,headers):
            result['status']=int(status.split()[0]);result['headers']=dict(headers)
            for key,value in headers:
                if key.lower()=='set-cookie':self.cookies.load(value)
        body=b''.join(wsgi.application(environ,response));self.last_headers=result['headers']
        return result['status'],json.loads(body) if self.last_headers.get('Content-Type','').startswith('application/json') else body
    def state(self):
        status,result=self.call('state')
        if status!=200:raise AssertionError(result)
        self.csrf=result['csrf'];return result
    def personal(self,sid):return next(s for s in self.state()['user_exam_states'] if s['id']==sid)
    def exam(self,subject='Math',**extra):
        data={'title':'Test','subject':subject,'exam_date':(date.today()+timedelta(days=3)).isoformat(),'difficulty':4}
        data.update(extra);status,result=self.call('exam',data)
        if status!=200:raise AssertionError(result)
        return result
    def change(self,action,sid,**extra):
        s=self.personal(sid)
        return self.call(action,{'user_exam_state_id':sid,'version':s['version'],'event_version':s['event_version'],**extra})
    def session(self,sid,**extra):
        return self.call('session',{'user_exam_state_id':sid,'date':date.today().isoformat(),'duration_minutes':30,
          'resources':'Book','location':'Library','interruptions':0,**extra})

class LearnoTestCase(unittest.TestCase):
    def setUp(self):
        test_root=Path(__file__).resolve().parent/'data'
        test_root.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='v2-test-',dir=test_root);self.original_db=app.DB
        app.DB=Path(self.temp.name)/'test.db';migrate_database(app.DB);app.init_db()
    def tearDown(self):
        app.DB=self.original_db;self.temp.cleanup()
    def register(self,name):
        c=Client(name)
        self.assertEqual(c.call('register',{'username':name,'password':'ExamplePassword123!'})[0],200)
        c.state();return c

class LearnoTests(LearnoTestCase):
    def test_priority_boundaries(self):
        today=date(2026,10,1);e={'exam_date':'2026-10-04','difficulty':4,'completed':0}
        self.assertEqual(app.priority(e,30,today),{'days':3,'score':10})
        self.assertEqual(app.priority(e,180,today)['score'],7)
        e['exam_date']='2026-10-05';self.assertEqual(app.priority(e,0,today)['score'],9)
        e['exam_date']='2026-09-30';self.assertIsNone(app.priority(e,0,today))
        e.update(exam_date='2026-10-01',completed=1);self.assertIsNone(app.priority(e,0,today))
    def test_auth_privacy_timer_and_sessions(self):
        a,b=self.register('alice'),self.register('bob');sid=a.exam()['user_exam_state_id']
        self.assertEqual(b.call('grade',{'user_exam_state_id':sid,'grade':1,'version':1})[0],400)
        self.assertEqual(a.session(sid)[0],200);self.assertEqual(b.state()['sessions'],[])
        self.assertEqual(a.call('start',{'user_exam_state_id':sid,'date':date.today().isoformat()})[0],200)
        self.assertEqual(a.call('start',{'subject':'Python','date':date.today().isoformat()})[0],400)
        a.call('pause',{});self.assertEqual(a.state()['active']['interruptions'],1);a.call('resume',{})
        a.call('stop',{});self.assertEqual(a.call('finish',{'resources':'Book','location':'My place'})[0],200)
        self.assertIsNone(a.state()['active']);self.assertEqual(len(a.state()['sessions']),2)
        self.assertIn('My place',a.state()['locations']);self.assertNotIn('My place',b.state()['locations'])
        a.csrf='invalid';self.assertEqual(a.call('settings',{})[0],403)
    def test_grade_history_and_start_filter(self):
        a=self.register('grades');sid=a.exam()['user_exam_state_id']
        for grade in range(1,6):self.assertEqual(a.change('grade',sid,grade=grade)[0],200)
        view=a.state();self.assertEqual([h['new_grade'] for h in view['grade_history']],[1,2,3,4,5])
        self.assertFalse(a.personal(sid)['startable'])
        self.assertEqual(a.call('start',{'user_exam_state_id':sid,'date':date.today().isoformat()})[0],400)
        self.assertEqual(a.change('grade',sid,grade=5)[0],200);self.assertEqual(len(a.state()['grade_history']),5)
        self.assertEqual(a.call('grade',{'user_exam_state_id':sid,'grade':2,'version':1})[0],409)
    def test_csv_import_atomicity(self):
        c=self.register('csv-user');content=(Path(__file__).parent/'learning_sessions.csv').read_text(encoding='utf-8')
        self.assertEqual(c.call('import',{'csv':content})[0],200);self.assertEqual(len(c.state()['sessions']),10)
        self.assertEqual(c.call('import',{'csv':content+'\n2026-10-01,-2,Book,Home,0,Math\n'})[0],400)
        self.assertEqual(len(c.state()['sessions']),10)
        self.assertEqual(c.call('export',legacy=True)[0],200)
        self.assertEqual(c.call('session',{'date':'2026-02-30','duration_minutes':1,'subject':'Math','resources':'Book','location':'Home','interruptions':0})[0],400)
    def test_session_posts_comments_ranking_and_csrf(self):
        a,b=self.register('alice'),self.register('bob');sid=a.exam()['user_exam_state_id'];a.session(sid)
        session=a.state()['sessions'][0]['id']
        for _ in range(2):self.assertEqual(a.call('post',{'session_id':session,'text':'Good','audience':'public','show_seconds':1})[0],200)
        self.assertEqual(a.state()['ranking'],[])
        self.assertEqual(a.call('session-ranking',{'session_id':session,'public':True})[0],200)
        self.assertEqual(a.state()['ranking'][0]['seconds'],1800)
        post=a.state()['posts'][0]['id'];self.assertEqual(b.call('comment',{'post_id':post,'text':'Hello'})[0],400)
        b.call('friend',{'username':'alice'});a.call('accept',{'sender':b.state()['user']['id']})
        self.assertEqual(b.call('comment',{'post_id':post,'text':'Good work'})[0],200)
        self.assertEqual(b.call('comment',{'post_id':post,'text':'Scheisse'})[0],400)
        self.assertEqual(b.call('comment',{'post_id':post,'text':'x'*501})[0],400)
        a.call('post-revoke',{'post_id':post});self.assertEqual(b.call('comment',{'post_id':post,'text':'No'})[0],400)
    def test_startup_and_legacy_write_protection(self):
        a=self.register('persistent');self.assertIn('Secure',a.cookies.output());app.init_db()
        self.assertEqual(a.state()['user']['username'],'persistent')
        self.assertEqual(a.call('exam',{'title':'Bad'},legacy=True)[0],409)
        self.assertEqual(a.call('logout',{})[0],200);self.assertEqual(a.call('state')[0],401)

if __name__=='__main__':unittest.main()
