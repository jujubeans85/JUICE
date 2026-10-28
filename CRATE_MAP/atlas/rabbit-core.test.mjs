import test from 'node:test';
import assert from 'node:assert/strict';
import {branchCandidates,classifyArticle,articleTitle,youtubeReference,safeCommonsAudio,makeConnection,mergeGraph,validCachedGraph,wikibaseID,sourceDates,excerptAround} from './rabbit-core.mjs';
const article=(title,first,blocks=[])=>({title,revision:123,pageid:55,blocks:[{kind:'p',heading:'Introduction',text:first,links:[]},...blocks]});
const block=(heading,text,titles)=>({kind:'p',heading,text,links:titles.map(title=>({title,text:title})),references:[]});
test('political branches require a musical source context, not a shared date or place',()=>{
 const a=article('Example Choir','The ensemble is a choir of singers.',[block('History','The singers performed during the campaign against racial segregation.',['Racial segregation','Example City'])]);
 const c=branchCandidates(a,'politics');assert.ok(c.some(x=>x.title==='Racial segregation'));assert.ok(c.every(x=>x.musical_context));assert.equal(c[0].source_revision,123);
 const unrelated=article('Example War','A war between neighbouring states.',[block('Campaign','The campaign led to a political revolution.',['Example President'])]);assert.equal(branchCandidates(unrelated,'politics').length,0);
});
test('a historical branch can return to a musical section but cannot drift into unrelated politics',()=>{
 const a=article('Example War','A war between neighbouring states.',[block('Military campaign','A general met the president.',['Example President']),block('Music','The soldiers sang a hymn performed by a choir.',['Example Hymn','Example Choir'])]);
 const c=branchCandidates(a,'instruments');assert.ok(c.some(x=>x.title==='Example Hymn'));assert.ok(!c.some(x=>x.title==='Example President'));
});
test('divergence is a source link, never promoted to a documented influence',()=>{
 const a=article('Example Spirituals','A traditional music genre.',[block('Derivatives','The genre influenced later gospel music and blues.',['Gospel music','Blues'])]);const c=branchCandidates(a,'divergence');assert.equal(c.length,2);const edge=makeConnection('root','child',c[0],'2026-10-29');assert.equal(edge.evidence,'context');assert.equal(edge.type,'source-linked divergence');assert.throws(()=>makeConnection('a','b',{musical_context:false}));
});
test('repeated links deduplicate and navigation namespaces do not become historical nodes',()=>{
 const b=block('Music technology','The music recording used an electric guitar.',['Electric guitar','Electric guitar','Category:Music','Special:Search']);const c=branchCandidates(article('Record','A music recording.',[b]),'technology');assert.equal(c.filter(x=>x.title==='Electric guitar').length,1);assert.ok(!c.some(x=>x.title.includes(':')));
});
test('music classification does not accept an ordinary place or political biography',()=>{assert.equal(classifyArticle(article('Example City','A town beside a river.')),false);assert.equal(classifyArticle(article('Example Singer','A musician and songwriter.')),true)});
test('provider links are parsed, never guessed or accepted from lookalike hosts',()=>{assert.equal(articleTitle('/wiki/Gospel_music'),'Gospel music');assert.equal(articleTitle('https://evil.example/wiki/Gospel_music'),null);assert.equal(articleTitle('/wiki/Category:Music'),null);assert.equal(youtubeReference('https://www.youtube.com/watch?v=lSzICmwmRsA'),'lSzICmwmRsA');assert.equal(youtubeReference('https://youtube.com.evil.example/watch?v=lSzICmwmRsA'),null);assert.equal(safeCommonsAudio('https://upload.wikimedia.org/wikipedia/commons/a/a0/Example.ogg'),'https://upload.wikimedia.org/wikipedia/commons/a/a0/Example.ogg');assert.equal(safeCommonsAudio('https://evil.example/song.ogg'),null)});
test('new forks preserve earlier nodes and cycles do not duplicate the graph',()=>{const a={nodes:[{id:'a'}],edges:[],sources:[]};const edge={id:'a-b',from_id:'a',to_id:'b'};const b=mergeGraph(a,{nodes:[{id:'b'}],edges:[edge]});const c=mergeGraph(b,{nodes:[{id:'b'}],edges:[edge,{id:'b-a',from_id:'b',to_id:'a'}]});assert.equal(c.nodes.length,2);assert.equal(c.edges.length,2);assert.equal(a.nodes.length,1);assert.throws(()=>mergeGraph(a,{edges:[{id:'bad',from_id:'a',to_id:'missing'}]}))});
test('exploration has no fixed traversal depth',()=>{let g={nodes:[{id:'0'}],edges:[],sources:[]};for(let i=1;i<=150;i++)g=mergeGraph(g,{nodes:[{id:String(i)}],edges:[{id:String(i),from_id:String(i-1),to_id:String(i)}]});assert.equal(g.nodes.length,151)});
test('invalid stored graphs and unsafe recording URLs fail closed',()=>{assert.equal(validCachedGraph(null),false);const g={version:1,nodes:[{id:'x',title:'Song',live:true,start:null,place:null,sources:[],play:{type:'commons_audio',url:'https://evil.example/audio'}}],edges:[],sources:[],trail:['x']};assert.equal(validCachedGraph(g),false);g.nodes[0].play.url='https://upload.wikimedia.org/wikipedia/commons/a/a0/Example.ogg';assert.equal(validCachedGraph(g),true);g.sources=[{id:'bad',url:'not a URL'}];assert.equal(validCachedGraph(g),false)});

test('MediaWiki v1 and v2 property shapes resolve the same entity',()=>{assert.equal(wikibaseID({wikibase_item:'Q123'}),'Q123');assert.equal(wikibaseID([{name:'wikibase_item','*':'Q123'}]),'Q123');assert.equal(wikibaseID([{name:'wikibase_item',value:'Q123'}]),'Q123');assert.equal(wikibaseID({wikibase_item:'javascript:alert(1)'}),null)});

test('an excerpt window keeps the actual linked target visible',()=>{const text='An opening description with many details before the important historical connection. The ensemble travelled along the Underground Railroad path during its tour.';assert.match(excerptAround(text,'Underground Railroad',20),/Underground Railroad/)});
test('structured source dates preserve their roles and do not infer dates from prose',()=>{const claim=time=>[{mainsnak:{datavalue:{value:{time,precision:11}}}}];assert.deepEqual(sourceDates({P580:claim('+1861-04-12T00:00:00Z'),P582:claim('+1865-05-26T00:00:00Z')}),{start:1861,end:1865,date_role:'event start/end'});assert.equal(sourceDates({P569:claim('+1971-11-04T00:00:00Z')}).start,null)});

test('award recognition is not offered as musical divergence',()=>{const a=article('Example Choir','A choir of gospel singers.',[block('Legacy and honors','The choir was nominated for the Best Gospel Album award.',['Best Gospel Album','Gospel Hall of Fame'])]);assert.equal(branchCandidates(a,'divergence').length,0)});
