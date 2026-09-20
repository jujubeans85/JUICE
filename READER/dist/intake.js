(function(root){
  'use strict';
  const CHANNEL='juice-reader-v1';
  function paragraphs(text){
    // Count prose/list blocks separated by blank lines. A fenced code block counts once.
    const withoutFences=String(text).replace(/```[^\n]*\n[\s\S]*?```/g,'\n\n[code block]\n\n');
    return withoutFences.split(/\n\s*\n/).map(x=>x.trim()).filter(x=>x&&!/^#{1,6}\s+[^\n]+$/.test(x)&&!/^[-*_]{3,}$/.test(x)).length;
  }
  function validate(value){
    if(!value||value.type!=='juice.reader.response'||value.version!==1||value.role!=='assistant'||value.status!=='completed')return null;
    if(typeof value.id!=='string'||!value.id||value.id.length>256||typeof value.text!=='string'||!value.text.trim()||value.text.length>500000)return null;
    if(typeof value.conversationId!=='string'||!value.conversationId||value.conversationId.length>256)return null;
    if(paragraphs(value.text)<=2)return null;
    return {type:value.type,version:1,id:value.id,conversationId:value.conversationId,role:'assistant',status:'completed',text:value.text,title:typeof value.title==='string'?value.title.slice(0,160):'Assistant reply'};
  }
  class Inbox{
    constructor(onItem,onPending=()=>{}){this.onItem=onItem;this.onPending=onPending;this.queue=[];this.seen=new Set();this.enabled=true;this.active=false;}
    receive(raw){
      const item=validate(raw);if(!item)return {accepted:false,reason:'ineligible'};
      if(!this.enabled)return {accepted:false,reason:'disabled'};
      const id=JSON.stringify([item.conversationId,item.id]);
      if(this.seen.has(id))return {accepted:true,duplicate:true};
      // Do not discard eligible unread replies to make room silently.
      if(this.queue.length>=50)return {accepted:false,reason:'queue-full'};
      this.seen.add(id);if(this.seen.size>2000)this.seen.delete(this.seen.values().next().value);
      const delivery=this.active?'queued':'loaded';
      if(this.active){this.queue.push(item);this.onPending(this.queue.length);}else{this.active=true;this.onItem(item);}
      return {accepted:true,delivery};
    }
    next(){const item=this.queue.shift();if(item){this.active=true;this.onItem(item);}this.onPending(this.queue.length);return item||null;}
  }
  root.JuiceIntake={CHANNEL,paragraphs,validate,Inbox};
  if(typeof module!=='undefined')module.exports=root.JuiceIntake;
})(typeof window==='undefined'?globalThis:window);
