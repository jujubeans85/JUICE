(function (root) {
  'use strict';
  function splitText(raw, limit = 220) {
    const text = String(raw).replace(/\r\n?/g, '\n').replace(/^\s*```[^\n]*$/gm, '').replace(/^#{1,6}\s+/gm, '').replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1 ($2)').replace(/\*\*|__/g, '').replace(/`/g, '');
    const chunks = [];
    for (const paragraph of text.split(/\n+/)) {
      let part = '';
      for (const word of paragraph.trim().split(/\s+/)) {
        if (!word) continue;
        if (part && part.length + word.length + 1 > limit) { chunks.push(part); part = ''; }
        part += (part ? ' ' : '') + word;
        if (/[.!?]$/.test(word) && part.length > 65) { chunks.push(part); part = ''; }
      }
      if (part) chunks.push(part);
    }
    return chunks;
  }
  class Reader {
    constructor(synth, Utterance, update = () => {}) {
      this.synth = synth; this.Utterance = Utterance; this.update = update;
      this.chunks = []; this.index = 0; this.offset = 0; this.boundary = 0;
      this.status = 'ready'; this.generation = 0; this.rate = 1.5; this.voice = null; this.timer = null; this.active = null;
    }
    snapshot(message = '') {
      const total = this.chunks.reduce((n, c) => n + c.length, 0);
      const done = this.chunks.slice(0, this.index).reduce((n, c) => n + c.length, 0) + this.offset;
      return { status: this.status, index: this.index, count: this.chunks.length, passage: this.chunks[this.index] || '', progress: this.status === 'finished' ? 100 : total ? Math.min(100, done / total * 100) : 0, message };
    }
    emit(message = '') { this.update(this.snapshot(message)); }
    interrupt() { this.generation++; clearTimeout(this.timer); this.timer = null; this.active = null; if (this.synth) this.synth.cancel(); }
    setText(raw) { this.interrupt(); this.chunks = splitText(raw); this.index = 0; this.offset = 0; this.boundary = 0; this.status = 'ready'; this.emit(); }
    play() {
      if (!this.chunks.length || !this.synth || !this.Utterance) return;
      if (this.status === 'playing' || this.status === 'starting') return;
      if (this.status === 'finished') { this.index = 0; this.offset = 0; }
      this.speak();
    }
    speak() {
      const chunk = this.chunks[this.index];
      if (chunk === undefined) { this.status = 'finished'; this.emit('Finished. Press Read again to restart.'); return; }
      const generation = this.generation;
      const startOffset = this.offset;
      const utterance = new this.Utterance(chunk.slice(startOffset));
      this.active = utterance; this.boundary = startOffset; utterance.rate = this.rate;
      if (this.voice) { utterance.voice = this.voice; utterance.lang = this.voice.lang; }
      else utterance.lang = 'en-AU';
      const current = () => generation === this.generation && this.active === utterance;
      this.status = 'starting'; this.emit();
      utterance.onstart = () => { if (!current()) return; clearTimeout(this.timer); this.status = 'playing'; this.emit(); };
      utterance.onboundary = event => {
        if (!current() || !Number.isFinite(event.charIndex)) return;
        this.boundary = Math.max(startOffset, Math.min(chunk.length - 1, startOffset + event.charIndex));
      };
      utterance.onend = () => {
        if (!current() || !['playing', 'starting'].includes(this.status)) return;
        clearTimeout(this.timer); this.active = null; this.index++; this.offset = 0;
        if (this.index >= this.chunks.length) { this.status = 'finished'; this.emit('Finished. Press Read again to restart.'); }
        else this.speak();
      };
      utterance.onerror = event => {
        if (!current()) return;
        this.offset = this.boundary; this.interrupt(); this.status = 'error';
        const code = event.error || 'unknown';
        this.emit(code === 'not-allowed' ? 'Tap Read aloud again. If it stays silent, open this page in Safari.' : 'The voice stopped (' + code + '). Try another voice, then press Read aloud.');
      };
      this.timer = setTimeout(() => {
        if (!current() || this.status !== 'starting') return;
        this.interrupt(); this.status = 'error'; this.emit('The voice did not start. Choose another voice or open this page in Safari.');
      }, 10000);
      try { this.synth.speak(utterance); } catch (error) { utterance.onerror({ error: error.message || 'unavailable' }); }
    }
    pause() {
      if (!['playing', 'starting'].includes(this.status)) return;
      this.offset = this.boundary; this.interrupt(); this.status = 'paused'; this.emit('Paused. Resume continues from your place.');
    }
    stop() { this.interrupt(); this.index = 0; this.offset = 0; this.boundary = 0; this.status = 'ready'; this.emit('Stopped. Read aloud starts from the beginning.'); }
    move(delta) {
      if (!this.chunks.length) return;
      const playing = ['playing', 'starting'].includes(this.status);
      const index = this.status === 'finished' ? this.chunks.length : this.index;
      this.interrupt(); this.index = Math.max(0, Math.min(this.chunks.length - 1, index + delta)); this.offset = 0; this.boundary = 0; this.status = 'paused';
      if (playing) this.speak(); else this.emit();
    }
    options(rate, voice) {
      const playing = ['playing', 'starting'].includes(this.status);
      if (playing) this.pause();
      this.rate = rate; this.voice = voice;
      if (playing) this.play(); else this.emit();
    }
  }
  root.JuiceSpeech = { splitText, Reader };
  if (typeof module !== 'undefined') module.exports = root.JuiceSpeech;
})(typeof window === 'undefined' ? globalThis : window);
