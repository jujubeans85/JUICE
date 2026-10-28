const SCRIPT='https://w.soundcloud.com/player/api.js';
let loading;
export function soundCloudURL(value,{playlist=false}={}){
  try{const u=new URL(value);if(u.protocol!=='https:'||!['soundcloud.com','www.soundcloud.com'].includes(u.hostname)||u.username||u.password||u.port||u.search||u.hash)return null;
    if(playlist&&!/^\/[^/]+\/sets\/[^/]+\/?$/.test(u.pathname))return null;
    u.hostname='soundcloud.com';return u.href.replace(/\/$/,'');
  }catch{return null;}
}
export function publicSound(s){
  return {id:s.id,urn:s.urn||null,title:s.title||null,permalink_url:s.permalink_url||null,duration:s.duration||null,genre:s.genre||null,tag_list:s.tag_list||null,created_at:s.created_at||null,release_date:s.release_date||null,access:s.access||null,
    publisher_metadata:s.publisher_metadata?{artist:s.publisher_metadata.artist||null,album_title:s.publisher_metadata.album_title||null}:null,
    user:s.user?{id:s.user.id,username:s.user.username,permalink_url:s.user.permalink_url}:null};
}
export function loadWidgetAPI(){
  if(globalThis.SC?.Widget)return Promise.resolve(SC.Widget);
  if(!loading)loading=new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=SCRIPT;s.async=true;s.onload=()=>globalThis.SC?.Widget?resolve(SC.Widget):reject(Error('SoundCloud’s player API did not initialise.'));s.onerror=()=>{loading=null;reject(Error('SoundCloud’s public player API could not load.'))};document.head.append(s)});
  return loading;
}
export function readPlaylist(url,host,options={}){
  const checked=soundCloudURL(url,{playlist:true});if(!checked)throw Error('Use an exact public SoundCloud playlist URL.');return readResource(checked,host,options);
}
export function readSoundID(id,host,options={}){
  if(!/^\d+$/.test(String(id)))throw Error('Invalid SoundCloud recording ID.');return readResource('https://api.soundcloud.com/tracks/'+id,host,options);
}
async function readResource(checked,host,{signal,timeout=18000}={}){
  const Widget=await loadWidgetAPI();signal?.throwIfAborted();
  return new Promise((resolve,reject)=>{
    const frame=document.createElement('iframe');frame.title='SoundCloud source playlist';frame.width='100%';frame.height='260';frame.allow='autoplay';frame.referrerPolicy='strict-origin-when-cross-origin';frame.src='https://w.soundcloud.com/player/?'+new URLSearchParams({url:checked,auto_play:'false',show_artwork:'false',show_comments:'false',show_reposts:'false',visual:'false'});host.replaceChildren(frame);
    const widget=Widget(frame);let settled=false;
    const finish=(error,tracks)=>{if(settled)return;settled=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);widget.unbind(Widget.Events.READY);widget.unbind(Widget.Events.ERROR);if(error)reject(error);else resolve({source_url:checked,method:'SoundCloud documented Widget API getSounds',retrieved_at:new Date().toISOString(),sounds:tracks.map(publicSound)})};
    const abort=()=>finish(new DOMException('Paused','AbortError'));const timer=setTimeout(()=>finish(Error('The SoundCloud player did not provide playlist metadata before the timeout.')),timeout);signal?.addEventListener('abort',abort,{once:true});
    widget.bind(Widget.Events.ERROR,()=>finish(Error('The SoundCloud player reported that this playlist could not be loaded.')));
    widget.bind(Widget.Events.READY,()=>widget.getSounds(sounds=>{if(!Array.isArray(sounds)||!sounds.length)finish(Error('The SoundCloud player returned no ordered recordings.'));else finish(null,sounds)}));
  });
}
