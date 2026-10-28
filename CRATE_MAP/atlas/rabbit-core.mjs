import {soundCloudURL} from './soundcloud-widget.mjs';
/** Pure contracts for on-demand, source-linked music exploration. */
export const FACETS = [
  { id: 'politics', label: 'Politics & power', hint: 'Movements, conflict, migration and social conditions.' },
  { id: 'divergence', label: 'Where it diverged', hint: 'Related styles, descendants and reinterpretations.' },
  { id: 'examples', label: 'Another recording', hint: 'Different source-linked performances and recordings.' },
  { id: 'people', label: 'People', hint: 'Performers, teachers, collaborators and organisers.' },
  { id: 'places', label: 'Other places', hint: 'Places connected to the music, with their geographic roles.' },
  { id: 'instruments', label: 'Instruments & sound', hint: 'Instruments, techniques and ensemble changes.' },
  { id: 'technology', label: 'Technology & media', hint: 'Recording, distribution, broadcasting and pop culture.' },
];
const MUSIC = /\b(music(?:al|ian|ians)?|songs?|singers?|singing|sang|sung|choirs?|choral|spirituals?|hymns?|anthems?|ballads?|gospel|blues|jazz|soul|funk|reggae|hip.hop|rap|rock|punk|folk|rhythm|melod(?:y|ies)|harmon(?:y|ies)|compos(?:er|ition)|orchestra|ensemble|instrument(?:al|s)?|guitar|piano|banjo|trumpet|recordings?|albums?|concerts?|perform(?:er|ers|ance|ances)|record label|drumm?(?:er|ing|s)?|dance music|soundtrack|audio|mp3|synthesizer|disc jockey|opera)\b/i;
const MATCH = {
  politics: /\b(politic\w*|war|slav(?:ery|es|e)|enslav\w*|emancipat\w*|abolition\w*|civil rights|segregat\w*|racis\w*|apartheid|colonial\w*|revolut\w*|protest\w*|activis\w*|censorship|bann?ed|propaganda|nationalis\w*|labor|labour|freedm[ae]n|underground railroad|migration|discriminat\w*)\b/i,
  divergence: /\b(diverg\w*|deriv\w*|influenc\w*|evol\w*|fusion|subgenre|genre|emerg\w*|develop\w*|reinterpret\w*|origin\w*|descend\w*|crossover|tradition|populariz\w*|popularis\w*|spread|blues|gospel|jazz|soul|funk|reggae|hip.hop|punk)\b/i,
  people: /\b(singer|musician|composer|producer|pianist|guitarist|drummer|teacher|mentor|director|arranger|founder|performer|vocalist|songwriter|collaborat\w*|member|engineer|organis\w*|organiz\w*)\b/i,
  places: /\b(born|raised|grew up|city|cities|town|country|countries|region|tour(?:s|ed|ing)?|migrat\w*|diaspora|recorded at|studio|based|formed in|origin|venue|festival|university)\b/i,
  instruments: /\b(voice|vocal|choirs?|hymns?|instrument\w*|guitars?|piano|banjo|trumpet|drums?|bass|violin|fiddle|flute|horns?|saxophone|percussion|organ|mellotron|synthesizer|tuning|technique|rhythm|a cappella|call.and.response|harmon\w*|melod\w*)\b/i,
  technology: /\b(technolog\w*|recording|phonograph|gramophone|microphone|amplif\w*|electric|electronic|radio|television|broadcast\w*|film|movie|soundtrack|advertis\w*|campaign|sample|sampling|compression|codec|mp3|digital|internet|vinyl|tape|synthesizer|media)\b/i,
};
const MUSIC_ANCHORS = /\b(music|song|singer|singing|choir|spiritual|hymn|anthem|ballad|gospel|blues|jazz|soul|funk|reggae|rhythm|rock|punk|folk|album|recording|concert|orchestra|instrument|guitar|piano|banjo|trumpet|saxophone|a cappella|hip.hop|synthesizer|audio|mp3)\b/i;
const BLOCKED = /^(?:File|Category|Template|Help|Portal|Wikipedia|Special|Talk|User|Draft|MediaWiki):|\(disambiguation\)$|^List of /i;
export const isMusicText = text => MUSIC.test(String(text || ''));
export const cleanText = text => String(text || '').replace(/\[\d+(?:,\s*\d+)*\]/g, '').replace(/\s+/g, ' ').trim();
export const wikiURL = (title, revision) => revision ? `https://en.wikipedia.org/w/index.php?oldid=${encodeURIComponent(revision)}` : 'https://en.wikipedia.org/wiki/' + encodeURIComponent(String(title).replace(/ /g, '_'));
export function articleTitle(href) {
  try {
    const u = new URL(href, 'https://en.wikipedia.org/wiki/');
    if (u.hostname !== 'en.wikipedia.org' || !u.pathname.startsWith('/wiki/')) return null;
    const title = decodeURIComponent(u.pathname.slice(6)).replace(/_/g, ' ').trim();
    return title && title.length <= 220 && !BLOCKED.test(title) ? title : null;
  } catch { return null; }
}
export function youtubeReference(url) {
  try { const u = new URL(url); if (u.protocol !== 'https:') return null;
    const id = ['youtu.be','www.youtu.be'].includes(u.hostname) ? u.pathname.slice(1) : ['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'].includes(u.hostname) ? u.searchParams.get('v') : null;
    return /^[\w-]{11}$/.test(id || '') ? id : null;
  } catch { return null; }
}
export function safeCommonsAudio(url) {
  try { const u=new URL(url); return u.protocol==='https:' && u.hostname==='upload.wikimedia.org' && u.pathname.startsWith('/wikipedia/commons/') ? u.href : null; } catch { return null; }
}
export function classifyArticle(article) {
  const first = article.blocks.filter(b=>b.kind==='p').slice(0,2).map(b=>b.text).join(' ');
  return isMusicText(article.title + ' ' + first);
}
export function branchCandidates(article, facet) {
  if (!MATCH[facet]) return [];
  const musicalArticle = classifyArticle(article), found = new Map();
  for (const block of article.blocks) {
    const context = cleanText(block.heading + ' ' + block.text);
    if (!musicalArticle && !isMusicText(block.text + ' ' + block.heading)) continue;
    if (!MATCH[facet].test(context)) continue;
    if(facet==='divergence'&&/award|grammy|nominat|hall of fame|induct|compilation/i.test(context)&&!/influenc|evol|deriv|populariz|popularis|pioneer|inspir|fusion|spread|develop|emerge|crossover|contribut/i.test(context))continue;
    for (const link of block.links) {
      const title=cleanText(link.title);
      if(facet==='divergence'&&/award|grammy|hall of fame|national medal/i.test(title))continue;
      if (!title || BLOCKED.test(title) || title.toLowerCase()===article.title.toLowerCase()) continue;
      // A generic historical article cannot take the exploration away from music.
      if (!musicalArticle && !MUSIC_ANCHORS.test(title+' '+link.text) && !isMusicText(block.heading)) continue;
      let score=2+(MATCH[facet].test(title+' '+link.text)?7:0)+(MATCH[facet].test(block.heading)?4:0)+(isMusicText(title)?2:0);
      if(facet==='divergence'&&MUSIC_ANCHORS.test(title+' '+link.text))score+=4;
      if (facet==='divergence' && /deriv|influenc|evol|stylistic|origins|fusion|development/i.test(block.heading)) score+=8;
      if (facet==='politics' && !MATCH.politics.test(title+' '+link.text)) score-=3;
      if (facet==='instruments' && !MATCH.instruments.test(title+' '+link.text)) score-=4;
      if (facet==='technology' && !MATCH.technology.test(title+' '+link.text)) score-=4;
      if (score<1) continue;
      const key=title.toLocaleLowerCase();const prev=found.get(key);
      const candidate={title,score,excerpt:excerptAround(block.text,link.text||title),section:block.heading||'Introduction',source_title:article.title,source_url:wikiURL(article.title,article.revision),source_revision:article.revision,source_links:block.references||[],facet,musical_context:musicalArticle||isMusicText(block.text)};
      if (!prev||prev.score<score) found.set(key,candidate);
    }
  }
  return [...found.values()].sort((a,b)=>b.score-a.score||a.title.localeCompare(b.title));
}
export function makeConnection(fromId, toId, candidate, retrievedAt) {
  if (!fromId || !toId || !candidate.musical_context) throw Error('A musical source context is required.');
  return { id: `live-edge:${fromId}:${candidate.facet}:${toId}`, from_id:fromId, to_id:toId, type:'source-linked '+candidate.facet, evidence:'context', label:`Linked in ${candidate.source_title} · ${candidate.section}`, sources:[], live:true, source_url:candidate.source_url, source_revision:candidate.source_revision||null, excerpt:candidate.excerpt, facet:candidate.facet, retrieved_at:retrievedAt };
}
export function mergeGraph(graph, incoming) {
  const nodes=new Map(graph.nodes.map(n=>[n.id,n])), edges=new Map(graph.edges.map(e=>[e.id,e])), sources=new Map(graph.sources.map(s=>[s.id,s]));
  for(const n of incoming.nodes||[]) nodes.set(n.id,n);
  for(const e of incoming.edges||[]) { if(!nodes.has(e.from_id)||!nodes.has(e.to_id)) throw Error('Disconnected branch'); edges.set(e.id,e); }
  for(const s of incoming.sources||[]) sources.set(s.id,s);
  return {...graph,nodes:[...nodes.values()],edges:[...edges.values()],sources:[...sources.values()]};
}
export function displayQuote(text, maxWords=24) { const words=cleanText(text).split(' ');return words.slice(0,maxWords).join(' ')+(words.length>maxWords?'…':''); }
export function validCachedGraph(g) {
  try {
    if (!g || g.version!==1 || !Array.isArray(g.nodes) || !Array.isArray(g.edges) || !Array.isArray(g.sources) || !Array.isArray(g.trail)) return false;
    const sourceIds=new Set(g.sources.map(s=>s.id));
    return g.nodes.every(n=>n && typeof n.id==='string' && n.id.length<400 && typeof n.title==='string' && n.live===true && Array.isArray(n.sources) && n.sources.every(s=>typeof s==='string') && (n.start===null||Number.isInteger(n.start)) && (!n.place||(Number.isFinite(n.place.lat)&&Math.abs(n.place.lat)<=90&&Number.isFinite(n.place.lon)&&Math.abs(n.place.lon)<=180)) && (!n.play||n.play.type==='youtube'&&/^[\w-]{11}$/.test(n.play.id||'')||n.play.type==='soundcloud'&&(/^\d+$/.test(String(n.play.id||''))||Boolean(soundCloudURL(n.play.url)&&/^\/[^/]+\/[^/]+\/?$/.test(new URL(n.play.url).pathname)))||n.play.type==='commons_audio'&&Boolean(safeCommonsAudio(n.play.url)))) && g.edges.every(e=>e && typeof e.id==='string' && typeof e.from_id==='string' && typeof e.to_id==='string' && e.evidence==='context' && e.live===true && Array.isArray(e.sources)) && g.sources.every(s=>s && typeof s.id==='string' && typeof s.url==='string' && new URL(s.url).protocol==='https:' && ['en.wikipedia.org','commons.wikimedia.org','www.wikidata.org','soundcloud.com','api.soundcloud.com','w.soundcloud.com','www.youtube.com','youtube.com','youtu.be','open.spotify.com'].includes(new URL(s.url).hostname)) && g.trail.every(id=>typeof id==='string');
  } catch { return false; }
}

