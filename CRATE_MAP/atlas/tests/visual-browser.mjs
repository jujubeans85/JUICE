const $=s=>document.querySelector(s),frame=$('#app'),report=$('#checks');
const until=async predicate=>{const end=Date.now()+5000;while(!predicate()&&Date.now()<end)await new Promise(r=>setTimeout(r,25));return predicate()};
const next=()=>new Promise(r=>setTimeout(r,90));
let ready=false;
async function load(){
 ready=false;$('#run').disabled=true;report.textContent='';$('#status').textContent='Loading the actual application…';
 frame.width=$('#width').value;frame.height=880;
 const html=await fetch('../index.html').then(r=>r.text()),base=new URL('../',location.href).href;
 // Test-only media/canvas shims run before the app module. CSS media-rule
 // inspection is separate: a synthetic matchMedia result cannot emulate Safari.
 let shim="history.replaceState=()=>{};";
 if($('#reduced').checked)shim+=`const nativeMatch=window.matchMedia.bind(window);window.matchMedia=q=>q.includes('prefers-reduced-motion')?{matches:true,media:q,addEventListener(){},removeEventListener(){}}:nativeMatch(q);`;
 if($('#no-canvas').checked)shim+=`HTMLCanvasElement.prototype.getContext=function(){return null};`;
 frame.srcdoc=html.replace('<head>',`<head><base href="${base}"><script>${shim}<\/script>`);
 const deadline=Date.now()+30000;
 while(Date.now()<deadline){await new Promise(r=>setTimeout(r,100));const d=frame.contentDocument;if(d?.querySelector('#coverage-summary')?.textContent.includes('crates')&&d.querySelector('#research-summary')?.textContent.includes('queued')){
  const pause=d.querySelector('#research-toggle');if(pause.textContent==='Pause research')pause.click();ready=true;break;
 }}
 $('#run').disabled=!ready;$('#status').textContent=ready?'Ready · '+frame.width+'px iframe · public data only':'App did not become ready in 30 seconds. Inspect the preview and browser console.';
}
$('#load').onclick=load;
$('#width').onchange=async()=>{frame.width=$('#width').value;await next();$('#status').textContent=frame.width+'px viewport. Run checks or inspect the layout.'};
$('#run').onclick=async()=>{
 if(!ready)return;$('#run').disabled=true;report.textContent='';$('#status').textContent='Checking layouts and interactions…';const d=frame.contentDocument,w=frame.contentWindow,rows=[];
 const check=(ok,message)=>rows.push((ok?'PASS':'FAIL')+' · '+message),css=e=>w.getComputedStyle(e),select=(id,value)=>{const e=d.getElementById(id);e.value=value;e.dispatchEvent(new w.Event('change',{bubbles:true}))};
 try{
  if(w.innerWidth<=1020)check(!d.querySelector('#catalogue-browse').open,'Compact entrance collapses record browsing');
  for(const width of [320,390,768,1024,1440]){frame.width=width;await next();check(d.documentElement.scrollWidth<=w.innerWidth,`${width}px: no document horizontal overflow`);check(parseFloat(css(d.querySelector('#search')).fontSize)>=16,`${width}px: search avoids iOS focus zoom`);const r=d.querySelector('.world').getBoundingClientRect();check(r.width>0&&r.right<=width+1,`${width}px: world remains within viewport`);}
  frame.width=$('#width').value;await next();
  const bodyKeys=['--bg','--text','--muted','--accent','--display'],shell=bodyKeys.map(k=>css(d.body).getPropertyValue(k));
  const rectangles=[];
  for(const mode of ['mosaic','deco','pop','afterworlds']){select('appearance',mode);await next();check(d.body.dataset.material===mode,mode+': working material selection');check(JSON.stringify(bodyKeys.map(k=>css(d.body).getPropertyValue(k)))===JSON.stringify(shell),mode+': fixed reading/navigation tokens');const r=d.querySelector('.world').getBoundingClientRect();rectangles.push([r.width,r.height]);}
  check(rectangles.every(r=>r.every((n,i)=>Math.abs(n-rectangles[0][i])<2)),'Material switch keeps the world frame geometry stable');select('appearance','auto');
  check(!d.querySelector('#atlas-tools').open,'Advanced tools closed on initial load');
  const search=d.querySelector('#search');search.value='Gregory Porter';search.dispatchEvent(new w.Event('input',{bubbles:true}));await next();check(d.querySelector('#catalogue-browse').open,'Search reveals the record list');
  const result=[...d.querySelectorAll('[data-track]')].find(e=>e.textContent.includes("It's Probably Me"));check(Boolean(result),'Exact reviewed recording remains searchable');result?.click();await next();
  check(d.querySelector('#detail').textContent.includes('Gregory Porter'),'Record selection updates the detail panel');check(d.querySelector('#detail .sources'),'Evidence disclosure remains available');check(d.querySelector('#detail [data-play]'),'Verified playback action remains available');
  check(!d.querySelector('#concept-inspector').hidden,'Concept inspector remains reachable');
  const toolsLink=d.querySelector('[data-open-tools]');toolsLink.addEventListener('click',e=>e.preventDefault(),{once:true});toolsLink.click();await next();check(d.querySelector('#atlas-tools').open,'Header opens advanced research and catalogue controls');
  check(d.querySelector('#research-toggle')&&d.querySelector('#match-start')&&d.querySelector('#coverage-open')&&d.querySelector('#genre'),'Research, matching, coverage and genres retained');
  d.querySelector('#export').focus();d.querySelector('#export').click();await until(()=>d.querySelector('#backup-dialog').open);check(d.querySelector('#backup-dialog').open,'Backups opens the existing recovery panel');await until(()=>!d.querySelector('#backup-dialog [data-close]').disabled);d.querySelector('#backup-dialog [data-close]').click();await next();check(d.activeElement===d.querySelector('#export'),'Dialog returns focus to Backups');
  check([...d.querySelectorAll('dialog')].every(e=>d.getElementById(e.getAttribute('aria-labelledby'))),'Every dialog has an accessible heading');
  const controls=[...d.querySelectorAll('button,select,input[type=search],summary')].filter(e=>e.getClientRects().length&&css(e).visibility!=='hidden');
  check(controls.every(e=>e.getBoundingClientRect().height>=43.5),'Visible controls have at least 44px target height');
  const small=[...d.querySelectorAll('p,small,label,summary,.badge,.eyebrow,.panel-label')].filter(e=>e.getClientRects().length&&!e.classList.contains('sr-only')).filter(e=>parseFloat(css(e).fontSize)<11);
  check(!small.length,'Visible labels and reading text are at least 11px');
  if($('#reduced').checked)check(d.querySelector('#globe').dataset.motion==='paused','Synthetic reduced-motion preference starts the renderer paused');
  const text=d.querySelector('#globe-status').textContent;
  if($('#no-canvas').checked){check(text.includes('unavailable'),'No-canvas failure has a readable timeline fallback');check(['rotate','zoom-in','zoom-out','reset'].every(id=>d.getElementById(id).disabled),'Unavailable rendering disables globe controls');}
  else{check(d.querySelector('#globe canvas'),'Globe has an active canvas');d.querySelector('#rotate').click();await next();d.querySelector('#globe').dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true,cancelable:true}));await next();check(d.querySelector('#globe').dataset.motion==='paused','Keyboard globe navigation pauses rotation and updates control state');}
  // Return to a reviewable world, with no user-facing modal left open.
  d.querySelector('#atlas-tools').open=false;search.value='';search.dispatchEvent(new w.Event('input',{bubbles:true}));if(w.innerWidth<=1020)d.querySelector('#catalogue-browse').open=false;
  const failed=rows.filter(r=>r.startsWith('FAIL')).length;$('#status').textContent=`${rows.length-failed} passed · ${failed} failed · ${$('#width').value}px preview`;
 }catch(e){rows.push('FAIL · '+e.message);$('#status').textContent='Acceptance run interrupted';}
 report.textContent=rows.join('\n');$('#run').disabled=false;
};
await load();
