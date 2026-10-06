"""Integrationstests ohne zusätzliche Pakete; eigene temporäre Datenbank."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import http.cookiejar
import io
from http.cookies import SimpleCookie
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
import app


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ''
        self.cookies = SimpleCookie()

    def call(self, path, data=None):
        import wsgi
        raw=json.dumps(data).encode() if data is not None else b''
        environ={'PATH_INFO':'/api/'+path,'REQUEST_METHOD':'POST' if data is not None else 'GET',
            'wsgi.url_scheme':'https','wsgi.input':io.BytesIO(raw),'CONTENT_LENGTH':str(len(raw)),
            'CONTENT_TYPE':'application/json','HTTP_HOST':'learno.test','HTTP_ORIGIN':'https://learno.test',
            'HTTP_COOKIE':self.cookies.output(header='',sep=';').strip(),
            'HTTP_X_CSRF_TOKEN':self.csrf,'REMOTE_ADDR':self.base}
        result={}
        def response(status,headers):
            result['status']=int(status.split()[0]);result['headers']=dict(headers)
            for key,value in headers:
                if key.lower()=='set-cookie':
                    self.cookies.load(value)
        body=b''.join(wsgi.application(environ,response))
        self.last_headers=result['headers']
        return result['status'],json.loads(body) if result['headers'].get('Content-Type','').startswith('application/json') else body

    def state(self):
        status, result = self.call('state')
        if status != 200:
            raise AssertionError(result)
        self.csrf = result['csrf']
        return result


class LearnoTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.original_db = app.DB
        app.DB = Path(cls.temp.name) / 'test.db'
        app.init_db()
        cls.base = 'test-client'

    @classmethod
    def tearDownClass(cls):
        app.DB = cls.original_db
        cls.temp.cleanup()

    def register(self, name):
        c = Client(name)
        self.assertEqual(c.call('register',{'username':name,'password':'ExamplePassword123!'})[0],200)
        c.state()
        return c


class LearnoTests(LearnoTestCase):
    def test_priority_boundaries(self):
        today = date(2026,10,1)
        exam = {'exam_date':'2026-10-04','difficulty':4,'completed':0}
        self.assertEqual(app.priority(exam,30,today),{'days':3,'score':10})
        self.assertEqual(app.priority(exam,180,today)['score'],7)
        exam['exam_date']='2026-10-05'
        self.assertEqual(app.priority(exam,0,today)['score'],9)
        exam['exam_date']='2026-09-30'
        self.assertIsNone(app.priority(exam,0,today))
        exam.update(exam_date='2026-10-01',completed=1)
        self.assertIsNone(app.priority(exam,0,today))

    def test_full_flow_and_authorization(self):
        alice,bob = self.register('alice'),self.register('bob')
        today = date.today().isoformat()
        self.assertEqual(alice.call('exam',{'title':'Zwischenprüfung','subject':'Mathematik','exam_date':(date.today()+timedelta(days=3)).isoformat(),'difficulty':4})[0],200)
        exam = alice.state()['exams'][0]
        self.assertEqual(bob.call('grade',{'id':exam['id'],'grade':1})[0],400)
        self.assertEqual(alice.call('session',{'subject':'Mathematik','exam_id':exam['id'],'date':today,'duration_minutes':30,'interruptions':0,'resources':'Skriptum','location':'Bibliothek'})[0],200)
        state = alice.state()
        sid = state['sessions'][0]['id']
        self.assertEqual(state['exams'][0]['priority']['score'],10)
        self.assertEqual(bob.state()['sessions'],[])
        self.assertEqual(alice.call('grade',{'id':exam['id'],'grade':2})[0],200)
        self.assertEqual(alice.call('post',{'exam_id':exam['id'],'text':'Geschafft!'})[0],200)
        self.assertEqual(alice.call('post',{'session_id':sid,'text':'Eine gute Session.'})[0],200)
        self.assertEqual(alice.state()['ranking'][0]['seconds'],1800)
        post = alice.state()['posts'][0]
        self.assertEqual(bob.call('comment',{'post_id':post['id'],'text':'Hallo'})[0],400)
        self.assertEqual(bob.call('friend',{'username':'alice'})[0],200)
        bid = bob.state()['user']['id']
        self.assertEqual(alice.call('accept',{'sender':bid})[0],200)
        self.assertEqual(bob.call('comment',{'post_id':post['id'],'text':'Gut gemacht!'})[0],200)
        self.assertEqual(bob.call('comment',{'post_id':post['id'],'text':'x'*501})[0],400)
        self.assertEqual(bob.call('comment',{'post_id':post['id'],'text':'Scheisse'})[0],400)
        self.assertEqual(len(alice.state()['comments']),1)
        self.assertEqual(alice.call('start',{'exam_id':None,'subject':'Python','date':today})[0],200)
        self.assertEqual(alice.call('start',{'subject':'Python','date':today})[0],400)
        self.assertEqual(alice.call('pause',{})[0],200)
        self.assertEqual(alice.state()['active']['interruptions'],1)
        self.assertEqual(alice.call('resume',{})[0],200)
        self.assertEqual(alice.call('stop',{})[0],200)
        self.assertEqual(alice.call('finish',{'resources':'Übungsaufgaben','location':'Zuhause'})[0],200)
        self.assertIsNone(alice.state()['active'])
        self.assertEqual(len(alice.state()['sessions']),2)
        alice.csrf='invalid'
        self.assertEqual(alice.call('settings',{})[0],403)

    def test_csv_import_atomicity(self):
        user = self.register('csv-user')
        content = (Path(__file__).parent / 'learning_sessions.csv').read_text(encoding='utf-8')
        self.assertEqual(user.call('import',{'csv':content})[0],200)
        self.assertEqual(len(user.state()['sessions']),10)
        bad = content + '\n2026-10-01,-2,Skriptum,Zuhause,0,Mathematik\n'
        self.assertEqual(user.call('import',{'csv':bad})[0],400)
        self.assertEqual(len(user.state()['sessions']),10)
        self.assertEqual(user.call('session',{'date':'2026-02-30','duration_minutes':1,'subject':'Mathematik','resources':'Buch','location':'Zuhause','interruptions':0})[0],400)


if __name__ == '__main__':
    unittest.main()
