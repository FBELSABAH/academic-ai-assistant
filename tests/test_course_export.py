import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from src.course_export import publish, folder_name

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.library = SimpleNamespace(root=self.root/'raw', course_id='1', manifest={
            'course_name':'2026F Test Course (STAT-1000-01)', 'files': {}})
        self.library.root.mkdir()
        self.dest, self.state = self.root/'visible', self.root/'state'
    def tearDown(self):
        self.temp.cleanup()
    def source(self, body, url='url', name='Lecture.pdf'):
        p=self.library.root/name
        p.write_bytes(body)
        self.library.manifest['files'][url]={'path':name,'sha256':hashlib.sha256(body).hexdigest(),'verified_in_last_run':True}
    def run_export(self):
        return publish(self.library,self.dest,'Fall 2026',self.state)
    def test_repeat_and_archive_update(self):
        self.source(b'original')
        folder, report=self.run_export()
        self.assertEqual(report['added'],1)
        self.assertEqual(self.run_export()[1]['unchanged'],1)
        self.source(b'updated')
        self.assertEqual(self.run_export()[1]['replaced'],1)
        self.assertEqual((folder/'Lecture.pdf').read_bytes(),b'updated')
        archived=list((self.dest/'Archive').rglob('*.pdf'))
        self.assertEqual(len(archived),1)
        self.assertEqual(archived[0].read_bytes(),b'original')
    def test_local_edit_is_never_overwritten(self):
        self.source(b'original')
        folder,_=self.run_export()
        (folder/'Lecture.pdf').write_bytes(b'my annotations')
        self.source(b'new version')
        self.assertEqual(self.run_export()[1]['local_edits_preserved'],1)
        self.assertEqual((folder/'Lecture.pdf').read_bytes(),b'my annotations')
        self.assertEqual((folder/'Lecture (2).pdf').read_bytes(),b'new version')
        self.assertEqual(self.run_export()[1]['unchanged'],1)
    def test_existing_unmanaged_filename_preserved(self):
        folder=self.dest/'Fall 2026'/folder_name(self.library.manifest['course_name'])
        folder.mkdir(parents=True)
        (folder/'Lecture.pdf').write_bytes(b'personal')
        self.source(b'moodle')
        self.run_export()
        self.assertEqual((folder/'Lecture.pdf').read_bytes(),b'personal')
        self.assertEqual((folder/'Lecture (2).pdf').read_bytes(),b'moodle')
    def test_unverified_sources_not_published(self):
        self.source(b'file')
        self.library.manifest['files']['url']['verified_in_last_run']=False
        folder,counts=self.run_export()
        self.assertEqual(list(folder.iterdir()),[])

if __name__=='__main__': unittest.main()
