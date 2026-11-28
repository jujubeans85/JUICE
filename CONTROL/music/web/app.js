/* JUICE Music — one same-origin JC client. No third-party scripts or cloud calls. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const PREVIEW = document.documentElement.dataset.preview === 'true';
  const PREVIEW_MESSAGE = 'Draft and explore here. Generation connects through your installed JC Music Door.';
  const DRAFT_KEY = PREVIEW ? 'juice.music.preview-draft.v1' : 'juice.music.unsent-draft.v1';
  const ACTIVE = new Set(['queued', 'submitting', 'running']);
  const STATUS_NAMES = { queued: 'Queued', submitting: 'Sending to engine', running: 'Making music', succeeded: 'Ready to listen', failed: 'Failed', interrupted: 'Interrupted', needs_attention: 'Needs attention', cancelled: 'Cancelled' };
  const PRESETS = {
    funk: 'Soulful funk with a warm, elastic bassline, loose live drums, Rhodes piano and cheeky brass replies. An intimate vocal, human swing, plenty of space. Build to one memorable call-and-response hook, then let it breathe.',
    choir: 'A dark, expressive choir over a slow, spacious art-funk groove. Deep bass, sparse percussion and uneasy warm harmonies. Begin close and whispered; build to a brief, powerful choral payoff, then return to silence and space.',
    house: 'Playful, off-centre house with a chunky bassline, swung drums, chopped vocal replies and a bright, unexpected keyboard hook. Soulful and tactile. A teasing pause before the groove returns; never a permanent wall of sound.'
  };
  const DEFAULT_DRAFT = { title: '', task: 'create', style: '', lyrics: '', duration: 60, composition: 'full', seed: '', source_id: '', source_name: '', request_id: '' };
  const state = { status: null, token: null, tab: 'create', filter: 'all', jobs: [], cards: new Map(), draft: { ...DEFAULT_DRAFT }, busy: false, uploading: false, connected: false, takesLoaded: false, takesError: '', pollTimer: null, toastTimer: null, jobsRequest: null, statusRequest: null };

  function string(value) { return typeof value === 'string' ? value : ''; }
  function notify(message) {
    clearTimeout(state.toastTimer);
    $('toast').textContent = message;
    $('toast').hidden = false;
    state.toastTimer = setTimeout(() => { $('toast').hidden = true; }, 4300);
  }
  function showError(id, message) {
    $(id).textContent = message || '';
    $(id).hidden = !message;
  }
  function uuid() {
    if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
    const bytes = new Uint8Array(16);
    if (globalThis.crypto?.getRandomValues) crypto.getRandomValues(bytes);
    else for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    return Array.from(bytes, (b, i) => ([4, 6, 8, 10].includes(i) ? '-' : '') + b.toString(16).padStart(2, '0')).join('');
  }
  async function api(path, options = {}) {
    if (PREVIEW) throw new Error('Interface preview: open your installed JC Music Door to use the engine and shared takes.');
    const headers = new Headers(options.headers || {});
    if (options.method && options.method !== 'GET' && state.token) headers.set('X-Juice-Token', state.token);
    if (options.json !== undefined) { headers.set('Content-Type', 'application/json'); options.body = JSON.stringify(options.json); }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeout || 30000);
    let response;
    try {
      response = await fetch(path, { method: options.method || 'GET', headers, body: options.body, credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: controller.signal });
      if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('JC did not return a music response. Open the Music Door from your running JC.');
      const data = await response.json();
      if (!response.ok || data.ok === false) {
        const message = typeof data.error === 'string' ? data.error : string(data.message) || `JC could not complete this request (${response.status}).`;
        const error = new Error(message);
        error.status = response.status;
        throw error;
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('JC took too long to respond. Your idea is saved. Check the connection and try again.');
      if (error instanceof TypeError) throw new Error('JC is not reachable. Your idea stays on this device; reconnect to continue.');
      throw error;
    } finally { clearTimeout(timer); }
  }

  function readDraft() {
    try {
      const raw = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
      if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
        state.draft = {
          ...DEFAULT_DRAFT,
          title: string(raw.title).slice(0, 120),
          task: raw.task === 'cover' ? 'cover' : 'create',
          style: string(raw.style).slice(0, 4000),
          lyrics: string(raw.lyrics).slice(0, 12000),
          duration: [30, 60, 120, 180, 240, 300, 360].includes(Number(raw.duration)) ? Number(raw.duration) : 60,
          composition: ['full', 'melody', 'off'].includes(raw.composition) ? raw.composition : 'full',
          seed: raw.seed === '' || raw.seed == null ? '' : String(raw.seed),
          source_id: string(raw.source_id), source_name: string(raw.source_name), request_id: string(raw.request_id)
        };
      }
    } catch (_) { /* A blocked or corrupt local draft must not block the studio. */ }
  }
  function saveDraft() {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(state.draft));
      $('draft-state').textContent = 'Draft saved on this device';
    } catch (_) { $('draft-state').textContent = 'Draft cannot save here · use Export'; }
  }
  function captureDraft(clearRequest = true) {
    state.draft = {
      ...state.draft,
      title: $('title').value, task: document.querySelector('input[name="task"]:checked').value,
      style: $('style').value, lyrics: $('lyrics').value, duration: Number($('duration').value),
      composition: $('composition').value, seed: $('seed').value
    };
    if (state.draft.task === 'cover') state.draft.composition = 'melody';
    if (clearRequest) state.draft.request_id = '';
    saveDraft();
    updateForm();
  }
  function applyDraft() {
    for (const key of ['title', 'style', 'lyrics', 'duration', 'composition', 'seed']) $(key).value = state.draft[key];
    document.querySelector(`input[name="task"][value="${state.draft.task}"]`).checked = true;
    updateForm();
  }
  function updateForm() {
    const cover = state.draft.task === 'cover';
    $('source-section').hidden = !cover;
    $('source-name').textContent = state.draft.source_name || (state.draft.source_id ? 'Saved reference recording' : 'Choose a recording');
    $('remove-source').hidden = !state.draft.source_id;
    $('reference-file').disabled = state.uploading || state.busy || !state.connected;
    $('composition').disabled = cover;
    if (cover) { $('composition').value = 'melody'; state.draft.composition = 'melody'; }
    const capable = Boolean(state.status?.ready && state.status?.capabilities?.[cover ? 'cover' : 'create']);
    const canSubmit = state.connected && capable && !state.busy && !state.uploading && (!cover || Boolean(state.draft.source_id));
    $('generate-button').disabled = !canSubmit;
    $('generate-label').textContent = state.busy ? 'Sending your idea…' : cover ? 'Make a rework' : 'Make music';
    let help = 'Generation runs on your connected engine.';
    if (PREVIEW) help = 'Interface preview · generation connects through JC.';
    else if (!state.connected) help = 'Write now. Connect JC when you’re ready.';
    else if (!state.status?.ready) help = 'Connect your YuE2 engine to generate.';
    else if (!capable) help = cover ? 'Audio reworks need SheetSage2 on the engine.' : 'The engine is missing a required YuE2 component.';
    else if (state.uploading) help = 'Uploading your reference recording…';
    else if (cover && !state.draft.source_id) help = 'Choose a reference recording first.';
    else if (state.busy) help = 'Keep this page open until your take joins the queue.';
    $('generate-help').textContent = help;
  }

  function updateConnection() {
    if (PREVIEW) {
      document.querySelector('.studio-heading .eyebrow').textContent = 'INTERFACE PREVIEW';
      $('connection-label').textContent = 'Preview';
      $('connection-button').className = 'connection offline';
      $('connection-button').setAttribute('aria-label', 'Interface preview. Open setup.');
      $('connection-notice').classList.remove('ready');
      $('connection-message').textContent = PREVIEW_MESSAGE;
      $('setup-badge').textContent = 'Interface preview';
      $('setup-badge').classList.remove('ready');
      $('setup-message').textContent = PREVIEW_MESSAGE;
      $('engine-name').textContent = 'YuE2 / ComfyUI';
      $('engine-model').textContent = 'Shown when connected through JC';
      $('capability-create').textContent = 'Needs your connected engine';
      $('capability-cover').textContent = 'Needs your connected engine and SheetSage2';
      $('engine-checks').hidden = true;
      $('refresh-engine').textContent = 'Preview — engine not connected';
      $('refresh-engine').disabled = true;
      updateForm();
      return;
    }
    const ready = state.connected && Boolean(state.status?.ready);
    const statusLabel = !state.connected ? 'Offline' : ready ? 'Ready' : 'Not ready';
    $('connection-label').textContent = statusLabel;
    $('connection-button').className = `connection ${ready ? 'ready' : 'offline'}`;
    $('connection-button').setAttribute('aria-label', `Music engine: ${statusLabel}. Open setup.`);
    $('connection-notice').classList.toggle('ready', ready);
    const message = !state.connected
      ? 'JC is offline or unreachable. Keep writing — your draft stays on this device.'
      : ready ? 'Your YuE2 engine is ready. Start with a short take and hear where it goes.'
        : string(state.status?.message) || 'JC is connected. The music engine needs setting up before you can generate.';
    $('connection-message').textContent = message;
    $('setup-badge').textContent = statusLabel;
    $('setup-badge').classList.toggle('ready', ready);
    $('setup-message').textContent = string(state.status?.message) || message;
    $('engine-name').textContent = string(state.status?.engine) || 'YuE2 / ComfyUI';
    $('engine-model').textContent = string(state.status?.models?.checkpoint) || 'Not configured';
    $('capability-create').textContent = state.status?.capabilities?.create ? 'Available' : 'Not available yet';
    $('capability-cover').textContent = state.status?.capabilities?.cover ? 'Available' : 'Needs SheetSage2 and audio encoder';
    $('engine-checks').replaceChildren();
    for (const task of ['create', 'cover']) {
      const errors = state.status?.checks?.[task];
      if (!Array.isArray(errors) || !errors.length) continue;
      const group = element('div');
      group.append(element('h3', '', task === 'create' ? 'For new songs' : 'For audio reworks'));
      const list = element('ul');
      for (const issue of errors) list.append(element('li', '', typeof issue === 'string' ? issue : JSON.stringify(issue)));
      group.append(list); $('engine-checks').append(group);
    }
    $('engine-checks').hidden = !$('engine-checks').childElementCount;
    updateForm();
  }
  function refreshStatus(force = false) {
    if (PREVIEW) {
      state.connected = false;
      state.status = { ready: false, message: PREVIEW_MESSAGE, capabilities: {} };
      updateConnection();
      return Promise.resolve();
    }
    if (state.statusRequest) return state.statusRequest;
    $('refresh-engine').disabled = true;
    state.statusRequest = (async () => {
      try {
        if (force && !state.token) {
          const initial = await api('/api/music/status');
          state.token = string(initial.csrf_token);
        }
        const data = await api(force ? '/api/music/refresh' : '/api/music/status', force ? { method: 'POST', json: {} } : {});
        state.status = data;
        state.token = string(data.csrf_token) || state.token;
        state.connected = true;
      } catch (error) {
        state.connected = false;
        state.status = { message: error.message, ready: false, capabilities: {} };
      } finally {
        state.statusRequest = null;
        $('refresh-engine').disabled = false;
        updateConnection();
      }
    })();
    return state.statusRequest;
  }

  function setTab(tab, focus = false) {
    if (!['create', 'takes', 'setup'].includes(tab)) return;
    state.tab = tab;
    for (const name of ['create', 'takes', 'setup']) {
      $(`panel-${name}`).hidden = name !== tab;
      $(`tab-${name}`).classList.toggle('active', name === tab);
      $(`tab-${name}`).setAttribute('aria-selected', String(name === tab));
      $(`tab-${name}`).tabIndex = name === tab ? 0 : -1;
    }
    if (focus) $(`tab-${tab}`).focus();
    if (location.hash !== `#${tab}`) {
      try { history.replaceState(null, '', `#${tab}`); } catch (_) { /* Some file viewers restrict history changes. */ }
    }
    window.scrollTo({ top: 0, behavior: 'auto' });
    if (tab === 'takes') refreshJobs();
  }

  function dateLabel(value) {
    if (!value) return '';
    const d = new Date(typeof value === 'number' && value < 100000000000 ? value * 1000 : value);
    if (Number.isNaN(d.getTime())) return '';
    return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(d);
  }
  function safeLocalUrl(raw) {
    try {
      const url = new URL(raw, location.href);
      return url.origin === location.origin && /^\/api\/music\//.test(url.pathname) ? url.href : null;
    } catch (_) { return null; }
  }
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  async function shareOutput(output, button, errorNode) {
    if (PREVIEW) { errorNode.textContent = 'Recordings are available through your installed JC Music Door.'; return; }
    const href = safeLocalUrl(output.download_url || output.url);
    if (!href) { errorNode.textContent = 'This recording does not have a valid JC download address.'; return; }
    button.disabled = true;
    errorNode.textContent = '';
    try {
      const response = await fetch(href, { credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
      if (!response.ok) throw new Error('Could not load this recording. Reconnect JC and try the download link.');
      const blob = await response.blob();
      const file = new File([blob], string(output.name) || 'juice-take.flac', { type: blob.type || 'audio/flac' });
      if (!navigator.canShare?.({ files: [file] })) throw new Error('This browser cannot share the audio file directly. Use Download, then share it from Files.');
      await navigator.share({ files: [file], title: string(output.name) || 'JUICE Music' });
    } catch (error) {
      if (error.name !== 'AbortError') errorNode.textContent = error.message || 'Sharing was not available. Use the download link instead.';
    } finally { button.disabled = false; }
  }

  function makeCard(id) {
    const card = element('article', 'take-card');
    card.dataset.id = id;
    const header = element('div', 'take-header');
    const heading = element('div', 'take-heading');
    const title = element('h2');
    const meta = element('p', 'take-meta');
    heading.append(title, meta);
    const badge = element('span', 'take-status');
    header.append(heading, badge);
    const prompt = element('p', 'take-prompt');
    const message = element('p', 'take-message');
    const outputs = element('div', 'take-outputs');
    const actions = element('div', 'take-actions');
    const reuse = element('button', 'text-button', 'Use this idea ↗');
    reuse.type = 'button';
    reuse.addEventListener('click', () => {
      const job = state.jobs.find((x) => x.id === id);
      if (!job) return;
      state.draft = { ...DEFAULT_DRAFT, title: string(job.title), task: job.task === 'cover' ? 'cover' : 'create', style: string(job.style), lyrics: string(job.lyrics), duration: job.duration || 60, composition: job.composition || 'full', source_id: job.task === 'cover' ? string(job.source_id) : '', source_name: job.task === 'cover' ? string(job.source_name) : '', seed: '' };
      applyDraft(); saveDraft(); setTab('create'); notify('Idea loaded. The next take gets a fresh seed.');
    });
    const cancel = element('button', 'text-button muted-button', 'Cancel queued take');
    cancel.type = 'button';
    cancel.addEventListener('click', async () => {
      cancel.disabled = true; error.textContent = '';
      try { await api(`/api/music/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST', json: {} }); await refreshJobs(); }
      catch (exc) { error.textContent = exc.message; }
      finally { cancel.disabled = false; }
    });
    const keep = element('button', 'text-button keep-button', '☆ Keep');
    keep.type = 'button';
    keep.addEventListener('click', async () => {
      const job = state.jobs.find((x) => x.id === id);
      if (!job) return;
      keep.disabled = true; error.textContent = '';
      try {
        const result = await api(`/api/music/jobs/${encodeURIComponent(id)}/keep`, { method: 'POST', json: { kept: !job.kept } });
        if (result.job) replaceJob(result.job); else await refreshJobs();
      } catch (exc) { error.textContent = exc.message; }
      finally { keep.disabled = false; }
    });
    const recover = element('button', 'text-button', 'Check original result');
    recover.type = 'button';
    recover.addEventListener('click', async () => {
      recover.disabled = true; error.textContent = '';
      try {
        const result = await api(`/api/music/jobs/${encodeURIComponent(id)}/recover`, { method: 'POST', json: {} });
        if (result.job) replaceJob(result.job); else await refreshJobs();
        notify('Checking the original engine job. No new take was generated.');
      } catch (exc) { error.textContent = exc.message; }
      finally { recover.disabled = false; }
    });
    actions.append(reuse, cancel, recover, keep);
    const details = element('details', 'take-details');
    details.append(element('summary', '', 'Take details'));
    const artifacts = element('div', 'artifact-links');
    details.append(artifacts);
    const error = element('p', 'take-error');
    error.setAttribute('role', 'alert');
    card.append(header, prompt, message, outputs, actions, details, error);
    const entry = { card, title, meta, badge, prompt, message, outputs, cancel, recover, keep, details, artifacts, error, outputKey: '', artifactKey: '' };
    state.cards.set(id, entry);
    return entry;
  }
  function updateCard(job) {
    const entry = state.cards.get(job.id) || makeCard(job.id);
    const { title, meta, badge, prompt, message, outputs, cancel, recover, keep, details, artifacts, error } = entry;
    title.textContent = string(job.title) || 'Untitled take';
    const detail = [job.task === 'cover' ? 'Audio rework' : 'New song', dateLabel(job.created_at), Number.isFinite(job.seed) ? `Seed ${job.seed}` : ''].filter(Boolean);
    meta.textContent = detail.join(' · ');
    badge.textContent = STATUS_NAMES[job.status] || 'Unknown status';
    badge.className = `take-status ${Object.hasOwn(STATUS_NAMES, job.status) ? job.status : ''}`;
    prompt.textContent = string(job.style);
    prompt.title = string(job.style);
    const failed = ['failed', 'interrupted', 'needs_attention'].includes(job.status);
    message.classList.toggle('error', failed);
    message.textContent = string(job.message) || (job.status === 'running' ? 'The engine is working. You can leave this screen and return later.' : '');
    message.hidden = !message.textContent;
    cancel.hidden = job.status !== 'queued';
    recover.hidden = job.recoverable !== true;
    keep.hidden = job.status !== 'succeeded';
    keep.textContent = job.kept ? '★ Kept' : '☆ Keep';
    keep.classList.toggle('kept', Boolean(job.kept));
    keep.setAttribute('aria-pressed', String(Boolean(job.kept)));
    keep.setAttribute('aria-label', `${job.kept ? 'Unkeep' : 'Keep'} ${string(job.title) || 'this take'}`);
    const items = Array.isArray(job.outputs) ? job.outputs : [];
    const outputKey = JSON.stringify(items);
    if (entry.outputKey !== outputKey) {
      entry.outputKey = outputKey;
      outputs.replaceChildren();
      for (const output of items) {
        const audioUrl = safeLocalUrl(output.url);
        const downloadUrl = safeLocalUrl(output.download_url || output.url);
        if (!audioUrl || !downloadUrl) continue;
        const wrap = element('div', 'take-audio');
        const label = element('p', 'audio-label', string(output.name) || 'Recording');
        const audio = document.createElement('audio');
        audio.controls = true; audio.preload = 'metadata'; audio.setAttribute('playsinline', ''); audio.src = audioUrl;
        audio.setAttribute('aria-label', `Listen to ${string(job.title) || 'your take'}`);
        audio.addEventListener('play', () => document.querySelectorAll('audio').forEach((other) => { if (other !== audio) other.pause(); }));
        audio.addEventListener('error', () => { error.textContent = 'Playback is unavailable here. Try Download, or check the JC connection.'; });
        const audioActions = element('div', 'audio-actions');
        const download = element('a', '', 'Download ↓');
        download.href = downloadUrl; download.download = string(output.name) || 'juice-take.flac';
        audioActions.append(download);
        if (typeof navigator.share === 'function' && typeof navigator.canShare === 'function') {
          const share = element('button', 'text-button', 'Share ↗'); share.type = 'button';
          share.addEventListener('click', () => shareOutput(output, share, error));
          audioActions.append(share);
        }
        wrap.append(label, audio, audioActions); outputs.append(wrap);
      }
    }
    const artifactItems = [['receipt_url', 'Generation receipt', 'receipt.json'], ['workflow_url', 'ComfyUI workflow', 'workflow.json'], ['score_url', 'Composition score', 'score.abc']];
    const artifactKey = JSON.stringify(artifactItems.map(([key]) => job[key]));
    if (entry.artifactKey !== artifactKey) {
      entry.artifactKey = artifactKey;
      artifacts.replaceChildren();
      for (const [key, label, filename] of artifactItems) {
        const href = safeLocalUrl(job[key]);
        if (!href) continue;
        const link = element('a', '', `${label} ↓`); link.href = href; link.download = filename; artifacts.append(link);
      }
      details.hidden = !artifacts.childElementCount;
    }
    return entry.card;
  }
  function replaceJob(job) {
    if (!job || typeof job.id !== 'string') return;
    const index = state.jobs.findIndex((x) => x.id === job.id);
    if (index < 0) state.jobs.unshift(job); else state.jobs[index] = job;
    renderJobs(); schedulePoll();
  }
  function renderJobs() {
    const validJobs = state.jobs.filter((job) => job && typeof job.id === 'string');
    const shown = validJobs.filter((job) => state.filter !== 'kept' || job.kept);
    const ids = new Set(validJobs.map((job) => job.id));
    for (const [id, entry] of state.cards) if (!ids.has(id)) { entry.card.remove(); state.cards.delete(id); }
    for (const job of validJobs) {
      const card = updateCard(job);
      card.hidden = state.filter === 'kept' && !job.kept;
      if (card.hidden) card.querySelectorAll('audio').forEach((audio) => audio.pause());
      if (!card.isConnected) $('takes-list').append(card);
    }
    // Preserve existing audio elements during status polling and Keep updates.
    // New takes insert before older ones without rebuilding the list.
    let previous = null;
    for (const job of validJobs) {
      const card = state.cards.get(job.id).card;
      const expected = previous ? previous.nextElementSibling : $('takes-list').firstElementChild;
      if (expected !== card) $('takes-list').insertBefore(card, expected);
      previous = card;
    }
    $('take-total').textContent = String(validJobs.length);
    $('kept-total').textContent = String(validJobs.filter((job) => job.kept).length);
    const active = validJobs.filter((job) => ACTIVE.has(job.status)).length;
    $('active-count').textContent = String(active);
    $('active-count').hidden = active === 0;
    $('takes-empty').hidden = shown.length > 0;
    const emptyTitle = $('takes-empty').querySelector('h2');
    const emptyText = $('takes-empty').querySelector('p');
    if (PREVIEW) {
      emptyTitle.textContent = 'Your takes will live in JC.';
      emptyText.textContent = 'This preview contains no recordings. Your connected Music Door will show the real queue and finished takes.';
    } else if (state.takesError && !state.takesLoaded) {
      emptyTitle.textContent = 'Your takes live in JC.';
      emptyText.textContent = 'Reconnect to your studio to see the shared queue and recordings.';
    } else if (state.filter === 'kept') {
      emptyTitle.textContent = 'Keep the good ones.';
      emptyText.textContent = 'Tap Keep on a finished take and it will appear here.';
    } else {
      emptyTitle.textContent = 'No takes yet.';
      emptyText.textContent = 'Your next favourite thing starts with an idea. Finished recordings will appear here.';
    }
  }
  function refreshJobs() {
    if (PREVIEW) {
      state.jobs = []; state.takesError = ''; state.takesLoaded = true;
      showError('takes-error', ''); renderJobs();
      return Promise.resolve();
    }
    if (state.jobsRequest) return state.jobsRequest;
    $('refresh-takes').disabled = true;
    state.jobsRequest = (async () => {
      try {
        const data = await api('/api/music/jobs');
        if (!Array.isArray(data.jobs)) throw new Error('JC returned an unexpected queue. Refresh the Music Door.');
        state.jobs = data.jobs;
        if (state.status) { state.connected = true; updateConnection(); }
        state.takesLoaded = true;
        state.takesError = '';
      } catch (error) { state.takesError = error.message; if (!error.status) { state.connected = false; updateConnection(); } }
      finally {
        state.jobsRequest = null;
        $('refresh-takes').disabled = false;
        showError('takes-error', state.takesError);
        renderJobs(); schedulePoll();
      }
    })();
    return state.jobsRequest;
  }
  function schedulePoll() {
    clearTimeout(state.pollTimer);
    if (PREVIEW) return;
    if (!document.hidden && state.jobs.some((job) => ACTIVE.has(job.status))) {
      state.pollTimer = setTimeout(() => { refreshJobs(); }, 3000);
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (state.busy || state.uploading || $('generate-button').disabled) return;
    if (!$('create-form').reportValidity()) return;
    captureDraft(false);
    if (!state.draft.style.trim()) { showError('form-error', 'Describe the sound before making a take.'); $('style').focus(); return; }
    state.busy = true; updateForm(); showError('form-error', '');
    if (!state.draft.request_id) state.draft.request_id = uuid();
    saveDraft();
    const payload = { title: state.draft.title.trim(), task: state.draft.task, style: state.draft.style.trim(), lyrics: state.draft.lyrics.trim(), duration: state.draft.duration, composition: state.draft.task === 'cover' ? 'melody' : state.draft.composition, request_id: state.draft.request_id };
    if (state.draft.seed !== '') payload.seed = Number(state.draft.seed);
    if (state.draft.task === 'cover') payload.source_id = state.draft.source_id;
    try {
      const data = await api('/api/music/jobs', { method: 'POST', json: payload });
      if (!data.job?.id) throw new Error('JC did not confirm the new take. Refresh Takes before trying again.');
      setFilter('all');
      replaceJob(data.job);
      state.draft.request_id = ''; saveDraft();
      setTab('takes'); notify('Your take is in the JC queue.');
    } catch (error) {
      showError('form-error', error.message);
      if (error.status === 403) await refreshStatus();
      else if (error.status === 503) await refreshStatus();
    } finally { state.busy = false; updateForm(); }
  }

  async function uploadReference(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size === 0 || file.size > 100 * 1024 * 1024) { $('source-status').textContent = 'Choose a non-empty audio file under 100 MB.'; event.target.value = ''; return; }
    if (!/\.(wav|mp3|flac|m4a|ogg|aiff?|aac|opus)$/i.test(file.name)) { $('source-status').textContent = 'Choose WAV, MP3, FLAC, M4A, OGG or AIFF audio.'; event.target.value = ''; return; }
    state.uploading = true; updateForm(); $('source-status').textContent = `Uploading ${file.name} to JC…`;
    try {
      const data = await api(`/api/music/sources?filename=${encodeURIComponent(file.name)}`, { method: 'POST', body: file, headers: { 'Content-Type': 'application/octet-stream' }, timeout: 120000 });
      if (!data.source?.id) throw new Error('JC did not confirm the audio upload. Try again after checking the connection.');
      state.draft.source_id = data.source.id;
      state.draft.source_name = data.source.name || file.name;
      state.draft.request_id = ''; saveDraft();
      $('source-status').textContent = 'Reference saved in JC. Ready for a new interpretation.';
    } catch (error) { $('source-status').textContent = error.message; }
    finally { state.uploading = false; event.target.value = ''; updateForm(); }
  }
  function exportDraft() {
    captureDraft(false);
    const { request_id, ...draft } = state.draft;
    const blob = new Blob([JSON.stringify({ format: 'juice-music-idea-v1', exported_at: new Date().toISOString(), ...draft }, null, 2)], { type: 'application/json' });
    const href = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = href; a.download = 'JUICE_Music_Idea.json'; a.hidden = true;
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 30000);
    notify('Idea exported. Audio and shared takes stay in JC.');
  }

  $('create-form').addEventListener('submit', submit);
  $('create-form').addEventListener('input', (event) => { if (event.target.id !== 'reference-file') captureDraft(); });
  $('create-form').addEventListener('change', (event) => { if (event.target.id !== 'reference-file') captureDraft(); });
  $('reference-file').addEventListener('change', uploadReference);
  $('remove-source').addEventListener('click', () => { state.draft.source_id = ''; state.draft.source_name = ''; state.draft.request_id = ''; $('source-status').textContent = ''; saveDraft(); updateForm(); });
  $('export-draft').addEventListener('click', exportDraft);
  $('clear-draft').addEventListener('click', () => {
    if (state.busy || state.uploading) return;
    const oldDraft = { ...state.draft };
    state.draft = { ...DEFAULT_DRAFT }; applyDraft(); saveDraft(); showError('form-error', ''); $('source-status').textContent = '';
    notify('Draft cleared.');
    // Allow native undo through an explicit, short-lived button instead of an approval dialog.
    const undo = element('button', 'text-button', 'Undo'); undo.type = 'button'; undo.style.color = 'inherit'; undo.style.marginLeft = '15px';
    undo.addEventListener('click', () => { state.draft = oldDraft; applyDraft(); saveDraft(); notify('Draft restored.'); });
    $('toast').append(undo);
  });
  document.querySelectorAll('[data-preset]').forEach((button) => button.addEventListener('click', () => {
    $('style').value = PRESETS[button.dataset.preset]; captureDraft(); $('style').focus();
  }));
  document.querySelectorAll('[data-tab]').forEach((button) => {
    button.addEventListener('click', () => setTab(button.dataset.tab));
    button.addEventListener('keydown', (event) => {
      const tabs = ['create', 'takes', 'setup'];
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); const direction = event.key === 'ArrowRight' ? 1 : -1; setTab(tabs[(tabs.indexOf(state.tab) + direction + 3) % 3], true); }
      else if (event.key === 'Home') { event.preventDefault(); setTab('create', true); }
      else if (event.key === 'End') { event.preventDefault(); setTab('setup', true); }
    });
  });
  document.querySelectorAll('[data-open-setup]').forEach((button) => button.addEventListener('click', () => setTab('setup')));
  document.querySelectorAll('[data-open-create]').forEach((button) => button.addEventListener('click', () => setTab('create')));
  $('connection-button').addEventListener('click', () => setTab('setup'));
  $('refresh-engine').addEventListener('click', async () => { await refreshStatus(true); notify(state.status?.ready ? 'YuE2 is ready.' : 'Connection checked. See engine details.'); });
  $('refresh-takes').addEventListener('click', refreshJobs);
  function setFilter(filter) {
    state.filter = filter;
    for (const name of ['all', 'kept']) { $(`filter-${name}`).classList.toggle('active', name === filter); $(`filter-${name}`).setAttribute('aria-pressed', String(name === filter)); }
    renderJobs();
  }
  for (const filter of ['all', 'kept']) $(`filter-${filter}`).addEventListener('click', () => setFilter(filter));
  window.addEventListener('online', () => { refreshStatus(); refreshJobs(); });
  window.addEventListener('offline', () => { state.connected = false; updateConnection(); });
  window.addEventListener('hashchange', () => setTab(location.hash.slice(1)));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) clearTimeout(state.pollTimer);
    else { refreshStatus(); refreshJobs(); }
  });
  readDraft(); applyDraft();
  const initialTab = location.hash.slice(1);
  if (['create', 'takes', 'setup'].includes(initialTab)) setTab(initialTab);
  refreshStatus(); refreshJobs();
  if (!PREVIEW && 'serviceWorker' in navigator && (location.protocol === 'https:' || ['localhost', '127.0.0.1'].includes(location.hostname))) {
    navigator.serviceWorker.register('/music/sw.js', { scope: '/music/' }).catch(() => { /* Online use still works without an installed shell. */ });
  }
})();
