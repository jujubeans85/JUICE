import {escapeHTML as esc,safeURL,recordingKey} from './core.mjs';
import {ConceptEngine,normalize,trackFingerprint,validArtistContext,validOverride,validateConceptExport} from './concept-engine.mjs';
import {ConceptStore} from './concept-store.mjs';
import {loadArtistContext} from './concept-sources.mjs';

const $=s=>document.querySelector(s);
const labels={reviewed:'Reviewed fit',suggested:'Suggested fit',chosen:'Your choice',pending:'Needs context',review:'Review options',conflict:'Check identity'};
const attention=r=>['pending','review','conflict'].includes(r.status);
export class ConceptDesk{
 constructor({registry,history,getTracks,onChange,onSelect}){
  this.engine=new ConceptEngine(registry,history);this.store=new ConceptStore();this.getTracks=getTracks;this.onChange=onChange;this.onSelect=onSelect;this.matches=new Map();this.trackIndex=new Map();this.epoch=0;this.offset=0;this.running=false;this.currentKey=null;
  $('#match-start').onclick=()=>this.start();$('#match-pause').onclick=()=>this.stop();$('#match-filter').onchange=()=>{this.offset=0;this.render()};$('#match-search').oninput=()=>{this.offset=0;this.render()};$('#match-more').onclick=()=>{this.offset+=18;this.render()};
  $('#match-results').onclick=e=>{const b=e.target.closest('[data-match-track]');if(b)this.onSelect(b.dataset.matchTrack)};
  $('#concept-detail').addEventListener('change',e=>{if(e.target.id==='scene-choice')this.choose(e.target.value)});
  $('#concept-detail').addEventListener('click',e=>{if(e.target.closest('[data-reset-match]'))this.reset();if(e.target.closest('[data-fetch-context]')){const t=this.trackIndex.get(this.currentKey);if(t)this.start({records:[t],force:true})}if(e.target.closest('[data-resolve-context]'))this.resolveTopic();});
  this.visibility=()=>{if(document.hidden)this.stop()};document.addEventListener('visibilitychange',this.visibility);
  this.ready=(async()=>{await this.store.ready;await this.refreshTracks();})();
 }
 status(text){$('#match-status').textContent=text;}
 context(track){const c=this.store.memory.contexts.get(normalize(track.artist));return validArtistContext(c)?c:null;}
 get(key){return this.matches.get(key)||null;}
 async refreshTracks(){
  const epoch=++this.epoch,next=new Map(),records=this.getTracks();this.trackIndex=new Map(records.map(t=>[recordingKey(t),t]));
  for(let i=0;i<records.length;i++){
   const t=records[i],key=recordingKey(t);next.set(key,this.engine.match(t,{context:this.context(t),override:this.store.memory.overrides.get(key)}));
   if(i%100===99){await new Promise(r=>setTimeout(r,0));if(epoch!==this.epoch)return false;}
  }
  if(epoch!==this.epoch)return false;this.matches=next;this.render();this.showTrack(this.currentKey);this.onChange?.();return true;
 }
 async ingest(records,{online=true}={}){await this.refreshTracks();this.status(records.length+' imported records checked. '+this.summary()+'.');if(online)void this.start({records});}
 summary(){const values=[...this.matches.values()],counts={};for(const r of values)counts[r.status]=(counts[r.status]||0)+1;return `${counts.reviewed||0} reviewed · ${(counts.suggested||0)+(counts.chosen||0)} suggested/chosen · ${values.filter(attention).length} open`;}
 render(){
  $('#match-summary').textContent=this.matches.size+' exact records · '+this.summary();
  const q=normalize($('#match-search').value),filter=$('#match-filter').value;
  const rows=[...this.matches].filter(([key,r])=>{const t=this.trackIndex.get(key);return(!q||normalize(t.artist+' '+t.title+' '+r.label+' '+r.facets.map(f=>f.label).join(' ')).includes(q))&&(filter==='all'||filter==='open'&&attention(r)||filter==='suggested'&&r.status==='suggested'||filter==='chosen'&&r.status==='chosen'||filter==='reviewed'&&r.status==='reviewed')});
  const page=rows.slice(0,this.offset+18);$('#match-results').innerHTML=page.map(([key,r])=>{const t=this.trackIndex.get(key);return `<button class="match-card" data-match-track="${esc(key)}"><span class="match-state" data-state="${r.status}">${labels[r.status]}</span><strong>${esc(t.title)}</strong><small>${esc(t.artist)}</small><span>${esc(r.label)}</span><small>${esc(r.confidence)}</small></button>`}).join('')||'<p class="micro">No records in this selection.</p>';
  $('#match-more').hidden=page.length>=rows.length;$('#match-visible').textContent=page.length+' / '+rows.length+' records in this view';$('#match-start').disabled=this.running;$('#match-pause').hidden=!this.running;
  $('#match-storage').textContent=this.store.persistent?'Choices and cached context stay on this browser. Export atlas includes them.':'Session storage only. Export atlas to keep your choices and cached context.';
 }
 showTrack(key){
  this.currentKey=key;const t=this.trackIndex.get(key),r=this.get(key),el=$('#concept-detail');if(!t||!r){el.replaceChildren();el.hidden=true;return}el.hidden=false;
  const c=this.context(t),selected=r.override?r.scene_id||'neutral':'auto';
  const options='<option value="auto">Follow the matching engine</option><option value="neutral">Keep context open / neutral</option>'+this.engine.registry.scenes.map(s=>`<option value="${esc(s.id)}">${esc(s.label)}</option>`).join('');
  const candidates=r.candidates.slice(0,3).map(x=>`<li><strong>${esc(x.label)}</strong><small>${x.reasons.map(v=>esc(v.scope+': '+v.value)).join(' · ')}</small></li>`).join('');
  const refs=uniqSources([...(c?.sources||[]),...(r.scene_id?r.visual.source_ids:[]).map(id=>this.engine.registry.sources.find(s=>s.id===id)).filter(Boolean)]);
  el.innerHTML=`<div class="concept-fit"><p class="eyebrow">THE WORLD FOR THIS RECORDING</p><span class="match-state" data-state="${r.status}">${labels[r.status]}</span><h3>${esc(r.label)}</h3><p class="micro">${esc(r.confidence)}${r.date.year!==null?' · '+esc(r.date.year)+' / '+esc(r.date.role):' · recording date open'}</p>${r.facets.length?`<div class="tags">${r.facets.map(f=>`<span title="${esc(f.scope)}">${esc(f.label)}</span>`).join('')}</div>`:''}<label for="scene-choice">Choose its visual world</label><select id="scene-choice">${options}</select>${r.override?'<button class="match-reset" data-reset-match>Use the engine again</button>':''}<details><summary>Why this match?</summary><ul>${r.reasons.map(s=>'<li>'+esc(s)+'</li>').join('')||'<li>More track context is needed. The original recording remains available.</li>'}</ul>${candidates?'<p class="micro">Other possibilities</p><ul class="match-candidates">'+candidates+'</ul>':''}<p class="micro">The fit selects an editorial visual treatment. Artist context does not prove this performance’s genre, location, camera format or historical influence.</p><ul class="match-references">${refs.map(s=>`<li><a href="${esc(safeURL(s.url))}" target="_blank" rel="noopener">${esc(s.title)} ↗</a></li>`).join('')}</ul></details>${c?.status==='ambiguous'?`<label for="artist-context-choice">Which music topic is this artist?</label><select id="artist-context-choice">${c.candidates.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('')}</select><button data-resolve-context>Use this music topic</button>`:''}<button class="match-context-button" data-fetch-context>${c?'Refresh':'Find'} artist context ↗</button><p id="track-match-status" class="micro" role="status"></p></div>`;
  $('#scene-choice').value=selected;
 }
 async choose(value){
  const t=this.trackIndex.get(this.currentKey);if(!t)return;if(value==='auto'){await this.reset();return}
  const o={recording_key:recordingKey(t),fingerprint:trackFingerprint(t),scene_id:value==='neutral'?null:value,updated_at:new Date().toISOString()};if(!validOverride(o,this.engine.registry))return;
  await this.store.put('overrides',o.recording_key,o);await this.refreshTracks();$('#scene-choice')?.focus();
 }
 async reset(){if(!this.currentKey)return;await this.store.remove('overrides',this.currentKey);await this.refreshTracks();$('#scene-choice')?.focus();}
 fresh(c){if(!validArtistContext(c))return false;return Date.now()-Date.parse(c.retrieved_at)<(c.lookup_error?300000:(c.status==='resolved'?30:1)*86400000);}
 async start({records=this.getTracks(),force=false}={}){
  await this.ready;if(this.running){this.status('Matching is already running. Pause it before starting another batch.');return}if(globalThis.navigator?.onLine===false){this.status('Offline: local matches and saved choices are ready. Online context lookup can continue when connected.');return}
  const artists=new Map();for(const t of records){if(t.artist_unresolved)continue;const r=this.get(recordingKey(t));if(!force&&(r?.status==='reviewed'||r?.status==='chosen'||this.fresh(this.context(t))))continue;if(!artists.has(normalize(t.artist)))artists.set(normalize(t.artist),t.artist);}
  const queue=[...artists.values()],batch=queue.slice(0,8);if(!batch.length){this.status('Current records have been checked. Open a record to inspect its evidence or refresh one artist.');return}
  this.running=true;this.controller=new AbortController();this.render();let completed=0,failed=0;
  try{for(const artist of batch){this.controller.signal.throwIfAborted();this.status(`Matching artist context ${completed+1} / ${batch.length}: ${artist}…`);
    try{const c=await loadArtistContext(artist,{signal:this.controller.signal,refresh:force});if(!validArtistContext(c))throw Error('Artist context failed validation.');await this.store.put('contexts',normalize(artist),c);completed++;await this.refreshTracks();}
    catch(e){if(this.controller.signal.aborted||e.name==='AbortError')throw e;failed++;completed++;await this.store.put('contexts',normalize(artist),{schema_version:1,artist,status:'unresolved',genres:[],sources:[],retrieved_at:new Date().toISOString(),candidates:[],lookup_error:String(e.message).slice(0,300)});this.status(artist+': '+e.message+' Local assignments remain available.');}
   }
   this.status(`${completed-failed} artist contexts checked${failed?' · '+failed+' unavailable':''}. ${this.summary()}.${queue.length>batch.length?' Continue matching for the next '+(queue.length-batch.length)+' artists.':''}`);
  }catch(e){if(e.name==='AbortError')this.status('Online matching paused. Completed context and local assignments are saved.');else this.status('Online context stopped: '+e.message)}finally{this.running=false;this.render();}
 }
 stop(){this.controller?.abort();}
 async resolveTopic(){const t=this.trackIndex.get(this.currentKey),title=$('#artist-context-choice')?.value;if(!t||!title)return;$('#track-match-status').textContent='Checking the selected music topic…';try{const c=await loadArtistContext(t.artist,{articleTitle:title});if(!validArtistContext(c))throw Error('Invalid context.');await this.store.put('contexts',normalize(t.artist),c);await this.refreshTracks();}catch(e){$('#track-match-status').textContent=e.message}}
 export(){const artists=new Set(this.getTracks().map(t=>normalize(t.artist))),keys=new Set(this.getTracks().map(recordingKey));return {schema_version:1,engine_version:'1.0.0',registry_version:this.engine.registry.version,contexts:[...this.store.memory.contexts.values()].filter(c=>validArtistContext(c)&&artists.has(normalize(c.artist))),overrides:[...this.store.memory.overrides.values()].filter(o=>validOverride(o,this.engine.registry)&&keys.has(o.recording_key))};}
 async restore(data){validateConceptExport(data,this.engine.registry);for(const c of data.contexts){const old=this.store.memory.contexts.get(normalize(c.artist));if(!old||Date.parse(c.retrieved_at)>Date.parse(old.retrieved_at))await this.store.put('contexts',normalize(c.artist),c)}for(const o of data.overrides){const old=this.store.memory.overrides.get(o.recording_key);if(!old||Date.parse(o.updated_at)>=Date.parse(old.updated_at))await this.store.put('overrides',o.recording_key,o)}await this.refreshTracks();}
 dispose(){this.stop();document.removeEventListener('visibilitychange',this.visibility);}
}
function uniqSources(sources){return [...new Map(sources.map(s=>[s.url,s])).values()];}
