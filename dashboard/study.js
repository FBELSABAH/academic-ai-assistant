/* Study packs use local source matching with an explicit user-reviewed scope. */
const studyDialog=document.createElement('dialog');
studyDialog.id='studyDialog';
studyDialog.innerHTML='<header><div><div class="eyebrow">FROM YOUR SAVED MOODLE LIBRARY</div><h2 id="studyTitle">Prepare a study pack</h2></div><button class="textbutton" id="studyClose" aria-label="Close study packs">Close</button></header><div id="studyBody"></div>';
document.body.append(studyDialog);
document.getElementById('studyClose').onclick=()=>studyDialog.close();
const studyBody=document.getElementById('studyBody');
let studyBusy=false;

async function studyPost(action,payload){
  if(!dashboardToken)await status();
  const response=await fetch('/api/study/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Dashboard-Token':dashboardToken},body:JSON.stringify(payload)});
  const result=await response.json();
  if(!response.ok)throw Error(result.error||'Please reopen Academic Assistant.app and retry.');
  return result;
}
function studyError(error){
  let box=document.getElementById('studyError');
  if(!box){box=document.createElement('div');box.id='studyError';box.className='study-error';box.setAttribute('role','alert');studyBody.append(box)}
  box.textContent=error.message||'Could not complete this request. Please reopen the app and retry.';
}
async function studyTask(button,work){
  if(studyBusy)return;
  studyBusy=true;const label=button.textContent;button.disabled=true;button.textContent='Preparing…';
  document.getElementById('studyError')?.remove();
  try{await work()}catch(e){studyError(e)}finally{studyBusy=false;button.disabled=false;button.textContent=label}
}
function openStudyPack(initial={}){
  if(studyBusy)return;
  chatOpen(false);
  if(!studyDialog.open)studyDialog.showModal();
  document.getElementById('studyTitle').textContent='Prepare a study pack';
  studyBody.innerHTML=`<p class="study-note" style="margin-top:0">Tell me what you’re studying. I’ll suggest materials from your saved course files, then you choose what goes in the folder.</p><form id="studyForm"><div class="study-grid"><label class="study-field">Course<select id="studyCourse" required><option value="">Choose your course</option>${courses.map(c=>`<option value="${esc(c.id)}" ${c.id===initial.course_id?'selected':''}>${esc(c.code+' — '+c.name)}</option>`).join('')}</select></label><label class="study-field">Exam / assessment<input id="studyExam" required maxlength="100" placeholder="e.g. Midterm 1" value="${esc(initial.exam||'')}"></label><label class="study-field wide">Chapters or topics your instructor specified<textarea id="studyCoverage" rows="3" maxlength="500" placeholder="e.g. Chapters 1–3, or simple linear regression and residuals">${esc(initial.coverage||'')}</textarea></label></div><label class="study-check"><input id="studyAll" type="checkbox" ${initial.all_materials?'checked':''}><span>I don’t know the exact coverage — include all available course materials.<br><span class="study-note">This creates a broad pack; it does not confirm what is on the exam.</span></span></label><div class="study-actions"><button class="primary" id="studyPreview" type="submit">Find my materials →</button><button class="textbutton" type="button" id="studyHistory">My saved packs</button></div></form>`;
  const coverage=document.getElementById('studyCoverage'),all=document.getElementById('studyAll');
  const toggle=()=>{coverage.disabled=all.checked;coverage.required=!all.checked};all.onchange=toggle;toggle();
  const contextButton=document.createElement('button');contextButton.type='button';contextButton.className='textbutton';contextButton.textContent='Look up saved exam details';
  const contextBox=document.createElement('div');contextBox.id='studyContext';
  document.getElementById('studyForm').querySelector('.study-grid').after(contextButton,contextBox);
  contextButton.onclick=()=>studyTask(contextButton,async()=>{const result=await studyPost('context',{course_id:document.getElementById('studyCourse').value,exam:document.getElementById('studyExam').value});contextBox.innerHTML='<div class="study-warning">These are source excerpts, not confirmed coverage. Check the exact exam and any tentative wording.</div>'+studyContextHTML(result.context)});
  document.getElementById('studyHistory').onclick=showStudyHistory;
  document.getElementById('studyForm').onsubmit=e=>{e.preventDefault();const payload={course_id:document.getElementById('studyCourse').value,exam:document.getElementById('studyExam').value,coverage:all.checked?'':coverage.value,all_materials:all.checked};studyTask(document.getElementById('studyPreview'),async()=>renderStudyPreview(await studyPost('preview',payload),payload))};
}
function studyContextHTML(context){
  return context.length?context.map(s=>`<details><summary>${esc(s.name)}</summary>${s.excerpts.map(t=>`<blockquote style="white-space:pre-wrap">${esc(t)}</blockquote>`).join('')}<a href="${esc(s.source)}" target="_blank" rel="noopener">Open Moodle source ↗</a></details>`).join(''):'<p class="study-note">No readable mentions of that exam name were found. Confirm the scope with your instructor, or choose a broad course pack.</p>';
}
function renderStudyPreview(draft,input){
  document.getElementById('studyTitle').textContent=draft.course.code+' · '+draft.exam;
  studyBody.innerHTML=`<div class="eyebrow">REVIEW YOUR MATERIALS</div><p class="study-note">${esc(draft.all_materials?'Broad course pack — exam scope unconfirmed.':'Your coverage: '+draft.coverage)}</p><div class="study-warning">Suggested matches need your review. Add any related assignments, data or solutions that were not matched.</div><div class="study-actions" style="margin:12px 0"><span class="study-count" id="studyCount"></span><button class="textbutton" id="studySelectAll">Select all</button><button class="textbutton" id="studySuggested">Suggested only</button></div><div>${draft.files.map(f=>`<div class="study-file"><input type="checkbox" id="sf-${f.id}" data-study-id="${f.id}" ${f.selected?'checked':''}><label for="sf-${f.id}"><b>${esc(f.name)}</b><small>${esc(f.reason)} · ${(f.size/1048576).toFixed(1)} MB</small>${f.warning?`<small style="color:#9b7139">${esc(f.warning)}</small>`:''}</label><a href="${fileURL(draft.course,f)}" target="_blank" rel="noopener" aria-label="Preview ${esc(f.name)}">View ↗</a></div>`).join('')}</div><details><summary>Source notes, gaps & exam evidence</summary>${draft.notes.map(n=>`<p>${esc(n)}</p>`).join('')}${draft.events.map(e=>`<p><b>${esc(e.title)}</b> · ${esc(e.date||'Date unknown')}${e.review||e.tentative?' · Needs checking':''}</p>${(e.sources||[]).map(s=>`<blockquote>${esc(s.evidence)}<br>${esc(s.name)}</blockquote>`).join('')}`).join('')}${draft.excluded.map(n=>`<p>${esc(n)}</p>`).join('')}</details><p class="study-note">You’ll get the original selected files, a Start Here guide with sources and gaps, and a ChatGPT prompt. Creating another pack preserves your earlier folders.</p><div class="study-actions"><button class="primary" id="studyBuild">Create study pack</button><button class="textbutton" id="studyBack">Change coverage</button></div>`;
  const boxes=()=>[...studyBody.querySelectorAll('[data-study-id]')];
  const evidence=document.createElement('details');evidence.innerHTML='<summary>Exam mentions in saved files & Moodle pages</summary><p class="study-note">Verbatim excerpts; check whether they apply to this exam. Included in Start Here.</p>'+studyContextHTML(draft.context||[]);document.getElementById('studyBuild').parentElement.before(evidence);
  const count=()=>{const chosen=boxes().filter(b=>b.checked);const size=draft.files.filter(f=>chosen.some(b=>b.dataset.studyId===f.id)).reduce((n,f)=>n+f.size,0);document.getElementById('studyCount').textContent=chosen.length+' of '+draft.files.length+' materials · '+(size/1048576).toFixed(1)+' MB';document.getElementById('studyBuild').disabled=!chosen.length};
  boxes().forEach(b=>b.onchange=count);count();
  document.getElementById('studySelectAll').onclick=()=>{boxes().forEach(b=>b.checked=true);count()};
  document.getElementById('studySuggested').onclick=()=>{boxes().forEach(b=>b.checked=draft.files.find(f=>f.id===b.dataset.studyId).selected);count()};
  document.getElementById('studyBack').onclick=()=>openStudyPack(input);
  document.getElementById('studyBuild').onclick=()=>studyTask(document.getElementById('studyBuild'),async()=>renderStudyReady(await studyPost('build',{id:draft.id,selected:boxes().filter(b=>b.checked).map(b=>b.dataset.studyId)})));
}
function renderStudyReady(pack){
  document.getElementById('studyTitle').textContent='Your study pack is ready';
  studyBody.innerHTML=`<div class="eyebrow">SAVED ON YOUR MAC</div><h3>${esc(pack.name)}</h3><p>${pack.file_count} course files + Start Here guide + ChatGPT prompt.</p><div class="study-path">${esc(pack.folder)}</div><div class="study-actions"><button class="primary" id="studyOpenFolder">Open folder in Finder</button><a href="${esc(pack.download)}" download>Download ZIP ↓</a></div><p class="study-note">Open the folder, select its files and upload them into your ChatGPT project. Then paste the text from <b>00 - ChatGPT prompt.txt</b> to begin. If an upload is rejected, use smaller batches or omit unsupported data files. The ZIP is for keeping or sharing the pack.</p><div class="study-actions"><button class="textbutton" id="studyAnother">Prepare another pack</button><button class="textbutton" id="studyHistory">My saved packs</button></div>`;
  document.getElementById('studyOpenFolder').onclick=()=>studyTask(document.getElementById('studyOpenFolder'),()=>studyPost('open',{id:pack.id}));
  document.getElementById('studyAnother').onclick=()=>openStudyPack();
  document.getElementById('studyHistory').onclick=showStudyHistory;
}
async function showStudyHistory(){
  try{
    const r=await fetch('/api/study/packs');if(!r.ok)throw Error('Reopen Academic Assistant.app to load study packs.');
    const packs=await r.json();document.getElementById('studyTitle').textContent='My saved study packs';
    studyBody.innerHTML='<p class="study-note">Snapshots of the materials you selected. Prepare a new pack after updating Moodle to include newer files.</p>'+packs.map((p,i)=>`<div class="study-pack-card"><b>${esc(p.name)}</b><p class="study-note">${p.file_count} materials · ${esc(dateLabel(p.created_at))}</p><button class="textbutton" data-pack="${i}">Open pack →</button></div>`).join('')+(!packs.length?'<p>No study packs yet.</p>':'')+'<button class="primary" id="studyNew">Prepare a study pack</button>';
    studyBody.querySelectorAll('[data-pack]').forEach(b=>b.onclick=()=>renderStudyReady(packs[Number(b.dataset.pack)]));
    document.getElementById('studyNew').onclick=()=>openStudyPack();
  }catch(e){studyError(e)}
}
const studyNav=document.createElement('button');studyNav.innerHTML='<span>✧</span>Study packs';studyNav.onclick=()=>openStudyPack();document.querySelector('nav').append(studyNav);
const studyQuick=document.createElement('button');studyQuick.textContent='Prepare study pack';studyQuick.onclick=()=>openStudyPack();document.getElementById('chatWeek').parentElement.prepend(studyQuick);
