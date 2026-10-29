import {Globe} from './globe.js';
import {FallbackGlobe} from './globe-fallback.js';
import {MATERIALS} from './material-theme.mjs';
const $=s=>document.querySelector(s);
let globe;
function choose(id){const look=MATERIALS[id];document.body.dataset.design=id;$('#look-title').textContent=look.label;$('#look-era').textContent=look.description;$('#look-description').textContent=look.style.pattern+' surface · '+(look.style.shine>30?'polished light':'matte finish')+'. The same material definitions now power the Atlas review branch.';document.querySelectorAll('[data-look]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.look===id)));if(!globe)return;globe.setPalette(look.palette);globe.setStyle({...look.style,lights:look.lights});$('#surface-status').textContent=globe.ball?'WEBGL / PROCEDURAL MATERIAL':'CANVAS COMPATIBILITY / NO PHYSICAL REFLECTIONS';}
try{const topo=await fetch('./vendor/countries-110m.json').then(r=>r.json());try{globe=new Globe($('#review-globe'),topo,()=>{});}catch{globe=new FallbackGlobe($('#review-globe'),topo,()=>{});}choose('mosaic');$('#motion').textContent=globe.paused?'Resume rotation':'Pause rotation';}catch{$('#surface-status').textContent='Globe unavailable; visual tokens still selectable';$('#motion').disabled=true;}
document.querySelectorAll('[data-look]').forEach(b=>b.onclick=()=>choose(b.dataset.look));
function motionLabel(){if(globe)$('#motion').textContent=globe.paused?'Resume rotation':'Pause rotation';}
$('#motion').onclick=()=>{globe.paused=!globe.paused;motionLabel()};$('#review-globe').addEventListener('globe-motionchange',motionLabel);window.addEventListener('pagehide',()=>globe?.dispose(),{once:true});
