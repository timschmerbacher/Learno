"""WSGI-Einstieg für PythonAnywhere. Nutzt dieselben Routen wie python app.py.

Kein Entwicklungsserver wird beim Import gestartet. HTTPS kommt vom WSGI-Server.
"""
from http import HTTPStatus
from email.message import Message
import io
import logging
import app



class WSGIHandler(app.Handler):
    def __init__(self,environ):
        self.path=environ.get('PATH_INFO','/')
        self.scheme=environ.get('wsgi.url_scheme','http')
        self.command=environ.get('REQUEST_METHOD','GET')
        self.client_address=(environ.get('REMOTE_ADDR','unknown'),0)
        self.headers=Message()
        for key,value in environ.items():
            if key.startswith('HTTP_'):
                self.headers[key[5:].replace('_','-')]=value
        self.headers['Content-Length']=environ.get('CONTENT_LENGTH','0') or '0'
        self.headers['Content-Type']=environ.get('CONTENT_TYPE','')
        self.rfile=environ['wsgi.input']
        self.wfile=io.BytesIO()
        self.response_headers=[]
        self.status=200

    def send_response(self,code,message=None):
        self.status=code

    def send_header(self,key,value):
        self.response_headers.append((key,value))

    def end_headers(self):
        pass

    def log_message(self,*args):
        pass


def application(environ,start_response):
    handler=WSGIHandler(environ)
    try:
        app.init_db()
        if handler.command in ('GET','HEAD'):
            handler.do_GET()
        elif handler.command=='POST':
            handler.do_POST()
        else:
            handler.send(405,{'error':'Methode nicht erlaubt.'})
    except Exception:
        logging.exception('Learno request failed')
        handler.wfile=io.BytesIO()
        handler.response_headers=[]
        handler.send(500,{'error':'Interner Fehler. Bitte erneut versuchen.'})
    start_response(f'{handler.status} {HTTPStatus(handler.status).phrase}',handler.response_headers)
    return [b'' if handler.command=='HEAD' else handler.wfile.getvalue()]
