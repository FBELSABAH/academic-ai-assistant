import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import sync_service  # Configures imports for the existing project.
from auth_session import seed_missing_cookies, reconnect


class AuthTests(unittest.TestCase):
    def test_cookie_migration_preserves_newer_browser_cookies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json'
            cookie={'name':'session','domain':'moodle.test','path':'/','value':'old','expires':-1}
            expired=dict(cookie,name='expired',expires=1)
            missing=dict(cookie,name='microsoft')
            path.write_text(json.dumps({'cookies':[cookie,expired,missing]}))
            context=MagicMock();context.cookies.return_value=[dict(cookie,value='new')]
            seed_missing_cookies(context,path)
            context.add_cookies.assert_called_once_with([missing])

    def test_persistent_profile_reused_and_session_saved_privately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/'state.json';profile=root/'auth'
            context=MagicMock();page=MagicMock();context.pages=[page]
            page.url='https://moodle.test/my/';page.content.return_value='authenticated'
            context.cookies.return_value=[];context.storage_state.return_value={'cookies':[]}
            playwright=MagicMock();playwright.chromium.launch_persistent_context.return_value=context
            with patch('playwright.sync_api.sync_playwright') as factory,patch('auth_session._resolve_storage_state_path',return_value=state),patch('auth_session.authenticated_html',return_value=True):
                factory.return_value.__enter__.return_value=playwright
                for _ in range(2):reconnect(lambda **kw:None,auth_root=profile)
            calls=playwright.chromium.launch_persistent_context.call_args_list
            self.assertEqual(calls[0].args,calls[1].args)
            self.assertEqual(calls[0].args,(str(profile/'browser'),))
            self.assertEqual(state.stat().st_mode & 0o777,0o600)
            self.assertEqual(profile.stat().st_mode & 0o777,0o700)
            self.assertEqual(context.close.call_count,2)

    def test_timeout_does_not_replace_saved_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/'state.json';state.write_text('{"cookies":[]}')
            context=MagicMock();context.pages=[MagicMock()];context.cookies.return_value=[]
            with patch('playwright.sync_api.sync_playwright') as factory,patch('auth_session._resolve_storage_state_path',return_value=state):
                factory.return_value.__enter__.return_value.chromium.launch_persistent_context.return_value=context
                with self.assertRaises(sync_service.LoginRequired):
                    reconnect(lambda **kw:None,auth_root=root/'auth',timeout=0)
            self.assertEqual(state.read_text(),'{"cookies":[]}')
            context.storage_state.assert_not_called()
            context.close.assert_called_once()

    def test_expired_session_recovers_once_without_manual_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=root/'session.json';state.write_text('{}')
            service=sync_service.SyncService(root/'status.json')
            with patch('sync_service._resolve_storage_state_path',return_value=state),patch('sync_service.session_from_state') as sessions,patch('sync_service.enrolled_courses',side_effect=[sync_service.LoginRequired('expired'),[]]) as discovery,patch.object(service,'reconnect',return_value={}) as login:
                service._sync(False,root)
            login.assert_called_once()
            self.assertEqual(discovery.call_count,2)
            self.assertEqual(sessions.call_count,2)

if __name__=='__main__':unittest.main()
