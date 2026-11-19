(function () {
  'use strict';

  const root = document.getElementById('litho-configurator');
  if (!root || typeof LithoConfig === 'undefined') return;

  const canvas = root.querySelector('#litho-preview');
  const previewStage = root.querySelector('.litho-preview-stage');
  const ctx = canvas.getContext('2d');
  const fileInput = root.querySelector('input[type="file"]');
  const FIXED_SIZE = '150x200';
  const housingInput = root.querySelector('#litho-housing-color');
  const ledInput = root.querySelector('#litho-led-color');
  const zoomInput = root.querySelector('#litho-zoom');
  const positionXInput = root.querySelector('#litho-position-x');
  const positionYInput = root.querySelector('#litho-position-y');
  const positionXValue = root.querySelector('#litho-position-x-value');
  const positionYValue = root.querySelector('#litho-position-y-value');
  const zoomValue = root.querySelector('#litho-zoom-value');
  const brightnessInput = root.querySelector('#litho-brightness');
  const contrastInput = root.querySelector('#litho-contrast');
  const gammaInput = root.querySelector('#litho-gamma');
  const fitModeInput = root.querySelector('#litho-fit-mode');
  const brightnessValue = root.querySelector('#litho-brightness-value');
  const contrastValue = root.querySelector('#litho-contrast-value');
  const gammaValue = root.querySelector('#litho-gamma-value');
  const approve = root.querySelector('#litho-approve');
  const status = root.querySelector('#litho-status');
  const projectIdInput = root.querySelector('#litho-project-id');
  const signatureInput = root.querySelector('#litho-project-signature');
  const cartButton = document.querySelector('form.cart button.single_add_to_cart_button');

  const state = {image: null, file: null, orientation: 'landscape', fitMode: 'cover', previewMode: 'photo', rotation: 0, crop: {x: 0, y: 0, width: 1, height: 1}, dragging: false, dragStart: null, busy: false};
  // Match the full Litho generator: pointer capture and coordinates belong
  // to the canvas itself, not to its layout wrapper.
  const dragSurface = canvas;
  // The customer preview shows only the visible image field. The hidden
  // mounting flange is part of the generated mesh, but must not change the
  // preview aspect ratio or create an apparent margin around the photograph.
  const PANEL = {width: 200, height: 150};
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

  function syncPositionControls() {
    if (!positionXInput || !positionYInput || !positionXValue || !positionYValue) return;
    const maxX = Math.max(0, 1 - state.crop.width);
    const maxY = Math.max(0, 1 - state.crop.height);
    positionXInput.max = String(maxX);
    positionYInput.max = String(maxY);
    positionXInput.value = String(Math.max(0, Math.min(maxX, state.crop.x)));
    positionYInput.value = String(Math.max(0, Math.min(maxY, state.crop.y)));
    positionXValue.textContent = Number(state.crop.x).toFixed(3);
    positionYValue.textContent = Number(state.crop.y).toFixed(3);
    if (zoomInput) {
      const zoom = currentZoom();
      zoomInput.value = zoom.toFixed(2);
      if (zoomValue) zoomValue.textContent = zoom.toFixed(2);
    }
  }

  // The full Litho generator derives the zoom from the crop viewport.  It
  // does not keep a second zoom state which could reset the crop while the
  // pointer is moving.
  function currentZoom() {
    const base = baseCrop();
    return Math.max(1, Math.min(5, base.width / Math.max(0.000001, state.crop.width)));
  }

  function rotatedDimensions() {
    if (!state.image) return {width: 1, height: 1};
    const quarter = Math.abs(Math.round(state.rotation / 90)) % 2;
    return quarter ? {width: state.image.height, height: state.image.width} : {width: state.image.width, height: state.image.height};
  }

  function modelDimensions() {
    const landscape = state.orientation === 'landscape';
    const width = PANEL.width;
    const height = PANEL.height;
    return landscape ? {width, height} : {width: height, height: width};
  }

  function imageAreaDimensions() {
    return state.orientation === 'landscape'
      ? {width: PANEL.width, height: PANEL.height}
      : {width: PANEL.height, height: PANEL.width};
  }

  function automaticCrop(width, height, targetWidth, targetHeight) {
    const sourceAspect = width / height;
    const targetAspect = targetWidth / targetHeight;
    if (sourceAspect > targetAspect) {
      const cropWidth = targetAspect / sourceAspect;
      return {x: (1 - cropWidth) / 2, y: 0, width: cropWidth, height: 1};
    }
    if (sourceAspect < targetAspect) {
      const cropHeight = sourceAspect / targetAspect;
      return {x: 0, y: (1 - cropHeight) / 2, width: 1, height: cropHeight};
    }
    return {x: 0, y: 0, width: 1, height: 1};
  }

  function zoomCrop(base, current, zoom) {
    zoom = Number.isFinite(zoom) ? Math.max(1, zoom) : 1;
    const width = base.width / zoom;
    const height = base.height / zoom;
    const centerX = current.x + current.width / 2;
    const centerY = current.y + current.height / 2;
    return {
      // Match the full Litho generator: the automatic crop defines the
      // initial viewport only. After zooming, the user may pan through the
      // complete source image instead of being pulled back to that crop.
      x: Math.max(0, Math.min(1 - width, centerX - width / 2)),
      y: Math.max(0, Math.min(1 - height, centerY - height / 2)),
      width,
      height,
    };
  }

  function zoomCropAt(base, current, zoom, focalX, focalY) {
    zoom = Number.isFinite(zoom) ? Math.max(1, zoom) : 1;
    const width = base.width / zoom;
    const height = base.height / zoom;
    const sourceX = current.x + current.width * focalX;
    const sourceY = current.y + current.height * focalY;
    return {
      x: Math.max(0, Math.min(1 - width, sourceX - width * focalX)),
      y: Math.max(0, Math.min(1 - height, sourceY - height * focalY)),
      width,
      height,
    };
  }

  // Keep this identical to the full Litho generator: panning changes only
  // the crop origin and never recalculates its width or height.
  function panCrop(crop, deltaX, deltaY) {
    return {
      ...crop,
      x: Math.max(0, Math.min(1 - crop.width, crop.x + deltaX)),
      y: Math.max(0, Math.min(1 - crop.height, crop.y + deltaY)),
    };
  }

  function baseCrop() {
    if (!state.image) return {x: 0, y: 0, width: 1, height: 1};
    if (state.fitMode === 'contain') return {x: 0, y: 0, width: 1, height: 1};
    const dims = rotatedDimensions();
    const area = imageAreaDimensions();
    return automaticCrop(dims.width, dims.height, area.width, area.height);
  }

  function setCanvasAspect() {
    const model = modelDimensions();
    const ratio = model.width / model.height;
    canvas.width = 1200;
    canvas.height = Math.max(320, Math.round(canvas.width / ratio));
    const portrait = state.orientation === 'portrait';
    root.classList.toggle('is-portrait', portrait);
    root.classList.toggle('is-fit-contain', state.fitMode === 'contain');
    previewStage.dataset.orientation = portrait ? 'portrait' : 'landscape';
    previewStage.style.setProperty('aspect-ratio', `${model.width} / ${model.height}`, 'important');
    previewStage.style.setProperty('width', `min(100%, ${Math.round(720 * ratio)}px)`, 'important');
    previewStage.style.setProperty('margin-inline', 'auto', 'important');
    canvas.style.setProperty('position', 'absolute', 'important');
    canvas.style.setProperty('inset', '0', 'important');
    canvas.style.setProperty('width', '100%', 'important');
    canvas.style.setProperty('height', '100%', 'important');
    canvas.style.setProperty('max-width', 'none', 'important');
    canvas.style.setProperty('max-height', 'none', 'important');
    syncPositionControls();
    draw();
  }

  function draw() {
    const model = modelDimensions();
    const area = imageAreaDimensions();
    const borderX = 0;
    const borderY = 0;
    const innerWidth = canvas.width;
    const innerHeight = canvas.height;
    ctx.fillStyle = state.fitMode === 'contain' ? '#dfe4eb' : '#302b27';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!state.image) {
      ctx.fillStyle = '#b9c1ce';
      ctx.font = '600 24px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Wybierz zdjęcie', canvas.width / 2, canvas.height / 2);
      return;
    }
    const quarter = ((Math.round(state.rotation / 90) % 4) + 4) % 4;
    const oriented = document.createElement('canvas');
    const swapped = quarter % 2 === 1;
    oriented.width = swapped ? state.image.height : state.image.width;
    oriented.height = swapped ? state.image.width : state.image.height;
    const orientedContext = oriented.getContext('2d');
    orientedContext.translate(oriented.width / 2, oriented.height / 2);
    orientedContext.rotate(quarter * Math.PI / 2);
    orientedContext.drawImage(state.image, -state.image.width / 2, -state.image.height / 2);

    const adjusted = makeAdjustedCanvas(oriented);
    if (state.fitMode === 'contain') {
      // Contain is rendered as a uniform scale/translation of the complete
      // image.  Never map an arbitrary source crop directly to the panel:
      // that is what caused portrait images to stretch after a small pan.
      const crop = state.crop;
      const zoom = 1 / Math.max(0.000001, crop.width);
      const scale = Math.min(innerWidth / adjusted.width, innerHeight / adjusted.height) * zoom;
      const width = adjusted.width * scale;
      const height = adjusted.height * scale;
      const centerX = crop.x + crop.width / 2;
      const centerY = crop.y + crop.height / 2;
      const x = borderX + innerWidth / 2 - centerX * width;
      const y = borderY + innerHeight / 2 - centerY * height;
      drawMarginHatch(x, y, width, height);
      ctx.save();
      ctx.beginPath();
      ctx.rect(borderX, borderY, innerWidth, innerHeight);
      ctx.clip();
      ctx.drawImage(adjusted, x, y, width, height);
      ctx.restore();
      if (zoom <= 1.001) {
        ctx.save();
        ctx.strokeStyle = '#8b98aa';
        ctx.lineWidth = Math.max(1, canvas.width / 900);
        ctx.setLineDash([8, 6]);
        ctx.strokeRect(x, y, width, height);
        ctx.restore();
      }
    } else {
      const crop = state.crop;
      ctx.drawImage(adjusted, crop.x * adjusted.width, crop.y * adjusted.height, crop.width * adjusted.width, crop.height * adjusted.height, borderX, borderY, innerWidth, innerHeight);
    }
  }

  function drawMarginHatch(imageX, imageY, imageWidth, imageHeight) {
    // Start with a clearly visible hatch layer. The image is drawn over it,
    // leaving the hatch only in the blank areas caused by "contain" fitting.
    ctx.save();
    ctx.fillStyle = '#f5f7fa';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = 'rgba(119, 132, 151, .30)';
    ctx.lineWidth = Math.max(1, canvas.width / 900);
    ctx.beginPath();
    const spacing = Math.max(12, canvas.width / 45);
    for (let offset = -canvas.height; offset < canvas.width + canvas.height; offset += spacing) {
      ctx.moveTo(offset, 0);
      ctx.lineTo(offset + canvas.height, canvas.height);
    }
    ctx.stroke();
    ctx.restore();
  }

  function makeAdjustedCanvas(source) {
    const adjusted = document.createElement('canvas');
    const maxDimension = 1800;
    const scale = Math.min(1, maxDimension / Math.max(source.width, source.height));
    adjusted.width = Math.max(1, Math.round(source.width * scale));
    adjusted.height = Math.max(1, Math.round(source.height * scale));
    const adjustedContext = adjusted.getContext('2d');
    adjustedContext.drawImage(source, 0, 0, adjusted.width, adjusted.height);
    const brightness = Number(brightnessInput.value);
    const contrast = Number(contrastInput.value);
    const gamma = Number(gammaInput.value);
    const pixels = adjustedContext.getImageData(0, 0, adjusted.width, adjusted.height);
    const lookup = new Uint8ClampedArray(256);
    for (let value = 0; value < 256; value += 1) {
      let light = value / 255;
      light = light * brightness;
      light = (light - 0.5) * contrast + 0.5;
      light = Math.max(0, Math.min(1, light));
      light = 1 - Math.pow(1 - light, gamma);
      lookup[value] = Math.round(255 * light);
    }
    for (let index = 0; index < pixels.data.length; index += 4) {
      const luminance = (lookup[pixels.data[index]] * 0.299)
        + (lookup[pixels.data[index + 1]] * 0.587)
        + (lookup[pixels.data[index + 2]] * 0.114);
      if (state.previewMode === 'photo') {
        pixels.data[index] = lookup[pixels.data[index]];
        pixels.data[index + 1] = lookup[pixels.data[index + 1]];
        pixels.data[index + 2] = lookup[pixels.data[index + 2]];
      } else {
        // Match the full generator's Lithophane view: grayscale, inverted,
        // with a subtle warm light overlay rather than a hard binary posterize.
        const tone = 255 - Math.round(luminance);
        pixels.data[index] = Math.min(255, Math.round(tone + 255 * Math.min(0.42, gamma / 10) * 0.95));
        pixels.data[index + 1] = Math.min(255, Math.round(tone + 255 * Math.min(0.42, gamma / 10) * 0.68));
        pixels.data[index + 2] = Math.min(255, Math.round(tone + 255 * Math.min(0.42, gamma / 10) * 0.30));
      }
    }
    adjustedContext.putImageData(pixels, 0, 0);
    return adjusted;
  }

  function crop() {
    const current = state.crop;
    return {
      x: Number(current.x.toFixed(6)),
      y: Number(current.y.toFixed(6)),
      width: Number(current.width.toFixed(6)),
      height: Number(current.height.toFixed(6)),
    };
  }

  function resetView() {
    state.dragStart = null;
    state.crop = baseCrop();
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
      state.crop = automaticCrop(image.width, image.height, PANEL.width, PANEL.height);
      resetView();
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      setStatus('Nie można odczytać zdjęcia.', 'error');
    };
    image.src = url;
  });

  housingInput.addEventListener('change', invalidate);
  ledInput.addEventListener('change', invalidate);
  fitModeInput.addEventListener('change', () => {
    state.fitMode = fitModeInput.value === 'contain' ? 'contain' : 'cover';
    state.dragStart = null;
    state.crop = baseCrop();
    setCanvasAspect();
    invalidate();
  });
  zoomInput.addEventListener('input', () => {
    const parsedZoom = Number(zoomInput.value);
    const nextZoom = Number.isFinite(parsedZoom) ? Math.max(1, Math.min(5, parsedZoom)) : 1;
    const base = baseCrop();
    state.crop = zoomCrop(base, state.crop, nextZoom);
    syncPositionControls();
    draw(); invalidate();
  });
  [
    [positionXInput, positionXValue, 'x'],
    [positionYInput, positionYValue, 'y'],
  ].forEach(([input, output, axis]) => {
    if (!input || !output) return;
    input.addEventListener('input', () => {
      state.crop = {...state.crop, [axis]: Number(input.value)};
      syncPositionControls();
      draw(); invalidate();
    });
  });
  [
    [brightnessInput, brightnessValue],
    [contrastInput, contrastValue],
    [gammaInput, gammaValue],
  ].forEach(([input, output]) => input.addEventListener('input', () => {
    output.textContent = Number(input.value).toFixed(2);
    draw();
    invalidate();
  }));

  root.querySelectorAll('[data-orientation]').forEach(button => button.addEventListener('click', () => {
    state.orientation = button.dataset.orientation;
    root.querySelectorAll('[data-orientation]').forEach(item => item.classList.toggle('active', item === button));
    resetView();
  }));
  root.querySelectorAll('[data-preview-mode]').forEach(button => button.addEventListener('click', () => {
    state.previewMode = button.dataset.previewMode;
    root.querySelectorAll('[data-preview-mode]').forEach(item => item.classList.toggle('active', item === button));
    draw();
  }));
  root.querySelectorAll('[data-rotate]').forEach(button => button.addEventListener('click', () => {
    state.rotation = ((state.rotation + Number(button.dataset.rotate) + 540) % 360) - 180;
    resetView();
  }));

  dragSurface.addEventListener('pointerdown', event => {
    if (!state.image || state.busy) return;
    event.preventDefault();
    state.dragging = true;
    state.dragStart = {pointerId: event.pointerId, x: event.clientX, y: event.clientY, crop: {...state.crop}};
    dragSurface.setPointerCapture(event.pointerId);
  });
  dragSurface.addEventListener('pointermove', event => {
    if (!state.dragging) return;
    const start = state.dragStart;
    if (!start || start.pointerId !== event.pointerId) return;
    event.preventDefault();
    const area = imageAreaDimensions();
    const model = modelDimensions();
    const rect = event.currentTarget.getBoundingClientRect();
    const innerWidth = rect.width * area.width / model.width;
    const innerHeight = rect.height * area.height / model.height;
    const directionX = -1;
    const deltaPixelsX = event.clientX - start.x;
    const deltaPixelsY = event.clientY - start.y;
    // Some Chromium pointer-capture paths can deliver one bogus event whose
    // coordinates jump far outside the canvas. Applying that event makes the
    // normalized crop hit the 0/1 clamp and looks like a zoom/position reset.
    // Re-anchor only that event; ordinary movement remains the same pan math
    // as the full Litho generator.
    if (!Number.isFinite(deltaPixelsX) || !Number.isFinite(deltaPixelsY)
      || Math.abs(deltaPixelsX) > rect.width * 1.5
      || Math.abs(deltaPixelsY) > rect.height * 1.5) {
      start.x = event.clientX;
      start.y = event.clientY;
      return;
    }
    state.crop = panCrop(
      state.crop,
      directionX * deltaPixelsX / Math.max(1, innerWidth) * state.crop.width,
      -deltaPixelsY / Math.max(1, innerHeight) * state.crop.height,
    );
    start.x = event.clientX;
    start.y = event.clientY;
    syncPositionControls();
    draw(); invalidate();
  });
  dragSurface.addEventListener('pointerup', event => {
    state.dragging = false;
    state.dragStart = null;
    if (dragSurface.hasPointerCapture(event.pointerId)) dragSurface.releasePointerCapture(event.pointerId);
  });
  dragSurface.addEventListener('pointercancel', () => { state.dragging = false; state.dragStart = null; });
  dragSurface.addEventListener('wheel', event => {
    if (!state.image || state.busy) return;
    event.preventDefault();
    const rect = dragSurface.getBoundingClientRect();
    const area = imageAreaDimensions();
    const model = modelDimensions();
    const innerWidth = Math.max(1, rect.width * area.width / model.width);
    const innerHeight = Math.max(1, rect.height * area.height / model.height);
    const focalX = Math.max(0, Math.min(1, (event.clientX - rect.left) / innerWidth));
    const focalY = Math.max(0, Math.min(1, (event.clientY - rect.top) / innerHeight));
    const base = baseCrop();
    const nextZoom = Math.max(1, Math.min(5, base.width / state.crop.width * Math.exp(-event.deltaY * 0.0015)));
    state.crop = zoomCropAt(base, state.crop, nextZoom, focalX, focalY);
    syncPositionControls(); draw(); invalidate();
  }, {passive: false});

  async function request(path, options, browserToken) {
    const headers = Object.assign({'X-Litho-Nonce': LithoConfig.nonce, 'X-Litho-CSRF-Token': LithoConfig.csrf}, options.headers || {});
    if (browserToken) headers['X-Litho-Project-Key'] = browserToken;
    const response = await fetch(apiRoot + path, Object.assign({}, options, {headers, credentials: 'same-origin'}));
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
          size: FIXED_SIZE,
          orientation: state.orientation,
          housing_color: housingInput.value,
          light_temperature: ledInput.value,
          brightness: Number(brightnessInput.value),
          contrast: Number(contrastInput.value),
          gamma: Number(gammaInput.value),
          fit_mode: state.fitMode,
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
