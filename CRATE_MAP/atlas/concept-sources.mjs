import {normalize} from './concept-engine.mjs';
import {loadArticle,searchTopics} from './rabbit-sources.mjs';
import {wikiURL} from './rabbit-core.mjs';

const performer=/\b(singer|musician|band|duo|trio|quartet|group|rapper|songwriter|orchestra|composer|ensemble|pianist|record producer|disc jockey)\b/i;
export const artistName=title=>normalize(String(title).replace(/\s*\([^)]*\)\s*$/,''));
export function artistContextFromArticle(artist,a){
 if(!a?.musical||artistName(a.title)!==normalize(artist)||!performer.test(a.blocks?.find(b=>b.kind==='p')?.text||''))return null;
 const genres=[];
 for(const row of a.infobox||[])if(/^genres?$/i.test(row.label.trim())){
  const values=row.links.length?row.links.map(l=>l.text):row.text.split(/[\n,;|]/);
  for(const value of values){const clean=value.replace(/\[[^\]]*\]/g,'').trim();if(clean&&clean.length<=120&&!/^genres?$/i.test(clean)&&!genres.some(g=>normalize(g)===normalize(clean)))genres.push(clean);}
 }
 return {schema_version:1,artist,status:genres.length?'resolved':'unresolved',article_title:a.title,genres:genres.slice(0,60),sources:[{title:'Wikipedia contributors — '+a.title,url:wikiURL(a.title,a.revision),revision:a.revision||null,kind:'live artist context / not exact-recording analysis',licence:'CC BY-SA 4.0'}],retrieved_at:a.retrieved_at||new Date().toISOString(),stale:Boolean(a.stale),candidates:[]};
}
export async function loadArtistContext(artist,{signal,articleTitle,refresh=false,load=loadArticle,search=searchTopics}={}){
 const fallback={schema_version:1,artist,status:'unresolved',genres:[],sources:[],retrieved_at:new Date().toISOString(),candidates:[]};
 if(typeof artist!=='string'||!artist.trim()||artist.length>220)return fallback;
 if(articleTitle){if(artistName(articleTitle)!==normalize(artist))throw Error('This source title does not match the artist name.');const a=await load(articleTitle,{signal,refresh});return artistContextFromArticle(artist,a)||fallback;}
 try{const a=await load(artist,{signal,refresh});const context=artistContextFromArticle(artist,a);if(context?.status==='resolved')return context;}catch(e){if(signal?.aborted||e.name==='AbortError')throw e;}
 const topics=await search(artist,{signal,refresh});const candidates=topics.filter(p=>artistName(p.title)===normalize(artist)&&performer.test(p.description)).map(p=>p.title).slice(0,12);
 if(candidates.length!==1)return {...fallback,status:candidates.length?'ambiguous':'unresolved',candidates};
 const a=await load(candidates[0],{signal,refresh});return artistContextFromArticle(artist,a)||fallback;
}
