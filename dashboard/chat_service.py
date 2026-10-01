"""Local command routing with persistent proposals, user overrides, and undo."""
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
import re
import secrets
import sqlite3
import time
from zoneinfo import ZoneInfo
from assessments import dates


def key(event):
    return event['course_id']+'|'+event['title'].lower()


def fingerprint(events):
    value=[{'date':e['date'],'sources':[{k:v for k,v in s.items() if k!='verified_at'} for s in e['sources']]} for e in events]
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def parse_date(text, today):
    iso=re.search(r'\b20\d{2}-\d{2}-\d{2}\b',text)
    if iso:
        try:return date.fromisoformat(iso[0]).isoformat(),iso.span()
        except ValueError:return None,None
    explicit=dates(text,today.year)
    if explicit:
        from assessments import DATE
        matches=list(DATE.finditer(text))
        if len(explicit)!=1:return None,None
        return explicit[0],matches[0].span()
    m=re.search(r'\b(today|tomorrow|(?:(?:this|next)\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b',text,re.I)
    if not m:return None,None
    phrase=m[0].lower()
    if phrase=='today':day=today
    elif phrase=='tomorrow':day=today+timedelta(days=1)
    else:
        weekdays=['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
        delta=(weekdays.index(phrase.split()[-1])-today.weekday())%7
        if phrase.startswith('next '):delta+=7
        day=today+timedelta(days=delta)
    return day.isoformat(),m.span()


class ChatService:
    def __init__(self,path):
        self.path=path;path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS overrides (key TEXT PRIMARY KEY, value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, value TEXT NOT NULL, created REAL NOT NULL); CREATE TABLE IF NOT EXISTS actions (id INTEGER PRIMARY KEY, key TEXT, before_value TEXT, after_value TEXT, undone INTEGER DEFAULT 0);')

    def connect(self):
        return sqlite3.connect(self.path,timeout=10)

    def overlay(self,feed):
        result=deepcopy(feed)
        with self.connect() as db:rows=db.execute('SELECT key,value FROM overrides').fetchall()
        for target,raw in rows:
            override=json.loads(raw);sources=[e for e in result['events'] if key(e)==target]
            if override['operation']=='add':
                event=deepcopy(override['event'])
            else:
                event=deepcopy(override['event'])
                event['review']=fingerprint(sources)!=override['fingerprint']
                event['sources']=[s for e in sources for s in e['sources']] or event['sources']
                event['source_changed']=event['review']
                result['events']=[e for e in result['events'] if key(e)!=target]
            event['confirmed_by_user']=True
            result['events'].append(event)
        result['events'].sort(key=lambda e:(e['date'] or '9999',e['course'],e['title']))
        result['user_revision']=hashlib.sha256(json.dumps(rows).encode()).hexdigest()
        return result

    def handle(self,payload,feed,courses,today=None):
        today=today or datetime.now(ZoneInfo('America/Halifax')).date()
        if payload.get('confirm'):return self.confirm(payload['confirm'],feed)
        if payload.get('undo'):return self.undo()
        if payload.get('cancel'):
            with self.connect() as db:db.execute('DELETE FROM proposals WHERE id=?',(payload['cancel'],))
            return {'message':'Cancelled. Nothing was changed.'}
        text=payload.get('message','').strip()
        if not text or len(text)>1000:return {'message':'Please enter a request under 1,000 characters.'}
        if re.fullmatch(r'(?:please )?(?:sync|update)(?: moodle| everything)?[.!]?',text,re.I):return {'action':'sync'}
        if text.lower() in ('undo','undo last change'):return self.undo()
        if not re.match(r'^(?:please\s+)?(?:add|confirm|change|move|set)\b',text,re.I):
            if re.search(r'week|tomorrow|today|upcoming',text,re.I):
                merged=self.overlay(feed)
                start=today;end=today+timedelta(days=6-today.weekday())
                if re.search('tomorrow',text,re.I):start=end=today+timedelta(days=1)
                elif re.search('today',text,re.I):end=today
                rows=[e for e in merged['events'] if e['date'] and start.isoformat()<=e['date']<=end.isoformat()]
                answer='\n'.join(f"• {e['date']} — {e['course']} — {e['title']} ({e['kind']})"+(' — needs checking' if e.get('review') or e.get('tentative') else '') for e in rows)
                recurring=[e for e in merged['events'] if e['title']=='Recurring pop quizzes']
                if recurring:answer+='\n'+ '\n'.join('• '+e['course']+' — recurring pop quizzes; no fixed date found.' for e in recurring)
                return {'message':(answer.strip() or 'No dated assessments found in that period.')+'\nBased on saved sources; this may not include every assessment.'}
            return {'message':'Try “What do I have this week?”, “Add STAT 2910 quiz this Friday”, or “Confirm Concept Deck is due October 8”. I support these schedule commands locally; I am not a general AI tutor.'}
        when,span=parse_date(text,today)
        if not when:return {'message':'Please specify one clear date, such as October 8, 2026, tomorrow, or 2026-10-08. Include the course and assessment again.'}
        if re.search(r'\b\d{1,2}:\d{2}|\b\d{1,2}\s*(?:am|pm)\b',text,re.I):return {'message':'This first version saves dates only, not times. Please resend with the course, assessment, and date; leave out the time.'}
        course_match=re.search(r'\b([A-Z]{2,6})[ -]?(\d{4})(?:-\d{2})?\b',text,re.I)
        course=None
        if course_match:
            code=course_match[1].upper()+' '+course_match[2]
            course=next((c for c in courses if c['code']==code),None)
            if not course:return {'message':'That course is not in your library. Use one of: '+', '.join(c['code'] for c in courses)}
        clean=text[:span[0]]+' '+text[span[1]:]
        clean=re.sub(r'\b[A-Z]{2,6}[ -]?\d{4}(?:-\d{2})?\b',' ',clean,flags=re.I)
        clean=re.sub(r'\b(?:please|add|confirm|change|move|set|the|a|an|is|due|on|to|for|this|next)\b',' ',clean,flags=re.I)
        clean=re.sub(r'\s+',' ',clean).strip(' .,!')
        operation='add' if re.match(r'^(please\s+)?add\b',text,re.I) else 'confirm'
        if operation=='add':
            if not course:return {'message':'Which course? Please resend, for example: “Add STAT 2910 quiz October 8”.'}
            if not clean or clean.lower() in ('stuff','something'):return {'message':'Please give the assessment a name, course, and date.'}
            title=clean[0].upper()+clean[1:]
            event={'id':'user-'+secrets.token_hex(8),'course_id':course['id'],'course':course['name'],'title':title,'date':when,'kind':'Assessment','sources':[],'tentative':False,'review':False,'submission_status':'Unknown','user_note':text,'confirmed_by_user':True}
            target=key(event)
            if any(key(e)==target for e in self.overlay(feed)['events']):return {'message':'An item with that name already exists in this course. Use “Confirm” to change its date, or choose a more specific name.'}
            proposal={'operation':'add','event':event,'target':target}
        else:
            groups={}
            words=set(re.findall(r'[a-z0-9]+',clean.lower()))
            for e in self.overlay(feed)['events']:
                if course and e['course_id']!=course['id']:continue
                title_words=set(re.findall(r'[a-z0-9]+',e['title'].lower()))
                if words and words<=title_words:groups.setdefault(key(e),[]).append(e)
            if len(groups)!=1:return {'message':'I could not identify one assessment. Include its course code and exact name from the dashboard, followed by the date.'}
            target,matched=next(iter(groups.items()))
            if len(matched)>1 and re.search(r'^(In-class test|Technical presentation|Stakeholder presentation)$',matched[0]['title'],re.I):return {'message':'That name refers to several occurrences. This first version cannot safely change one of those from chat. Please use a uniquely named assessment.'}
            raw=[e for e in feed['events'] if key(e)==target]
            event=deepcopy(matched[0]);event.update(date=when,tentative=False,review=False,confirmed_by_user=True,user_note=text)
            event.pop('conflict_dates',None);event.pop('source_changed',None)
            event['sources']=[s for e in raw for s in e['sources']] or event['sources']
            proposal={'operation':'confirm' if raw else 'add','event':event,'target':target,'fingerprint':fingerprint(raw)}
        with self.connect() as db:
            row=db.execute('SELECT value FROM overrides WHERE key=?',(proposal['target'],)).fetchone()
            proposal['expected']=row[0] if row else None
            proposal_id=secrets.token_urlsafe(20)
            db.execute('DELETE FROM proposals WHERE created<?',(time.time()-600,))
            db.execute('INSERT INTO proposals VALUES (?,?,?)',(proposal_id,json.dumps(proposal),time.time()))
        return {'message':f"{operation.title()} {proposal['event']['title']} for {proposal['event']['course']} on {when}?\nThis will be marked “Confirmed by you”. No time or reminder will be set.", 'proposal':proposal_id}

    def confirm(self,proposal_id,feed):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT value,created FROM proposals WHERE id=?',(proposal_id,)).fetchone()
            if not row or time.time()-row[1]>600:return {'message':'That preview expired or was already applied. Please send the request again.'}
            proposal=json.loads(row[0]);target=proposal['target']
            old=db.execute('SELECT value FROM overrides WHERE key=?',(target,)).fetchone();before=old[0] if old else None
            if before!=proposal['expected']:return {'message':'This assessment changed after your preview. Please send your request again.'}
            sources=[e for e in feed['events'] if key(e)==target]
            if proposal['operation']=='confirm' and fingerprint(sources)!=proposal['fingerprint']:return {'message':'The source changed after your preview. Please review it and send the request again.'}
            after=json.dumps({k:v for k,v in proposal.items() if k not in ('expected','target')})
            db.execute('INSERT OR REPLACE INTO overrides VALUES (?,?)',(target,after))
            db.execute('INSERT INTO actions (key,before_value,after_value) VALUES (?,?,?)',(target,before,after))
            db.execute('DELETE FROM proposals WHERE id=?',(proposal_id,))
        return {'message':f"Saved: {proposal['event']['title']} — {proposal['event']['date']}. Marked Confirmed by you.",'changed':True,'undo_available':True}

    def undo(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT id,key,before_value,after_value FROM actions WHERE undone=0 ORDER BY id DESC LIMIT 1').fetchone()
            if not row:return {'message':'There is no saved chat change to undo.'}
            current=db.execute('SELECT value FROM overrides WHERE key=?',(row[1],)).fetchone()
            if not current or current[0]!=row[3]:return {'message':'This item changed elsewhere; I cannot safely undo it.'}
            if row[2] is None:db.execute('DELETE FROM overrides WHERE key=?',(row[1],))
            else:db.execute('UPDATE overrides SET value=? WHERE key=?',(row[2],row[1]))
            db.execute('UPDATE actions SET undone=1 WHERE id=?',(row[0],))
        return {'message':'Undone. The previous information has been restored.','changed':True}
