'use strict';
const assert=require('node:assert/strict');
const intake=require('../dist/intake.js');
const {connect,STATUS,RECEIVE}=require('../dist/site-tools.js');

(async()=>{
  const tools=new Map(),events=[],loaded=[];
  const context={registerTool:tool=>tools.set(tool.name,tool),unregisterTool:name=>tools.delete(name)};
  const inbox=new intake.Inbox(item=>loaded.push(item));
  const connection=await connect({context,inbox,onConnection:value=>events.push(value)});
  assert.equal(connection.available,true);
  assert.deepEqual(events,['available']); // Availability is not contact.
  const send=tools.get(RECEIVE).execute;
  const reply={id:'r1',conversationId:'test-chat',role:'assistant',status:'completed',text:'First paragraph.\n\nSecond paragraph.\n\nThird paragraph.'};
  assert.equal((await tools.get(STATUS).execute()).conversationSubscription,false);
  assert.equal(events.at(-1),'contact');
  assert.equal((await send({...reply,text:'One.\n\nTwo.'})).accepted,false);
  assert.equal((await send({...reply,role:'user'})).accepted,false);
  assert.equal((await send({...reply,status:'draft'})).accepted,false);
  assert.equal((await send(null)).accepted,false);
  assert.equal((await send({...reply,text:'## Heading\n\nOne.\n\nTwo.'})).accepted,false);
  const first=await send(reply);
  assert.equal(first.delivery,'loaded');
  assert.equal(first.audioStarted,false);
  assert.equal(loaded[0].text,reply.text);
  assert.equal((await send(reply)).duplicate,true);
  assert.equal(loaded.length,1);
  const second=await send({...reply,id:'r2'});
  assert.equal(second.delivery,'queued');
  assert.equal(inbox.queue.length,1);
  assert.equal(loaded.length,1); // Active reading is preserved.
  const status=await tools.get(STATUS).execute();
  assert.equal(status.lastReceipt.id,'r2');
  assert.equal(status.pendingReplies,1);
  assert.equal('text' in status,false);
  inbox.enabled=false;
  assert.equal((await send({...reply,id:'r3'})).reason,'disabled');
  inbox.enabled=true;
  assert.equal((await send({...reply,id:'r3'})).accepted,true); // Opt-out did not consume ID.
  const anotherChat=await send({...reply,conversationId:'another-chat'});
  assert.equal(anotherChat.duplicate,false);
  while(inbox.queue.length<50)await send({...reply,id:`queued-${inbox.queue.length}`});
  assert.equal((await send({...reply,id:'overflow'})).reason,'queue-full');
  connection.dispose();
  assert.equal(tools.size,0);
  assert.equal((await send({...reply,id:'closed'})).reason,'reader-closed');

  const unsupported=[];
  const absent=await connect({inbox,onConnection:x=>unsupported.push(x)});
  assert.equal(absent.available,false);
  assert.deepEqual(unsupported,['unsupported']);
  const remaining=new Set(),failed=[];
  const broken=await connect({inbox,context:{registerTool:tool=>{if(tool.name===RECEIVE)throw Error('registration failed');remaining.add(tool.name);},unregisterTool:name=>remaining.delete(name)},onConnection:x=>failed.push(x)});
  assert.equal(broken.available,false);
  assert.deepEqual(failed,['error']);
  assert.equal(remaining.size,0); // Partial registration is removed.
  console.log('Direct reader tools: registration, receipt, eligibility, opt-out, duplicate, protected queue and cleanup checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
