import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit

from src.course_library import CourseLibrary, LoginRequired, canonical, safe_name

ORIGIN = 'https://moodle.example.edu'
COURSE = ORIGIN + '/course/view.php?id=42'
FILE = ORIGIN + '/pluginfile.php/9/mod_resource/content/1/lecture.pdf'
FOLDER = ORIGIN + '/mod/folder/view.php?id=7'
PDF = b'%PDF-1.4\nfixture lecture\n%%EOF'


def page(content):
    return ('<html><head><title>F2026 Biology</title></head><body>'
            '<a href="/login/logout.php">Log out</a><h1>F2026 Biology</h1>'
            '<main id="region-main">' + content + '</main></body></html>').encode()


class Response:
    def __init__(self, url, body=b'', mime='text/html', status=200, headers=None):
        self.url, self.body, self.status_code = url, body, status
        self.encoding = 'utf-8'
        self.headers = {'Content-Type': mime, **(headers or {})}
    def iter_content(self, size):
        yield self.body
    def close(self):
        pass
    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f'HTTP {self.status_code}')


class Session:
    def __init__(self, routes):
        self.routes, self.calls = routes, []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.routes[url]
        return response(url, kwargs) if callable(response) else response


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def make(self, content=None, file_response=None, extra=None):
        routes = {
            COURSE: Response(COURSE, page(content or f'<a href="{FILE}">Lecture</a>')),
            FILE: file_response or Response(FILE, PDF, 'application/pdf'),
            **(extra or {}),
        }
        session = Session(routes)
        return CourseLibrary(session, COURSE, self.root), session

    def test_nested_folder_and_repeat_are_idempotent(self):
        library, session = self.make(f'<a href="{FOLDER}">Week 1</a>', extra={
            FOLDER: Response(FOLDER, page(f'<a href="{FILE}?forcedownload=1">Lecture</a><a href="{FILE}">Again</a>'))})
        report = library.sync()
        self.assertEqual(report['new'], 1)
        self.assertEqual(report['files_verified'], 1)
        self.assertEqual(report['pages_verified'], 2)
        second = CourseLibrary(session, COURSE, self.root).sync()
        self.assertEqual(second['unchanged'], 1)
        self.assertEqual(len(list(library.root.glob('files/**/*.pdf'))), 1)
        self.assertIn('Lecture', (library.root / 'INDEX.md').read_text())

    def test_changed_file_preserves_previous_version(self):
        library, session = self.make()
        library.sync()
        session.routes[FILE] = Response(FILE, PDF + b' changed', 'application/pdf')
        updated = CourseLibrary(session, COURSE, self.root)
        self.assertEqual(updated.sync()['updated'], 1)
        record = updated.manifest['files'][FILE]
        self.assertEqual(len(record['previous_versions']), 1)
        self.assertTrue((updated.root / record['previous_versions'][0]['path']).exists())
        self.assertEqual(len(list(updated.root.glob('files/**/*.pdf'))), 2)

    def test_valid_etag_skips_body_but_corruption_forces_repair(self):
        library, session = self.make(file_response=Response(FILE, PDF, 'application/pdf', headers={'ETag': 'v1'}))
        library.sync()
        def conditional(url, kwargs):
            if kwargs['headers'].get('If-None-Match') == 'v1':
                return Response(url, status=304)
            return Response(url, PDF, 'application/pdf', headers={'ETag': 'v1'})
        session.routes[FILE] = conditional
        self.assertEqual(CourseLibrary(session, COURSE, self.root).sync()['unchanged'], 1)
        local = library.root / library.manifest['files'][FILE]['path']
        local.write_bytes(b'corrupt')
        repaired = CourseLibrary(session, COURSE, self.root)
        self.assertEqual(repaired.sync()['files_verified'], 1)
        self.assertEqual(local.read_bytes(), PDF)
        self.assertEqual(session.calls[-1][1]['headers'], {})

    def test_login_redirect_stops_and_does_not_save_html_as_pdf(self):
        library, session = self.make(file_response=Response(FILE, status=302, headers={'Location': '/login/index.php'}))
        result = library.sync()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['files_verified'], 0)
        self.assertFalse(list(library.root.glob('files/**/*.*')))
        self.assertEqual(len(session.calls), 2)

    def test_invalid_pdf_and_oversize_report_errors(self):
        library, session = self.make(file_response=Response(FILE, b'not a pdf', 'application/pdf'))
        self.assertEqual(len(library.sync()['errors']), 1)
        library, session = self.make()
        library.MAX_BYTES = 5
        self.assertEqual(library.sync()['status'], 'partial')

    def test_external_and_interactive_links_are_not_followed(self):
        library, session = self.make('<a href="https://external.example/file.pdf">External</a>'
                                    '<a href="/mod/quiz/view.php?id=5">Quiz</a>'
                                    '<a href="/mod/assign/view.php?id=6&action=submit">Submit</a>')
        report = library.sync()
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(len(report['not_downloaded']), 2)

    def test_removed_source_retained_but_not_marked_current(self):
        library, session = self.make()
        library.sync()
        session.routes[COURSE] = Response(COURSE, page('No files now'))
        next_run = CourseLibrary(session, COURSE, self.root)
        next_run.sync()
        item = next_run.manifest['files'][FILE]
        self.assertFalse(item['verified_in_last_run'])
        self.assertTrue((next_run.root / item['path']).exists())

    def test_filename_cannot_escape_library(self):
        library, session = self.make(file_response=Response(FILE, PDF, 'application/pdf',
                    headers={'Content-Disposition': 'attachment; filename="../../outside.pdf"'}))
        library.sync()
        path = (library.root / library.manifest['files'][FILE]['path']).resolve()
        self.assertTrue(path.is_relative_to(library.root.resolve()))
        self.assertNotIn('/', safe_name('../../outside.pdf'))

    def test_resource_redirect_to_pdf_and_assignment_attachment(self):
        resource = ORIGIN + '/mod/resource/view.php?id=5'
        assignment = ORIGIN + '/mod/assign/view.php?id=6'
        library, session = self.make(f'<a href="{resource}">Notes</a><a href="{assignment}">Assignment</a>', extra={
            resource: Response(resource, status=303, headers={'Location': FILE}),
            assignment: Response(assignment, page(f'<a href="{FILE}">Reference</a>'))})
        report = library.sync()
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['pages_verified'], 2)
        self.assertEqual(report['files_verified'], 2)
        self.assertEqual(len(list(library.root.glob('files/**/*.pdf'))), 1)

    def test_external_resource_redirect_does_not_stop_other_downloads(self):
        resource = ORIGIN + '/mod/resource/view.php?id=99'
        library, session = self.make(f'<a href="{resource}">External</a><a href="{FILE}">Lecture</a>', extra={
            resource: Response(resource, status=302, headers={'Location': 'https://external.example/notes.pdf'})})
        result = library.sync()
        self.assertEqual(result['files_verified'], 1)
        self.assertEqual(len(result['not_downloaded']), 1)
        self.assertFalse(any(urlsplit(url).hostname == 'external.example' for url, _ in session.calls))

    def test_unauthenticated_course_is_not_reported_success(self):
        library, session = self.make()
        session.routes[COURSE] = Response(COURSE, b'<html><form id="login">Sign in</form></html>')
        self.assertEqual(library.sync()['status'], 'partial')
        self.assertFalse(library.manifest['files'])


if __name__ == '__main__':
    unittest.main()
