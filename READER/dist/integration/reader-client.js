(function(root){
  'use strict';
  function create({readerPath='/reader/',onDelivery=()=>{}}={}){
    if(!root.JuiceIntake)throw new Error('Load intake.js before reader-client.js.');
    if(typeof root.BroadcastChannel==='undefined')throw new Error('Use the authenticated JC event stream on this browser.');
    const url=new URL(readerPath,root.location.href);
    if(url.origin!==root.location.origin)throw new Error('Serve the Reader release from the same JC origin. Do not use wildcard cross-origin messaging.');
    const clientId=root.crypto.randomUUID();
    const channel=new root.BroadcastChannel(root.JuiceIntake.CHANNEL);
    const pending=new Map(),sent=new Set();let readerWindow=null,connected=false,closed=false,lastReady=0;
    const key=item=>JSON.stringify([item.conversationId,item.id]);
    function flush(){if(!closed)for(const item of pending.values())channel.postMessage({...item,clientId});}
    function ping(){if(closed)return;channel.postMessage({type:'juice.reader.ping',version:1,clientId});if(Date.now()-lastReady>35000)connected=false;}
    channel.onmessage=event=>{
      const data=event.data;if(!data||typeof data!=='object'||(data.clientId&&data.clientId!==clientId))return;
      if(data.type==='juice.reader.ready'){connected=true;lastReady=Date.now();flush();return;}
      if(data.type!=='juice.reader.ack')return;
      const id=key(data);if(!pending.has(id))return;
      if(data.accepted){pending.delete(id);sent.add(id);if(sent.size>2000)sent.delete(sent.values().next().value);}
      onDelivery({id:data.id,conversationId:data.conversationId,accepted:!!data.accepted,reason:data.reason||null,pending:pending.size});
    };
    const heartbeat=root.setInterval(ping,10000);ping();
    return {
      open(){if(closed)return {opened:false};readerWindow=root.open(url.href,'juice-reader');if(readerWindow){readerWindow.focus();ping();return {opened:true};}return {opened:false,reason:'popup-blocked'};},
      publish({id,conversationId,text,title='Assistant reply',role='assistant',status='completed'}){
        if(closed)return {state:'blocked',reason:'closed'};
        const item=root.JuiceIntake.validate({type:'juice.reader.response',version:1,id,conversationId,text,title,role,status});
        if(!item)return {state:'ignored',reason:'not-a-completed-long-assistant-reply'};
        const idKey=key(item);if(sent.has(idKey))return {state:'delivered',duplicate:true};
        if(!pending.has(idKey)&&pending.size>=50)return {state:'blocked',reason:'queue-full'};
        pending.set(idKey,item);channel.postMessage({...item,clientId});return {state:'queued',id:item.id};
      },
      status(){return {connected,pending:pending.size};},
      close(){closed=true;root.clearInterval(heartbeat);channel.close();pending.clear();}
    };
  }
  root.JuiceReaderClient={create};
})(window);
