import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from src.library_audit import refresh, report, largest_files


class LibraryAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.library = self.root/'library'
        self.database = self.root/'audit.sqlite'
        self.course = self.library/'course-1'
        self.course.mkdir(parents=True)
        self.manifest = {'course_name': 'Example', 'files': {
            'https://example.test/a': {'path': 'files/a.pdf', 'bytes': 42, 'verified_in_last_run': True},
            'https://example.test/b': {'path': 'files/b.pdf', 'bytes': 7}}}
        self.save()

    def save(self):
        (self.course/'manifest.json').write_text(json.dumps(self.manifest))

    def test_idempotency_aggregation_and_ranking(self):
        refresh(self.library, self.database)
        refresh(self.library, self.database)
        row = report(self.database)[0]
        self.assertEqual((row['files'], row['bytes'], row['needs_verification']), (2,49,1))
        self.assertEqual(largest_files(self.database, 1)[0]['byte_count'],42)
        self.assertEqual(report(self.database, "1' OR 1=1 --"), [])

    def test_invalid_snapshot_preserves_previous_report(self):
        refresh(self.library, self.database)
        before = report(self.database)
        self.manifest['files']['https://example.test/a']['path'] = '../../private.pdf'
        self.save()
        with self.assertRaises(ValueError):
            refresh(self.library, self.database)
        self.assertEqual(report(self.database), before)

    def test_empty_course_and_removed_files(self):
        refresh(self.library, self.database)
        self.manifest['files'] = {}
        self.save()
        refresh(self.library, self.database)
        self.assertEqual(report(self.database)[0]['files'],0)
        self.assertEqual(largest_files(self.database),[])

    def test_foreign_key_integrity(self):
        refresh(self.library, self.database)
        with sqlite3.connect(self.database) as db:
            db.execute('PRAGMA foreign_keys=ON')
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO library_files VALUES ('missing','url','title','path',1,1)")

    def test_missing_directory_does_not_clear_database(self):
        refresh(self.library, self.database)
        with self.assertRaises(ValueError):
            refresh(self.root/'missing', self.database)
        self.assertEqual(report(self.database)[0]['files'],2)

    def test_database_failure_rolls_back_replacement(self):
        refresh(self.library, self.database)
        before = report(self.database)
        with sqlite3.connect(self.database) as db:
            db.execute("CREATE TRIGGER reject_insert BEFORE INSERT ON library_files BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
        self.manifest['course_name'] = 'Changed name'
        self.save()
        with self.assertRaises(sqlite3.IntegrityError):
            refresh(self.library, self.database)
        self.assertEqual(report(self.database), before)
