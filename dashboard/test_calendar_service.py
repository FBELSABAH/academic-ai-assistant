import json
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from calendar_service import CalendarService, CalendarError, GoogleError, event_body, managed_body, preview, SCOPE


def assessment(**overrides):
    return {'course_id':'1', 'course':'STAT 2240', 'title':'Midterm', 'date':'2026-10-20',
            'kind':'Assessment', 'sources':[{'name':'Syllabus.pdf', 'page':2, 'evidence':'Midterm October 20'}], **overrides}


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.service=CalendarService(Path(self.tmp.name), lambda:{'events':[]})
        self.remote={};self.writes=[]
        self.service.api=self.api
        self.today=patch('calendar_service.datetime', wraps=datetime)
        mocked=self.today.start();mocked.now.return_value=datetime.fromisoformat('2026-10-02T12:00:00-03:00')

    def tearDown(self):
        self.today.stop();self.tmp.cleanup()

    def api(self, method, path, body=None, etag=None):
        if method=='POST' and path=='calendars':
            self.writes.append(('calendar',body));return 200,{'id':'test-calendar'}
        if '/events' not in path:return 200,{'id':'test-calendar'}
        key=path.split('/')[-1]
        if method=='GET':return (200,deepcopy(self.remote[key])) if key in self.remote else (404,{})
        if method=='POST':
            key=body['id']
            if key in self.remote:return 409,{}
            self.remote[key]=dict(deepcopy(body),etag='v1');self.writes.append(('event',key))
        if method=='PATCH':
            self.assertEqual(etag,self.remote[key]['etag'])
            self.remote[key].update(deepcopy(body));self.writes.append(('patch',key))
        if method=='DELETE':
            self.remote.pop(key,None);return 204,{}
        return 200,deepcopy(self.remote[key])

    def test_filters_uncertain_practice_past_and_repeated(self):
        items=[assessment(),assessment(title='Old',date='2026-09-01'),assessment(title='Practice',kind='Practice'),
               assessment(title='Unclear',review=True),assessment(title='Tentative',tentative=True),
               assessment(title='No date',date=None),assessment(title='Repeated'),assessment(title='Repeated',date='2026-10-22')]
        plan=preview(items,date(2026,10,2))
        self.assertEqual([e['title'] for e in plan['ready']],['Midterm'])
        self.assertEqual(len(plan['held']),7)

    def test_repeated_sync_and_restart_do_not_duplicate(self):
        self.service.sync([assessment()]);self.service.sync([assessment()])
        restarted=CalendarService(Path(self.tmp.name), lambda:{'events':[]});restarted.api=self.api
        restarted.sync([assessment()])
        self.assertEqual([w[0] for w in self.writes],['calendar','event'])

    def test_date_change_updates_same_event(self):
        self.service.sync([assessment()]);self.service.sync([assessment(date='2026-10-25')])
        self.assertEqual(len(self.remote),1)
        self.assertEqual(next(iter(self.remote.values()))['start'],{'date':'2026-10-25'})
        self.assertEqual(self.writes[-1][0],'patch')

    def test_manual_google_edit_is_preserved(self):
        self.service.sync([assessment()]);next(iter(self.remote.values()))['summary']='My edited exam'
        self.service.sync([assessment(date='2026-10-25')])
        self.assertEqual(next(iter(self.remote.values()))['summary'],'My edited exam')
        self.assertTrue(self.service.state['warnings'])

    def test_deleted_event_is_not_recreated(self):
        self.service.sync([assessment()]);self.remote.clear();self.service.sync([assessment()])
        self.assertFalse(self.remote)
        self.assertIn('not recreated',self.service.state['warnings'][0])

    def test_source_becomes_uncertain_preserves_event_and_warns(self):
        self.service.sync([assessment()]);self.service.sync([assessment(review=True)])
        self.assertEqual(len(self.remote),1)
        self.assertIn('needs checking',self.service.state['warnings'][0])

    def test_insert_with_unknown_outcome_recovers_without_duplicate(self):
        original=self.service.save
        def fail_after_insert():
            if self.remote:raise OSError('simulated disk error')
            original()
        self.service.save=fail_after_insert
        with self.assertRaises(OSError):self.service.sync([assessment()])
        self.service.save=original;self.service.state['records']={}
        self.service.sync([assessment()])
        self.assertEqual(len(self.remote),1)
        self.assertEqual(len([w for w in self.writes if w[0]=='event']),1)

    def test_unknown_calendar_creation_does_not_retry(self):
        self.service.state['creation_pending']=True
        with self.assertRaises(CalendarError):self.service.sync([assessment()])
        self.assertEqual(self.writes,[])

    def test_all_day_end_is_exclusive(self):
        body=event_body(assessment(date='2026-10-31'))
        self.assertEqual(body['end'],{'date':'2026-11-01'})
        self.assertIn('page 2',body['description'])

    def test_oauth_state_pkce_and_private_credentials(self):
        self.service.import_credentials({'installed':{'client_id':'example.apps.googleusercontent.com','client_secret':'example'}})
        params=parse_qs(urlparse(self.service.authorize()).query)
        self.assertEqual(params['code_challenge_method'],['S256'])
        self.assertEqual(params['scope'],[SCOPE])
        self.assertEqual((Path(self.tmp.name)/'credentials.json').stat().st_mode & 0o777,0o600)
        with patch.object(self.service,'token_request') as exchange:
            with self.assertRaises(CalendarError):self.service.callback({'state':['wrong'],'code':['secret']})
            exchange.assert_not_called()

    def test_unconfigured_or_disabled_cannot_start(self):
        self.assertFalse(self.service.start())
        with self.assertRaises(CalendarError):self.service.enable()

    def test_successful_oauth_is_single_use_and_requires_enable(self):
        self.service.import_credentials({'installed':{'client_id':'example.apps.googleusercontent.com','client_secret':'example'}})
        query=parse_qs(urlparse(self.service.authorize()).query)
        callback={'state':query['state'],'code':['private-code']}
        with patch.object(self.service,'token_request',return_value={'access_token':'private-access','refresh_token':'private-refresh','scope':SCOPE}):
            self.service.callback(callback)
            with self.assertRaises(CalendarError):self.service.callback(callback)
        self.assertTrue(self.service.status()['connected'])
        self.assertFalse(self.service.state['enabled'])
        self.assertNotIn('private',json.dumps(self.service.status()))

    def test_callback_denial_does_not_exchange_code(self):
        self.service.credentials={'client_id':'example'}
        query=parse_qs(urlparse(self.service.authorize()).query)
        with patch.object(self.service,'token_request') as exchange:
            with self.assertRaises(CalendarError):self.service.callback({'state':query['state'],'error':['access_denied']})
            exchange.assert_not_called()

    def test_timed_deadline_has_reminders_and_valid_duration(self):
        body=event_body(assessment(start_at='2026-11-06T14:30:00-04:00',source_type='moodle_calendar'))
        self.assertEqual(body['start']['dateTime'],'2026-11-06T14:30:00-04:00')
        self.assertEqual(body['end']['dateTime'],'2026-11-06T14:31:00-04:00')
        self.assertEqual([r['minutes'] for r in body['reminders']['overrides']],[1440,60])

    def test_google_timestamp_and_reminder_normalization(self):
        body=event_body(assessment(start_at='2026-11-06T14:30:00-04:00',source_type='moodle_calendar'))
        remote=deepcopy(body);remote['start']={'dateTime':'2026-11-06T18:30:00Z'}
        remote['reminders']['overrides'].reverse()
        self.assertEqual(managed_body(body),managed_body(remote))

    def test_document_event_upgrades_to_moodle_without_duplicate(self):
        self.service.sync([assessment()])
        self.service.sync([assessment(source_type='moodle_calendar',source_uid='new-uid',start_at='2026-10-20T14:30:00-03:00')])
        self.assertEqual(len(self.remote),1)
        self.assertEqual(len(self.service.state['records']),1)
        self.assertEqual(self.writes[-1][0],'patch')

    def test_explicit_cancellation_removes_only_unedited_managed_event(self):
        e=assessment(source_type='moodle_calendar',source_uid='moodle-1')
        self.service.sync([e]);self.service.sync([dict(e,cancelled=True)])
        self.assertFalse(self.remote)

    def test_google_edit_survives_moodle_cancellation(self):
        e=assessment(source_type='moodle_calendar',source_uid='moodle-1')
        self.service.sync([e]);next(iter(self.remote.values()))['summary']='My note'
        self.service.sync([dict(e,cancelled=True)])
        self.assertEqual(len(self.remote),1)

    def test_definite_create_rejection_allows_retry(self):
        with patch.object(self.service,'api',side_effect=GoogleError('Not authorized',403)):
            with self.assertRaises(GoogleError):self.service.sync([assessment()])
        self.assertFalse(self.service.state['creation_pending'])

    def test_transport_retries_transient_error(self):
        from unittest.mock import Mock
        s=CalendarService(Path(self.tmp.name),lambda:{'events':[]},transport=Mock())
        s.access_token=lambda:'private'
        s.http.request.side_effect=[Mock(status_code=503,json=lambda:{},content=b'{}'),Mock(status_code=200,json=lambda:{'id':'ok'},content=b'{}')]
        with patch('calendar_service.time.sleep'):
            code,result=s.api('GET','calendars/example')
        self.assertEqual((code,result),(200,{'id':'ok'}));self.assertEqual(s.http.request.call_count,2)


if __name__=='__main__':unittest.main()
