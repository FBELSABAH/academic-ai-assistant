import hashlib,json,tempfile,unittest
from pathlib import Path
from datetime import date
from class_schedule import class_events
from calendar_service import event_body,managed_body,preview,identity
class ClassScheduleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  source=self.root/'course-1'/'outline.pdf';source.parent.mkdir();source.write_bytes(b'source')
  self.config={'start':'2026-09-08','end':'2026-12-09','timezone':'America/Halifax','excluded_dates':['2026-09-30','2026-10-12','2026-10-13','2026-10-14','2026-10-15','2026-10-16','2026-11-11'],'calendar_source':'https://calendar.upei.ca','verified_on':'2026-10-05','courses':[dict(course_id='1',code='TEST',weekdays=[0,2,4],start_time='14:30',end_time='15:20',location='Room 432',path='outline.pdf',sha256=hashlib.sha256(b'source').hexdigest(),evidence='MWF 2:30–3:20')]}
 def events(self):
  p=self.root/'classes.json';p.write_text(json.dumps(self.config));return class_events(p,self.root)
 def test_bounds_holidays_and_unique_identities(self):
  events=self.events();self.assertTrue(events);self.assertEqual(len(events),len({identity(e) for e in events}))
  for e in events:
   self.assertNotIn(e['date'],self.config['excluded_dates']);self.assertLessEqual(e['date'],'2026-12-09');self.assertGreaterEqual(e['date'],'2026-09-08')
 def test_dst_preserves_wall_clock_and_duration(self):
  events=self.events();before=next(e for e in events if e['date']=='2026-10-30');after=next(e for e in events if e['date']=='2026-11-02')
  self.assertTrue(before['start_at'].endswith('14:30:00-03:00'));self.assertTrue(after['start_at'].endswith('14:30:00-04:00'))
  body=event_body(after);self.assertIn('15:20',body['end']['dateTime']);self.assertEqual(body['location'],'Room 432');self.assertEqual(body['reminders']['overrides'][0]['minutes'],15)
 def test_missing_end_and_changed_source_are_held(self):
  self.config['courses'][0]['end_time']=None;self.assertFalse(preview(self.events(),date(2026,9,1))['ready'])
  self.config['courses'][0]['end_time']='15:20';(self.root/'course-1/outline.pdf').write_bytes(b'changed');self.assertTrue(all(e['source_changed'] for e in self.events()))
 def test_past_classes_do_not_clutter_held_list(self):
  plan=preview(self.events(),date(2026,10,5));self.assertFalse(plan['held']);self.assertTrue(all(e['date']>='2026-10-05' for e in plan['ready']))
 def test_room_changes_are_managed(self):
  body=event_body(self.events()[0]);other=dict(body,location='Room 123');self.assertNotEqual(managed_body(body),managed_body(other))
if __name__=='__main__':unittest.main()

class IndependentClassSyncTests(unittest.TestCase):
 def test_failed_moodle_refresh_only_passes_classes_to_sync(self):
  from calendar_service import CalendarService
  from unittest.mock import Mock
  with tempfile.TemporaryDirectory() as d:
   classes={'source_type':'class_schedule','title':'Lecture'}
   deadline={'source_type':'moodle_calendar','title':'Exam'}
   service=CalendarService(Path(d),lambda:{'events':[classes,deadline]},refresh_source=lambda:{'status':'error'})
   service.access_token=Mock(return_value='fake');service.sync=Mock()
   service._run()
   service.sync.assert_called_once_with([classes])
