// Visual interpretations of periods, never a classification of a culture or sound.
const theme = (id, label, period, colors, globe) => ({id, label, period, colors, globe});
export const ERA_THEMES = [
  theme('afterworlds', 'AFTERWORLDS', 'Slate & lime',
    {bg:'#080d10',surface:'#10171b',raised:'#1b272d',text:'#edf5f4',muted:'#b2c1c7',line:'#35474f',accent:'#c5f486',onAccent:'#10180c',secondary:'#a2d9e0'},
    {top:'#294c50',mid:'#142b31',bottom:'#080f16',line:'#8cb8b5',grid:'#577b80',documented:'#c5f486',context:'#e6ae91'}),
  theme('manuscript', 'Manuscript', 'Before 1800',
    {bg:'#e8dfc9',surface:'#f7f0df',raised:'#ded2b6',text:'#302c25',muted:'#625646',line:'#ac9d7e',accent:'#7a3528',onAccent:'#fff4de',secondary:'#41594e'},
    {top:'#887c5e',mid:'#514e3d',bottom:'#302f2b',line:'#e7d8b5',grid:'#b6a680',documented:'#f4dc94',context:'#e5b79c'}),
  theme('engraved', 'Engraved', '1800–1919',
    {bg:'#e9e5d9',surface:'#faf6eb',raised:'#ded8c8',text:'#2b3430',muted:'#536055',line:'#a5ac9b',accent:'#2d594a',onAccent:'#fbf5e8',secondary:'#85452e'},
    {top:'#536b5b',mid:'#2c433a',bottom:'#132722',line:'#e5dcba',grid:'#9ca991',documented:'#f3d88e',context:'#eab59c'}),
  theme('deco', 'Art deco', '1920–1939',
    {bg:'#101c1d',surface:'#162729',raised:'#22383a',text:'#f5ecd7',muted:'#bfcbc5',line:'#566864',accent:'#e6c786',onAccent:'#1b231f',secondary:'#9ed0c6'},
    {top:'#345857',mid:'#1c3438',bottom:'#0c1a20',line:'#d5c38e',grid:'#7a9a8e',documented:'#f5d895',context:'#b7ded1'}),
  theme('midcentury', 'Mid-century', '1940–1959',
    {bg:'#f0ece1',surface:'#fcf8ee',raised:'#e2e3d5',text:'#20363b',muted:'#4f6260',line:'#9caea5',accent:'#12646b',onAccent:'#fff9ed',secondary:'#a13e2c'},
    {top:'#5c9b9b',mid:'#2c646d',bottom:'#183b4a',line:'#f1e6bc',grid:'#a4cbc0',documented:'#f2d285',context:'#f3aa8e'}),
  theme('pop', 'Pop art', '1960s',
    {bg:'#f5e9a7',surface:'#fff8df',raised:'#ebdfa8',text:'#192342',muted:'#51536b',line:'#8b865e',accent:'#aa1458',onAccent:'#fff9df',secondary:'#006478'},
    {top:'#368b9d',mid:'#19566c',bottom:'#133149',line:'#fff2a8',grid:'#a5ddd7',documented:'#ffdf54',context:'#ffa9cb'}),
  theme('analog', 'Analog warmth', '1970s',
    {bg:'#261c16',surface:'#33271e',raised:'#49362a',text:'#f8ebd4',muted:'#d2bda2',line:'#78634d',accent:'#f4ae72',onAccent:'#2a1a0e',secondary:'#d5db93'},
    {top:'#6d7250',mid:'#3b4937',bottom:'#202b26',line:'#e1c98c',grid:'#b0a17b',documented:'#ffc08a',context:'#d6df99'}),
  theme('electric', 'Electric colour', '1980s',
    {bg:'#130f20',surface:'#20172e',raised:'#332342',text:'#f6edf9',muted:'#c9bcd8',line:'#665575',accent:'#f3afe1',onAccent:'#271329',secondary:'#8de0ed'},
    {top:'#4d4d80',mid:'#282e56',bottom:'#11182e',line:'#b9c9ee',grid:'#8386bd',documented:'#f3afe1',context:'#8de0ed'}),
  theme('rave', 'After hours', '1990s',
    {bg:'#101411',surface:'#192019',raised:'#2c3526',text:'#f2f5e7',muted:'#bec9ae',line:'#52634a',accent:'#d4f969',onAccent:'#18210b',secondary:'#d1b4ff'},
    {top:'#3c5650',mid:'#203730',bottom:'#0e1b1a',line:'#b7cca1',grid:'#718e6a',documented:'#d4f969',context:'#d1b4ff'}),
  theme('digital', 'Digital blue', '2000s',
    {bg:'#0b1520',surface:'#132230',raised:'#213544',text:'#eaf4fa',muted:'#b2c9d7',line:'#456274',accent:'#98deef',onAccent:'#0c2934',secondary:'#c1c0ff'},
    {top:'#3c6d85',mid:'#1d425c',bottom:'#102235',line:'#a5d4e4',grid:'#5f95b3',documented:'#98deef',context:'#c1c0ff'}),
];
export const BASE_THEME = ERA_THEMES[0];
export function themeForYear(year) {
  if (!Number.isInteger(year)) return BASE_THEME;
  const id = year < 1800 ? 'manuscript' : year < 1920 ? 'engraved' : year < 1940 ? 'deco' : year < 1960 ? 'midcentury' : year < 1970 ? 'pop' : year < 1980 ? 'analog' : year < 1990 ? 'electric' : year < 2000 ? 'rave' : year < 2010 ? 'digital' : 'afterworlds';
  return ERA_THEMES.find(t => t.id === id);
}
const yearLabel = year => year < 0 ? Math.abs(year)+' BCE' : String(year);
export function appearanceFor(node, {mode='auto', parentOf=()=>null}={}) {
  const manual = ERA_THEMES.find(t=>t.id===mode);
  if(manual) return {theme:manual, label:manual.period+' / '+manual.label, note:'Manual appearance. The selected point’s dates are unchanged.', inherited:false};
  const visited = new Set(); let dated=node;
  while(dated && !Number.isInteger(dated.start)) {
    if(visited.has(dated.id)){dated=null;break;}
    visited.add(dated.id); dated=parentOf(dated);
  }
  if(!dated) return {theme:BASE_THEME, label:'AFTERWORLDS / Slate & lime', note:'Date unresolved. A neutral palette keeps the period open.', inherited:false};
  const t=themeForYear(dated.start), inherited=dated!==node;
  const period=yearLabel(dated.start)+(Number.isInteger(dated.end)&&dated.end!==dated.start?'–'+yearLabel(dated.end):'');
  return {theme:t, label:t.id==='afterworlds'?'AFTERWORLDS / Slate & lime':t.period+' / '+t.label,
    note:inherited?'Date unresolved here. Continuing the atmosphere from '+period+'.':period+' · '+(dated.end>dated.start?'palette follows the opening year.':'selected point.'), inherited};
}
