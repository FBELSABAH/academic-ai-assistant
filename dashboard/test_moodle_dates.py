from datetime import date
import unittest
from moodle_dates import parse_calendar, merge
from calendar_service import preview, identity

COURSES = [{'id':'1','code':'STAT 2910','name':'Probability','url':'https://moodle.example/course/view.php?id=1'}]


def ics(summary='Test 1', start='20261106T183000Z', extra=''):
    return ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:event1\r\nSUMMARY:'+summary+
            '\r\nCATEGORIES:2026F STAT-2910-01\r\nDTSTART:'+start+'\r\n'+extra+
            'END:VEVENT\r\nEND:VCALENDAR\r\n').encode()


class MoodleDatesTests(unittest.TestCase):
    def test_exact_time_converts_dst_and_keeps_identity(self):
        e=parse_calendar(ics(),COURSES)['events'][0]
        self.assertEqual(e['start_at'],'2026-11-06T14:30:00-04:00')
        self.assertFalse(e['review'])
        before=parse_calendar(ics(start='20261006T183000Z'),COURSES)['events'][0]
        self.assertEqual(identity(e),identity(before))
        self.assertEqual(before['start_at'],'2026-10-06T15:30:00-03:00')

    def test_other_courses_and_attendance_excluded(self):
        self.assertEqual(parse_calendar(ics('Attendance'),COURSES)['events'],[])
        self.assertEqual(parse_calendar(ics(),[])['events'],[])

    def test_naive_times_and_recurrences_need_review(self):
        for raw in [ics(start='20261106T183000'),ics(extra='RRULE:FREQ=WEEKLY\r\n')]:
            self.assertTrue(parse_calendar(raw,COURSES)['events'][0]['review'])

    def test_practice_policy_applies_to_future_assignments(self):
        event=parse_calendar(ics('Assignment 12 due'),COURSES)['events'][0]
        doc={'course_id':'1','title':'Assignment 1','kind':'Practice','submission_status':'Not submitted by course policy'}
        result=merge({'events':[doc]},{'status':'complete','events':[event]})
        self.assertEqual(result['events'][-1]['kind'],'Practice')

    def test_moodle_uid_distinguishes_repeated_titles(self):
        a=parse_calendar(ics(),COURSES)['events'][0]
        b=dict(a,source_uid='event2',date='2026-11-20')
        self.assertEqual(len(preview([a,b],date(2026,10,2))['ready']),2)

    def test_user_confirmation_preserved_and_stale_feed_unused(self):
        event=parse_calendar(ics(),COURSES)['events'][0]
        doc=dict(event,date='2026-11-09',confirmed_by_user=True)
        self.assertEqual(merge({'events':[doc]},{'status':'complete','events':[event]})['events'],[doc])
        self.assertEqual(merge({'events':[]},{'status':'error','events':[event]})['events'],[])

    def test_cancelled_is_explicit_not_inferred_from_missing(self):
        event=parse_calendar(ics(extra='STATUS:CANCELLED\r\n'),COURSES)['events'][0]
        self.assertTrue(event['cancelled'])
        self.assertFalse(preview([event],date(2026,10,2))['ready'])

if __name__=='__main__':unittest.main()
