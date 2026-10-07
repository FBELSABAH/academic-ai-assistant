from pathlib import Path
import hashlib
import json
import tempfile
import unittest
import zipfile

from study_service import StudyService, chapters, study_request


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.base = self.root/'library'/'course-1'
        self.base.mkdir(parents=True)
        self.course = {'id':'1', 'code':'STAT 2240', 'name':'Applied Regression'}
        self.manifest = {'files':{}, 'last_run':{'status':'complete'}}
        self.service = StudyService(self.root/'library', self.root/'runtime', self.root/'packs')
        self.add('Chapter1.txt', 'First chapter lecture notes about simple regression and examples. '*4)
        self.add('Chapter2.txt', 'Second chapter lecture notes about linear regression and residuals. '*4)
        self.add('Chapter3.txt', 'Third chapter lecture notes about inference and estimation. '*4)
        self.add('Practice.txt', 'Problems on residuals and linear regression. Try before reading solutions. '*4)
        self.add('Outline.txt', 'Course outline and attendance policies. Exam details are not yet announced. '*4)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, name, text, current=True):
        path = self.base/name
        path.write_text(text)
        self.manifest['files']['https://moodle.example/'+name] = {'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'title':name, 'verified_in_last_run':current, 'verified_at':'2026-10-01'}
        self.save()

    def save(self):
        (self.base/'manifest.json').write_text(json.dumps(self.manifest))

    def preview(self, coverage='Chapters 1-2', broad=False):
        return self.service.preview(self.course,'Midterm',coverage,broad,[])

    def test_chat_understands_study_intent_and_course(self):
        result = study_request('I will be studying for my STAT2240 midterm covering chapters 1-2', [self.course])
        self.assertEqual(result, {'course_id':'1','exam':'Midterm','coverage':'chapters 1-2'})
        self.assertIsNone(study_request('Add STAT 2240 quiz tomorrow',[self.course]))
        self.assertEqual(study_request('Prepare a study pack',[self.course])['course_id'],'')
        self.assertEqual(chapters('chapters 1, 2 and 3'), {1,2,3})

    def test_unknown_scope_requires_explicit_broad_choice(self):
        with self.assertRaises(ValueError): self.preview('')
        draft = self.preview('',True)
        self.assertTrue(all(f['selected'] for f in draft['files']))
        self.assertIn('unconfirmed',draft['notes'][0])
        self.assertFalse(self.service.destination.exists())

    def test_chapter_and_topic_matching_are_reviewable(self):
        draft = self.preview()
        self.assertEqual({f['name'] for f in draft['files'] if f['selected']}, {'Chapter1.txt','Chapter2.txt','Outline.txt'})
        self.assertTrue(next(f for f in self.preview('residuals')['files'] if f['name']=='Practice.txt')['selected'])
        self.assertIn('No chapter-labelled', '\n'.join(self.preview('chapter 9')['notes']))

    def test_integrity_stale_and_outside_files_are_excluded(self):
        self.add('Old.txt','Old',False)
        (self.base/'Chapter1.txt').write_text('Corrupt local file')
        outside = self.root/'outside.txt';outside.write_text('Private outside content')
        self.manifest['files']['outside']={'path':'../../outside.txt','verified_in_last_run':True}
        self.save()
        draft = self.preview('',True)
        self.assertEqual(len(draft['excluded']),3)
        self.assertNotIn('Chapter1.txt',[f['name'] for f in draft['files']])

    def test_build_copies_selected_bytes_and_documents_omissions(self):
        draft = self.preview()
        selected = [f for f in draft['files'] if f['selected']]
        result = self.service.build(draft['id'],[f['id'] for f in selected])
        folder = Path(result['folder'])
        self.assertEqual(result['file_count'],3)
        self.assertEqual(len(list(folder.iterdir())),5)
        for f in selected:
            copy = next(p for p in folder.iterdir() if p.name.endswith(f['name']))
            self.assertEqual(copy.read_bytes(),(self.base/f['name']).read_bytes())
        notes = (folder/'00 - Start here.txt').read_text()
        self.assertIn('Chapter3.txt — not selected',notes)
        self.assertIn('https://moodle.example/Chapter1.txt',notes)
        self.assertIn('No matching saved exam entry',notes)
        self.assertIn('not an independently confirmed',notes)
        self.assertIn('Cite filenames',(folder/'00 - ChatGPT prompt.txt').read_text())
        with zipfile.ZipFile(self.service.artifact(draft['id'],True)) as z:
            self.assertEqual(len(z.namelist()),5)
            self.assertTrue(all(n.startswith(folder.name+'/') for n in z.namelist()))
        self.assertEqual(self.service.build(draft['id'],[f['id'] for f in selected]),result)
        self.assertEqual(StudyService(self.root/'library',self.root/'runtime',self.root/'packs').artifact(draft['id']),folder.resolve())

    def test_changed_source_and_invalid_selection_do_not_build(self):
        draft = self.preview()
        with self.assertRaises(ValueError): self.service.build(draft['id'],[])
        with self.assertRaises(ValueError): self.service.build(draft['id'],['unknown'])
        f = next(f for f in draft['files'] if f['name']=='Chapter1.txt')
        self.add('Chapter1.txt','Updated lecture material')
        with self.assertRaisesRegex(ValueError,'changed'): self.service.build(draft['id'],[f['id']])
        self.assertFalse(self.service.destination.exists())

    def test_duplicate_names_have_unique_outputs_and_packs_do_not_overwrite(self):
        (self.base/'other').mkdir()
        self.add('other/Chapter1.txt','Another separate chapter source. '*10)
        draft = self.preview('',True)
        result = self.service.build(draft['id'],[f['id'] for f in draft['files']])
        names = [p.name for p in Path(result['folder']).iterdir()]
        self.assertEqual(len(names),8)
        self.assertEqual(sum(n.endswith('Chapter1.txt') for n in names),2)
        other = self.preview('',True)
        second = self.service.build(other['id'],[f['id'] for f in other['files']])
        self.assertNotEqual(result['folder'],second['folder'])
        self.assertTrue(Path(result['folder']).exists())

    def test_bad_tokens_cannot_access_arbitrary_paths(self):
        for token in ('../anything', '', None, True):
            with self.assertRaises(ValueError): self.service.artifact(token)

    def test_saved_moodle_exam_context_included_and_rechecked(self):
        page=self.base/'exam.md';page.write_text('Midterm covers chapters 1 and 2. Tentative scope. Ask instructor for confirmation.')
        self.manifest['pages']={'https://moodle.example/exam':{'path':'exam.md','verified_in_last_run':True,'sha256':hashlib.sha256(page.read_bytes()).hexdigest(),'title':'Exam announcement'}}
        self.save()
        self.assertIn('Tentative scope',self.service.context(self.course,'Midterm')['context'][0]['excerpts'][0])
        draft=self.preview()
        chosen=[f['id'] for f in draft['files'] if f['selected']]
        page.write_text('Changed exam announcement')
        with self.assertRaisesRegex(ValueError,'Exam notes changed'):self.service.build(draft['id'],chosen)

    def test_unreadable_files_and_conflicting_exam_sources_are_labelled(self):
        self.add('scan.pdf','not a readable PDF')
        event={'course_id':'1','title':'Midterm 1','date':'2026-10-20','review':True,'sources':[{'name':'Outline','evidence':'Tentative midterm date','url':'https://example.test'}]}
        draft=self.service.preview(self.course,'Midterm','all',True,[event])
        self.assertTrue(next(f for f in draft['files'] if f['name']=='scan.pdf')['warning'])
        result=self.service.build(draft['id'],[f['id'] for f in draft['files']])
        notes=(Path(result['folder'])/'00 - Start here.txt').read_text()
        self.assertIn('Needs checking',notes)
        self.assertIn('check this file visually',notes)


if __name__=='__main__': unittest.main()
