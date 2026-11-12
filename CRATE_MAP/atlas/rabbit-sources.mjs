import {STORE_SCHEMAS} from './storage-schema.mjs';
import {articleTitle, cleanText, wikiURL, youtubeReference, safeCommonsAudio, classifyArticle, wikibaseID, isMusicText, sourceDates} from './rabbit-core.mjs';
const WIKI='https://en.wikipedia.org/w/api.php', COMMONS='https://commons.wikimedia.org/w/api.php', WD='https://www.wikidata.org/w/api.php';
const memory=new Map(), pending=new Map(); let nextRequest=0;
export class ExplorationStore {
  constructor(){this.persistent=false;this.ready=this.open();}
  async open(){if(!globalThis.indexedDB)return;try{this.db=await new Promise((resolve,reject)=>{const r=indexedDB.open(STORE_SCHEMAS.exploration.name,STORE_SCHEMAS.exploration.version);r.onupgradeneeded=()=>{for(const name of STORE_SCHEMAS.exploration.stores)r.result.createObjectStore(name)};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)});this.persistent=true}catch{}}
  async get(store,key){await this.ready;if(!this.db)return memory.get(store+':'+key);try{return await new Promise((resolve,reject)=>{const r=this.db.transaction(store).objectStore(store).get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)})}catch{return memory.get(store+':'+key)}}
  async put(store,key,value){memory.set(store+':'+key,value);await this.ready;if(!this.db)return false;try{await new Promise((resolve,reject)=>{const tx=this.db.transaction(store,'readwrite');tx.objectStore(store).put(value,key);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error)});return true}catch{this.persistent=false;return false}}
  async clear(){await this.ready;memory.clear();if(this.db)await new Promise((resolve,reject)=>{const tx=this.db.transaction(['state','cache'],'readwrite');tx.objectStore('state').clear();tx.objectStore('cache').clear();tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error)})}
}
export const explorationStore=new ExplorationStore();
async function jsonAPI(endpoint,params,{signal,refresh=false}={}){
  const u=new URL(endpoint);u.search=new URLSearchParams({...params,format:'json',formatversion:'2',origin:'*',maxlag:'5'}).toString();const key=u.href;
  const cached=await explorationStore.get('cache',key);if(!refresh&&cached&&Date.now()-cached.at<86400000)return {...cached.data,_cached_at:cached.at};
  if(pending.has(key)&&!pending.get(key).signal?.aborted)return pending.get(key).promise;
  const promise=(async()=>{signal?.throwIfAborted();const gap=Math.max(0,nextRequest-Date.now());nextRequest=Date.now()+gap+250;if(gap)await new Promise((resolve,reject)=>{const timer=setTimeout(resolve,gap);signal?.addEventListener('abort',()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'))},{once:true})});
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),18000);signal?.addEventListener('abort',()=>controller.abort(),{once:true});
    try{const r=await fetch(u,{signal:controller.signal,credentials:'omit',headers:{'Accept':'application/json'}});if(!r.ok){const retry=r.headers.get('Retry-After');throw Error(`Source returned ${r.status}${retry?'; retry after '+retry+' seconds':''}.`)}const text=await r.text();if(text.length>8000000)throw Error('Source article exceeds the request size budget.');const data=JSON.parse(text);if(data.error)throw Error(data.error.info||data.error.code||'Source API error');await explorationStore.put('cache',key,{at:Date.now(),data});return data}
    catch(e){if(signal?.aborted)throw new DOMException('Aborted','AbortError');if(cached)return {...cached.data,_stale:true,_cached_at:cached.at,_error:e.message};throw Error(e.name==='AbortError'?'The source timed out. Try again or open its original page.':e.message)}finally{clearTimeout(timeout)}
  })();pending.set(key,{promise,signal});try{return await promise}finally{if(pending.get(key)?.promise===promise)pending.delete(key)}
}
export function parseArticle(result){
  const p=result.parse;if(!p?.title||typeof p.text!=='string')throw Error('The source did not return an article.');
  const d=new DOMParser().parseFromString(p.text,'text/html');
  d.querySelectorAll('.navbox,.vertical-navbox,.sidebar,.metadata,.hatnote,.ambox,.toc,.mw-editsection,script,style,noscript,figure').forEach(x=>x.remove());
  const blocks=[];let heading='Introduction',inReferences=false;
  for(const el of d.querySelectorAll('h2,h3,h4,p,li,table.infobox tr')){
    if(/^H[234]$/.test(el.tagName)){heading=cleanText(el.textContent).replace(/\[edit\]/g,'').trim();inReferences=/^(references|notes|footnotes|bibliography|further reading|external links)$/i.test(heading);continue}
    if(inReferences||el.closest('.reflist,.references,.refbegin')||el.querySelector('li')||el.closest('li')&&el.tagName==='P')continue;
    const text=cleanText(el.textContent);if(text.length<20||text.length>12000)continue;
    const links=[];for(const a of el.querySelectorAll('a[href]')){const title=articleTitle(a.getAttribute('href'));if(title)links.push({title,text:cleanText(a.textContent)})}
    const references=[];for(const ref of el.querySelectorAll('sup.reference a[href^="#"]')){const id=decodeURIComponent(ref.getAttribute('href').slice(1));const target=d.getElementById(id);for(const a of target?.querySelectorAll('a.external[href]')||[]){try{const u=new URL(a.getAttribute('href'));if(u.protocol==='https:'&&references.length<4)references.push({title:cleanText(a.textContent).slice(0,150),url:u.href})}catch{}}}
    blocks.push({kind:el.tagName.toLowerCase(),heading,text:text.slice(0,1600),links:links.slice(0,100),references});if(blocks.length>=1600)break;
  }
  const musical=classifyArticle({title:p.title,blocks});const videos=[];for(const a of d.querySelectorAll('a.external[href]')){const id=youtubeReference(a.getAttribute('href'));if(id&&!videos.some(v=>v.id===id)){const context=cleanText(a.closest('p,li')?.textContent||a.textContent);if(musical||isMusicText(context))videos.push({id,title:context.slice(0,200)||p.title+' · source video',source_url:wikiURL(p.title,p.revid)})}}
  const infobox=[...d.querySelectorAll('table.infobox tr')].map(row=>({label:cleanText(row.querySelector('th')?.textContent||''),text:cleanText(row.querySelector('td')?.textContent||''),links:[...row.querySelectorAll('td a[href]')].map(a=>({title:articleTitle(a.getAttribute('href')),text:cleanText(a.textContent)})).filter(a=>a.title)})).filter(row=>row.label&&row.text).slice(0,60);
  const qid=wikibaseID(p.properties);const article={title:p.title,pageid:p.pageid,revision:p.revid||null,qid,blocks,infobox,videos:videos.slice(0,20),retrieved_at:new Date().toISOString(),stale:Boolean(result._stale),cached_at:result._cached_at||null};article.musical=classifyArticle(article);return article;
}
export async function loadArticle(title,options={}){
  if(typeof title!=='string'||title.length>220||/^(File|Special|Category|Template|User|Wikipedia):/i.test(title))throw Error('Choose a normal music article.');
  const r=await jsonAPI(WIKI,{action:'parse',page:title,prop:'text|revid|properties',redirects:'1',disableeditsection:'1'},options);return parseArticle(r);
}
export async function searchTopics(term,options={}){
  const r=await jsonAPI(WIKI,{action:'query',generator:'search',gsrsearch:String(term).slice(0,160)+' music',gsrnamespace:'0',gsrlimit:'8',prop:'extracts|pageprops',exintro:'1',explaintext:'1',exsentences:'2'},options);
  return (r.query?.pages||[]).filter(p=>!p.missing&&!('disambiguation' in(p.pageprops||{}))).map(p=>({title:p.title,description:p.extract||'',pageid:p.pageid})).filter(p=>classifyArticle({title:p.title,blocks:[{kind:'p',text:p.description}]}));
}
export async function geolocateArticle(article,options={}){
  const parentSignal=options.signal,controller=new AbortController(),cancel=()=>controller.abort(),timer=setTimeout(cancel,10000);parentSignal?.addEventListener('abort',cancel,{once:true});options={...options,signal:controller.signal};
  let knownPlace=null;
  try{
    const r=await jsonAPI(WIKI,{action:'query',titles:article.title,prop:'pageprops|coordinates',colimit:'max',coprimary:'primary'},options),p=r.query?.pages?.[0];
    const direct=p?.coordinates?.[0],place=direct?{name:article.title,lat:direct.lat,lon:direct.lon,role:'topic location, from source coordinates',precision:'source geographic anchor'}:null;knownPlace=place;
    const qid=p?.pageprops?.wikibase_item;if(!/^Q\d+$/.test(qid||''))return place?{place,start:null}:{};
    const w=await jsonAPI(WD,{action:'wbgetentities',ids:qid,props:'claims|labels',languages:'en'},options),entity=w.entities?.[qid],claims=entity?.claims||{};
    const fact=k=>claims[k]?.find(x=>x.rank!=='deprecated')?.mainsnak?.datavalue?.value;
    const dates=sourceDates(claims);if(place)return {place,qid,...dates};
    let anchor=fact('P19'),role='person’s birthplace; not a style origin';if(!anchor){anchor=fact('P740');role='group formation place; not the recording location'}
    if(!anchor?.id)return {qid,...dates};
    const a=await jsonAPI(WD,{action:'wbgetentities',ids:anchor.id,props:'claims|labels',languages:'en'},options),e=a.entities?.[anchor.id],coord=e?.claims?.P625?.find(x=>x.rank!=='deprecated')?.mainsnak?.datavalue?.value;
    if(!coord||coord.globe!=='http://www.wikidata.org/entity/Q2')return {qid,...dates};return {qid,place:{name:e.labels?.en?.value||anchor.id,lat:coord.latitude,lon:coord.longitude,role,precision:'Wikidata place anchor'},place_source:'https://www.wikidata.org/wiki/'+anchor.id,...dates};
  }catch(e){if(parentSignal?.aborted)throw e;return {...(knownPlace?{place:knownPlace,start:null}:{}),geography_error:e.message}}finally{clearTimeout(timer);parentSignal?.removeEventListener('abort',cancel)}
}
export async function findAudio(article,{offset=0,...options}={}){
  const term=article.title.replace(/\s*\([^)]*\)/g,'').trim();
  const r=await jsonAPI(COMMONS,{action:'query',generator:'search',gsrsearch:'"'+term.replace(/"/g,'')+'"'+(article.musical?'':' music')+' filetype:audio',gsrnamespace:'6',gsrlimit:'8',gsroffset:String(offset),prop:'imageinfo',iiprop:'url|mime|extmetadata',iiurlwidth:'300'},options);
  const plain=s=>{const d=new DOMParser().parseFromString(String(s||''),'text/html');return cleanText(d.body.textContent).slice(0,600)};
  const files=[];for(const p of r.query?.pages||[]){const info=p.imageinfo?.[0],m=info?.extmetadata||{};const url=safeCommonsAudio(info?.url);if(!url||!info.mime?.startsWith('audio/'))continue;const licence=plain(m.LicenseShortName?.value);if(!licence)continue;if(!article.musical&&!isMusicText(p.title+' '+plain(m.ImageDescription?.value)+' '+plain(m.Artist?.value)))continue;
    files.push({id:'commons:'+p.pageid,title:p.title.replace(/^File:/,''),url,description_url:info.descriptionurl||'https://commons.wikimedia.org/wiki/'+encodeURIComponent(p.title),mime:info.mime,artist:plain(m.Artist?.value)||'See source credits',licence,licence_url:m.LicenseUrl?.value||null,credit:plain(m.Credit?.value),date:plain(m.DateTimeOriginal?.value||m.DateTime?.value)||'Recording date unresolved',query:term,source_relation:'Source search result for this music topic; style/date match requires checking.'});
  }
  return {files,offset:offset+8,more:Boolean(r.continue),videos:offset===0?article.videos:[],stale:Boolean(r._stale)};
}
