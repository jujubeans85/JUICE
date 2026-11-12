import test from 'node:test';
import assert from 'node:assert/strict';
import {FallbackGlobe} from './globe-fallback.js';
import {Globe} from './globe.js';
for(const Renderer of [FallbackGlobe,Globe])test(Renderer.name+' reacts to an accessibility pause without inventing data',()=>{
 const g=Object.create(Renderer.prototype),events=[];g.host={dispatchEvent:e=>events.push(e.type)};
 g.paused=false;g.dirty=false;g.paused=true;assert.equal(g.paused,true);assert.equal(g.dirty,true);assert.deepEqual(events,['globe-motionchange','globe-motionchange']);
 g.dirty=false;g.paused=true;assert.equal(g.dirty,true);assert.equal(events.length,2);
});
test('a paused compatibility globe redraws on demand, while idle frames skip drawing',()=>{
 const old={devicePixelRatio:globalThis.devicePixelRatio,document:globalThis.document,matchMedia:globalThis.matchMedia,requestAnimationFrame:globalThis.requestAnimationFrame,cancelAnimationFrame:globalThis.cancelAnimationFrame,ResizeObserver:globalThis.ResizeObserver};
 const ctx={setTransform(){}},listeners=new Map(),media=new Map();let scheduled,draws=0;
 const element=()=>({style:{},setAttribute(){},getContext:()=>ctx,append(){},replaceChildren(){}});
 globalThis.devicePixelRatio=1;globalThis.document={hidden:false,createElement:element};globalThis.matchMedia=()=>({matches:true,addEventListener:(k,f)=>media.set(k,f),removeEventListener:k=>media.delete(k)});
 globalThis.requestAnimationFrame=fn=>{scheduled=fn;return 1};globalThis.cancelAnimationFrame=()=>{};
 globalThis.ResizeObserver=class{observe(){}disconnect(){}};
 const host={clientWidth:390,clientHeight:320,prepend(){},append(){},dispatchEvent(){},addEventListener:(k,f)=>listeners.set(k,f),removeEventListener:k=>listeners.delete(k)};
 try{
  const g=new FallbackGlobe(host,{arcs:[]},()=>{});g.draw=()=>draws++;assert.equal(g.paused,true);assert.deepEqual(g.markers,[]);g.resize();scheduled(40);assert.equal(draws,1);scheduled(90);assert.equal(draws,1);
  g.zoom(-.2);scheduled(140);assert.equal(draws,2);scheduled(190);assert.equal(draws,2);
  g.paused=false;scheduled(240);scheduled(290);assert.equal(draws,4);media.get('change')({matches:true});scheduled(340);assert.equal(g.paused,true);scheduled(390);assert.equal(draws,5);
  g.dispose();assert.equal(listeners.size,0);assert.equal(media.size,0);
 }finally{for(const[k,v]of Object.entries(old)){if(v===undefined)delete globalThis[k];else globalThis[k]=v;}}
});
