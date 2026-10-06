import base64
from datetime import date
import test_app
import app


class GroupTests(test_app.LearnoTestCase):
    # Eigene temporäre DB pro Testklasse, echte WSGI-Anfragen ohne Netzwerkport.
    def test_groups_files_sync_and_deletion(self):
        owner,author,student,outsider=[self.register(n) for n in ('owner','author','student','outsider')]
        status,created=owner.call('group-create',{'name':'BWI 1','description':'Gemeinsame Tests'})
        self.assertEqual(status,200);gid=created['id']
        self.assertEqual(len(outsider.state()['groups']),1)
        for user in (author,student):
            self.assertEqual(user.call('group-join',{'id':gid})[0],200)
        status,res=author.call('group-exam',{'group_id':gid,'subject':'Mathematik','title':'Test 1','exam_date':date.today().isoformat()})
        self.assertEqual(status,200);shared=res['id']
        self.assertEqual(student.state()['exams'],[])
        self.assertEqual(outsider.state()['group_exams'],[])
        self.assertEqual(outsider.call('group-adopt',{'id':shared,'difficulty':2})[0],400)
        personal=student.call('group-adopt',{'id':shared,'difficulty':4})[1]['id']
        self.assertEqual(student.call('group-adopt',{'id':shared,'difficulty':2})[0],400)
        self.assertEqual(student.call('session',{'exam_id':personal,'duration_minutes':30,'date':date.today().isoformat(),'interruptions':0,'resources':'Skriptum','location':'Lernraum'})[0],200)
        student.call('grade',{'id':personal,'grade':2})
        change={'id':shared,'subject':'Mathematik neu','title':'Test verschoben','exam_date':'2027-01-15'}
        self.assertEqual(student.call('group-exam-edit',change)[0],400)
        self.assertEqual(author.call('group-exam-edit',change)[0],200)
        view=student.state();exam=view['exams'][0]
        self.assertEqual((exam['exam_date'],exam['difficulty'],exam['grade'],exam['seconds']),('2027-01-15',4,2,1800))
        self.assertEqual(view['sessions'][0]['subject'],'Mathematik neu')
        self.assertTrue(view['notices'])
        content=b'%PDF-1.4\nTest fixture\n%%EOF'
        upload={'group_exam_id':shared,'filename':'Übung.pdf','content':base64.b64encode(content).decode()}
        self.assertEqual(outsider.call('file-upload',upload)[0],400)
        status,res=author.call('file-upload',upload);self.assertEqual(status,200);fid=res['id']
        self.assertEqual(student.call(f'files/{fid}'),(200,content))
        self.assertIn("filename*=UTF-8''",student.last_headers['Content-Disposition'])
        self.assertEqual(outsider.call(f'files/{fid}')[0],404)
        self.assertEqual(student.call('file-delete',{'id':fid})[0],400)
        self.assertEqual(author.call('file-upload',{**upload,'filename':'script.html'})[0],400)
        self.assertEqual(author.call('file-upload',{**upload,'content':'!invalid'})[0],400)
        self.assertEqual(student.call('exam-delete',{'id':personal})[0],200)
        self.assertIsNone(student.state()['sessions'][0]['exam_id'])
        self.assertEqual(student.call(f'files/{fid}')[0],200)
        student.call('group-adopt',{'id':shared,'difficulty':2})
        self.assertEqual(student.call('group-leave',{'id':gid})[0],200)
        self.assertEqual(student.call(f'files/{fid}')[0],404)
        self.assertIsNone(student.state()['exams'][0]['group_exam_id'])
        owner.call('group-adopt',{'id':shared,'difficulty':3})
        self.assertEqual(owner.call('group-exam-delete',{'id':shared})[0],200)
        self.assertIsNone(owner.state()['exams'][0]['group_exam_id'])
        self.assertEqual(author.call(f'files/{fid}')[0],404)

    def test_own_edit_delete_and_session_detach(self):
        c=self.register('edit-user');other=self.register('edit-other')
        eid=c.call('exam',{'title':'Test','subject':'Java','exam_date':date.today().isoformat(),'difficulty':2})[1]['id']
        self.assertEqual(c.call('start',{'exam_id':eid,'date':date.today().isoformat()})[0],200)
        self.assertEqual(other.call('exam-delete',{'id':eid})[0],400)
        self.assertEqual(c.call('exam-edit',{'id':eid,'title':'Test 2','subject':'Python','exam_date':'2027-01-03','difficulty':4})[0],200)
        self.assertEqual(c.state()['active']['subject'],'Python')
        self.assertEqual(c.call('exam-delete',{'id':eid})[0],200)
        self.assertIsNone(c.state()['active']['exam_id'])
        c.call('stop',{})
        self.assertEqual(c.call('finish',{'resources':'Buch','location':'Mein Lernort'})[0],200)
        self.assertIn('Mein Lernort',c.state()['locations'])

    def test_persistent_auth_and_https(self):
        c=self.register('persistent');self.assertIn('Secure',c.cookies.output())
        app.init_db() # Erneute Initialisierung/Worker-Start löscht keine Daten.
        self.assertEqual(c.state()['user']['username'],'persistent')
        self.assertEqual(c.call('logout',{})[0],200)
        self.assertEqual(c.call('state')[0],401)
