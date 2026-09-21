(function () {
  'use strict';

  const root = document.getElementById('litho-configurator');
  if (!root || typeof LithoConfig === 'undefined') return;

  const canvas = root.querySelector('#litho-preview');
  const ctx = canvas.getContext('2d');
  const fileInput = root.querySelector('input[type="file"]');
  const sizeInput = root.querySelector('#litho-size');
  const housingInput = root.querySelector('#litho-housing-color');
  const ledInput = root.querySelector('#litho-led-color');
  const zoomInput = root.querySelector('#litho-zoom');
  const approve = root.querySelector('#litho-approve');
  const status = root.querySelector('#litho-status');
  const projectIdInput = root.querySelector('#litho-project-id');
  const signatureInput = root.querySelector('#litho-project-signature');
  const cartButton = document.querySelector('form.cart button.single_add_to_cart_button');

  const state = {image: null, file: null, orientation: 'landscape', rotation: 0, zoom: 1, panX: 0, panY: 0, dragging: false, lastX: 0, lastY: 0, busy: false};
  const apiRoot = String(LithoConfig.restUrl).replace(/\/$/, '');

  function fillSelect(select, choices) {
    Object.entries(choices || {}).forEach(([value, label]) => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    });
  }
  fillSelect(housingInput, LithoConfig.housingColors);
  fillSelect(ledInput, LithoConfig.ledColors);

  function setStatus(message, type) {
    status.textContent = message || '';
    status.className = 'litho-status' + (type ? ' ' + type : '');
  }

  function lockCart(locked) {
    if (cartButton) cartButton.disabled = locked;
  }

  function setBusy(busy) {
    state.busy = busy;
    root.classList.toggle('is-busy', busy);
    root.setAttribute('aria-busy', busy ? 'true' : 'false');
    root.querySelectorAll('input:not([type="hidden"]), select, button').forEach(control => {
      control.disabled = busy;
    });
  }
  lockCart(true);

  function invalidate() {
    if (state.busy) return;
    projectIdInput.value = '';
    signatureInput.value = '';
    lockCart(true);
    setStatus('');
  }

  function rotatedDimensions() {
    if (!state.image) return {width: 1, height: 1};
    const quarter = Math.abs(Math.round(state.rotation / 90)) % 2;
    return quarter ? {width: state.image.height, height: state.image.width} : {width: state.image.width, height: state.image.height};
  }

  function setCanvasAspect() {
    const parts = sizeInput.value.split('x').map(Number);
    const shortSide = parts[0];
    const longSide = parts[1];
    const ratio = state.orientation === 'landscape' ? longSide / shortSide : shortSide / longSide;
    canvas.width = state.orientation === 'landscape' ? 900 : Math.round(900 * ratio);
    canvas.height = state.orientation === 'landscape' ? Math.round(900 / ratio) : 900;
    clampPan();
    draw();
  }

  function geometry() {
    const dims = rotatedDimensions();
    const baseScale = Math.max(canvas.width / dims.width, canvas.height / dims.height);
    return {width: dims.width, height: dims.height, scale: baseScale * state.zoom};
  }

  function clampPan() {
    if (!state.image) return;
    const g = geometry();
    const maxX = Math.max(0, (g.width * g.scale - canvas.width) / 2);
    const maxY = Math.max(0, (g.height * g.scale - canvas.height) / 2);
    state.panX = Math.max(-maxX, Math.min(maxX, state.panX));
    state.panY = Math.max(-maxY, Math.min(maxY, state.panY));
  }

  function draw() {
    ctx.fillStyle = '#161c26';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!state.image) {
      ctx.fillStyle = '#b9c1ce';
      ctx.font = '600 24px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Wybierz zdjęcie', canvas.width / 2, canvas.height / 2);
      return;
    }
    const g = geometry();
    ctx.save();
    ctx.translate(canvas.width / 2 + state.panX, canvas.height / 2 + state.panY);
    ctx.rotate(state.rotation * Math.PI / 180);
    ctx.scale(g.scale, g.scale);
    ctx.drawImage(state.image, -state.image.width / 2, -state.image.height / 2);
    ctx.restore();
  }

  function crop() {
    const g = geometry();
    const width = Math.min(1, canvas.width / (g.scale * g.width));
    const height = Math.min(1, canvas.height / (g.scale * g.height));
    const x = Number(Math.max(0, Math.min(1 - width, 0.5 - (canvas.width / 2 + state.panX) / (g.scale * g.width))).toFixed(6));
    const y = Number(Math.max(0, Math.min(1 - height, 0.5 - (canvas.height / 2 + state.panY) / (g.scale * g.height))).toFixed(6));
    const safeWidth = Number(Math.min(width, 1 - x).toFixed(6));
    const safeHeight = Number(Math.min(height, 1 - y).toFixed(6));
    return {x, y, width: safeWidth, height: safeHeight};
  }

  function resetView() {
    state.zoom = 1;
    state.panX = 0;
    state.panY = 0;
    zoomInput.value = '1';
    setCanvasAspect();
    invalidate();
  }

  fileInput.addEventListener('change', () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 20 * 1024 * 1024) {
      setStatus('Wybierz plik JPG lub PNG o rozmiarze do 20 MB.', 'error');
      fileInput.value = '';
      return;
    }
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      state.image = image;
      state.file = file;
      state.rotation = 0;
      resetView();
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      setStatus('Nie można odczytać zdjęcia.', 'error');
    };
    image.src = url;
  });

  sizeInput.addEventListener('change', () => { setCanvasAspect(); invalidate(); });
  housingInput.addEventListener('change', invalidate);
  ledInput.addEventListener('change', invalidate);
  zoomInput.addEventListener('input', () => { state.zoom = Number(zoomInput.value); clampPan(); draw(); invalidate(); });

  root.querySelectorAll('[data-orientation]').forEach(button => button.addEventListener('click', () => {
    state.orientation = button.dataset.orientation;
    root.querySelectorAll('[data-orientation]').forEach(item => item.classList.toggle('active', item === button));
    resetView();
  }));
  root.querySelectorAll('[data-rotate]').forEach(button => button.addEventListener('click', () => {
    state.rotation = ((state.rotation + Number(button.dataset.rotate) + 540) % 360) - 180;
    resetView();
  }));

  canvas.addEventListener('pointerdown', event => {
    if (!state.image || state.busy) return;
    state.dragging = true; state.lastX = event.clientX; state.lastY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', event => {
    if (!state.dragging) return;
    const rect = canvas.getBoundingClientRect();
    state.panX += (event.clientX - state.lastX) * canvas.width / rect.width;
    state.panY += (event.clientY - state.lastY) * canvas.height / rect.height;
    state.lastX = event.clientX; state.lastY = event.clientY;
    clampPan(); draw(); invalidate();
  });
  canvas.addEventListener('pointerup', () => { state.dragging = false; });
  canvas.addEventListener('pointercancel', () => { state.dragging = false; });
  canvas.addEventListener('wheel', event => {
    if (!state.image || state.busy) return;
    event.preventDefault();
    state.zoom = Math.max(1, Math.min(3, state.zoom * (event.deltaY < 0 ? 1.08 : 0.92)));
    zoomInput.value = String(state.zoom);
    clampPan(); draw(); invalidate();
  }, {passive: false});

  async function request(path, options, browserToken) {
    const headers = Object.assign({'X-Litho-Nonce': LithoConfig.nonce, 'X-Litho-CSRF-Token': LithoConfig.csrf}, options.headers || {});
    if (browserToken) headers['X-Litho-Project-Key'] = browserToken;
    const response = await fetch(apiRoot + path, Object.assign({}, options, {headers}));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || LithoConfig.messages.failed);
    return data;
  }

  async function waitForProject(projectId, browserToken) {
    for (let attempt = 0; attempt < 150; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      const result = await request('/projects/' + encodeURIComponent(projectId), {method: 'GET'}, browserToken);
      if (result.status === 'completed') return result;
      if (result.status === 'failed') throw new Error(result.generation_error || LithoConfig.messages.failed);
    }
    throw new Error('Generowanie trwa zbyt długo. Spróbuj ponownie później.');
  }

  approve.addEventListener('click', async () => {
    if (!state.file || !state.image) { setStatus(LithoConfig.messages.chooseImage, 'error'); return; }
    if (state.busy) return;
    setBusy(true); lockCart(true);
    setStatus(LithoConfig.messages.working, 'working');
    try {
      const created = await request('/projects', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          product_id: LithoConfig.productId,
          size: sizeInput.value,
          orientation: state.orientation,
          housing_color: housingInput.value,
          light_temperature: ledInput.value,
          rotation_degrees: state.rotation,
          crop: crop(),
        }),
      });
      const form = new FormData(); form.append('image', state.file, state.file.name);
      await request('/projects/' + encodeURIComponent(created.project_id) + '/image', {method: 'POST', body: form}, created.browser_token);
      await request('/projects/' + encodeURIComponent(created.project_id) + '/generate', {method: 'POST'}, created.browser_token);
      await waitForProject(created.project_id, created.browser_token);
      projectIdInput.value = created.project_id;
      signatureInput.value = created.cart_signature;
      setStatus(LithoConfig.messages.ready, 'success');
      lockCart(false);
    } catch (error) {
      setStatus(error.message || LithoConfig.messages.failed, 'error');
      projectIdInput.value = ''; signatureInput.value = '';
    } finally {
      setBusy(false);
    }
  });

  setCanvasAspect();
}());
