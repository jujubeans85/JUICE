(function(root){
  'use strict';
  const STATUS='juice_reader_status';
  const RECEIVE='juice_reader_receive_response';
  // Registration only makes tools available. An actual invocation proves contact.
  async function connect({context,inbox,state=()=>({}),onConnection=()=>{},onReceipt=()=>{}}){
    const registered=[];
    let lastReceipt=null;
    let disposed=false;
    const report=(value)=>onConnection(value);
    const status=()=>({
      autoLoad:inbox.enabled,
      minimumParagraphs:3,
      pendingReplies:inbox.queue.length,
      activeReadProtected:inbox.active,
      ...state(),
      lastReceipt,
      pageMustRemainOpen:true,
      conversationSubscription:false
    });
    const cleanup=()=>{
      disposed=true;
      if(typeof context?.unregisterTool==='function'){
        for(const name of registered){try{context.unregisterTool(name);}catch(_){}}
      }
    };
    if(typeof context?.registerTool!=='function'){
      report('unsupported');return {available:false,dispose:cleanup};
    }
    const definitions=[{
      name:STATUS,
      description:'Check the open JUICE Reader connection, automatic loading preference and last delivery receipt. Does not read the text in the editor or start audio. Use this to verify contact before claiming the reader is connected.',
      inputSchema:{type:'object',properties:{},additionalProperties:false},
      annotations:{readOnlyHint:true},
      execute:async()=>{
        if(disposed)return {error:'reader-closed'};
        report('contact');return status();
      }
    },{
      name:RECEIVE,
      description:'Send a completed assistant reply of at least three paragraphs to the user’s open JUICE Reader when the user requests it or has requested automatic forwarding. Supply the exact final reply and post the same text in chat. Never send reasoning, tool output, user messages or unfinished drafts. Loading does not start speech. A current read or manual edit is preserved; new replies queue. Reuse message and conversation IDs on retry. Check the returned receipt; tool availability alone does not mean delivery.',
      inputSchema:{
        type:'object',
        properties:{
          id:{type:'string',minLength:1,maxLength:256,description:'Stable ID for this reply. Reuse it if retrying.'},
          conversationId:{type:'string',minLength:1,maxLength:256,description:'A stable identifier for the current conversation.'},
          text:{type:'string',minLength:1,maxLength:500000,description:'The exact completed assistant response, with blank lines between paragraphs.'},
          title:{type:'string',maxLength:160,description:'A short optional reading label.'},
          role:{type:'string',enum:['assistant']},
          status:{type:'string',enum:['completed']}
        },
        required:['id','conversationId','text','role','status'],
        additionalProperties:false
      },
      annotations:{readOnlyHint:false},
      execute:async(args)=>{
        if(disposed)return {accepted:false,reason:'reader-closed'};
        report('contact');
        // Browser schemas are not authorization or validation. Use the shared gate.
        const value=args&&typeof args==='object'?{...args,type:'juice.reader.response',version:1}:null;
        const result=inbox.receive(value);
        if(!result.accepted)return {...result,autoLoad:inbox.enabled,pendingReplies:inbox.queue.length};
        const receipt={
          id:value.id,conversationId:value.conversationId,
          accepted:true,duplicate:!!result.duplicate,
          delivery:result.duplicate?'already-received':result.delivery,
          characters:value.text.length,
          paragraphs:root.JuiceIntake.paragraphs(value.text),
          pendingReplies:inbox.queue.length,
          audioStarted:false
        };
        lastReceipt=receipt;report('received');onReceipt(receipt);
        return receipt;
      }
    }];
    try{
      for(const definition of definitions){
        await context.registerTool(definition);registered.push(definition.name);
      }
      report('available');return {available:true,dispose:cleanup};
    }catch(_){
      cleanup();report('error');return {available:false,dispose:cleanup};
    }
  }
  root.JuiceSiteTools={connect,STATUS,RECEIVE};
  if(typeof module!=='undefined')module.exports=root.JuiceSiteTools;
})(typeof window==='undefined'?globalThis:window);
