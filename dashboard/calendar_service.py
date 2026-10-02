"""App-owned Google OAuth and conservative, click-triggered Calendar sync."""
import base64
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlencode, quote
from zoneinfo import ZoneInfo
import requests

SCOPE = 'https://www.googleapis.com/auth/calendar.app.created'
CALENDAR_NAME = 'University — Fall 2026'


def private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + '.' + secrets.token_hex(6))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream)
    temp.replace(path)


def identity(event):
    return str(event['course_id']) + '|' + event['title'].strip().casefold()


def preview(events, today=None):
    today = today or datetime.now(ZoneInfo('America/Halifax')).date()
    counts = Counter(identity(e) for e in events)
    ready, held = [], []
    for event in events:
        reason = None
        try:
            day = date.fromisoformat(event.get('date') or '')
        except ValueError:
            day = None
        if event.get('kind') == 'Practice':
            reason = 'Practice material, not a submitted assessment'
        elif day is None:
            reason = 'No definite date'
        elif day < today:
            reason = 'Past date'
        elif not '2026-09-01' <= day.isoformat() <= '2026-12-31':
            reason = 'Outside Fall 2026'
        elif event.get('review') or event.get('tentative') or event.get('source_changed') or event.get('conflict_dates'):
            reason = 'Date or source needs checking'
        elif counts[identity(event)] > 1:
            reason = 'Repeated assessment name; occurrence needs checking'
        elif not event.get('sources') and not event.get('confirmed_by_user'):
            reason = 'No source evidence'
        if reason:
            held.append(dict(event, hold_reason=reason))
        else:
            ready.append(event)
    return {'ready': ready, 'held': held}


def event_body(event):
    day = date.fromisoformat(event['date'])
    description = ['Academic AI Assistant', 'Date only — exact deadline time has not been verified.',
                   'Confirmed by you.' if event.get('confirmed_by_user') else 'Extracted from saved course materials. Check the source for instructions.']
    for source in event.get('sources', [])[:5]:
        description.append('\n' + source.get('name', '') + (f" · page {source['page']}" if source.get('page') else ''))
        description.append(source.get('evidence', '')[:1000])
        if source.get('url', '').startswith('https://'):
            description.append(source['url'])
    return {'summary': event['course'] + ' — ' + event['title'],
            'description': '\n'.join(description),
            'start': {'date': day.isoformat()}, 'end': {'date': (day + timedelta(days=1)).isoformat()},
            'reminders': {'useDefault': True}}


class CalendarError(Exception):
    pass


