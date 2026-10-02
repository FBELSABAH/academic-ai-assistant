/* App-owned calendar connection; no scheduled Moodle polling. */
let calendarState={}, calendarLoading=false;
function paintCalendar(){
 if(view!=='overview')return;
 let panel=document.getElementById('calendarPanel');
 if(!panel){panel=document.createElement('section');panel.id='calendarPanel';panel.className='sync-panel';document.querySelector('.stats').after(panel)}
 const s=calendarState;
 for(const row of document.querySelectorAll('.status-row'))if(row.textContent.includes('Calendar & reminders'))row.querySelector('span').textContent=s.enabled?'Connected':'Not enabled';
 const signature=JSON.stringify(s);if(panel.dataset.signature===signature)return;panel.dataset.signature=signature;
 panel.innerHTML=`<div class="section-title"><h2>Your university calendar</h2><span class="tag">${s.busy?'SYNCING':s.needs_reconnect?'RECONNECT':s.result==='error'?'RETRY NEEDED':s.result==='attention'?'CHECK ITEMS':s.enabled?'CONNECTED':s.connected?'READY TO ENABLE':'SETUP'}</span></div>
 <p>${esc(s.message||'Loading calendar connection…')}</p>
 <p style="margin-top:8px;font-size:12px">University — Fall 2026 · Moodle deadline times in Halifax time · Document-only dates stay all-day</p>
 <div class="actions" style="margin-top:14px;display:flex;gap:15px;flex-wrap:wrap">
 ${!s.connected||s.needs_reconnect?`<button class="primary" onclick="calendarAction('connect')" ${!s.configured?'disabled':''}>${s.needs_reconnect?'Reconnect Google':'Connect Google Calendar'}</button>`:!s.enabled?'<button class="primary" onclick="calendarPreview(true)">Review & enable syncing</button>':`<button class="primary" onclick="calendarAction('sync')" ${s.busy?'disabled':''}>Sync calendar now</button>`}
 <button class="textbutton" onclick="calendarPreview(false)">Preview dates</button>
 ${s.calendar_url?`<a class="textbutton" href="${esc(s.calendar_url)}" target="_blank" rel="noopener noreferrer">Open Google Calendar ↗</a>`:''}
 ${s.connected&&!s.needs_reconnect?`<button class="textbutton" onclick="calendarAction('connect')" ${s.busy?'disabled':''}>Reconnect Google</button>`:''}
 ${s.connected?`<button class="textbutton" onclick="calendarAction('disconnect')" ${s.busy?'disabled':''}>Disconnect</button>`:''}</div>
 ${s.enabled?'<p style="margin-top:12px;font-size:12px">Syncs after you click Update Moodle and after confirmed planner changes. Keep the app running until syncing finishes.</p>':''}
 ${s.last_sync?`<p style="margin-top:8px;font-size:12px">Last calendar sync: ${esc(dateLabel(s.last_sync))}</p>`:''}
 <p style="margin-top:8px;font-size:12px">Reminders: 24 hours and 1 hour before timed events; 9 a.m. the day before all-day dates. Google Calendar notifications must be enabled on your device.</p>
 ${(s.warnings||[]).length?'<details style="margin-top:12px"><summary>Calendar items needing attention ('+s.warnings.length+')</summary><ul>'+s.warnings.map(w=>'<li>'+esc(w)+'</li>').join('')+'</ul></details>':''}`;
}
async function loadCalendar(){
 if(calendarLoading)return;calendarLoading=true;
 try{const r=await fetch('/api/calendar');if(!r.ok)throw Error();const next=await r.json();const changed=next.last_sync!==calendarState.last_sync;calendarState=next;paintCalendar();if(changed)await loadAssessments()}
 catch(e){const p=document.getElementById('calendarPanel');if(p)p.textContent='Calendar service unavailable. Reopen Academic Assistant.app to load the update.'}
 finally{calendarLoading=false}
}
async function calendarAction(action){
 // Open synchronously so the user's browser permits the sign-in tab.
 const popup=action==='connect'?window.open('about:blank','_blank'):null;
 try{
  if(!dashboardToken)await status();
  const r=await fetch('/api/calendar/'+action,{method:'POST',headers:{'X-Dashboard-Token':dashboardToken}});
  const result=await r.json();if(!r.ok)throw Error(result.error||'Calendar request failed.');
  if(result.url){if(popup)popup.location=result.url;else window.location.assign(result.url)}
  await loadCalendar();
 }catch(e){if(popup)popup.close();modal('Google Calendar',`<p>${esc(e.message)}</p>`)}
}
async function calendarPreview(enable){
 modal('Calendar preview','<p>Checking your saved assessment dates…</p>');
 try{
  const r=await fetch('/api/calendar/preview');const plan=await r.json();if(!r.ok)throw Error(plan.error);
  const rows=items=>items.map(e=>`<li style="margin:12px 0"><b>${esc(e.display_title||e.title)}</b> · ${esc(e.start_at?dateLabel(e.start_at):e.date||'Date unknown')}<br><small>${esc(e.course)}${e.hold_reason?' · '+esc(e.hold_reason):''}</small></li>`).join('');
  document.getElementById('dialogBody').innerHTML=`<p><b>${plan.ready.length} dates eligible for sync</b> to a separate University — Fall 2026 calendar. Exact Moodle times use Halifax time. Document-only dates stay all-day. Day-before reminders are included, plus a one-hour reminder for timed events.</p><ul style="max-height:220px;overflow:auto;padding-left:20px">${rows(plan.ready)||'<li>No eligible dates yet.</li>'}</ul><details><summary>${plan.held.length} items held back</summary><ul style="max-height:200px;overflow:auto;padding-left:20px">${rows(plan.held)}</ul></details><p>Uncertain dates, practice work, past dates, and ambiguous repeated names stay out. Moodle event IDs distinguish recurring tests. Existing events are kept if their sources become uncertain. Changes made in Google are preserved.</p>${enable?'<button id="enableCalendar" class="primary" style="float:none;margin-bottom:15px">Enable & sync these dates</button>':''}`;
  const b=document.getElementById('enableCalendar');if(b)b.onclick=()=>{document.getElementById('dialog').close();calendarAction('enable')};
 }catch(e){document.getElementById('dialogBody').textContent=e.message||'Could not load the calendar preview.'}
}
const beforeCalendarRender=render;
render=function(){beforeCalendarRender();paintCalendar()};
loadCalendar();setInterval(loadCalendar,4000);
