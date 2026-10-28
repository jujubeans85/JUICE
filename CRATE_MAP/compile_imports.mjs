#!/usr/bin/env node
// Join independently observed provider order with native, rendered metadata.
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {validateLibraryBundle,importCounts} from './atlas/import-core.mjs';

export function sourceURL(value){
  const u=new URL(value);
  if(u.protocol!=='https:'||!['soundcloud.com','www.soundcloud.com'].includes(u.hostname)||u.username||u.password||u.search||u.hash)throw Error('Use a clean, exact SoundCloud source URL.');
  u.hostname='soundcloud.com';
  return u.href.replace(/\/$/,'');
}
export function joinPublicCapture(base,capture){
  const d=capture,tail=d.source_visibility==='public-source-evidence';
  if(!['public-source-view','public-source-evidence'].includes(d.source_visibility)||d.source_session_required||d.evidence_flags?.explicit_private||d.evidence_flags?.made_for_owner)throw Error('An owner-only capture cannot enter the public metadata join.');
  if(sourceURL(d.request_url)!==sourceURL(base.url))throw Error('Native source does not match the existing crate.');
  const rows=tail?d.ordered_tracks:d.rows,count=tail?d.declared_track_count:d.declared_count;
  const agreement=tail?d.status==='complete'&&d.original_public_evidence&&d.consistency?.checks_passed:d.complete&&d.contiguous&&d.order_consistent_with_input;
  // The native view alone does not establish public visibility. Require the
  // independently retrieved public source ID sequence and its verified total.
  if(!base.import_evidence?.total_verified||base.import_evidence.observed_total!==count||!agreement||count!==(base.tracks||[]).length||rows?.length!==count)throw Error('Native count/order agreement failed for '+base.id);
  const result=structuredClone(base),checked=d.captured_at||d.checked_at;
  for(let i=0;i<rows.length;i++){
    const row=rows[i],t=result.tracks[i];
    if(row.position!==i+1||t.position!==i+1||row.requires_source_session||row.source_session_required)throw Error('Native source order/access is unresolved.');
    const target=sourceURL(row.url);
    if(t.metadata_status==='resolved'&&sourceURL(t.url)!==target)throw Error('Recording permalink conflict for '+base.id+' at '+(i+1));
    if(!row.title)throw Error('Missing rendered title');
    Object.assign(t,{title:row.title,source_title:row.title,url:target,source_display_credit:row.uploader||null,metadata_status:'resolved',verification:'metadata-verified',checked_at:checked.slice(0,10)});
    if(t.artist_unresolved){t.research_context=row.uploader||t.uploader||null;t.context_role='SoundCloud displayed credit; performer/uploader distinction unresolved'}
  }
  result.tracklist_status='complete';
  result.import_evidence={...result.import_evidence,resolved_metadata:count,unresolved_metadata:0,native_order_verified:true,native_count:count,native_checked_at:checked,native_source_url:d.native_url||d.current_url,identity_note:'SoundCloud IDs retain public provider order; every previously resolved permalink agrees with the current rendered position.'};
  return result;
}
export function compileLibrary(raw,captures=[],ownerCapture=null){
  const catalogue=validateLibraryBundle(raw);
  if(catalogue.some(c=>c.visibility==='private'))throw Error('The public input must not contain owner-private membership.');
  const publicMap=new Map(catalogue.map(c=>[c.id,structuredClone(c)]));let nativeJoined=0;
  for(const capture of captures)for(const d of capture.rows){const base=publicMap.get(d.crate_id);if(!base)throw Error('Unknown existing crate '+d.crate_id);publicMap.set(base.id,joinPublicCapture(base,d));nativeJoined++}
  const byURL=new Map(),collisions=new Set();
  for(const c of publicMap.values())for(const t of c.tracks||[]){
    if(t.metadata_status==='unresolved'||!t.url.startsWith('https://soundcloud.com/'))continue;
    const key=sourceURL(t.url),old=byURL.get(key);if(collisions.has(key))continue;
    if(old&&old.soundcloud_id!==t.soundcloud_id){byURL.delete(key);collisions.add(key);continue}
    if(!old||old.artist_unresolved&&!t.artist_unresolved)byURL.set(key,t);
  }
  const ownerEntries=[];
  for(const d of ownerCapture?.rows||[]){
    const base=publicMap.get(d.crate_id);if(!base)throw Error('Owner capture needs an existing crate ID');
    const count=d.declared_track_count,rows=d.ordered_tracks||[],checked=d.captured_at||d.checked_at;
    if(!Number.isInteger(count)||rows.length!==count||count>0&&d.status!=='complete'||count===0&&!d.evidence_flags?.declared_empty)throw Error('Incomplete owner source: '+d.crate_id);
    if(sourceURL(d.request_url)!==sourceURL(base.url))throw Error('Owner source URL conflict.');
    const tracks=rows.map((r,i)=>{
      if(r.position!==i+1||!r.title||!r.url)throw Error('Incomplete owner slot');
      const permalink=sourceURL(r.url),known=byURL.get(permalink),credited=known&&!known.artist_unresolved;
      return {...(known||{}),position:i+1,title:r.title,source_title:r.title,artist:credited?known.artist:'Artist unresolved',artist_source:credited?known.artist_source:'unresolved',artist_unresolved:!credited,url:permalink,version:known?.version||'Exact SoundCloud item · version as titled',duration:known?.duration||'Unresolved',source_display_credit:r.uploader||null,source_display_profile:r.uploader_url?sourceURL(r.uploader_url):null,research_context:credited?null:r.uploader||null,context_role:credited?null:'SoundCloud displayed credit; performer/uploader distinction unresolved',source_session_required:Boolean(r.source_session_required),metadata_status:'resolved',verification:'metadata-verified',checked_at:checked.slice(0,10),seed:false};
    });
    ownerEntries.push({...base,visibility:'private',source_visibility:'owner-only capture',tracklist_status:'complete',source_platform:'SoundCloud',updated_at:checked.slice(0,10),tracks,import_evidence:{method:'Signed-in SoundCloud rendered owner view',source_url:base.url,checked_at:checked,observed_total:count,ordered_slots:count,resolved_metadata:count,unresolved_metadata:0,total_verified:true,declared_empty:count===0,note:count===0?'Native source explicitly declared zero tracks at capture time; earlier contents are not reconstructed.':'Contiguous rendered order matches the native declared count. Performer/uploader roles remain explicit; playback not checked.'}});
  }
  const pack={format:'crate-juice-library-v1',exported_at:new Date().toISOString(),crates:[...publicMap.values()]};validateLibraryBundle(pack);
  const owner={format:'crate-juice-library-v1',visibility:'private',crates:ownerEntries};if(ownerEntries.length)validateLibraryBundle(owner);
  return {public:pack,owner,report:{public:importCounts(pack.crates),nativeJoined,owner_crates:ownerEntries.length,owner_slots:ownerEntries.reduce((n,c)=>n+c.tracks.length,0),owner_empty:ownerEntries.filter(c=>!c.tracks.length).length}};
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
  const a=process.argv.slice(2),value=k=>a[a.indexOf(k)+1],values=k=>a.flatMap((v,i)=>v===k?[a[i+1]]:[]),read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
  if(!a.includes('--library')||!a.includes('--public-output'))throw Error('Use --library export.json --public-dom capture.json [repeat] --owner-dom capture.json --public-output public.json --owner-output owner.json');
  const result=compileLibrary(read(value('--library')),values('--public-dom').map(read),a.includes('--owner-dom')?read(value('--owner-dom')):null);
  if(result.owner.crates.length&&!a.includes('--owner-output'))throw Error('Owner-private output is required.');
  fs.writeFileSync(value('--public-output'),JSON.stringify(result.public,null,2)+'\n');
  if(result.owner.crates.length)fs.writeFileSync(value('--owner-output'),JSON.stringify(result.owner,null,2)+'\n',{mode:0o600});
  console.log(JSON.stringify(result.report));
}
