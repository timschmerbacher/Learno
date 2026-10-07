"""HTTP boundary tests on isolated databases; no live application writes."""
import io
import json
import unittest
from unittest.mock import patch
import wsgi
from test_app import LearnoTestCase


class TransportTests(LearnoTestCase):
    def request(self, path, method='GET', body=b'', client=None, **extra):
        route, _, query=path.partition('?')
        env={'PATH_INFO':route,'QUERY_STRING':query,'REQUEST_METHOD':method,
             'wsgi.url_scheme':'https','wsgi.input':io.BytesIO(body),
             'CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':'application/json',
             'HTTP_HOST':'learno.test','HTTP_ORIGIN':'https://learno.test',
             'REMOTE_ADDR':'transport-tests'}
        if client:
            env.update(HTTP_COOKIE=client.cookies.output(header='',sep=';').strip(),
                       HTTP_X_CSRF_TOKEN=client.csrf)
        env.update(extra)
        response={}
        def start(status,headers):
            response.update(status=int(status.split()[0]),headers=dict(headers))
        response['body']=b''.join(wsgi.application(env,start))
        return response

    def test_static_head_headers_and_methods(self):
        for path in ('/','/app.js','/v2.js','/ui.js','/style.css'):
            with self.subTest(path=path):
                result=self.request(path)
                self.assertEqual(result['status'],200)
                self.assertTrue(result['body'])
                self.assertEqual(result['headers']['Cache-Control'],'no-store')
                self.assertEqual(result['headers']['X-Content-Type-Options'],'nosniff')
                self.assertIn("frame-ancestors 'none'",result['headers']['Content-Security-Policy'])
                head=self.request(path,'HEAD')
                self.assertEqual(head['status'],200)
                self.assertEqual(head['body'],b'')
                self.assertEqual(head['headers']['Content-Length'],result['headers']['Content-Length'])
        for method in ('PUT','PATCH','DELETE','OPTIONS'):
            self.assertEqual(self.request('/api/v2/state',method)['status'],405)

    def test_authentication_unknown_paths_and_file_access(self):
        for path in ('/api/v2/state','/api/v2/feed','/api/v2/statistics',
                     '/api/v2/notices','/api/v2/export','/api/v2/files/1'):
            self.assertEqual(self.request(path)['status'],401,path)
        c=self.register('transport-user')
        for path in ('/missing','/../data/learno.db','/api/v2/files/not-an-id',
                     '/api/v2/files/-1','/api/v2/files/0','/api/v2/files/999999'):
            self.assertEqual(self.request(path,client=c)['status'],404,path)
        self.assertEqual(self.request('/api/v2/missing','POST',b'{}',c)['status'],404)

    def test_malformed_requests_origin_and_csrf_are_atomic(self):
        c=self.register('transport-writer')
        for raw in (b'',b'{',b'[]',b'null',b'"text"',b'\xff'):
            with self.subTest(raw=raw):
                self.assertEqual(self.request('/api/v2/exam','POST',raw,c)['status'],400)
        for length in ('-1','not-a-number','7500001'):
            self.assertEqual(self.request('/api/v2/exam','POST',b'{}',c,CONTENT_LENGTH=length)['status'],400)
        body=json.dumps({'name':'Must not exist'}).encode()
        self.assertEqual(self.request('/api/v2/group-create','POST',body,c,
                                     HTTP_ORIGIN='https://other.test')['status'],403)
        self.assertEqual(self.request('/api/v2/group-create','POST',body,c,
                                     HTTP_X_CSRF_TOKEN='wrong')['status'],403)
        self.assertEqual(c.state()['groups'],[])
        self.assertEqual(c.state()['user_exam_states'],[])

    def test_extremely_large_file_id_should_be_rejected_not_crash(self):
        # Reject oversized IDs before binding them to SQLite.
        c=self.register('large-id-user')
        with patch('logging.exception'):
            result=self.request('/api/v2/files/'+'9'*100,client=c)
        self.assertEqual(result['status'],404)
