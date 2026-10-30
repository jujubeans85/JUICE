// Presentation only. ConceptEngine remains the sole authority for record fits.
// The three directions come from design-review.mjs; no date or nationality rules.
export const MATERIALS = {
  mosaic: {id:'mosaic', label:'Mosaic Night', description:'Graphite tiles · split light',
    palette:{top:'#b8abc9',mid:'#171b29',bottom:'#070b13',line:'#d6e0ee',grid:'#728ca6',documented:'#f0a2d5',context:'#8bcde7'},
    style:{pattern:'mosaic',shine:85,type:'display',frame:'round'},lights:['#d8eaff','#e887c5']},
  deco: {id:'deco', label:'Deco Signal', description:'Engraved enamel · champagne light',
    palette:{top:'#9b946f',mid:'#162a25',bottom:'#090f10',line:'#e3ce9e',grid:'#6d8f78',documented:'#f2d3a0',context:'#9bcebb'},
    style:{pattern:'rays',shine:58,type:'serif',frame:'stepped'},lights:['#ffe3b0','#79b8aa']},
  pop: {id:'pop', label:'Print Pop', description:'Matte ink · halftone print',
    palette:{top:'#c77e64',mid:'#bb573e',bottom:'#301b32',line:'#fff0b8',grid:'#60394e',documented:'#ffcf9b',context:'#d6df93'},
    style:{pattern:'halftone',shine:2,type:'display',frame:'square'},lights:['#fff2d9','#e3a38e']},
  afterworlds: {id:'afterworlds',label:'AFTERWORLDS',description:'Slate · lime · clear surface',
    palette:{top:'#294c50',mid:'#142b31',bottom:'#080f16',line:'#b9d5d4',grid:'#577b80',documented:'#c5f486',context:'#a2d9e0'},
    style:{pattern:'clear',shine:10,type:'display',frame:'round'},lights:['#e6f5ff','#a2d9e0']}
};
const archive=new Set(['manuscript','engraved','deco']);
const print=new Set(['midcentury','pop']);
export function materialFor(fit,{mode='auto'}={}) {
  if(MATERIALS[mode])return {...MATERIALS[mode],note:'Preview choice · visual only; recording concepts and evidence are unchanged.',scope:'manual'};
  // A date-only fallback, ambiguous fit or neutral override keeps Mosaic Night.
  const usable=fit?.scene_id&&['reviewed','suggested','chosen'].includes(fit.status);
  if(!usable)return {...MATERIALS.mosaic,note:'Context open · Mosaic Night is the neutral starting surface.',scope:'open'};
  const v=fit.visual||{}, family=v.family_id;
  const id=archive.has(family)||fit.scene_id==='jazz-editorial'?'deco':print.has(family)?'pop':'mosaic',base=MATERIALS[id];
  // Keep the registry's distinctive notation, grooves, cinema and other motifs.
  // Standard pixels become the mosaic; Pop's halftone stays matte.
  const pattern=v.pattern&&v.pattern!=='clear'&&v.pattern!=='pixels'?v.pattern:base.style.pattern;
  const hybrid=['manuscript','engraved','analog','electric','digital'].includes(family);
  return {...base,palette:hybrid?{...base.palette,...v.globe}:base.palette,
    style:{...base.style,pattern,shine:hybrid?v.shine??base.style.shine:base.style.shine},
    note:fit.label+' · '+fit.confidence+'. Visual interpretation; not historical influence.',scope:fit.status};
}
