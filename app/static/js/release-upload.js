/* Resumable uploads: only one 8 MiB Blob is in flight; no whole-file ArrayBuffer. */
(() => {
  'use strict';
  const box = document.querySelector('[data-installer-upload]');
  if (!box) return;
  const form = box.closest('form');
  const picker = box.querySelector('input[type=file]');
  const token = form.querySelector('[name=csrf_token]').value;
  const uploadId = box.querySelector('[data-upload-id]');
  const start = box.querySelector('[data-upload-start]');
  const cancel = box.querySelector('[data-upload-cancel]');
  const progress = box.querySelector('progress');
  const status = box.querySelector('[data-upload-status]');
  const summary = box.querySelector('[data-file-summary]');
  const save = form.querySelector('[data-release-save]');
  const endpoint = '/api/v1/admin/release-uploads';
  let file, transfer, active = false, currentId = uploadId.value, cacheKey;
  const cached = (value) => { try { if (value) sessionStorage.setItem(cacheKey,value); else sessionStorage.removeItem(cacheKey); } catch (_) {} };
  async function api(path, method='GET', body) {
    const response = await fetch(endpoint + path, {method, credentials:'same-origin',
      headers:{'X-CSRF-Token':token,'Content-Type':'application/json'}, body:body ? JSON.stringify(body) : undefined});
    const data = response.status === 204 ? {} : await response.json();
    if (!response.ok) throw new Error(data.error?.message || 'Upload request failed. Retry after checking your connection.');
    return data;
  }
  function chunk(id, offset, blob) {
    return new Promise((resolve,reject) => {
      transfer = new XMLHttpRequest();
      transfer.open('PUT', endpoint + '/' + id);
      transfer.timeout = 180000;
      transfer.setRequestHeader('X-CSRF-Token',token);
      transfer.setRequestHeader('Content-Type','application/octet-stream');
      transfer.setRequestHeader('Upload-Offset',String(offset));
      transfer.upload.onprogress = e => { if (e.lengthComputable) {
        progress.value = (offset + e.loaded) / file.size * 100;
        status.textContent = `Uploading ${Math.floor(progress.value)}% — saving this chunk…`;
      }};
      transfer.onload = () => {
        let data; try { data = JSON.parse(transfer.responseText); } catch (_) {}
        if (transfer.status >= 200 && transfer.status < 300) resolve(data);
        else reject(new Error(data?.error?.message || 'Chunk failed. Retry to resume from the saved offset.'));
      };
      transfer.onerror = transfer.ontimeout = () => reject(new Error('Connection interrupted. Retry to resume from the saved offset.'));
      transfer.onabort = () => reject(new Error('Upload stopped. You can retry to resume.'));
      transfer.send(blob);
    });
  }
  picker.addEventListener('change', () => {
    file = picker.files[0];
    uploadId.value = ''; currentId = ''; progress.value = 0;
    save.disabled = !!file || box.dataset.existing !== '1';
    start.disabled = !file; cancel.hidden = true;
    if (!file) return;
    summary.textContent = `${file.name} · ${file.size.toLocaleString()} bytes`;
    if (!/\.exe$/i.test(file.name) || file.size > Number(box.dataset.maxBytes) || file.size < 128) {
      status.textContent = 'Select an .exe installer within the displayed size limit.'; start.disabled = true; return;
    }
    cacheKey = 'vr-upload:' + location.pathname + ':' + file.name + ':' + file.size + ':' + file.lastModified;
    try { currentId = sessionStorage.getItem(cacheKey) || ''; } catch (_) {}
    status.textContent = currentId ? 'A previous transfer is available. Click Resume upload.' : 'Ready to upload.';
    start.textContent = currentId ? 'Resume upload' : 'Upload installer';
  });
  start.addEventListener('click', async () => {
    if (!file || active) return;
    active = true; start.disabled = true; picker.disabled = true; save.disabled = true; cancel.hidden = false;
    status.textContent = 'Checking saved upload…';
    try {
      let upload = currentId ? await api('/'+currentId) : await api('','POST',{filename:file.name,size:file.size});
      currentId = upload.id; cached(currentId);
      if (upload.original_filename !== file.name || upload.expected_bytes !== file.size) throw new Error('The selected file does not match this upload. Cancel it and start again.');
      while (upload.state === 'uploading' && upload.received_bytes < file.size) {
        const offset = upload.received_bytes;
        upload = await chunk(currentId,offset,file.slice(offset,Math.min(offset+upload.chunk_bytes,file.size)));
        progress.value = upload.received_bytes / file.size * 100;
      }
      status.textContent = 'All bytes saved. Verifying the Windows header, size and file integrity…';
      upload = await api('/'+currentId+'/complete','POST');
      if (upload.state !== 'verified') throw new Error('This installer already belongs to a release. Open that release to edit it.');
      uploadId.value = currentId; progress.value = 100;
      status.textContent = 'Installer saved and verified. Save the draft, then review and publish it.';
      const published = form.querySelector('[name=is_published]');
      if (published) published.checked = false;
      save.disabled = false; cancel.hidden = false; cancel.textContent = 'Discard verified upload';
    } catch (error) {
      status.textContent = error.message; start.disabled = false; start.textContent = 'Retry / resume upload';
    } finally { active = false; picker.disabled = false; transfer = null; }
  });
  cancel.addEventListener('click', async () => {
    cancel.disabled = true; transfer?.abort();
    try {
      if (currentId) await api('/'+currentId,'DELETE');
      cached(null); currentId = ''; uploadId.value = ''; progress.value = 0;
      save.disabled = true;
      status.textContent = 'Upload cancelled. Temporary installer bytes removed.';
      start.disabled = !file; start.textContent = 'Upload installer'; cancel.hidden = true; cancel.textContent = 'Cancel upload';
    } catch (error) { status.textContent = error.message + ' Retry cancellation after the current request stops.'; }
    finally { cancel.disabled = false; }
  });
  form.addEventListener('submit', e => {
    if (active || (file && !uploadId.value) || (box.dataset.existing !== '1' && !uploadId.value)) {
      e.preventDefault(); status.textContent = 'Finish and verify the installer upload first.'; return;
    }
    cached(null); save.disabled = true; save.textContent = 'Saving…';
  });
  window.addEventListener('beforeunload', e => { if (active) { e.preventDefault(); e.returnValue=''; } });
})();
