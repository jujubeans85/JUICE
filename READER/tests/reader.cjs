'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const { test } = require('node:test');
const intake = require('../dist/intake.js');
const { Reader } = require('../dist/speech.js');
const reply = {type:'juice.reader.response',version:1,id:'one',conversationId:'chat',role:'assistant',status:'completed',text:'One.\n\nTwo.\n\nThree.'};

test('intake validates boundaries and preserves FIFO/current read', () => {
  for (const patch of [{version:2},{id:''},{conversationId:''},{id:'x'.repeat(257)},{text:'x'.repeat(500001)},{text:'## Title\n\nOne.\n\nTwo.'},{text:'```js\na\n\nb\n\nc\n```'}]) {
    assert.equal(intake.validate({...reply,...patch}), null);
  }
  const loaded = [], pending = [];
  const inbox = new intake.Inbox(x=>loaded.push(x.id), n=>pending.push(n));
  inbox.receive(reply);
  inbox.receive({...reply,id:'two'});
  inbox.receive({...reply,id:'three'});
  assert.deepEqual(loaded,['one']);
  assert.equal(inbox.next().id,'two');
  assert.equal(inbox.next().id,'three');
  assert.equal(inbox.next(),null);
  assert.deepEqual(loaded,['one','two','three']);
  assert.equal(pending.at(-1),0);
});

test('speech needs explicit play; pause resumes boundary; stale callbacks cannot advance', () => {
  const spoken=[];
  const reader=new Reader({cancel(){},speak(u){spoken.push(u);u.onstart();}},class {constructor(text){this.text=text;}});
  try {
    reader.setText('First passage here.\nSecond passage here.');
    assert.equal(spoken.length,0);
    reader.play();
    const old=spoken.at(-1);
    old.onboundary({charIndex:6});
    reader.pause();
    old.onend(); old.onerror({error:'cancelled'});
    assert.equal(reader.status,'paused');
    assert.equal(reader.index,0);
    reader.play();
    assert.equal(spoken.at(-1).text,'passage here.');
    old.onend();
    assert.equal(reader.index,0);
    spoken.at(-1).onend();
    assert.equal(spoken.at(-1).text,'Second passage here.');
    spoken.at(-1).onend();
    assert.equal(reader.snapshot().progress,100);
    reader.play();
    assert.equal(spoken.at(-1).text,'First passage here.');
    const active=spoken.at(-1);
    reader.setText('Replacement.'); active.onend();
    assert.equal(reader.status,'ready');
    assert.equal(reader.index,0);
  } finally {reader.stop();}
});

test('speech failure is recoverable and unavailable speech stays idle', () => {
  const reader=new Reader({cancel(){},speak(){throw Error('unavailable');}},class {});
  try {reader.setText('Hello.');reader.play();assert.equal(reader.status,'error');reader.stop();assert.equal(reader.status,'ready');}
  finally {reader.stop();}
  const unavailable=new Reader(null,null);unavailable.setText('Hello.');unavailable.play();assert.equal(unavailable.status,'ready');
});

function clientHarness() {
  const messages=[],channels=[],timers=new Map(),receipts=[];
  let now=100000;
  const root={JuiceIntake:intake,location:new URL('https://jc.example/dashboard/'),crypto:{randomUUID:()=> 'client-one'},
    BroadcastChannel:class {constructor(name){this.name=name;channels.push(this);}postMessage(x){messages.push(x);}close(){this.closed=true;}},
    setInterval(fn){timers.set(1,fn);return 1;},clearInterval(id){timers.delete(id);},open(){return null;}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../dist/integration/reader-client.js'),'utf8'),{window:root,URL,Date:{now:()=>now}});
  return {root,messages,channels,timers,receipts,advance(){now+=36000;timers.get(1)();},create(){return root.JuiceReaderClient.create({onDelivery:x=>receipts.push(x)});}};
}

test('client enforces same origin and requires acknowledgement before delivered', () => {
  const h=clientHarness();
  assert.throws(()=>h.root.JuiceReaderClient.create({readerPath:'https://elsewhere.example/'}),/same JC origin/);
  assert.equal(h.channels.length,0);
  const c=h.create(), channel=h.channels[0];
  const send=data=>channel.onmessage({data});
  assert.equal(c.status().connected,false);
  assert.equal(c.publish(reply).state,'queued');
  send({...reply,type:'juice.reader.ack',clientId:'another-client',accepted:true});
  assert.equal(c.status().pending,1);
  send({...reply,type:'juice.reader.ack',clientId:'client-one',accepted:false,reason:'disabled'});
  assert.equal(c.status().pending,1);
  assert.equal(h.receipts.at(-1).reason,'disabled');
  send({type:'juice.reader.ready',clientId:'client-one'});
  assert.equal(c.status().connected,true);
  assert.equal(h.messages.at(-1).id,reply.id);
  send({...reply,type:'juice.reader.ack',clientId:'client-one',accepted:true});
  assert.equal(c.status().pending,0);
  assert.equal(c.publish(reply).duplicate,true);
  assert.equal(c.open().reason,'popup-blocked');
  h.advance();assert.equal(c.status().connected,false);
  c.close();assert.equal(channel.closed,true);assert.equal(h.timers.size,0);
  assert.equal(c.publish(reply).reason,'closed');
});

test('client eligibility and queue capacity protect unread replies', () => {
  const h=clientHarness(), c=h.create();
  assert.equal(c.publish({...reply,role:'user'}).state,'ignored');
  for(let i=0;i<50;i++)assert.equal(c.publish({...reply,id:String(i)}).state,'queued');
  assert.equal(c.publish({...reply,id:'overflow'}).reason,'queue-full');
  assert.equal(c.status().pending,50);
  assert.equal(c.publish({...reply,id:'0'}).state,'queued');
  c.close();assert.equal(c.status().pending,0);
  delete h.root.BroadcastChannel;
  assert.throws(()=>h.create(),/authenticated JC event stream/);
});
