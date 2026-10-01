from datetime import date
from pathlib import Path
import tempfile
import unittest
from chat_service import ChatService, parse_date

class ChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'chat.sqlite';self.chat=ChatService(self.path)
        self.courses=[{'id':'1','code':'STAT 2910','name':'Statistics'}]
        self.event={'id':'e','course_id':'1','course':'Statistics','title':'Concept deck','date':'2026-10-09','sources':[{'evidence':'Due October 9','url':'https://example.org','name':'Outline','file_url':'/file'}],'kind':'Assessment','review':True,'tentative':False,'submission_status':'Unknown'}
        self.feed={'events':[self.event]};self.today=date(2026,10,1)
    def tearDown(self):self.tmp.cleanup()
    def send(self,**payload):return self.chat.handle(payload,self.feed,self.courses,self.today)
    def test_preview_does_not_write_until_confirmed(self):
        result=self.send(message='Add STAT 2910 quiz this Friday')
        self.assertIn('2026-10-02',result['message'])
        self.assertEqual(len(self.chat.overlay(self.feed)['events']),1)
        saved=self.send(confirm=result['proposal']);self.assertTrue(saved['changed'])
        self.assertEqual(len(ChatService(self.path).overlay(self.feed)['events']),2)
        self.assertNotIn('changed',self.send(confirm=result['proposal']))
        self.send(undo=True);self.assertEqual(len(self.chat.overlay(self.feed)['events']),1)
    def test_confirmation_preserved_and_source_change_flagged(self):
        result=self.send(message='Confirm Concept Deck is due October 8')
        self.send(confirm=result['proposal'])
        e=self.chat.overlay(self.feed)['events'][0];self.assertEqual(e['date'],'2026-10-08');self.assertFalse(e['review'])
        self.event['sources'][0]['evidence']='Due October 10'
        e=self.chat.overlay(self.feed)['events'][0];self.assertTrue(e['source_changed']);self.assertEqual(e['date'],'2026-10-08')
    def test_stale_proposal_rejected(self):
        result=self.send(message='Confirm Concept Deck October 8')
        self.event['date']='2026-10-10'
        self.assertNotIn('changed',self.send(confirm=result['proposal']))
    def test_ambiguous_or_missing_course_does_not_write(self):
        self.assertNotIn('proposal',self.send(message='Add quiz tomorrow'))
        self.assertNotIn('proposal',self.send(message='Move that quiz to tomorrow'))
        self.assertNotIn('proposal',self.send(message='Add STAT 9999 quiz tomorrow'))
    def test_cancel_and_invalid_date(self):
        proposal=self.send(message='Add STAT 2910 quiz tomorrow')['proposal']
        self.send(cancel=proposal)
        self.assertNotIn('changed',self.send(confirm=proposal))
        self.assertNotIn('proposal',self.send(message='Add STAT 2910 quiz 2026-02-30'))
    def test_queries_read_saved_overrides(self):
        p=self.send(message='Add STAT 2910 quiz tomorrow')['proposal'];self.send(confirm=p)
        self.assertIn('2026-10-02',self.send(message='What is due tomorrow?')['message'])
    def test_times_not_silently_discarded(self):
        self.assertNotIn('proposal',self.send(message='Add STAT 2910 quiz October 8 at 4pm'))

if __name__=='__main__':unittest.main()