export function wikibaseID(properties) {
 const value=Array.isArray(properties)?properties.find(x=>x.name==='wikibase_item'):properties?.wikibase_item;
 const id=typeof value==='string'?value:value?.['*']||value?.value;
 return /^Q\d+$/.test(id||'')?id:null;
}

export function excerptAround(text, anchor, size=65) {
 const clean=cleanText(text),words=clean.split(' '),at=clean.toLocaleLowerCase().indexOf(cleanText(anchor).toLocaleLowerCase());
 if(at<0)return words.slice(0,size).join(' ')+(words.length>size?'…':'');
 const before=clean.slice(0,at).trim().split(/\s+/).filter(Boolean).length,start=Math.max(0,before-8),end=Math.min(words.length,start+size);
 return (start?'…':'')+words.slice(start,end).join(' ')+(end<words.length?'…':'');
}

export function sourceDates(claims) {
 const first=k=>claims[k]?.find(x=>x.rank!=='deprecated')?.mainsnak?.datavalue?.value;
 const year=v=>v?.precision>=9?Number(/^([+-]\d+)/.exec(v.time||'')?.[1]):null;
 const property=['P580','P571','P577'].find(p=>Number.isInteger(year(first(p))));
 if(!property)return {start:null,end:null,date_role:null};
 const start=year(first(property)),last=year(first('P582'));
 return {start,end:Number.isInteger(last)&&last>=start?last:start,date_role:({P580:'event start/end',P571:'inception',P577:'publication'})[property]};
}
