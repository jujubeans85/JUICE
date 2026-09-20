(function () {
  'use strict';
  const el = id => document.getElementById(id);
  const synth = window.speechSynthesis;
  const available = !!(synth && window.SpeechSynthesisUtterance);
  let voices = [], selectedVoice = '', preferredVoice = '', lastNotice = '', preview = null, inbox = null;
  const editor = el('text');
  try { const prefs = JSON.parse(localStorage.getItem('juice-reader-prefs') || '{}'); if ([0.8,1,1.25,1.5,1.75,2].includes(prefs.rate)) el('rate').value = String(prefs.rate); preferredVoice = prefs.voice || ''; } catch (_) {}
  let userPickedVoice=!!preferredVoice;
  editor.value = window.JUICE_REPAIR_TEXT || '';
  function notice(text, error = false) { if (text && text !== lastNotice) { el('notice').textContent = text; lastNotice = text; } el('notice').classList.toggle('error', error); }
  function wordCount() { const words = editor.value.trim().split(/\s+/).filter(Boolean).length; el('count').textContent = words.toLocaleString() + ' words'; el('estimate').textContent = words ? 'About ' + Math.max(1, Math.round(words / (165 * Number(el('rate').value)))) + ' min' : 'Paste something to begin'; }
  function render(state) {
    const playing = ['playing','starting'].includes(state.status);
    el('play').textContent = playing ? 'Pause' : state.status === 'paused' ? 'Resume' : state.status === 'finished' ? 'Read again' : 'Read aloud';
    el('play').disabled = !available || !state.count;
    el('play').setAttribute('aria-label', el('play').textContent);
    el('back').disabled = !available || !state.count || state.index === 0;
    el('next').disabled = !available || !state.count || state.index >= state.count - 1;
    el('stop').disabled = !available || !state.count;
    el('progress').value = state.progress;
    el('percent').textContent = Math.floor(state.progress) + '%';
    el('position').textContent = state.status === 'finished' ? 'Finished' : state.count ? 'Passage ' + Math.min(state.index + 1, state.count) + ' of ' + state.count : 'Ready';
    el('passage').textContent = state.status === 'finished' ? 'That’s the lot.' : state.passage || 'Your next read goes here.';
    if (inbox && state.status === 'finished' && !inbox.queue.length) inbox.active = false;
    if (state.message) notice(state.message, state.status === 'error');
    else if (state.status === 'starting') notice('Starting the voice…');
    else if (state.status === 'playing') notice('Reading. You can change speed or voice as you listen.');
    else if (state.status === 'ready') notice(state.count ? 'Ready. Press Read aloud.' : 'Paste some text, then press Read aloud.');
    else if (state.status === 'paused') notice('Paused. Press Resume when you’re ready.');
  }
  const reader = new window.JuiceSpeech.Reader(synth, window.SpeechSynthesisUtterance, render);
  reader.rate = Number(el('rate').value);
  const voiceKey = window.JuiceVoices.key;
  function stopPreview() { if(preview){preview.stop();preview=null;}el('sample-voice').textContent='Listen sample'; }
  function voiceButtons() {
    el('quick-voices').replaceChildren();
    for(const voice of window.JuiceVoices.shortlist(voices)){
      const button=document.createElement('button');button.type='button';button.className='voice-choice';button.setAttribute('aria-pressed',String(voiceKey(voice)===selectedVoice));
      const name=document.createElement('span');name.className='voice-name';name.textContent=voice.name;
      const language=document.createElement('span');language.className='voice-language';language.textContent=window.JuiceVoices.dialect(voice);
      button.append(name,language);button.addEventListener('click',()=>{el('voice').value=voiceKey(voice);preferences();});el('quick-voices').append(button);
    }
    const distinct=new Set(voices.map(window.JuiceVoices.family)).size;
    el('voice-count').textContent=distinct>1?distinct+' distinct voices available. Choose one, then listen to a sample.':distinct===1?'Your browser currently exposes one voice. Open “Want more natural voices?” below.':'No named voices are exposed yet. Try Refresh voices or open the voice settings below.';
    el('sample-voice').disabled=!available;
  }
  function updateVoiceNote(voice) { el('voice-note').textContent = voice ? (voice.localService ? 'On-device voice.' : 'Online voice: text may be sent to the voice provider.') : 'Device default voice. Processing depends on your device’s voice settings.'; }
  function loadVoices() {
    if (!available) return;
    const listed = synth.getVoices(); if (!listed.length) {voiceButtons();return;}
    voices = window.JuiceVoices.list(listed);
    const keepCurrent=userPickedVoice||['playing','starting','paused'].includes(reader.status);
    const choice = (keepCurrent&&voices.find(v => voiceKey(v) === selectedVoice)) || voices.find(v => voiceKey(v) === preferredVoice) || voices[0];
    el('voice').replaceChildren();
    for (const voice of voices) { const option = document.createElement('option'); option.value = voiceKey(voice); option.textContent = voice.name + ' · ' + voice.lang + (voice.localService ? ' · on-device' : ' · online'); el('voice').append(option); }
    selectedVoice = voiceKey(choice); el('voice').value = selectedVoice; reader.voice = choice; updateVoiceNote(choice);voiceButtons();
  }
  function preferences() {
    stopPreview();
    selectedVoice = el('voice').value; preferredVoice = selectedVoice;
    userPickedVoice=true;
    const voice = voices.find(v => voiceKey(v) === selectedVoice) || null;
    reader.options(Number(el('rate').value), voice); updateVoiceNote(voice); wordCount();voiceButtons();
    try { localStorage.setItem('juice-reader-prefs', JSON.stringify({ rate: Number(el('rate').value), voice: selectedVoice })); } catch (_) {}
  }
  function refresh(manual=true) {stopPreview();reader.setText(editor.value);wordCount();if(inbox&&manual)inbox.active=!!editor.value.trim();}
  el('play').addEventListener('click', () => {stopPreview();if(inbox)inbox.active=true;if (['playing','starting'].includes(reader.status)) reader.pause(); else reader.play(); });
  el('stop').addEventListener('click', () => {stopPreview();reader.stop();});
  el('back').addEventListener('click', () => reader.move(-1));
  el('next').addEventListener('click', () => reader.move(1));
  el('rate').addEventListener('change', preferences); el('voice').addEventListener('change', preferences);
  editor.addEventListener('input', ()=>refresh());
  el('clear').addEventListener('click', () => { editor.value = ''; refresh(); editor.focus(); });
  el('example').addEventListener('click', () => { editor.value = window.JUICE_REPAIR_TEXT || ''; refresh(); notice('The JC repair prompt is loaded. Press Read aloud.'); });
  el('paste').addEventListener('click', async () => {
    try {
      if (!navigator.clipboard || !navigator.clipboard.readText) throw new Error('manual');
      const text = await navigator.clipboard.readText();
      if (!text.trim()) { notice('Your clipboard has no text. Copy a response first.'); return; }
      editor.value = text; refresh(); notice('Pasted. Press Read aloud.');
    } catch (_) { editor.focus(); editor.select(); notice('Paste into the selected text box: long-press and choose Paste, or use Command-V / Ctrl-V.'); }
  });
  el('sample-voice').addEventListener('click',()=>{
    if(!available)return;
    if(preview&&['playing','starting'].includes(preview.status)){stopPreview();return;}
    reader.pause();stopPreview();
    preview=new window.JuiceSpeech.Reader(synth,window.SpeechSynthesisUtterance,state=>{
      el('sample-voice').textContent=['playing','starting'].includes(state.status)?'Stop sample':'Listen sample';
      if(state.status==='error')notice(state.message,true);
    });
    preview.rate=Number(el('rate').value);preview.voice=reader.voice;
    preview.setText('This is JUICE Reader. Give your eyes a break. I’ll read the long stuff, and you can get on with your day.');preview.play();
  });
  el('refresh-voices').addEventListener('click',loadVoices);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')loadVoices();});
  window.addEventListener('focus',loadVoices);
  inbox=new window.JuiceIntake.Inbox(item=>{
    editor.value=item.text;refresh(false);notice(item.title+' loaded automatically. Press Read aloud.');
  },count=>{el('pending-replies').hidden=!count;el('pending-count').textContent=count+' new '+(count===1?'reply':'replies')+' ready.';});
  try{inbox.enabled=localStorage.getItem('juice-reader-auto')!=='off';}catch(_){}
  el('auto-load').checked=inbox.enabled;
  el('auto-load').addEventListener('change',()=>{inbox.enabled=el('auto-load').checked;try{localStorage.setItem('juice-reader-auto',inbox.enabled?'on':'off');}catch(_){};notice(inbox.enabled?'Automatic loading is on for replies sent by ChatGPT or your dashboard.':'Automatic loading is off. You can still paste text.');});
  el('load-next-reply').addEventListener('click',()=>{stopPreview();reader.stop();inbox.next();});
  let channel=null,stream=null,lastContact=0,heartbeat=null,hasReceived=false;
  const connected=(received=false)=>{lastContact=Date.now();hasReceived=hasReceived||received;el('connection-state').textContent=hasReceived?'Receiving dashboard replies':'Dashboard link ready — awaiting replies';};
  const config=window.JUICE_READER_CONFIG||{};
  if(config.installed===true)el('integration-help').hidden=true;
  if(typeof BroadcastChannel!=='undefined'){
    channel=new BroadcastChannel(window.JuiceIntake.CHANNEL);
    channel.onmessage=event=>{
      const data=event.data;if(!data||typeof data!=='object')return;
      if(data.type==='juice.reader.ping'){connected();channel.postMessage({type:'juice.reader.ready',version:1,clientId:data.clientId});return;}
      if(data.type!=='juice.reader.response')return;
      const result=inbox.receive(data);if(result.accepted)connected(true);
      channel.postMessage({type:'juice.reader.ack',version:1,clientId:data.clientId,id:data.id,conversationId:data.conversationId,...result});
    };
    channel.postMessage({type:'juice.reader.ready',version:1});
    heartbeat=setInterval(()=>{if(!stream&&lastContact&&Date.now()-lastContact>35000)el('connection-state').textContent='Dashboard disconnected';},10000);
  }
  if(config.eventsUrl){
    try{
      const url=new URL(config.eventsUrl,location.href);
      if(url.origin!==location.origin||!['http:','https:'].includes(url.protocol))throw new Error('origin');
      stream=new EventSource(url.href,{withCredentials:true});stream.onopen=()=>connected();
      stream.onerror=()=>{el('connection-state').textContent='Dashboard reconnecting…';};
      const accept=event=>{try{const result=inbox.receive(JSON.parse(event.data));if(result.accepted)connected(true);}catch(_){}};
      stream.onmessage=accept;stream.addEventListener('assistant.response.completed',accept);
    }catch(_){el('connection-state').textContent='Dashboard connection unavailable';}
  }
  let siteTools=null,leaving=false;
  window.JuiceSiteTools.connect({
    context:document.modelContext||navigator.modelContext,
    inbox,
    state:()=>({playback:reader.status,editorCharacters:editor.value.length}),
    onConnection:status=>{
      const labels={unsupported:'Open in ChatGPT desktop to connect.',available:'ChatGPT tools ready — awaiting contact.',contact:'ChatGPT connected — awaiting a reply.',received:'ChatGPT connected — reply received.',error:'Connection tools could not start. Reload to retry.'};
      el('chatgpt-state').textContent=labels[status];
    },
    onReceipt:receipt=>{
      el('chatgpt-receipt').hidden=false;
      el('chatgpt-receipt').textContent=receipt.duplicate?'Reply already received — no duplicate added.':receipt.delivery==='queued'?'New reply queued. Your current read is unchanged.':'Reply loaded. Press Read aloud.';
    }
  }).then(connection=>{siteTools=connection;if(leaving)connection.dispose();});
  window.addEventListener('pagehide',()=>{leaving=true;stopPreview();reader.stop();if(channel)channel.close();if(stream)stream.close();clearInterval(heartbeat);if(siteTools)siteTools.dispose();});
  refresh(false);
  if (!available) { notice('Speech is unavailable in this browser. Open this page in Safari, Chrome or Edge on your device.', true); el('voice').disabled = true; }
  else { loadVoices(); synth.addEventListener('voiceschanged', loadVoices); setTimeout(loadVoices, 600); setTimeout(loadVoices, 2000); notice('The JC repair prompt is loaded. Press Read aloud.'); }
  // A read link can preload a reply without putting its text into an HTTP request.
  if(location.hash.startsWith('#read=')){
    const text=new URLSearchParams(location.hash.slice(1)).get('read');
    history.replaceState(null,'',location.pathname+location.search);
    if(text&&text.length<=500000){editor.value=text;refresh();notice('Reply loaded. Press Read aloud.');}
  }
})();
