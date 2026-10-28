import {catalogueTracks,parseImport,recordingKey} from './core.mjs';
import {soundCloudURL} from './soundcloud-widget.mjs';
const text=v=>typeof v==='string'?v.trim():'';
export const metadataReady=s=>Boolean(s?.title&&soundCloudURL(s.permalink_url));
export function sourceRecording(s,position){
  const id=String(s?.id||'');if(!/^\d+$/.test(id))throw Error('Every ordered SoundCloud slot needs an exact numeric source ID.');
  if(s.urn&&s.urn!=='soundcloud:tracks:'+id)throw Error('Conflicting SoundCloud ID and URN.');
  const artist=text(s.publisher_metadata?.artist),url=soundCloudURL(s.permalink_url),duration=Number.isFinite(s.duration)&&s.duration>0?s.duration:null;
  return {position,artist:artist||'Artist unresolved',artist_source:artist?'SoundCloud publisher metadata':'unresolved',artist_unresolved:!artist,uploader:text(s.user?.username)||null,research_context:!artist?text(s.user?.username)||null:null,context_role:!artist?'source uploader; performing artist unresolved':null,title:text(s.title)||'[Metadata unresolved · SoundCloud '+id+']',source_title:text(s.title)||null,version:'Exact SoundCloud item · version as titled',soundcloud_id:id,source_urn:'soundcloud:tracks:'+id,url:url||'https://api.soundcloud.com/tracks/'+id,duration:duration?Math.floor(duration/60000)+':'+String(Math.floor(duration/1000)%60).padStart(2,'0'):'Unresolved',duration_scope:'SoundCloud player-reported duration; may be a preview',source_duration_ms:duration,source_release_date:text(s.release_date)||null,genre:text(s.genre)||null,source_tags:text(s.tag_list)||null,album:text(s.publisher_metadata?.album_title)||null,metadata_status:metadataReady(s)?'resolved':'unresolved',verification:metadataReady(s)?'metadata-verified':'unverified',checked_at:new Date().toISOString().slice(0,10),seed:false};
}
export function crateFromSource(base,payload){
  if(!base?.id||payload.crate_id&&payload.crate_id!==base.id)throw Error('The source capture must match its existing crate ID.');
  if(soundCloudURL(payload.source_url,{playlist:true})!==soundCloudURL(base.url,{playlist:true}))throw Error('The playlist source does not match this crate.');
  const sounds=payload.sounds||payload.tracks;if(!Array.isArray(sounds)||!sounds.length&&payload.source_total!==0)throw Error('No ordered source slots returned.');if(sounds.length>20000)throw Error('A crate exceeds the 20,000-slot import limit.');
  const tracks=sounds.map((s,i)=>sourceRecording(s,i+1)),resolved=tracks.filter(t=>t.metadata_status==='resolved').length,total=Number.isInteger(payload.source_total)?payload.source_total:null;
  const complete=total===tracks.length&&resolved===tracks.length;
  return {...base,tracks,source_platform:'SoundCloud',tracklist_status:complete?'complete':'partial',updated_at:new Date().toISOString().slice(0,10),import_evidence:{method:payload.method||'public source metadata',source_url:base.url,retrieved_at:payload.retrieved_at||new Date().toISOString(),observed_total:total,ordered_slots:tracks.length,resolved_metadata:resolved,unresolved_metadata:tracks.length-resolved,total_verified:total!==null&&total===tracks.length,note:total===null?'The source returned ordered slots; a current independent total is unresolved.':total!==tracks.length?'The current source total differs from the returned order.':'Current source total and returned order agree. source metadata only; playback not checked.'}};
}
export function importCounts(catalogue){
  const slots=catalogue.reduce((n,c)=>n+(c.tracks?.length||0),0),complete=catalogue.filter(c=>c.tracklist_status==='complete').length,partial=catalogue.filter(c=>c.tracklist_status==='partial').length;
  return {crates:catalogue.length,complete,partial,indexOnly:catalogue.length-complete-partial,slots,recordings:catalogueTracks(catalogue).length,unresolvedSlots:catalogue.flatMap(c=>c.tracks||[]).filter(t=>t.metadata_status==='unresolved').length};
}
export function mergeLibrary(canonical,device=[]){const map=new Map(canonical.map(c=>[c.id,c]));for(const c of device){const old=map.get(c.id);if(old?.tracklist_status==='complete'&&c.tracklist_status!=='complete')continue;map.set(c.id,c)}return [...map.values()]}
export function validateLibraryBundle(raw){
  const crates=raw?.format==='crate-juice-library-v1'?raw.crates:Array.isArray(raw)?raw:[raw];
  if(!Array.isArray(crates)||!crates.length||crates.length>2000)throw Error('Use a CRATE JUICE library or ordered list export.');
  parseImport(crates.map(c=>({...c,tracks:c.tracks||[]})));const ids=new Set();for(const c of crates){if(typeof c.id!=='string'||ids.has(c.id)||c.id.length>180)throw Error('Crates need unique stable IDs.');ids.add(c.id);if((c.tracks||[]).some((t,i)=>t.position!==i+1))throw Error('Ordered source positions must be contiguous.');for(const t of c.tracks||[])if(t.soundcloud_id&&!/^\d+$/.test(String(t.soundcloud_id)))throw Error('Invalid SoundCloud ID.');}
  return crates;
}
export function jobFingerprint(t){return JSON.stringify([recordingKey(t),t.artist,t.artist_source,t.artist_unresolved,t.research_context,t.context_role,t.title,t.version,t.source_release_date]);}
