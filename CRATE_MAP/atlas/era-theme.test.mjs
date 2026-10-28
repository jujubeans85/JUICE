import test from 'node:test';
import assert from 'node:assert/strict';
import {BASE_THEME,ERA_THEMES,themeForYear,appearanceFor} from './era-theme.mjs';

test('the entrance uses the actual AFTERWORLDS colour tokens',()=>{
  assert.equal(BASE_THEME.colors.bg,'#080d10');
  assert.equal(BASE_THEME.colors.accent,'#c5f486');
  assert.equal(appearanceFor({start:2017,end:2017}).theme.id,'afterworlds');
});
test('selected historical dates switch across period boundaries',()=>{
  for(const [year,id] of [[1773,'manuscript'],[1909,'engraved'],[1920,'deco'],[1939,'deco'],[1940,'midcentury'],[1960,'pop'],[1969,'pop'],[1970,'analog'],[1987,'electric'],[1992,'rave'],[2003,'digital'],[2010,'afterworlds']]) assert.equal(themeForYear(year).id,id,String(year));
});
test('an event range follows its opening year and discloses the range',()=>{
  const a=appearanceFor({start:1920,end:1959});assert.equal(a.theme.id,'deco');assert.match(a.note,/1920–1959/);assert.match(a.note,/opening year/);
});
test('undated music never becomes year zero or an inferred artist birth year',()=>{
  for(const start of [null,undefined,NaN,'1968'])assert.equal(appearanceFor({id:'x',start,date:'born 1968',description:'Recorded in 2020'}).theme.id,'afterworlds');
});
test('an undated branch can carry its previous atmosphere without claiming its date',()=>{
  const n={id:'clip',start:null},parent={id:'source',start:1968,end:1968};
  const a=appearanceFor(n,{parentOf:x=>x.id==='clip'?parent:null});assert.equal(a.theme.id,'pop');assert.equal(a.inherited,true);assert.match(a.note,/Date unresolved here/);assert.match(a.note,/1968/);
});
test('undated graph cycles terminate and leave chronology open',()=>{
  const a={id:'a',start:null},b={id:'b',start:null};assert.equal(appearanceFor(a,{parentOf:n=>n===a?b:a}).theme.id,'afterworlds');
});
test('manual appearances leave source records unchanged and can return to automatic',()=>{
  const n={start:1928,end:1928},snapshot=JSON.stringify(n);assert.equal(appearanceFor(n,{mode:'pop'}).theme.id,'pop');assert.match(appearanceFor(n,{mode:'pop'}).note,/Manual/);assert.equal(appearanceFor(n).theme.id,'deco');assert.equal(JSON.stringify(n),snapshot);assert.equal(appearanceFor(n,{mode:'unrecognised'}).theme.id,'deco');
});
const luminance=hex=>{const c=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722};
const contrast=(a,b)=>{const [lo,hi]=[luminance(a),luminance(b)].sort((x,y)=>x-y);return(hi+.05)/(lo+.05)};
test('every era keeps reading text, muted text and action labels above AA contrast',()=>{
  for(const t of ERA_THEMES){const c=t.colors;for(const foreground of ['text','muted','accent','secondary'])for(const background of ['bg','surface','raised'])assert.ok(contrast(c[foreground],c[background])>=4.5,`${t.id} ${foreground} on ${background}: ${contrast(c[foreground],c[background]).toFixed(2)}`);assert.ok(contrast(c.onAccent,c.accent)>=4.5,t.id+' action label');}
});
