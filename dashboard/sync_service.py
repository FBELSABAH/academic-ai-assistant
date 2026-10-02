"""Background dashboard updates reusing the existing Moodle library and exporter."""
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import hashlib
from pathlib import Path
import sys
import threading
import time

PROJECT = Path('/Users/fbelsabah/Documents/academic-ai-assistant')
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / 'scripts'))
from src.config import settings
from src.course_library import CourseLibrary, LoginRequired, atomic_write, authenticated_html, session_from_state
from src.course_export import publish
from src.moodle_browser import _resolve_storage_state_path, launch_chromium
from update_courses import enrolled_courses, term_match
from auth_session import reconnect as persistent_reconnect


def now():
    return datetime.now(timezone.utc).isoformat()


def changed_files(before, after):
    """Only verified observations count; a missing source is not a confirmed deletion."""
    changes = []
    for url, item in after.get('files', {}).items():
        if not item.get('verified_in_last_run'):
            continue
        previous = before.get('files', {}).get(url)
        kind = 'new' if previous is None else 'changed' if previous['sha256'] != item['sha256'] else None
        if kind:
            changes.append({'kind': kind, 'name': Path(item['path']).name, 'source': url, 'sha256': item['sha256']})
    return changes


class SyncService:
    def __init__(self, state_path=None):
        self.on_complete = None
        self.path = state_path or Path(__file__).parent / '.runtime' / 'sync.json'
        self.lock = threading.Lock()
        self.state = {'status': 'idle', 'message': 'Ready to update Moodle.', 'courses': [], 'changes': []}
        if self.path.exists():
            try:
                self.state.update(json.loads(self.path.read_text()))
            except (ValueError, OSError):
                self.state['message'] = 'Previous update status could not be read. You can start a new update.'
        if self.state['status'] in ('running', 'connecting'):
            self.state.update(status='interrupted', message='The app stopped during an update. Completed files are safe; update again to resume.')
        # Upgrade older status files without discarding the last meaningful run.
        self.state.setdefault('change_history', [])
        self._remember_changes(self.state.get('changes', []))

    def _remember_changes(self, changes):
        """Keep a durable timeline separate from the current run's counters."""
        history=self.state['change_history']
        known={item['id'] for item in history}
        observed=self.state.get('started_at') or self.state.get('finished_at') or now()
        for change in changes:
            identity=json.dumps([observed, change.get('course_id'), change.get('source'), change['kind'], change.get('sha256')])
            change_id=hashlib.sha256(identity.encode()).hexdigest()[:24]
            if change_id not in known:
                history.append(dict(change,id=change_id,observed_at=observed))
                known.add(change_id)

    def snapshot(self):
        with self.lock:
            return deepcopy(self.state)

    def update(self, **fields):
        with self.lock:
            self.state.update(fields)
            self._remember_changes(fields.get('changes', []))
            atomic_write(self.path, json.dumps(self.state, indent=2).encode())

    def start(self, reconnect=False):
        with self.lock:
            if self.state['status'] in ('running', 'connecting'):
                return False
            # Persist migrated history before resetting the transient run state.
            self._remember_changes(self.state.get('changes', []))
            self.state.update(status='connecting' if reconnect else 'running', message='Opening Microsoft sign-in…' if reconnect else 'Checking Moodle sign-in…', started_at=now(), finished_at=None, courses=[], changes=[], total=0, completed=0, error_type=None)
            atomic_write(self.path, json.dumps(self.state, indent=2).encode())
        threading.Thread(target=self._run, args=(reconnect,), daemon=True).start()
        return True

    def reconnect(self):
        return persistent_reconnect(self.update)

    def _run(self, reconnect):
        try:
            state_root = PROJECT / 'data' / 'course-export-state'
            state_root.mkdir(parents=True, exist_ok=True)
            with (state_root / 'update.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    self.update(status='busy', message='Another course updater is running. Wait for it to finish, then retry.', finished_at=now())
                    return
                self._sync(reconnect, state_root)
                if self.on_complete and self.snapshot()['status'] in ('complete', 'partial'):
                    # Calendar failures must not turn a successful download into an error.
                    try:
                        self.on_complete()
                    except Exception:
                        pass
        except LoginRequired:
            self.update(status='login_required', message='Sign-in was not completed. Click Reconnect Moodle and finish verification in the browser.', finished_at=now())
        except Exception as exc:
            # Never expose exception strings: remote exceptions can include session tokens.
            self.update(status='error', message=('The sign-in browser could not open. Open Academic Assistant.app on your Mac and retry.' if self.snapshot().get('status') == 'connecting' else 'Update could not finish. Check your connection and retry. Existing files are safe.'), error_type=type(exc).__name__, finished_at=now())

    def _sync(self, reconnect, state_root):
        path = _resolve_storage_state_path()
        if reconnect:
            state = self.reconnect()
        elif path.exists():
            state = json.loads(path.read_text())
        else:
            self.update(status='connecting')
            state = self.reconnect()
        session = session_from_state(state, settings.moodle_home_url)
        results, changes = [], []
        try:
            try:
                discovered = enrolled_courses(session)
            except LoginRequired:
                if reconnect:
                    raise
                session.close()
                self.update(status='connecting', message='Moodle needs a fresh session. Reconnecting with your saved browser profile…')
                state = self.reconnect()
                session = session_from_state(state, settings.moodle_home_url)
                discovered = enrolled_courses(session)
            courses = sorted((c for c in discovered if term_match(c.name, 'F2026')), key=lambda c:c.name)
            if not courses:
                self.update(status='error', message='No Fall 2026 courses were found. Existing files were kept.', finished_at=now())
                return
            self.update(status='running', total=len(courses), message=f'Found {len(courses)} courses. Updating materials…')
            for course in courses:
                self.update(message=f'Updating {course.name}', current_course=course.name)
                result = {'id':course.moodle_course_id, 'name':course.name}
                try:
                    library = CourseLibrary(session, course.url, PROJECT/'data'/'library')
                    before = deepcopy(library.manifest)
                    run = library.sync()
                    library.manifest['course_name'] = course.name
                    library.save_manifest()
                    _, counts = publish(library, Path.home()/'Documents'/'University Courses', 'Fall 2026', state_root)
                    result.update(status=run['status'], verified=run['files_verified'], new=run['new'], updated=run['updated'], unchanged=run['unchanged'], issues=len(run['errors']), recorded_only=len(run['not_downloaded']))
                    for change in changed_files(before, library.manifest):
                        changes.append(dict(change, course=course.name, course_id=course.moodle_course_id))
                    if any('sign' in e['reason'].lower() or 'authenticated' in e['reason'].lower() for e in run['errors']):
                        results.append(result)
                        self.update(courses=results, changes=changes, completed=len(results))
                        raise LoginRequired('Session expired during sync')
                except LoginRequired:
                    raise
                except Exception as exc:
                    result.update(status='error', error_type=type(exc).__name__, message='Could not update this course. Existing files retained.')
                results.append(result)
                self.update(courses=results, changes=changes, completed=len(results))
            failed = sum(c['status'] != 'complete' for c in results)
            self.update(status='partial' if failed else 'complete', message=f'{len(results)-failed} of {len(results)} courses updated. {len(changes)} new or changed files.' + (f' {failed} course(s) need another attempt.' if failed else ''), finished_at=now(), current_course=None)
            report = ['University Courses dashboard update — '+now(), self.snapshot()['message']]
            report += [f"{c['name']}: {c['status']}; {c.get('verified',0)} files verified" for c in results]
            report += ['External/interactive activities are recorded in each internal course manifest; they are not downloaded.', 'Your own files and previous versions are preserved.']
            atomic_write(Path.home()/'Documents'/'University Courses'/'Last Update.txt', ('\n'.join(report)+'\n').encode())
        finally:
            session.close()
