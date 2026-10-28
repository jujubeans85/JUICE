export const escapeHTML = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function safeURL(value){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:'#'}catch{return '#'}}
export function recordingKey(t){if(/^[\w-]{11}$/.test(t.youtube_id||''))return 'youtube:'+t.youtube_id;if(/^\d+$/.test(String(t.soundcloud_id||'')))return 'soundcloud:'+t.soundcloud_id;const u=safeURL(t.url);if(u!=='#'){const parsed=new URL(u),id=parsed.hostname==='api.soundcloud.com'?/^\/tracks\/(\d+)\/?$/.exec(parsed.pathname)?.[1]:null;if(id)return 'soundcloud:'+id}return u!=='#'?'url:'+u:null}
export function catalogueTracks(catalogue){const out=new Map();for(const c of catalogue)for(const t of c.tracks||[]){const id=recordingKey(t);if(!id)continue;if(out.has(id)){const old=out.get(id);old.crates=[...new Set([...old.crates,c.id])];if(old.artist_unresolved&&!t.artist_unresolved&&t.artist){old.artist=t.artist;old.artist_unresolved=false;old.artist_source=t.artist_source}if(old.metadata_status==='unresolved'&&t.metadata_status==='resolved'){const membership=old.crates,position=old.position;out.set(id,{...old,...t,position,crates:membership,key:id,collection:'canonical'})}continue}out.set(id,{...t,key:id,crates:[c.id],collection:'canonical'})}return [...out.values()]}
export function parseImport(data){
 const lists=Array.isArray(data)?data:[data];if(!lists.length||!lists.every(c=>c&&typeof c==='object'&&Array.isArray(c.tracks)))throw Error('Use a CRATE JUICE list or catalogue JSON export with an ordered tracks array.');
 let n=0;for(const c of lists){if(c.tracks.length>20000)throw Error('Import at most 20,000 recordings per list.');for(const t of c.tracks){if(!t||typeof t.artist!=='string'||typeof t.title!=='string'||!t.artist.trim()||!t.title.trim()||!recordingKey(t))throw Error('Each recording needs artist, title and an exact HTTP(S) source URL or YouTube ID.');if(n++>50000)throw Error('Import at most 50,000 records at a time.')}}
 return catalogueTracks(lists.map((c,i)=>({...c,id:typeof c.id==='string'?c.id:'local-'+i}))).map(t=>({...t,collection:'device import'}));
}
export function visibleNodes(history,journey,{context=true,year=2026,kind='all'}={}){
 const ids=new Set(journey.nodes);if(!context){for(const e of history.edges.filter(e=>e.evidence==='context'))if(ids.has(e.from_id)&&ids.has(e.to_id))ids.delete(e.from_id);ids.delete('grace-1773');ids.delete('fisk-1909')}
 return history.nodes.filter(n=>ids.has(n.id)&&(n.start===null||n.start<=year)&&(kind==='all'||n.kind===kind)).sort((a,b)=>(a.start??Infinity)-(b.start??Infinity));
}
export function validateHistory(h){
 const ids=new Set(h.nodes.map(n=>n.id)),sources=new Set(h.sources.map(s=>s.id));if(ids.size!==h.nodes.length)throw Error('Duplicate event');
 for(const n of h.nodes){if(n.start!==null&&(!Number.isInteger(n.start)||!Number.isInteger(n.end)||n.start>n.end))throw Error('Invalid event dates');if(n.place&&(!Number.isFinite(n.place.lat)||Math.abs(n.place.lat)>90||!Number.isFinite(n.place.lon)||Math.abs(n.place.lon)>180||!n.place.role||!n.place.precision))throw Error('Invalid geography');if(!n.sources.length||n.sources.some(s=>!sources.has(s)))throw Error('Unsourced event');if(n.play?.type==='youtube'&&!/^[\w-]{11}$/.test(n.play.id))throw Error('Invalid playback ID')}
 for(const e of h.edges){if(!ids.has(e.from_id)||!ids.has(e.to_id)||!['documented','context','hypothesis','disputed'].includes(e.evidence)||!e.sources.length||e.sources.some(s=>!sources.has(s)))throw Error('Invalid relationship')}
 for(const j of h.journeys){if(!j.nodes.every(n=>ids.has(n))||!j.nodes.includes(j.focus))throw Error('Invalid journey')}
 return true;
}
