'use strict';
// Run the real browser adapter against a minimal DOM and network doubles.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
class Element {
  constructor() { this.children = []; this.events = {}; this.textContent = ''; this.disabled = false; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = [...children]; }
  addEventListener(event, handler) { (this.events[event] ||= []).push(handler); }
  click() { this.onclick?.(); }
}
const tick = () => new Promise(resolve => setImmediate(resolve));
async function harness({failureIndex = -1, stalled = false} = {}) {
  const selectors = ['drop', 'files', 'status', 'results', 'cancel'];
  const elements = Object.fromEntries(selectors.map(name => [`[data-${name}]`, new Element()]));
  const root = new Element(); root.querySelector = name => elements[name];
  const uploads = [], sent = [], batchId = 'a'.repeat(32);
  let saved = null;
  const clone = value => JSON.parse(JSON.stringify(value));
  async function fetch(url, options = {}) {
    if (url === '/api/intake') return {ok: true, json: async () => ({max_file_bytes: 2 * 1024**3, max_batch_bytes: 8 * 1024**3})};
    if (options.method === 'POST') {
      assert.equal(options.headers['X-Juice-Token'], 'test-token');
      const files = JSON.parse(options.body).files;
      sent.push(files);
      saved = {id: batchId, staging_path: '/local/capture/audio-intake/' + batchId,
        files: files.map((file, index) => ({...file, index, entries: [], status: file.name.endsWith('.pdf') ? 'rejected' : 'pending', reason: file.name.endsWith('.pdf') ? 'Unsupported type' : null}))};
    }
    return {ok: true, json: async () => clone(saved)};
  }
  class XHR {
    constructor() { this.upload = {}; this.status = 200; }
    open(method, url) { this.url = url; }
    setRequestHeader(key, value) { assert.ok(key === 'Content-Type' || value === 'test-token'); }
    send(file) {
      uploads.push(file);
      const index = Number(this.url.split('/').at(-1));
      this.index = index;
      if (stalled) return;
      queueMicrotask(() => {
        this.upload.onprogress?.({loaded: file.size});
        if (index === failureIndex) {
          this.status = 500; this.responseText = JSON.stringify({error: 'Test disk unavailable'});
        } else {
          saved.files[index].status = 'accepted';
          this.responseText = JSON.stringify(saved);
        }
        this.onload();
      });
    }
    abort() { saved.files[this.index].status = 'interrupted'; this.onabort(); }
  }
  const context = {
    window: {},
    document: {getElementById: () => root, querySelector: () => ({content: 'test-token'}), createElement: () => new Element(), createTextNode: text => ({textContent: text})},
    fetch, XMLHttpRequest: XHR,
    // Reproduce Firefox private/blocked storage: intake must still work.
    localStorage: {getItem() { throw new Error('Storage blocked'); }, setItem() { throw new Error('Storage blocked'); }},
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'intake.js'), 'utf8'), context);
  await tick();
  return {root, elements, uploads, sent, saved: () => saved, attach: context.window.JuiceAudioIntake.attach};
}
async function run() {
  const h = await harness();
  const stems = [{name: 'drums.wav', size: 200}, {name: 'bass.aiff', size: 250}, {name: 'stems.zip', size: 500}, {name: 'notes.pdf', size: 20}];
  h.elements['[data-files]'].files = stems;
  await h.elements['[data-files]'].onchange();
  await tick();
  assert.deepEqual(h.uploads, stems.slice(0, 3), 'Every supported File, not only files[0], must be uploaded');
  assert.equal(h.sent[0].length, 4);
  assert.match(h.elements['[data-status]'].textContent, /3 accepted, 1 rejected, 0 unfinished/);
  assert.equal(h.elements['[data-files]'].disabled, false);
  console.log('PASS multi-file picker, unsupported receipt, and blocked browser storage');

  const drag = await harness();
  const handler = drag.elements['[data-drop]'].events.drop.at(-1);
  handler({dataTransfer: {files: stems.slice(0, 2), items: []}});
  await tick(); await tick();
  assert.equal(drag.uploads.length, 2);
  handler({dataTransfer: {files: [], items: [{webkitGetAsEntry: () => ({isDirectory: true})}]}});
  assert.match(drag.elements['[data-status]'].textContent, /Folders are unsupported/);
  console.log('PASS drag-and-drop multiple stems and clear folder rejection');

  const failed = await harness({failureIndex: 0});
  const adapter = failed.attach(failed.root);
  await adapter.importFiles(stems.slice(0, 2));
  assert.equal(failed.uploads.length, 2, 'One failed upload must not silently abandon the next stem');
  assert.equal(failed.saved().files[0].status, 'pending');
  assert.equal(failed.saved().files[1].status, 'accepted');
  assert.match(failed.elements['[data-status]'].textContent, /1 accepted, 0 rejected, 1 unfinished/);
  console.log('PASS continuation after upload failure and honest unfinished count');

  const cancelled = await harness({stalled: true});
  const promise = cancelled.attach(cancelled.root).importFiles(stems.slice(0, 2));
  await tick();
  cancelled.elements['[data-cancel]'].onclick();
  await promise;
  assert.equal(cancelled.uploads.length, 1);
  assert.match(cancelled.elements['[data-status]'].textContent, /Stopped: 0 accepted, 0 rejected, 2 unfinished/);
  assert.equal(cancelled.elements['[data-cancel]'].disabled, true);
  console.log('PASS cancellation leaves unstarted stems visible and unlocks the UI');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
