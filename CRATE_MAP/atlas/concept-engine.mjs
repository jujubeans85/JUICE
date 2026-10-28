import {recordingKey, safeURL} from './core.mjs';
import {ERA_THEMES, themeForYear} from './era-theme.mjs';

export const ENGINE_VERSION='1.0.0';
export const normalize=s=>String(s??'').normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase().replace(/[×]/g,' x ').replace(/&/g,' and ').replace(/[’'`]/g,'').replace(/[^\p{L}\p{N}]+/gu,' ').trim().replace(/\s+/g,' ');
const list=v=>(Array.isArray(v)?v.slice(0,100).filter(x=>typeof x==='string'):typeof v==='string'?[v]:[]).flatMap(s=>s.split(/[,;|]/).map(x=>x.trim()).filter(Boolean));
const uniq=a=>[...new Set(a)];
const names=v=>uniq(list(v).slice(0,100).map(normalize).filter(Boolean));
const hasTerm=(text,term)=>(' '+text+' ').includes(' '+term+' ');
const allYears=v=>typeof v==='number'&&Number.isInteger(v)?[v]:typeof v==='string'&&/^\d{4}(?:-\d{2}(?:-\d{2})?)?$/.test(v.trim())?[Number(v.slice(0,4))]:[];
const meaningfulYear=v=>allYears(v).find(y=>y>=1000&&y<=new Date().getFullYear()+1)??null;
const youtubeKey=url=>{try{const u=new URL(url);let id;if(['youtube.com','www.youtube.com','m.youtube.com','www.youtube-nocookie.com'].includes(u.hostname))id=u.searchParams.get('v')||u.pathname.match(/^\/(?:embed|shorts)\/([\w-]{11})$/)?.[1];else if(u.hostname==='youtu.be')id=u.pathname.slice(1);return /^[\w-]{11}$/.test(id||'')?'youtube:'+id:null}catch{return null}};
export function exactKeys(t){return uniq([recordingKey(t),youtubeKey(t.url)].filter(Boolean));}
export function trackFingerprint(t){
 const fields=[recordingKey(t),normalize(t.artist),normalize(t.title),normalize(t.version),t.original_release_year,t.recording_year,t.release_year,t.year,names(t.genres||t.genre||t.tags),names(t.instruments),names(t.scenes),names(t.formats)];if(t.source_release_date)fields.push({source_release_date:t.source_release_date});const value=JSON.stringify(fields);
 let h=2166136261;for(let i=0;i<value.length;i++){h^=value.charCodeAt(i);h=Math.imul(h,16777619)}return(h>>>0).toString(16).padStart(8,'0');
}

export function validateRegistry(r){
 if(r?.schema_version!==1||typeof r.version!=='string'||!Array.isArray(r.families)||!Array.isArray(r.scenes)||!Array.isArray(r.concepts)||!Array.isArray(r.sources)||!Array.isArray(r.recording_bindings)||!r.node_bindings)throw Error('Invalid concept registry.');
 for(const key of ['families','scenes','concepts','sources'])if(new Set(r[key].map(x=>x.id)).size!==r[key].length)throw Error('Duplicate concept registry ID.');
 const families=new Set(r.families.map(x=>x.id)),scenes=new Set(r.scenes.map(x=>x.id)),sources=new Set(r.sources.map(x=>x.id)),themes=new Set(ERA_THEMES.map(t=>t.id));
 for(const f of r.families)if(!themes.has(f.id)||!f.visual||f.source_ids.some(id=>!sources.has(id)))throw Error('Unresolved visual family.');
 for(const s of r.scenes)if(!families.has(s.family_id)||s.source_ids.some(id=>!sources.has(id))||s.cues.some(c=>!['genres','instruments','formats','scenes'].includes(c.channel)||!Array.isArray(c.terms)||!c.terms.every(t=>typeof t==='string'&&t.length<=100)||!Number.isFinite(c.weight)||c.weight<0||c.weight>10))throw Error('Invalid scene rule.');
 for(const b of r.recording_bindings)if(!scenes.has(b.scene_id)||!r.node_bindings[b.node_id]||typeof b.recording_key!=='string'||!b.artist_aliases?.length||!b.title_aliases?.length)throw Error('Invalid exact recording binding.');
 for(const b of Object.values(r.node_bindings))if(!scenes.has(b.scene_id))throw Error('Unknown node scene.');
 return r;
}

export function dateEvidence(track){
 // Creation/upload/check dates and artist biography dates are intentionally absent.
 const fields=[['recording_year','performance / recording'],['original_release_year','original release'],['release_year','release'],['year','supplied release metadata'],['source_release_date','source release']];
 for(const [field,role]of fields){const value=field==='source_release_date'&&typeof track[field]==='string'?track[field].slice(0,10):track[field],year=meaningfulYear(value);if(year!==null)return {year,role,field,scope:'imported metadata',verified:false};}
 return {year:null,role:'recording / release date unresolved',field:null,scope:'unresolved',verified:false};
}

export function signalsFor(track,context){
 const signals={genres:[],instruments:[],formats:[],scenes:[]};
 const push=(ch,values,scope,weight=1,source=null)=>{for(const value of names(values))signals[ch].push({value,scope,weight,source});};
 push('genres',track.genres||track.genre||track.tags,'imported metadata');push('instruments',track.instruments,'imported metadata');push('scenes',track.scenes,'imported metadata');push('formats',track.formats||track.recording_type,'imported metadata');
 const version=normalize(track.version);if(version)signals.formats.push({value:version,scope:'version label',weight:1,source:null});
 // Titles, lyrics, uploader names, curation prose and artist nationalities are not genre classifiers.
 if(!track.artist_unresolved&&validArtistContext(context)&&normalize(context.artist)===normalize(track.artist)&&context.status==='resolved')push('genres',context.genres,'artist context',.65,context.sources[0]?.url||null);
 return signals;
}
export function validArtistContext(c){
 return Boolean(c&&c.schema_version===1&&typeof c.artist==='string'&&c.artist.length<=300&&['resolved','ambiguous','unresolved'].includes(c.status)&&Array.isArray(c.genres)&&c.genres.length<=60&&c.genres.every(g=>typeof g==='string'&&g.length<=120)&&Array.isArray(c.sources)&&c.sources.length<=12&&c.sources.every(s=>typeof s.title==='string'&&typeof s.url==='string'&&safeURL(s.url)!=='#'&&/^https:\/\/en\.wikipedia\.org\//.test(s.url))&&typeof c.retrieved_at==='string'&&Number.isFinite(Date.parse(c.retrieved_at))&&(!c.candidates||Array.isArray(c.candidates)&&c.candidates.length<=12&&c.candidates.every(v=>typeof v==='string'&&v.length<=220)));
}
export function validOverride(o,registry){return Boolean(o&&typeof o.recording_key==='string'&&o.recording_key.length<=3000&&typeof o.fingerprint==='string'&&/^[a-f0-9]{8}$/.test(o.fingerprint)&&typeof o.updated_at==='string'&&Number.isFinite(Date.parse(o.updated_at))&&(o.scene_id===null||registry.scenes.some(s=>s.id===o.scene_id)));}
export function validateConceptExport(data,registry){
 if(!data||data.schema_version!==1||!Array.isArray(data.contexts)||data.contexts.length>20000||!data.contexts.every(validArtistContext)||!Array.isArray(data.overrides)||data.overrides.length>50000||!data.overrides.every(o=>validOverride(o,registry)))throw Error('Invalid concept matching export.');return data;
}

export class ConceptEngine{
 constructor(registry,history){
  this.registry=validateRegistry(registry);this.history=history;this.families=new Map(registry.families.map(f=>[f.id,f]));this.scenes=new Map(registry.scenes.map(s=>[s.id,s]));this.nodes=new Map((history?.nodes||[]).map(n=>[n.id,n]));this.bindings=new Map(registry.recording_bindings.map(b=>[b.recording_key,b]));
  this.rules=registry.scenes.map(s=>({...s,cues:s.cues.map(c=>({...c,terms:c.terms.map(normalize)}))}));this.facets=registry.concepts.map(c=>({...c,terms:c.terms.map(normalize)}));
 }
 visual(scene,fallbackFamily='afterworlds'){
  const family=this.families.get(scene?.family_id||fallbackFamily)||this.families.get('afterworlds'),base=family.visual;
  return {...base,...scene?.visual,family_id:family.id,scene_id:scene?.id||null,label:scene?.label||family.label,globe:{...base.globe,...scene?.visual?.globe},source_ids:uniq([...family.source_ids,...(scene?.source_ids||[])])};
 }
 forNode(node){
  const b=this.registry.node_bindings[node?.id];if(!b)return null;const scene=this.scenes.get(b.scene_id);return {scene_id:scene.id,label:scene.label,status:'reviewed',confidence:'reviewed editorial fit',reason:b.note,visual:this.visual(scene),historical_sources:node.sources||[],node_id:node.id};
 }
 match(track,{context,override}={}){
  const key=recordingKey(track),fingerprint=trackFingerprint(track),date=dateEvidence(track),signals=signalsFor(track,context),facets=[];
  for(const c of this.facets){const hit=signals[c.channel].find(s=>c.terms.some(t=>c.channel==='formats'?hasTerm(s.value,t):s.value===t));if(hit)facets.push({id:c.id,label:c.label,dimension:c.dimension,scope:hit.scope,source:hit.source});}
  // Preserve unfamiliar supplied concepts even before the visual vocabulary grows.
  for(const channel of ['genres','instruments','scenes'])for(const hit of signals[channel])if(!facets.some(f=>f.id==='term:'+channel+':'+hit.value))facets.push({id:'term:'+channel+':'+hit.value,label:hit.value,dimension:channel==='genres'?'sound':channel==='instruments'?'instrument':'scene',scope:hit.scope,source:hit.source});
  for(const place of Array.isArray(track.places)?track.places.slice(0,16):[])if(place&&typeof place.name==='string'&&place.name.length<=180&&typeof place.role==='string'&&place.role.length<=180)facets.push({id:'place:'+normalize(place.name)+':'+normalize(place.role),label:place.name+' / '+place.role,dimension:'place',scope:'imported geographic role',source:safeURL(place.source_url)==='#'?null:safeURL(place.source_url)});
  const out={engine_version:ENGINE_VERSION,registry_version:this.registry.version,recording_key:key,fingerprint,date,facets,scene_id:null,label:'Context still open',status:'pending',confidence:'insufficient context',reasons:[],candidates:[],historical_node_id:null,visual:this.visual(null,date.year===null?'afterworlds':themeForYear(date.year).id),scope:'Editorial visual assignment; no musical influence or audio analysis inferred.'};
  const binding=exactKeys(track).map(k=>this.bindings.get(k)).find(Boolean);
  const workTitle=value=>normalize(String(value).replace(/\s*\([^)]*\)\s*$/,'').replace(/\s+[-–—]\s+(?:live|remaster(?:ed)?|official|audio|video).*$/i,''));
  const conflict=binding&&(!binding.artist_aliases.some(a=>normalize(a)===normalize(track.artist))||!binding.title_aliases.some(a=>workTitle(a)===workTitle(track.title)));
  const boundNode=binding&&!conflict?this.nodes.get(binding.node_id):null;
  if(boundNode){out.historical_node_id=boundNode.id;if(Number.isInteger(boundNode.start))out.date={year:boundNode.start,end:boundNode.end,role:'reviewed event',scope:'reviewed event',field:'start',verified:true};for(const c of this.facets)if(!out.facets.some(x=>x.id===c.id)&&(boundNode.tags||[]).some(tag=>c.terms.includes(normalize(tag))))out.facets.push({id:c.id,label:c.label,dimension:c.dimension,scope:'reviewed event tags',source:boundNode.id});}
  const overrideValid=validOverride(override,this.registry)&&override.recording_key===key&&override.fingerprint===fingerprint;
  if(overrideValid){const scene=this.scenes.get(override.scene_id);return {...out,status:'chosen',scene_id:scene?.id||null,label:scene?.label||'Neutral / keep context open',confidence:'your choice',reasons:['Saved for this exact recording and metadata version.',...(conflict?['The source identity still conflicts with its title or artist; choosing a visual does not resolve that conflict.']:[])],visual:this.visual(scene),override:true};}
  if(conflict)return {...out,status:'conflict',confidence:'identity needs review',reasons:['The exact source is already bound to a different artist or work title. The engine has not reused that recording’s concepts.']};
  if(binding){const scene=this.scenes.get(binding.scene_id),n=this.nodes.get(binding.node_id),f=this.forNode(n);
   return {...out,status:'reviewed',scene_id:scene.id,label:scene.label,confidence:'reviewed editorial fit',historical_node_id:binding.node_id,visual:f.visual,reasons:['Exact recording source matches the reviewed event '+binding.node_id+'.','Historical facts retain the event’s own evidence; this visual fit is an editorial choice.'],date:n?.start!==null&&Number.isInteger(n?.start)?{year:n.start,end:n.end,role:'reviewed event',scope:'reviewed event',field:'start',verified:true}:out.date};
  }
  for(const scene of this.rules){let score=0;const reasons=[];const scopes=new Set();
   for(const cue of scene.cues){const hits=signals[cue.channel].filter(s=>cue.terms.some(t=>cue.channel==='formats'?hasTerm(s.value,t):s.value===t));if(!hits.length)continue;const hit=hits.sort((a,b)=>b.weight-a.weight)[0];score+=cue.weight*hit.weight;scopes.add(hit.scope);reasons.push({channel:cue.channel,value:hit.value,scope:hit.scope,source:hit.source});}
   if(score>0)out.candidates.push({scene_id:scene.id,label:scene.label,score:Math.round((score+(scene.priority||0)*.1)*100)/100,reasons,scopes:[...scopes],fallback:Boolean(scene.fallback)});
  }
  out.candidates.sort((a,b)=>b.score-a.score||a.scene_id.localeCompare(b.scene_id));out.candidates=out.candidates.slice(0,6);
  let eligible=out.candidates.filter(c=>c.score>=3||c.score>=2.5&&c.scopes.includes('artist context'));if(eligible.some(c=>!c.fallback))eligible=eligible.filter(c=>!c.fallback);
  const top=eligible[0],second=eligible[1];
  if(top&&(!second||top.score-second.score>=1.5)){
   const scene=this.scenes.get(top.scene_id);out.status='suggested';out.scene_id=scene.id;out.label=scene.label;out.confidence=top.scopes.every(s=>s==='artist context')?'artist-context suggestion':'metadata suggestion';out.visual=this.visual(scene);out.reasons=top.reasons.map(r=>`${r.scope}: ${r.channel} → ${r.value}.`);
  }else if(out.candidates.length){out.status='review';out.confidence='several possibilities / limited evidence';out.reasons=['The engine kept the result open rather than choosing between close or weak matches.'];}
  if(date.year!==null)out.reasons.push(`${date.year} is ${date.role}, not an assumed camera or style origin.`);
  if(override&&!overrideValid)out.reasons.push('A previous choice no longer matches this recording’s metadata. Review it again.');
  if(context?.status==='ambiguous')out.reasons.push('The artist name has multiple music-topic matches. Choose the right context before using its genres.');
  if(!top&&date.year!==null){out.label=themeForYear(date.year).label+' / era fallback';out.confidence='date-only atmosphere';}
  return out;
 }
}

export function visualContrast(a,b){
 const brightness=hex=>{const v=hex.slice(1).match(/../g).map(n=>parseInt(n,16));return(v[0]*.2126+v[1]*.7152+v[2]*.0722)/255};
 return ['pattern','type','frame'].filter(k=>a[k]!==b[k]).concat(Math.abs(brightness(a.globe.mid)-brightness(b.globe.mid))>.22?['light / dark mass']:[],a.shine>=30!==b.shine>=30?['surface finish']:[]);
}
