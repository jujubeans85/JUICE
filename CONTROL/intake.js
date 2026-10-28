/* Same-origin adapter: accepts File objects directly, never stores audio in browser storage. */
(() => {
  'use strict';
  function attach(root) {
    const drop = root.querySelector('[data-drop]');
    const picker = root.querySelector('[data-files]');
    const status = root.querySelector('[data-status]');
    const results = root.querySelector('[data-results]');
    const cancel = root.querySelector('[data-cancel]');
    const token = document.querySelector('meta[name="juice-csrf"]').content;
    let busy = false, stopped = false, active = null, limits = null;
    async function api(path, body) {
      const response = await fetch(path, {method: body ? 'POST' : 'GET', cache: 'no-store',
        headers: body ? {'Content-Type': 'application/json', 'X-Juice-Token': token} : {},
        body: body ? JSON.stringify(body) : undefined});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      return data;
    }
    function show(batch) {
      results.replaceChildren();
      for (const file of batch.files) {
        const row = document.createElement('li');
        row.textContent = `${file.name}: ${file.status}${file.reason ? ' — ' + file.reason : ''}`;
        if (file.entries.length) {
          const entries = document.createElement('ul');
          for (const entry of file.entries) {
            const child = document.createElement('li');
            child.textContent = `${entry.name}: ${entry.status}${entry.reason ? ' — ' + entry.reason : ''}${entry.path ? ' → ' + entry.path : ''}`;
            entries.append(child);
          }
          row.append(entries);
        }
        results.append(row);
      }
      const receipt = document.createElement('li');
      const link = document.createElement('a');
      link.href = `/api/intake/batches/${batch.id}`;
      link.textContent = 'Open saved receipt';
      link.target = '_blank'; link.rel = 'noopener';
      receipt.append(link, document.createTextNode(` · Staging: ${batch.staging_path}`));
      results.append(receipt);
    }
    function upload(batchId, index, file) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        active = xhr;
        xhr.open('POST', `/api/intake/batches/${batchId}/files/${index}`);
        xhr.setRequestHeader('Content-Type', 'application/octet-stream');
        xhr.setRequestHeader('X-Juice-Token', token);
        xhr.upload.onprogress = event => {
          status.textContent = `Uploading ${file.name}: ${Math.floor(event.loaded / Math.max(1, file.size) * 100)}% (server validation follows)`;
        };
        xhr.onload = () => {
          try {
            const data = JSON.parse(xhr.responseText);
            if (xhr.status < 200 || xhr.status >= 300) throw new Error(data.error || `HTTP ${xhr.status}`);
            resolve(data);
          } catch (error) { reject(error); }
        };
        xhr.onerror = () => reject(new Error('Connection lost. Check the saved receipt; retry interrupted files in a new drop.'));
        xhr.onabort = () => reject(new Error('Cancelled. Earlier imports remain saved; check the receipt.'));
        // Sending the File streams it from disk; no arrayBuffer, Base64, IndexedDB or offline queue.
        xhr.send(file);
      });
    }
    async function importFiles(files) {
      if (busy || !files.length) return;
      busy = true; stopped = false; cancel.disabled = false; picker.disabled = true;
      let batch;
      try {
        if (!limits) limits = await api('/api/intake');
        batch = await api('/api/intake/batches', {files: files.map(file => ({name: file.name, size: file.size}))});
        try { localStorage.setItem('juice.lastAudioBatch', batch.id); } catch (_) { /* Storage is optional. */ }
        show(batch);
        for (const item of batch.files) {
          if (stopped) break;
          if (item.status !== 'pending') continue;
          status.textContent = `Uploading ${item.name}…`;
          try {
            batch = await upload(batch.id, item.index, files[item.index]);
            show(batch);
          } catch (error) {
            status.textContent = error.message;
            if (stopped) break;
            // Do not silently abandon the remaining stems after one failed request.
            const row = document.createElement('li'); row.textContent = `${item.name}: upload error — ${error.message}`; results.append(row);
          } finally { active = null; }
        }
        try { batch = await api(`/api/intake/batches/${batch.id}`); show(batch); } catch (_) { /* Existing receipt remains linked. */ }
        const counts = batch.files.reduce((out, file) => {out[file.status] = (out[file.status] || 0) + 1; return out;}, {});
        status.textContent = `${stopped ? 'Stopped' : 'Drop finished'}: ${counts.accepted || 0} accepted, ${counts.rejected || 0} rejected, ${(counts.pending || 0) + (counts.interrupted || 0) + (counts.receiving || 0)} unfinished. See every file below.`;
      } catch (error) { status.textContent = `Intake failed: ${error.message}`; }
      finally { busy = false; active = null; cancel.disabled = true; picker.disabled = false; picker.value = ''; }
    }
    drop.onclick = () => { if (!busy) picker.click(); };
    drop.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); drop.click(); } };
    picker.onchange = () => importFiles(Array.from(picker.files));
    for (const event of ['dragenter', 'dragover', 'dragleave', 'drop']) {
      drop.addEventListener(event, e => { e.preventDefault(); e.stopPropagation(); });
    }
    drop.addEventListener('drop', event => {
      const items = Array.from(event.dataTransfer.items || []);
      if (items.some(item => item.webkitGetAsEntry && item.webkitGetAsEntry()?.isDirectory)) {
        status.textContent = 'Folders are unsupported. ZIP the folder, or select its stems.'; return;
      }
      importFiles(Array.from(event.dataTransfer.files));
    });
    cancel.onclick = () => { stopped = true; if (active) active.abort(); };
    api('/api/intake').then(config => {
      limits = config;
      status.textContent = `Ready · max ${(config.max_file_bytes / 1024**3).toFixed(1)} GiB/file · ${(config.max_batch_bytes / 1024**3).toFixed(1)} GiB/drop`;
      try {
        const id = localStorage.getItem('juice.lastAudioBatch');
        if (/^[0-9a-f]{32}$/.test(id || '')) api(`/api/intake/batches/${id}`).then(batch => { if (!busy) show(batch); }).catch(() => {});
      } catch (_) { /* No dependency on browser storage. */ }
    }).catch(error => { status.textContent = `Intake unavailable: ${error.message}`; });
    return {importFiles};
  }
  window.JuiceAudioIntake = {attach};
  const root = document.getElementById('audio-intake');
  if (root) attach(root);
})();
