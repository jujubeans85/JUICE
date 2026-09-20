(function(root){
  'use strict';
  const key = v => [v.voiceURI,v.lang,v.name].join('|');
  const family = v => v.name.replace(/\([^)]*\)/g,'').replace(/\b(enhanced|premium|compact|natural|desktop|online)\b/gi,'').replace(/\s+/g,' ').trim().toLowerCase();
  const rank = v => (/^en/i.test(v.lang)?1000:0)+(v.localService?150:0)+(/premium|enhanced|natural/i.test(v.name)?300:0)+(/^en-AU/i.test(v.lang)?60:0)+(/Karen|Samantha|Serena|Moira|Tessa|Fiona|Victoria/i.test(v.name)?10:0)+(v.default?2:0);
  function list(input){ return [...new Map(input.map(v=>[key(v),v])).values()].sort((a,b)=>rank(b)-rank(a)||a.name.localeCompare(b.name)); }
  function shortlist(input){
    const sorted=list(input), picked=[], used=new Set();
    const add = v => { if(v&&!used.has(family(v))){picked.push(v);used.add(family(v));} };
    for(const locale of ['en-AU','en-GB','en-US']) add(sorted.find(v=>v.lang.toLowerCase()===locale.toLowerCase()&&!used.has(family(v))));
    for(const v of sorted){if(picked.length>=3)break;add(v);}
    return picked.slice(0,3);
  }
  function dialect(v){ const known={'en-AU':'Australian','en-GB':'British','en-US':'American','en-IE':'Irish','en-ZA':'South African','en-IN':'Indian'};return known[v.lang]||v.lang; }
  root.JuiceVoices={key,family,rank,list,shortlist,dialect};
  if(typeof module!=='undefined')module.exports=root.JuiceVoices;
})(typeof window==='undefined'?globalThis:window);
