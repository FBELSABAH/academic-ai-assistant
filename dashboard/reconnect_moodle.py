"""Run from the Mac launcher when the agent's sandbox cannot open Chromium."""
import json
from urllib.request import Request, urlopen
from sync_service import SyncService


class LoginWindow(SyncService):
    def update(self, **fields):
        if fields.get('message'):
            print(fields['message'], flush=True)


if __name__ == '__main__':
    try:
        LoginWindow().reconnect()
        print('Moodle connected. Starting your course update…', flush=True)
        base='http://127.0.0.1:8767'
        with urlopen(base+'/api/status',timeout=10) as response:
            status=json.load(response)
        request=Request(base+'/api/sync',method='POST',headers={'Origin':base,'X-Dashboard-Token':status['token']})
        with urlopen(request,timeout=10) as response:
            print(json.load(response)['message'])
        print('You can close this window and follow progress in the dashboard.')
    except Exception as exc:
        print(f'Could not complete reconnection ({type(exc).__name__}). Open the dashboard and retry.')
        raise SystemExit(1)
