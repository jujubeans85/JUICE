import test from 'node:test';
import assert from 'node:assert/strict';
import {geolocateArticle} from './rabbit-sources.mjs';
const reply=data=>({ok:true,text:async()=>JSON.stringify(data)});
test('a topic with direct coordinates retains its sourced period for automatic appearance',async t=>{
  t.mock.method(globalThis,'fetch',async url=>{
    const u=new URL(url);if(u.hostname==='en.wikipedia.org')return reply({query:{pages:[{coordinates:[{lat:40,lon:-74}],pageprops:{wikibase_item:'Q123456789'}}]}});
    assert.equal(u.hostname,'www.wikidata.org');return reply({entities:{Q123456789:{claims:{P580:[{mainsnak:{datavalue:{value:{time:'+1968-01-01T00:00:00Z',precision:11}}}}]}}}});
  });
  const a=await geolocateArticle({title:'Fixture music festival'},{refresh:true});assert.equal(a.start,1968);assert.equal(a.date_role,'event start/end');assert.equal(a.place.lat,40);assert.match(a.place.role,/topic location/);
});
test('a failed date lookup preserves known coordinates and leaves the era unresolved',async t=>{
  t.mock.method(globalThis,'fetch',async url=>{
    if(new URL(url).hostname==='en.wikipedia.org')return reply({query:{pages:[{coordinates:[{lat:51,lon:0}],pageprops:{wikibase_item:'Q987654321'}}]}});
    throw Error('Fixture date lookup unavailable');
  });
  const a=await geolocateArticle({title:'Fixture music venue'},{refresh:true});assert.equal(a.place.lat,51);assert.equal(a.start,null);assert.match(a.geography_error,/unavailable/);
});
