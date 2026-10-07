"""Additional account/transport/import regression tests; isolated databases only."""
import csv
import hashlib
import io
import time
import unittest

import app
from test_app import Client, LearnoTestCase


class ExtendedAccountTests(LearnoTestCase):
    def test_login_duplicate_password_logout_and_token_storage(self):
        owner = self.register('account-owner')
        other = Client('second-device')
        self.assertEqual(other.call('register', {'username': 'account-owner', 'password': 'OtherPassword123!'})[0], 400)
        self.assertEqual(other.call('register', {'username': 'ACCOUNT-OWNER', 'password': 'OtherPassword123!'})[0], 400)
        self.assertEqual(other.call('login', {'username': 'account-owner', 'password': 'WrongPassword123!'})[0], 401)
        self.assertEqual(other.call('login', {'username': 'absent-user', 'password': 'WrongPassword123!'})[0], 401)
        self.assertEqual(other.call('login', {'username': 'account-owner', 'password': 'ExamplePassword123!'})[0], 200)
        self.assertEqual(other.state()['user']['id'], owner.state()['user']['id'])
        token = other.cookies['learno'].value
        with app.connect() as db:
            stored = db.execute('SELECT token_hash FROM auth_sessions').fetchall()
            self.assertIn(hashlib.sha256(token.encode()).hexdigest(), [r[0] for r in stored])
            self.assertNotIn(token, [r[0] for r in stored])
            user = db.execute('SELECT * FROM users').fetchone()
            self.assertNotEqual(user['password'], 'ExamplePassword123!')
        self.assertEqual(other.call('logout', {})[0], 200)
        self.assertEqual(other.call('state')[0], 401)
        self.assertEqual(owner.call('state')[0], 200)

    def test_registration_validation_expiry_and_rate_limit_persistence(self):
        c = Client('invalid-registration')
        for username, password in [('ab', 'ExamplePassword123!'), ('name with spaces', 'ExamplePassword123!'), ('valid-name', 'short'), ('valid-name', 'x'*129)]:
            self.assertEqual(c.call('register', {'username': username, 'password': password})[0], 400)
        owner = self.register('expiry-user')
        token_hash = hashlib.sha256(owner.cookies['learno'].value.encode()).hexdigest()
        with app.connect() as db:
            db.execute('UPDATE auth_sessions SET expires=? WHERE token_hash=?', (time.time()-1, token_hash))
        self.assertEqual(owner.call('state')[0], 401)
        self.assertEqual(owner.call('settings', {})[0], 401)
        limited = Client('rate-limit-ip')
        # Validation failures count too, without wasting expensive password hashing.
        for _ in range(30):
            self.assertEqual(limited.call('login', {'username': 'x', 'password': 'short'})[0], 400)
        app.init_db()
        self.assertEqual(limited.call('login', {'username': 'x', 'password': 'short'})[0], 429)
        with app.connect() as db:
            bucket = hashlib.sha256(('rate-limit-ip/api/login').encode()).hexdigest()
            db.execute('UPDATE auth_attempts SET created=? WHERE bucket=?', (time.time()-901, bucket))
        self.assertEqual(limited.call('login', {'username': 'x', 'password': 'short'})[0], 400)

    def test_settings_validation_atomicity_persistence_and_isolation(self):
        a, b = self.register('settings-a'), self.register('settings-b')
        baseline = b.state()['user']
        valid = {'reminder': '07:15', 'reminder_on': 1, 'timezone': 'Europe/London'}
        self.assertEqual(a.call('settings', valid)[0], 200)
        for key, value in [('reminder', '24:00'), ('reminder', '7:15'), ('timezone', 'Mars/Base'), ('reminder_on', True), ('reminder_on', 2)]:
            self.assertEqual(a.call('settings', {**valid, key: value})[0], 400)
            self.assertEqual({k: a.state()['user'][k] for k in valid}, valid)
        app.init_db()
        self.assertEqual({k: a.state()['user'][k] for k in valid}, valid)
        self.assertEqual(b.state()['user'], baseline)
        self.assertEqual(a.call('settings', {**valid, 'reminder_on': 0, 'timezone': 'UTC'})[0], 200)

    def test_friend_lifecycle_duplicates_and_unauthorized_mutations(self):
        a, b, outsider = self.register('friend-a'), self.register('friend-b'), self.register('friend-c')
        aid, bid = a.state()['user']['id'], b.state()['user']['id']
        self.assertEqual(a.call('friend', {'username': 'friend-a'})[0], 400)
        self.assertEqual(a.call('friend', {'username': 'missing-user'})[0], 400)
        self.assertEqual(a.call('friend', {'username': 'friend-b'})[0], 200)
        self.assertEqual(a.call('friend', {'username': 'friend-b'})[0], 400)
        self.assertEqual(b.call('friend', {'username': 'friend-a'})[0], 400)
        self.assertEqual(outsider.state()['friends'], [])
        # Unauthorized/no matching request is currently a successful no-op.
        outsider.call('accept', {'sender': aid}); a.call('accept', {'sender': bid})
        self.assertEqual(a.state()['friends'][0]['accepted'], 0)
        outsider.call('reject', {'sender': aid})
        self.assertEqual(len(a.state()['friends']), 1)
        self.assertEqual(b.call('reject', {'sender': aid})[0], 200)
        self.assertEqual(a.state()['friends'], [])
        a.call('friend', {'username': 'friend-b'})
        self.assertEqual(b.call('accept', {'sender': aid})[0], 200)
        self.assertEqual(a.state()['friends'][0]['accepted'], 1)
        b.call('reject', {'sender': aid})
        self.assertEqual(a.state()['friends'][0]['accepted'], 1)

    def test_csv_bom_quotes_roundtrip_privacy_and_atomicity(self):
        a, b = self.register('csv-source'), self.register('csv-target')
        header = 'date,duration_minutes,learning_resources,learning_location,interruptions,subject\r\n'
        good = '\ufeff' + header + '2026-10-01,45,"Buch, Notizen","Café \'West\'",2,Mathematik\r\n'
        self.assertEqual(a.call('import', {'csv': good})[0], 200)
        status, exported = a.call('export')
        self.assertEqual(status, 200); self.assertTrue(exported.startswith(b'\xef\xbb\xbf'))
        data = list(csv.DictReader(io.StringIO(exported.decode('utf-8-sig'))))
        self.assertEqual(data[0]['learning_resources'], 'Buch, Notizen')
        self.assertEqual(data[0]['duration_minutes'], '45')
        self.assertEqual(b.call('import', {'csv': exported.decode('utf-8')})[0], 200)
        fields = ('subject', 'date', 'seconds', 'resources', 'location', 'interruptions')
        self.assertEqual({k: a.state()['sessions'][0][k] for k in fields}, {k: b.state()['sessions'][0][k] for k in fields})
        before = a.state()['sessions']
        malformed = [header, header + '2026-10-01,1,Book,Home,0\n', header + '2026-10-01,1,Book,Home,0,Math,extra\n',
                     header + '2026-02-30,1,Book,Home,0,Math\n', header + '2026-10-01,1441,Book,Home,0,Math\n',
                     header + '2026-10-01,1,Book,Home,-1,Math\n', header + '2026-10-01,1,"unterminated,Home,0,Math\n']
        for content in malformed:
            self.assertEqual(a.call('import', {'csv': content})[0], 400)
            self.assertEqual(a.state()['sessions'], before)
        self.assertEqual(a.call('import', {'csv': good + '2026-10-01,-1,Book,Home,0,Math\n'})[0], 400)
        self.assertEqual(a.state()['sessions'], before)

    def test_csv_row_limit_rolls_back_all_rows(self):
        c = self.register('csv-limit')
        header = 'date,duration_minutes,learning_resources,learning_location,interruptions,subject\n'
        content = header + '2026-10-01,1,Book,Home,0,Math\n'*5001
        self.assertEqual(c.call('import', {'csv': content})[0], 400)
        self.assertEqual(c.state()['sessions'], [])
        self.assertEqual(c.call('import', {'csv': header.replace('subject', 'course') + '2026-10-01,1,Book,Home,0,Math\n'})[0], 400)
        self.assertEqual(c.state()['sessions'], [])



if __name__ == '__main__':
    unittest.main()
