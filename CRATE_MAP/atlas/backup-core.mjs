import {catalogueTracks, parseImport, recordingKey, validateHistory} from './core.mjs';
import {validateLibraryBundle, mergeLibrary} from './import-core.mjs';
import {validCachedGraph} from './rabbit-core.mjs';
import {validateConceptExport, normalize} from './concept-engine.mjs';

export const FORMAT = 'crate-juice-music-atlas-v3';
export const MAX_BACKUP_BYTES = 60 * 1024 * 1024;
const object = v => v && typeof v === 'object' && !Array.isArray(v);
const emptyGraph = () => ({version:1,nodes:[],edges:[],sources:[],trail:[]});
export function stableJSON(value) {
  if (Array.isArray(value)) return '[' + value.map(stableJSON).join(',') + ']';
  if (object(value)) return '{' + Object.keys(value).sort().filter(k=>value[k]!==undefined).map(k=>JSON.stringify(k)+':'+stableJSON(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
export async function digest(value) {
  if (!globalThis.crypto?.subtle) throw Error('Integrity checks need a secure HTTPS connection.');
  const bytes = new TextEncoder().encode(stableJSON(value));
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
}
export function payload(data) { const {backup, ...rest}=data; return rest; }
export function workState(data) {
  const {backup, exported_at, coverage, ...rest}=data;
  return rest;
}
function unique(rows, key, label) {
  if (!Array.isArray(rows) || rows.some(x=>!object(x)||typeof x[key]!=='string') || new Set(rows.map(x=>x[key])).size!==rows.length) throw Error('Invalid or duplicate '+label+'.');
}
export function validateResearch(state) {
  if (!state || state.version!==1 || !object(state.jobs) || !validCachedGraph(state.graph)) throw Error('Invalid automatic research export.');
  for (const kind of ['nodes','edges','sources']) unique(state.graph[kind],'id','research '+kind);
  const ids=new Set(state.graph.nodes.map(n=>n.id));
  for (const [key,j] of Object.entries(state.jobs)) {
    if (!object(j) || key!==j.key || typeof j.fingerprint!=='string' || !['queued','researching','ready','needs-review','failed'].includes(j.status) || !Array.isArray(j.node_ids) || j.node_ids.some(id=>!ids.has(id))) throw Error('Invalid research job associations.');
  }
  return state;
}
export function backupCounts(data) {
  return {crates:data.library?.length||0, ordered_entries:(data.library||[]).reduce((n,c)=>n+(c.tracks?.length||0),0), recordings:data.recordings?.length||0,
    research_jobs:Object.keys(data.automatic_research?.jobs||{}).length, research_nodes:data.automatic_research?.graph.nodes.length||0,
    research_edges:data.automatic_research?.graph.edges.length||0, exploration_nodes:data.exploration?.nodes.length||0,
    exploration_edges:data.exploration?.edges.length||0, trail_steps:data.exploration?.trail.length||0,
    artist_contexts:data.concepts?.contexts.length||0, concept_choices:data.concepts?.overrides.length||0};
}
export function validateBackup(data, registry) {
  if (!object(data) || ![FORMAT,'crate-juice-music-atlas-v2'].includes(data.format)) throw Error('Choose a Music Atlas v2 or v3 export.');
  if (data.format===FORMAT && (!Array.isArray(data.library)||!Array.isArray(data.recordings)||!data.research)) throw Error('Incomplete v3 backup.');
  if (data.library?.length) validateLibraryBundle(data.library);
  if (data.recordings) {
    parseImport({tracks:data.recordings});
    if (new Set(data.recordings.map(recordingKey)).size!==data.recordings.length) throw Error('Duplicate recording identities.');
  }
  if (data.research) validateHistory(data.research);
  if (data.automatic_research) validateResearch(data.automatic_research);
  if (data.exploration) {
    if (!validCachedGraph(data.exploration)) throw Error('Invalid exploration graph.');
    for (const k of ['nodes','edges','sources']) unique(data.exploration[k],'id','exploration '+k);
  }
  if (data.concepts) validateConceptExport(data.concepts,registry);
  // Exploration can legitimately refer to a reviewed-history parent.
  const graphs=[data.research,data.automatic_research?.graph,data.exploration].filter(Boolean);
  const nodes=new Set(graphs.flatMap(g=>g.nodes.map(n=>n.id))), sources=new Set(graphs.flatMap(g=>g.sources.map(s=>s.id)));
  for (const g of graphs) {
    for (const n of g.nodes) if (n.sources.some(id=>!sources.has(id))) throw Error('A research source is missing.');
    for (const e of g.edges) if (!nodes.has(e.from_id)||!nodes.has(e.to_id)||e.sources.some(id=>!sources.has(id))) throw Error('A relationship target or source is missing.');
  }
  if (data.backup && (data.backup.schema_version!==1 || !/^[a-f0-9]{64}$/.test(data.backup.sha256||'') || !/^[a-f0-9]{64}$/.test(data.backup.state_sha256||''))) throw Error('Unsupported backup integrity metadata.');
  return data;
}
export async function createBackup(data, registry, now=new Date()) {
  const out={...payload(data),format:FORMAT,exported_at:now.toISOString()};
  validateBackup(out,registry);
  out.backup={schema_version:1,sha256:await digest(out),state_sha256:await digest(workState(out)),counts:backupCounts(out)};
  return out;
}
export async function checkBackup(data, registry) {
  validateBackup(data,registry);
  if (data.backup) {
    if (await digest(payload(data))!==data.backup.sha256 || await digest(workState(data))!==data.backup.state_sha256 || stableJSON(backupCounts(data))!==stableJSON(data.backup.counts)) throw Error('Integrity check failed. Keep this file and try another backup.');
  }
  return {data,counts:backupCounts(data),integrity:data.backup?'SHA-256 matches':'Legacy export: structure checked; no original checksum'};
}
export function backupFilename(data) {
  const time=new Date(data.exported_at).toISOString().replace(/[:.]/g,'-');
  return `CRATE_JUICE_Music_Atlas_${time}_${data.backup.sha256.slice(0,8)}.json`;
}
const mergeRows=(a=[],b=[],key='id')=>[...new Map([...a,...b].map(x=>[x[key],x])).values()];
function graphMerge(a,b) {
  a=a||emptyGraph(); b=b||emptyGraph();
  return {...a,...b,version:1,nodes:mergeRows(a.nodes,b.nodes),edges:mergeRows(a.edges,b.edges),sources:mergeRows(a.sources,b.sources),trail:stableJSON(a.trail)===stableJSON(b.trail)?a.trail:[...a.trail,...b.trail]};
}
function newerRows(a=[],b=[],key,date) {
  const out=new Map(a.map(x=>[key(x),x]));
  for(const x of b) if(!out.has(key(x))||Date.parse(x[date])>=Date.parse(out.get(key(x))[date])) out.set(key(x),x);
  return [...out.values()];
}
export function mergeBackup(current,incoming) {
  const library=mergeLibrary(current.library||[],incoming.library||[]);
  const records=new Map([...(current.recordings||[]),...(incoming.recordings||[])].map(t=>[recordingKey(t),t]));
  for(const t of catalogueTracks(library)) records.set(t.key,t);
  const a=current.automatic_research,b=incoming.automatic_research;
  const jobs=Object.fromEntries(newerRows(Object.values(a?.jobs||{}),Object.values(b?.jobs||{}),j=>j.key,'updated_at').map(j=>[j.key,{...j,status:j.status==='researching'?'queued':j.status}]));
  return {...payload(current),format:FORMAT,library,recordings:[...records.values()],
    automatic_research:{version:1,jobs,graph:graphMerge(a?.graph,b?.graph)},
    exploration:graphMerge(current.exploration,incoming.exploration),
    concepts:{...current.concepts,...incoming.concepts,contexts:newerRows(current.concepts?.contexts,incoming.concepts?.contexts,c=>normalize(c.artist),'retrieved_at'),overrides:newerRows(current.concepts?.overrides,incoming.concepts?.overrides,o=>o.recording_key,'updated_at')}};
}
