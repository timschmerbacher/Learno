"""Diesen Inhalt in PythonAnywheres WSGI-Konfigurationsdatei kopieren."""
import os
import sys
import time

project = os.path.expanduser('~/learno')
if project not in sys.path:
    sys.path.insert(0, project)
os.environ['TZ'] = 'Europe/Vienna'
if hasattr(time, 'tzset'):
    time.tzset()

from wsgi import application
