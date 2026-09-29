from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import json
import mimetypes
import secrets
import os
from assessments import feed
from sync_service import SyncService

SYNC = SyncService()
TOKEN = secrets.token_urlsafe(32)
PORT = int(os.environ.get('ACADEMIC_DASHBOARD_PORT','8767'))

ROOT = Path(__file__).parent
LIBRARY = Path('/Users/fbelsabah/Documents/academic-ai-assistant/data/library')
COURSES = [('27355','CS 2520','Computer Organization & Architecture','Systems, circuits & computation','coral'),('27974','STAT 2910','Probability & Mathematical Statistics I','Probability, distributions & inference','blue'),('27973','STAT 2240','Applied Regression Analysis','Models, relationships & prediction','purple'),('27641','MATH 2420','Combinatorics I','Counting, proofs & graphs','gold'),('27151','AMS 1910','Introduction to Data Science','Data, exploration & discovery','green')]

def library():
    result=[]
    for cid,code,name,description,color in COURSES:
        path=LIBRARY / ('course-'+cid) / 'manifest.json'
        manifest=json.loads(path.read_text()) if path.exists() else {}
        files=[]
        for url, item in manifest.get('files',{}).items():
            files.append(dict(name=Path(item['path']).name,title=item.get('title',''),path=item['path'],source=url,size=item.get('bytes',0),verified=item.get('verified_at'),current=item.get('verified_in_last_run',False)))
        result.append(dict(id=cid,code=code,name=name,description=description,color=color,files=files,url=manifest.get('course_url',''),last_run=manifest.get('last_run')))
    return result

class Handler(BaseHTTPRequestHandler):
    def trusted(self):
        return self.headers.get('Host') in (f'127.0.0.1:{PORT}', f'localhost:{PORT}')

    def json_response(self, value, status=200):
        payload=json.dumps(value).encode()
        self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(payload)

    def do_POST(self):
        if not self.trusted() or self.headers.get('Origin') not in (f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}') or not secrets.compare_digest(self.headers.get('X-Dashboard-Token',''), TOKEN):
            self.send_error(403); return
        if self.path not in ('/api/sync', '/api/reconnect'):
            self.send_error(404); return
        started=SYNC.start(reconnect=self.path=='/api/reconnect')
        self.json_response(SYNC.snapshot(), 202 if started else 409)

    def do_GET(self):
        if not self.trusted():
            self.send_error(403); return
        u=urlparse(self.path)
        if u.path=='/api/status':
            self.json_response(dict(SYNC.snapshot(), token=TOKEN, app='academic-assistant', version=3)); return
        if u.path=='/api/assessments':
            try:
                self.json_response(feed(LIBRARY, ROOT/'.runtime'))
            except Exception:
                self.json_response({'error':'Assessment extraction could not complete. Saved files are safe.'},500)
            return
        if u.path=='/api/library':
            try:
                payload=json.dumps(library()).encode()
            except Exception:
                self.send_error(500,'Could not read saved library'); return
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(payload); return
        if u.path=='/file':
            args=parse_qs(u.query); cid=args.get('course',[''])[0]; relative=args.get('path',[''])[0]
            course=next((c for c in library() if c['id']==cid),None)
            manifest_path=LIBRARY/('course-'+cid)/'manifest.json'
            page_paths=[]
            if course and manifest_path.exists():
                page_paths=[p['path'] for p in json.loads(manifest_path.read_text()).get('pages',{}).values()]
            if not course or relative not in [f['path'] for f in course['files']]+page_paths:
                self.send_error(404); return
            base=(LIBRARY/('course-'+cid)).resolve(); path=(base/relative).resolve()
            if not path.is_relative_to(base):
                self.send_error(403); return
        elif u.path in ('/','/index.html'):
            path=ROOT/'index.html'
        else:
            self.send_error(404); return
        if not path.is_file():
            self.send_error(404); return
        self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream'); self.send_header('Content-Length',str(path.stat().st_size)); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers()
        with path.open('rb') as f:
            while chunk:=f.read(1024*1024):
                self.wfile.write(chunk)

if __name__=='__main__':
    print(f'Academic Assistant: http://127.0.0.1:{PORT}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