class CalendarService:
    def __init__(self, root, feed_provider, port=8767, transport=None):
        self.root = Path(root)
        self.feed_provider = feed_provider
        self.port = port
        self.http = transport or requests.Session()
        self.lock = threading.RLock()
        self.busy = False
        self.pending = None
        self.state = self.read('state.json', {'enabled': False, 'records': {}, 'message': 'Connect Google Calendar to get started.'})
        self.credentials = self.read('credentials.json', {})
        self.tokens = self.read('tokens.json', {})

    def read(self, name, default):
        path = self.root / name
        return json.loads(path.read_text()) if path.exists() else default

    def save(self):
        private_write(self.root / 'state.json', self.state)

    def import_credentials(self, value):
        config = value.get('installed', {})
        if not isinstance(config, dict) or not all(isinstance(config.get(k), str) and config[k] for k in ('client_id', 'client_secret')):
            raise CalendarError('Choose the JSON downloaded for a Desktop app OAuth client.')
        if not config['client_id'].endswith('.apps.googleusercontent.com'):
            raise CalendarError('Invalid Google OAuth client ID.')
        with self.lock:
            if self.busy or self.tokens:
                raise CalendarError('Disconnect Google before changing credentials.')
            self.credentials = {k: config[k] for k in ('client_id', 'client_secret')}
            private_write(self.root / 'credentials.json', self.credentials)

    def status(self):
        with self.lock:
            return {k: deepcopy(self.state.get(k)) for k in ('enabled', 'message', 'last_sync', 'counts', 'warnings')} | {
                'configured': bool(self.credentials), 'connected': bool(self.tokens.get('refresh_token')),
                'busy': self.busy, 'calendar_name': CALENDAR_NAME,
                'calendar_url': ('https://calendar.google.com/calendar/u/0/r?'+urlencode({'cid': self.state['calendar_id']})) if self.state.get('calendar_id') else None}

    def authorize(self):
        with self.lock:
            if not self.credentials:
                raise CalendarError('Import your Google credentials first.')
            if self.busy:
                raise CalendarError('Wait for calendar syncing to finish.')
            verifier = secrets.token_urlsafe(48)
            self.pending = {'state': secrets.token_urlsafe(32), 'verifier': verifier, 'expires': time.time()+600}
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
                'client_id': self.credentials['client_id'], 'redirect_uri': self.redirect_uri,
                'response_type': 'code', 'scope': SCOPE, 'access_type': 'offline', 'prompt': 'consent',
                'state': self.pending['state'], 'code_challenge': challenge, 'code_challenge_method': 'S256'})

    @property
    def redirect_uri(self):
        return f'http://127.0.0.1:{self.port}/oauth/google/callback'

    def token_request(self, values):
        try:
            response = self.http.post('https://oauth2.googleapis.com/token', data=values | self.credentials, timeout=20)
            if response.status_code != 200:
                raise CalendarError('Google authorization expired or failed. Connect Google again.')
            result = response.json()
            if not result.get('access_token'):
                raise CalendarError('Google did not return an access token. Connect again.')
            result['expires_at'] = time.time() + int(result.get('expires_in', 3600))
            return result
        except requests.RequestException:
            raise CalendarError('Could not reach Google. Check your internet connection and retry.') from None

    def callback(self, query):
        with self.lock:
            pending, self.pending = self.pending, None
            supplied = query.get('state', [''])[0]
            if not pending or time.time() > pending['expires'] or not secrets.compare_digest(supplied, pending['state']):
                raise CalendarError('Sign-in expired or was not started by this app. Connect again from the dashboard.')
            if query.get('error') or not query.get('code'):
                raise CalendarError('Google access was not granted. You can reconnect from the dashboard.')
            tokens = self.token_request({'code': query['code'][0], 'grant_type': 'authorization_code',
                                         'redirect_uri': self.redirect_uri, 'code_verifier': pending['verifier']})
            if not tokens.get('refresh_token') or SCOPE not in tokens.get('scope', '').split():
                raise CalendarError('Calendar access was not granted. Connect again and allow calendar access.')
            self.tokens = tokens
            private_write(self.root / 'tokens.json', tokens)
            self.state.update(enabled=False, message='Google connected. Review the preview, then enable syncing.')
            self.save()

    def access_token(self):
        if not self.tokens.get('refresh_token'):
            raise CalendarError('Connect Google Calendar first.')
        if self.tokens.get('expires_at', 0) < time.time()+60:
            self.tokens.update(self.token_request({'grant_type': 'refresh_token', 'refresh_token': self.tokens['refresh_token']}))
            private_write(self.root / 'tokens.json', self.tokens)
        return self.tokens['access_token']

    def api(self, method, path, body=None, etag=None):
        headers = {'Authorization': 'Bearer '+self.access_token()}
        if etag:
            headers['If-Match'] = etag
        try:
            response = self.http.request(method, 'https://www.googleapis.com/calendar/v3/'+path,
                                         json=body, headers=headers, timeout=20)
        except requests.RequestException:
            raise CalendarError('Google could not be reached. Retry calendar sync; Moodle files are safe.') from None
        if response.status_code in (404, 409, 410, 412):
            return response.status_code, {}
        if response.status_code >= 400:
            message = {401: 'Google sign-in expired. Connect Google again.',
                       403: 'Google denied calendar access. Check the Calendar API and your Google authorization.',
                       429: 'Google temporarily limited requests. Retry later.'}.get(response.status_code, 'Google Calendar could not finish this request. Retry later.')
            raise CalendarError(message)
        return response.status_code, response.json() if response.content else {}

    def enable(self):
        with self.lock:
            if not self.tokens:
                raise CalendarError('Connect Google first.')
            self.state['enabled'] = True
            self.save()
        self.start()

    def disconnect(self):
        with self.lock:
            if self.busy:
                raise CalendarError('Wait for calendar syncing to finish.')
            self.tokens = {}
            self.pending = None
            (self.root/'tokens.json').unlink(missing_ok=True)
            self.state.update(enabled=False, message='Disconnected locally. Existing Google events are preserved. You can also revoke access in your Google account.')
            self.save()

    def start(self):
        with self.lock:
            if self.busy or not self.state.get('enabled'):
                return False
            self.busy = True
            self.state['message'] = 'Checking assessment dates and syncing Google Calendar…'
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self):
        try:
            self.sync(self.feed_provider()['events'])
        except CalendarError as exc:
            with self.lock:
                self.state['message'] = str(exc)
        except Exception:
            with self.lock:
                self.state['message'] = 'Calendar sync could not finish. Existing events and Moodle files are safe.'
        finally:
            with self.lock:
                self.busy = False
                self.save()

    def sync(self, events):
        plan = preview(events)
        warnings = []
        counts = {'added': 0, 'updated': 0, 'unchanged': 0, 'held': len(plan['held'])}
        if not self.state.get('calendar_id'):
            if self.state.get('creation_pending'):
                raise CalendarError('Calendar creation had an uncertain result. Check Google Calendar before retrying setup; the app will not create a duplicate.')
            self.state['creation_pending'] = True
            self.save()
            code, calendar = self.api('POST', 'calendars', {'summary': CALENDAR_NAME, 'timeZone': 'America/Halifax',
                                                        'description': 'Assessment dates managed by Academic AI Assistant. Exact times are not verified.'})
            if code != 200 or not calendar.get('id'):
                raise CalendarError('Could not create the university calendar. Check Google Calendar before retrying.')
            self.state.update(calendar_id=calendar['id'], creation_pending=False)
            self.save()
        base = 'calendars/'+quote(self.state['calendar_id'], safe='')+'/events/'
        # A different Google account cannot access this app-created calendar: fail,
        # preserving the mapping instead of silently duplicating it in another account.
        status, _ = self.api('GET', 'calendars/'+quote(self.state['calendar_id'], safe=''))
        if status != 200:
            raise CalendarError('The saved university calendar is unavailable. Reconnect the original Google account or restore the calendar.')
        records = self.state.setdefault('records', {})
        eligible = {identity(e) for e in plan['ready']}
        past = {identity(e) for e in events if e.get('date') and e['date'] < datetime.now(ZoneInfo('America/Halifax')).date().isoformat()}
        for key in records.keys()-eligible-past:
            warnings.append('Previously synced item now missing or needs checking; its Google event was kept: '+key.split('|',1)[-1])
        for event in plan['ready']:
            key = identity(event)
            event_id = hashlib.sha256(('academic-assistant-v1|'+key).encode()).hexdigest()
            body = event_body(event)
            digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            record = records.get(key)
            code, remote = self.api('GET', base+event_id)
            if code in (404, 410):
                if record:
                    warnings.append('Deleted Google event was not recreated: '+event['title'])
                    continue
                code, remote = self.api('POST', base.rstrip('/'), body | {'id': event_id,
                     'extendedProperties': {'private': {'academicAssistant': 'v1'}}})
                if code == 409:
                    code, remote = self.api('GET', base+event_id)
                if code not in (200, 201):
                    raise CalendarError('Could not save a calendar event. Retry to safely resume.')
                # Verify a recovered event before claiming a timed-out insert succeeded.
                if any(remote.get(k) != v for k,v in body.items()):
                    warnings.append('Existing Google event differs; left untouched: '+event['title'])
                    continue
                counts['added'] += 1
            else:
                if remote.get('status') == 'cancelled':
                    warnings.append('Cancelled Google event was kept cancelled: '+event['title'])
                    continue
                managed = {k: remote.get(k) for k in body}
                previous = record.get('body') if record else body
                if managed != previous:
                    warnings.append('Edited in Google; left untouched: '+event['title'])
                    continue
                if managed != body:
                    if not remote.get('etag'):
                        warnings.append('Could not verify Google event version: '+event['title'])
                        continue
                    code, remote = self.api('PATCH', base+event_id, body, remote['etag'])
                    if code != 200:
                        warnings.append('Google event changed during sync; retry: '+event['title'])
                        continue
                    counts['updated'] += 1
                else:
                    counts['unchanged'] += 1
            records[key] = {'body': body, 'digest': digest, 'event_id': event_id}
            self.save()
        self.state.update(counts=counts, warnings=warnings, last_sync=datetime.now(ZoneInfo('America/Halifax')).isoformat(),
                          message=f"{counts['added']} added · {counts['updated']} updated · {counts['unchanged']} unchanged · {counts['held']} held back.")
        self.save()
