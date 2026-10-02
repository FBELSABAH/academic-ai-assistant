from pathlib import Path
import json
import hashlib
import tempfile
import unittest
from unittest.mock import patch
from assessments import candidates, dates, feed


class AssessmentTests(unittest.TestCase):
    def test_sample_spaces_assignment_is_not_a_sample_exam(self):
        rows=candidates('Assignment 2 — Chapter 2: Sample Spaces and Counting (due Sun September 20, 9:59 PM)',2026,'Course',True)
        self.assertEqual([(r['title'],r['date']) for r in rows],[('Assignment 2','2026-09-20')])
        self.assertEqual(candidates('Sample exam October 20',2026,'Course'),[])

    def test_ranges_and_historical_dates_require_review(self):
        self.assertTrue(candidates('Quiz 1 October 20–22',2026,'Schedule')[0]['review'])
        self.assertTrue(candidates('Quiz 1 October 20, 2025',2026,'Old quiz')[0]['review'])
        self.assertEqual(dates('Quiz 1 October 20, 2025',2026),['2025-10-20'])
        self.assertEqual(dates('Quiz 1 October 20',2026),['2026-10-20'])

    def test_changed_local_file_invalidates_cache_and_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);course=root/'library'/'course-1';course.mkdir(parents=True)
            source=course/'quiz.txt';source.write_text('Quiz 1 due October 4. '+ 'Course details. '*5)
            item={'path':'quiz.txt','verified_in_last_run':True,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
            (course/'manifest.json').write_text(json.dumps({'course_name':'2026F Course','files':{'source':item}}))
            self.assertEqual(len(feed(root/'library',root/'runtime')['events']),1)
            source.write_text('Quiz 1 due October 5. '+ 'Course details. '*5)
            updated=feed(root/'library',root/'runtime')
            self.assertEqual(updated['events'],[])
            self.assertIn('Content changed',updated['coverage'][0]['status'])
    def test_dates_and_invalid_dates(self):
        self.assertEqual(dates('Oct. 1; 9 October 2026; February 30',2026),['2026-10-01','2026-10-09'])

    def test_scheduled_test_list(self):
        text='The tests will occur on the following dates:\nSept. 17\nOct. 1\nOct. 22'
        rows=candidates(text,2026,'Outline')
        self.assertEqual([r['date'] for r in rows],['2026-09-17','2026-10-01','2026-10-22'])

    def test_review_class_is_not_an_exam(self):
        self.assertEqual(candidates('Midterm #1 Review (October 21)',2026,'Course'),[])

    def test_moodle_due_keeps_actual_title(self):
        rows=candidates('Concept Deck\nCompletion requirements\nDue:\nFriday, 9 October 2026, 12:00 AM',2026,'Course overview',True)
        self.assertEqual(rows[0]['title'],'Concept deck')
        self.assertIn('12:00 AM',rows[0]['evidence'])

    def test_tentative_dates_remain_tentative(self):
        rows=candidates('Tentative Testing Schedule:\nOctober 9 -- Quiz #2',2026,'Course')
        self.assertTrue(rows[0]['tentative'])

    def test_recurring_quiz_has_no_invented_date(self):
        rows=candidates('Pop Quizzes\nThe first 5 minutes of almost every class will be a pop quiz.',2026,'Syllabus')
        self.assertIsNone(rows[0]['date'])

    def test_cache_conflicts_and_practice_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);course=root/'library'/'course-1';course.mkdir(parents=True)
            a=course/'a.md';a.write_text('Concept Deck\nDue:\nFriday, 9 October 2026, 12:00 AM')
            b=course/'b.txt';b.write_text('Concept Deck (10%) — Due October 8\nThese assignments are practice. Nothing is submitted: you learn the questions.\nAssignment 4 due October 4')
            manifest={'course_name':'2026F Example','pages':{'https://moodle/assign':{'path':'a.md','title':'Concept Deck','verified_in_last_run':True}},'files':{'https://moodle/file':{'path':'b.txt','title':'Syllabus','verified_in_last_run':True}}}
            (course/'manifest.json').write_text(json.dumps(manifest))
            result=feed(root/'library',root/'runtime')
            decks=[e for e in result['events'] if e['title']=='Concept deck']
            self.assertEqual(len(decks),2)
            self.assertTrue(all(e['conflict_dates'] for e in decks))
            self.assertEqual(next(e for e in result['events'] if e['title']=='Assignment 4')['kind'],'Practice')
            with patch('assessments.extract',side_effect=AssertionError('Unchanged files must not be re-read')):
                again=feed(root/'library',root/'runtime')
            self.assertEqual(result['events'],again['events'])

    def test_unverified_source_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);course=root/'library'/'course-1';course.mkdir(parents=True)
            (course/'manifest.json').write_text(json.dumps({'course_name':'2026F Example','files':{'u':{'path':'missing.pdf','title':'Old outline','verified_in_last_run':False}}}))
            result=feed(root/'library',root/'runtime')
            self.assertEqual(result['events'],[])
            self.assertIn('Not verified',result['coverage'][0]['status'])

if __name__=='__main__':unittest.main()
