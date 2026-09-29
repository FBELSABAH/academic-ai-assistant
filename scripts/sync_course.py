#!/usr/bin/env python3
"""Sign in if needed, choose one current course, and build a local study library."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import PROJECT_ROOT, settings
from src.course_library import CourseLibrary, LoginRequired, atomic_write, authenticated_html, session_from_state
from src.moodle_browser import _resolve_storage_state_path, launch_chromium
from src.moodle_scraper import MoodleScraper


def browser_login_and_courses():
    from playwright.sync_api import sync_playwright
    path = _resolve_storage_state_path()
    with sync_playwright() as p:
        browser, context = launch_chromium(p, storage_state=path if path.exists() else None)
        try:
            page = context.new_page()
            page.goto(settings.moodle_courses_url, wait_until='domcontentloaded')
            if not authenticated_html(page.content(), page.url, settings.moodle_home_url):
                print('\nClick UPEI Microsoft Account and finish sign-in in the browser.')
                print('Keep your password and verification codes in the browser only.')
                while True:
                    input('Once your Moodle dashboard is visible, return here and press Enter: ')
                    # Sign-in may have completed in a newly opened tab.
                    candidates = [q for q in context.pages if urlsplit(q.url).netloc == urlsplit(settings.moodle_home_url).netloc]
                    if candidates:
                        page = candidates[-1]
                    page.goto(settings.moodle_courses_url, wait_until='domcontentloaded')
                    try:
                        page.wait_for_selector('a[href*="/login/logout.php"], [data-region="usermenu"]', timeout=10000)
                    except Exception:
                        pass
                    if authenticated_html(page.content(), page.url, settings.moodle_home_url):
                        break
                    print('Login is not complete. Finish Microsoft sign-in, then try again.')
            try:
                page.wait_for_selector('a[href*="/course/view.php"]', timeout=20000)
            except Exception:
                pass
            courses = MoodleScraper()._extract_courses_from_html(page.content(), page.url)
            if not courses:
                raise RuntimeError('No course links were visible. Open My courses and retry.')
            state = context.storage_state()
            atomic_write(path, json.dumps(state).encode())
            path.chmod(0o600)
            return state, courses
        finally:
            context.close()
            browser.close()


def term_match(name, term):
    normalized = re.sub(r'[^a-z0-9]', '', name.lower())
    if term.lower() in ('f2026', '2026f'):
        return any(x in normalized for x in ('2026f', 'f2026', 'fall2026', '2026fall'))
    return re.sub(r'[^a-z0-9]', '', term.lower()) in normalized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course-url', help='Exact course URL; otherwise choose a matching course.')
    parser.add_argument('--term', default='F2026', help='Required term when selecting automatically (default F2026).')
    parser.add_argument('--list', action='store_true', help='List available courses without downloading.')
    parser.add_argument('--login', action='store_true', help='Open browser to refresh sign-in and course discovery.')
    parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'data' / 'library')
    args = parser.parse_args()
    state_path = _resolve_storage_state_path()
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    courses = []
    if state and not args.login:
        session = session_from_state(state, settings.moodle_home_url)
        try:
            # Dashboard request is read-only; do not print redirect query parameters.
            r = session.get(settings.moodle_courses_url, timeout=30)
            if r.ok and authenticated_html(r.text, r.url, settings.moodle_home_url):
                courses = MoodleScraper()._extract_courses_from_html(r.text, r.url)
            else:
                state = None
        finally:
            session.close()
    if not state or args.login or (not courses and not args.course_url):
        state, courses = browser_login_and_courses()
    if args.list:
        for course in courses:
            print(f'{course.name}\n  {course.url}')
        return 0
    if args.course_url:
        if urlsplit(args.course_url).netloc != urlsplit(settings.moodle_home_url).netloc:
            raise ValueError('Course URL must use your configured Moodle host.')
        course_url = args.course_url
    else:
        choices = [c for c in courses if term_match(c.name, args.term)]
        if not choices:
            print(f'No visible courses matched {args.term}. Available courses:')
            for c in courses:
                print(f'  {c.name}: {c.url}')
            raise RuntimeError('No matching course. Use --course-url with a current course URL.')
        course = sorted(choices, key=lambda c: c.name)[0]
        course_url = course.url
        print(f'Using course: {course.name}', flush=True)
    session = session_from_state(state, settings.moodle_home_url)
    try:
        library = CourseLibrary(session, course_url, args.output.resolve())
        print('Downloading and verifying course materials. This can take a few minutes.', flush=True)
        report = library.sync()
    finally:
        session.close()
    print(json.dumps(report, indent=2))
    print(f'\nStudy library: {library.root}')
    print(f'Start with: {library.root / "INDEX.md"}')
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nStopped. Verified downloads are retained; rerun to resume.', file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f'Could not complete sync: {exc}', file=sys.stderr)
        sys.exit(1)
