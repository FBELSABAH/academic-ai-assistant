"""Remember Moodle/Microsoft sign-in in an app-specific local browser profile."""
from pathlib import Path
import fcntl
import json
import time
from urllib.parse import urlsplit

from src.config import settings
from src.course_library import LoginRequired, atomic_write, authenticated_html
from src.moodle_browser import _resolve_storage_state_path

AUTH_ROOT = Path.home() / 'Library' / 'Application Support' / 'Academic Assistant' / 'auth'


def seed_missing_cookies(context, state_path):
    """Migrate saved login once without overwriting newer persistent cookies."""
    if not state_path.exists():
        return
    state = json.loads(state_path.read_text())
    existing = {(c['name'], c['domain'], c['path']) for c in context.cookies()}
    missing = [c for c in state.get('cookies', [])
               if (c['name'], c['domain'], c.get('path', '/')) not in existing
               and (c.get('expires', -1) <= 0 or c['expires'] > time.time())]
    if missing:
        context.add_cookies(missing)


def reconnect(update, auth_root=None, timeout=600):
    """Let Microsoft enforce MFA; never capture passwords or automate verification."""
    from playwright.sync_api import sync_playwright
    root = auth_root or AUTH_ROOT
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    with (root / 'profile.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LoginRequired('A sign-in window is already open. Finish that sign-in first.')
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(root / 'browser'), headless=False,
                accept_downloads=False,
            )
            try:
                state_path = _resolve_storage_state_path()
                # Cookie snapshot also retains session cookies when Chromium exits.
                seed_missing_cookies(context, state_path)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(settings.moodle_courses_url, wait_until='domcontentloaded', timeout=60000)
                update(message='Reusing your saved sign-in. Complete Microsoft verification in the browser only if asked.')
                deadline = time.monotonic() + timeout
                clicked = False
                while time.monotonic() < deadline:
                    if not context.pages:
                        raise LoginRequired('Sign-in window closed. Click Reconnect Moodle when ready.')
                    for page in context.pages:
                        try:
                            html, url = page.content(), page.url
                        except Exception:
                            continue
                        if authenticated_html(html, url, settings.moodle_home_url):
                            state = context.storage_state()
                            atomic_write(state_path, json.dumps(state).encode())
                            state_path.chmod(0o600)
                            return state
                        # Only follow UPEI's named SSO link on the configured Moodle host.
                        if not clicked and urlsplit(url).netloc == urlsplit(settings.moodle_home_url).netloc:
                            link = page.get_by_role('link', name='UPEI Microsoft Account', exact=True)
                            if link.count() == 1 and link.is_visible():
                                clicked = True
                                link.click(timeout=10000)
                    time.sleep(0.5)
                raise LoginRequired('Sign-in timed out. Click Reconnect Moodle to try again.')
            finally:
                context.close()
