import {catalogueTracks,recordingKey} from './core.mjs';
import {digest} from './backup-core.mjs';
import {normalize} from './concept-engine.mjs';

import {STORE_SCHEMAS as specs} from './storage-schema.mjs';
const JOURNAL='backup-restore-journal-v1';
async function open(kind,prefix='') {
  if(!globalThis.indexedDB) throw Error('Browser database storage is unavailable. Keep the downloaded file.');
  const spec=specs[kind];
  return new Promise((resolve,reject)=>{
    const r=indexedDB.open(prefix+spec.name,spec.version);
    r.onupgradeneeded=()=>{for(const name of spec.stores)if(!r.result.objectStoreNames.contains(name))r.result.createObjectStore(name);};
    r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);r.onblocked=()=>reject(Error('Close other Atlas tabs, then try again.'));
  });
}
async function transaction(kind,stores,mode,run,prefix='') {
  const db=await open(kind,prefix);
  try{return await new Promise((resolve,reject)=>{
    const tx=db.transaction(stores,mode);let result;
    tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error||Error('Storage failed.'));tx.onabort=()=>reject(tx.error||Error('Storage transaction aborted.'));
    try{result=run(tx);}catch(e){tx.abort();reject(e);}
  });}finally{db.close();}
}
async function getOne(kind,store,key,prefix='') {
  let value;await transaction(kind,[store],'readonly',tx=>{const r=tx.objectStore(store).get(key);r.onsuccess=()=>value=r.result;},prefix);return value??null;
}
export async function recoveryJournal(prefix='') {return getOne('library','state',JOURNAL,prefix);}
async function journal(value,prefix='') {await transaction('library',['state'],'readwrite',tx=>value?tx.objectStore('state').put(value,JOURNAL):tx.objectStore('state').delete(JOURNAL),prefix);}
export function storagePlan(data) {
  const known=new Set(catalogueTracks(data.library||[]).map(recordingKey));
  return {crates:data.library||[],imports:JSON.stringify((data.recordings||[]).filter(t=>!known.has(recordingKey(t)))),
    research:data.automatic_research||{version:1,jobs:{},graph:{version:1,nodes:[],edges:[],sources:[],trail:[]}},
    concepts:{contexts:(data.concepts?.contexts||[]).map(c=>[normalize(c.artist),c]),overrides:(data.concepts?.overrides||[]).map(o=>[o.recording_key,o])},
    exploration:data.exploration||{version:1,nodes:[],edges:[],sources:[],trail:[]}};
}
async function readAll(kind,store,prefix) {
  let keys,values;await transaction(kind,[store],'readonly',tx=>{const s=tx.objectStore(store),k=s.getAllKeys(),v=s.getAll();k.onsuccess=()=>keys=k.result;v.onsuccess=()=>values=v.result;},prefix);return keys.map((key,i)=>[key,values[i]]);
}
export async function readPlan(prefix='') {
  const crates=await getOne('library','state','crates',prefix)||[];
  const meta=await getOne('library','state','research-meta',prefix);
  let research;
  if(meta){const parts={};for(const k of ['jobs','nodes','edges','sources'])parts[k]=(await readAll('library','research_'+k,prefix)).map(x=>x[1]);research={version:1,jobs:Object.fromEntries(parts.jobs.map(j=>[j.key,j])),graph:{version:1,nodes:parts.nodes,edges:parts.edges,sources:parts.sources,trail:[]}};}
  else research=await getOne('library','state','research-state',prefix)||{version:1,jobs:{},graph:{version:1,nodes:[],edges:[],sources:[],trail:[]}};
  return {crates,imports:prefix?await getOne('library','state','rehearsal-imports',prefix):localStorage.getItem('cj-atlas-imports-v1'),research,
    concepts:{contexts:await readAll('concepts','contexts',prefix),overrides:await readAll('concepts','overrides',prefix)},exploration:await getOne('exploration','state','graph',prefix)};
}
export async function writePlan(plan,prefix='') {
  await transaction('library',specs.library.stores,'readwrite',tx=>{
    const state=tx.objectStore('state');state.put(plan.crates,'crates');state.put({version:1},'research-meta');state.delete('research-state');state.put(false,'research-enabled');
    if(prefix)state.put(plan.imports,'rehearsal-imports');
    for(const k of ['jobs','nodes','edges','sources']){const s=tx.objectStore('research_'+k);s.clear();for(const item of k==='jobs'?Object.values(plan.research.jobs):plan.research.graph[k])s.put(item,k==='jobs'?item.key:item.id);}
  },prefix);
  await transaction('concepts',['contexts','overrides'],'readwrite',tx=>{for(const k of ['contexts','overrides']){const s=tx.objectStore(k);s.clear();for(const [key,value] of plan.concepts[k])s.put(value,key);}},prefix);
  await transaction('exploration',['state'],'readwrite',tx=>plan.exploration?tx.objectStore('state').put(plan.exploration,'graph'):tx.objectStore('state').delete('graph'),prefix);
  if(!prefix){if(plan.imports===null)localStorage.removeItem('cj-atlas-imports-v1');else localStorage.setItem('cj-atlas-imports-v1',plan.imports);}
}
export function comparablePlan(plan) {
  const copy=structuredClone(plan);
  for(const k of ['nodes','edges','sources'])copy.research.graph[k].sort((a,b)=>a.id.localeCompare(b.id));
  for(const k of ['contexts','overrides'])copy.concepts[k].sort((a,b)=>a[0].localeCompare(b[0]));
  // ResearchStore deliberately persists graph entities, not presentation metadata.
  copy.research.graph={version:1,nodes:copy.research.graph.nodes,edges:copy.research.graph.edges,sources:copy.research.graph.sources,trail:[]};
  return copy;
}
async function verify(plan,prefix='') {
  if(await digest(comparablePlan(plan))!==await digest(comparablePlan(await readPlan(prefix))))throw Error('Stored data did not match the restore plan.');
}
export async function restorePlan(plan,prefix='') {
  if(await recoveryJournal(prefix))throw Error('An interrupted restore needs recovery first.');
  const before=await readPlan(prefix);await journal({before,created_at:new Date().toISOString()},prefix);
  try{await writePlan(plan,prefix);await verify(plan,prefix);await journal(null,prefix);}
  catch(error){
    try{await writePlan(before,prefix);await verify(before,prefix);await journal(null,prefix);}
    catch{throw Error('Restore interrupted. Use Recover previous browser data before continuing. '+error.message);}
    throw Error('Restore failed; the previous browser data was recovered. '+error.message);
  }
}
export async function recoverPrevious(prefix='') {
  const saved=await recoveryJournal(prefix);if(!saved)throw Error('No interrupted restore.');
  await writePlan(saved.before,prefix);await verify(saved.before,prefix);await journal(null,prefix);
}
export async function destroyRehearsal(prefix) {
  if(!prefix.startsWith('cj-backup-rehearsal-'))throw Error('Only temporary rehearsal databases can be removed.');
  await Promise.all(Object.values(specs).map(s=>new Promise((resolve,reject)=>{const r=indexedDB.deleteDatabase(prefix+s.name);r.onsuccess=resolve;r.onerror=()=>reject(r.error);r.onblocked=()=>reject(Error('Rehearsal cleanup blocked. Close this Atlas tab to release storage.'));})));
}
export async function rehearseRestore(data) {
  const prefix='cj-backup-rehearsal-'+crypto.randomUUID()+'-',plan=storagePlan(data);
  try{await writePlan(plan,prefix);await verify(plan,prefix);return true;}
  finally{await destroyRehearsal(prefix);}
}
