import {normalize} from './concept-engine.mjs';
import {recordingKey} from './core.mjs';
const terms=value=>(Array.isArray(value)?value:typeof value==='string'?[value]:[]).filter(v=>typeof v==='string').flatMap(v=>v.split(/[,;|]/)).map(v=>v.trim()).filter(Boolean);
export function genreEvidence(track,context) {
  const entries=new Map();
  for(const label of terms(track.genres||track.genre)) entries.set(normalize(label),{id:normalize(label),label,scope:'source metadata'});
  if(!track.artist_unresolved && context?.status==='resolved') for(const label of terms(context.genres)) if(!entries.has(normalize(label))) entries.set(normalize(label),{id:normalize(label),label,scope:'artist context'});
  return [...entries.values()].filter(x=>x.id);
}
export function genreIndex(tracks,contextFor=()=>null,registry=null) {
  const byTrack=new Map(),counts=new Map();
  for(const t of tracks) {
    const evidence=genreEvidence(t,contextFor(t));byTrack.set(recordingKey(t),evidence);
    for(const g of evidence) {const row=counts.get(g.id)||{...g,count:0};row.count++;counts.set(g.id,row);}
  }
  const vocabulary=registry?[...new Set(registry.scenes.flatMap(s=>s.cues.filter(c=>c.channel==='genres').flatMap(c=>c.terms)).map(normalize))]:null;
  // Source fields also contain artist names and jokes. Keep every label searchable,
  // but offer only the common music terms supported by the existing scene registry.
  const options=[...counts.values()].filter(g=>!vocabulary||vocabulary.some(term=>(' '+g.id+' ').includes(' '+term+' '))).sort((a,b)=>b.count-a.count||a.label.localeCompare(b.label)).slice(0,48);
  return {byTrack,options};
}
export function trackMatches(track,query,genre,evidence=[]) {
  const text=normalize([track.artist,track.title,track.version,track.key,...(track.crates||[]),...evidence.map(g=>g.label)].join(' '));
  return (!query||text.includes(normalize(query))) && (!genre||evidence.some(g=>g.id===genre));
}
