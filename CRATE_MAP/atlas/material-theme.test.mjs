import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {MATERIALS,materialFor} from './material-theme.mjs';
import {ConceptEngine} from './concept-engine.mjs';
const registry=JSON.parse(readFileSync(new URL('./concepts.json',import.meta.url)));
const history=JSON.parse(readFileSync(new URL('./history.json',import.meta.url)));
const engine=new ConceptEngine(registry,history);
test('all three directions differ in material, finish and framing, not just colour',()=>{
 const looks=['mosaic','deco','pop'].map(id=>MATERIALS[id]);
 assert.equal(new Set(looks.map(v=>v.style.pattern)).size,3);
 assert.equal(new Set(looks.map(v=>v.style.frame)).size,3);
 assert.ok(looks[0].style.shine>30);assert.ok(looks[2].style.shine<5);
});
test('decade, genre label and nationality alone do not turn visual styling into historical evidence',()=>{
 for(const t of [{artist:'Unknown',title:'Unknown',year:1928,nationality:'French'},{artist:'Unknown',title:'Unknown',year:1967},{artist:'Unknown',title:'Unknown',genre:'jazz'}]){
  const fit=engine.match({...t,url:'https://soundcloud.com/synthetic/record'}),before=JSON.stringify(fit);
  materialFor(fit);assert.equal(JSON.stringify(fit),before);assert.equal(fit.historical_node_id,null);
  if(!fit.scene_id)assert.equal(materialFor(fit).id,'mosaic');
 }
});
test('reviewed and suggested scenes use the existing registry motifs without changing fits',()=>{
 const outputs=[];
 for(const s of registry.scenes){const fit={scene_id:s.id,status:'suggested',label:s.label,confidence:'metadata suggestion',visual:engine.visual(s)},before=JSON.stringify(fit);const m=materialFor(fit);assert.equal(JSON.stringify(fit),before);assert.ok(m.style.pattern);outputs.push(m);}
 assert.ok(outputs.some(v=>v.style.pattern==='notation'));assert.ok(outputs.some(v=>v.style.pattern==='grooves'));assert.ok(outputs.some(v=>v.style.pattern==='cinema'));assert.ok(outputs.some(v=>v.id==='pop'));assert.ok(outputs.some(v=>v.id==='deco'));
});
test('open, ambiguous and neutral matches use Mosaic Night regardless of date fallback',()=>{
 for(const status of ['pending','review','conflict'])assert.equal(materialFor({status,scene_id:null,visual:{family_id:'pop'}}).id,'mosaic');
 assert.equal(materialFor({status:'chosen',scene_id:null,override:true}).id,'mosaic');
});
test('manual appearance is a reversible preview and cannot change record concepts',()=>{
 const fit=engine.forNode(history.nodes.find(n=>registry.node_bindings[n.id])),before=JSON.stringify(fit);
 for(const mode of Object.keys(MATERIALS)){assert.equal(materialFor(fit,{mode}).id,mode);assert.equal(JSON.stringify(fit),before);assert.match(materialFor(fit,{mode}).note,/unchanged/);}
 assert.equal(materialFor(fit).scope,'reviewed');
});
