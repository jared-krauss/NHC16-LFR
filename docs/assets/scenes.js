/**
 * Scenes page: full-screen viewers for the 3D gaussian-splat scenes (PlayCanvas, .sog).
 *
 * Nothing is fetched until a viewer opens: the engine (vendor/playcanvas/playcanvas.js) is imported and the .sog
 * downloaded (with byte progress, stall detection and Retry) when scenes.html#<id> is opened or a Load button is tapped.
 * The camera starts exactly on one of the training photos' poses, with that photo shown on top until the splat is drawn.
 *
 * Controls (the on-screen hint states exactly these):
 *   touch: one finger looks around, two fingers move (drag = slide sideways/up/down, pinch = move forward/back)
 *   mouse: drag looks, right-drag (or Shift-drag) moves, wheel moves forward/back
 *   keys:  arrows look, W/S forward and back, A/D slide
 * Scene data (camera views already in the viewer's world frame, gallery list) comes from the #scenes-data JSON that
 * render/scenes.py writes from scenes-config.json.
 */
const ENGINE_URL = new URL('../vendor/playcanvas/playcanvas.js', import.meta.url).href;
const STALL_MS = 20000;
const MSG_NO_WEBGL = 'WebGL is not available in this browser';
const MSG_FAILED = 'Could not load this scene';
const MSG_PREPARING = 'Preparing';
const HINT_TOUCH = '1 finger to look, 2 fingers to move';
const HINT_MOUSE = 'Drag to look, right-drag to move, scroll to zoom';
const EGG_FLAG = 'nhcEgg';
const RAD = Math.PI / 180;

const dataEl = document.getElementById('scenes-data');
const DATA = dataEl ? JSON.parse(dataEl.textContent) : { scenes: [] };
const SCENES = Object.fromEntries(DATA.scenes.map(s => [s.id, s]));
const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

let enginePromise = null;
let engineReady = false;
let active = null;
let pushed = false;

/**
 * Tells whether this browser can create a WebGL context.
 *
 * @returns {boolean} True when WebGL 2 or 1 is available.
 */
function hasWebGL() {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch (err) {
    return false;
  }
}

/**
 * Downloads a file with byte progress. Fails when no bytes arrive for STALL_MS.
 *
 * @param {string} url The file address.
 * @param {function(number): void} onBytes Called with the size of each chunk received.
 * @param {AbortSignal} signal Aborts the download.
 * @returns {Promise<Blob>} The file.
 */
async function download(url, onBytes, signal) {
  const ac = new AbortController();
  const relay = () => ac.abort();
  signal.addEventListener('abort', relay);
  let timer = 0;
  const arm = () => { clearTimeout(timer); timer = setTimeout(() => ac.abort(), STALL_MS); };
  try {
    arm();
    const res = await fetch(url, { signal: ac.signal });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    if (!res.body || !res.body.getReader) {
      const blob = await res.blob();
      onBytes(blob.size);
      return blob;
    }
    const reader = res.body.getReader();
    const parts = [];
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      arm();
      parts.push(value);
      onBytes(value.length);
    }
    return new Blob(parts);
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', relay);
  }
}

/**
 * Downloads (with progress) and imports the engine once; later calls return the same module.
 *
 * @param {function(number): void} onBytes Progress callback for the engine bytes.
 * @param {AbortSignal} signal Aborts the download.
 * @returns {Promise<object>} The engine module.
 */
function loadEngine(onBytes, signal) {
  if (!enginePromise) {
    enginePromise = (async () => {
      await download(ENGINE_URL, onBytes, signal);
      const pc = await import(ENGINE_URL);
      engineReady = true;
      return pc;
    })().catch(err => { enginePromise = null; throw err; });
  }
  return enginePromise;
}

/**
 * Smooth ease used for camera moves.
 *
 * @param {number} t Progress 0..1.
 * @returns {number} Eased progress.
 */
const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

/**
 * Converts a view's forward vector to the engine's yaw and pitch (degrees, no roll).
 *
 * @param {number[]} f World-frame forward vector.
 * @returns {{yaw: number, pitch: number}} The angles.
 */
function anglesOf(f) {
  const n = Math.hypot(f[0], f[1], f[2]) || 1;
  return { yaw: Math.atan2(-f[0] / n, -f[2] / n) / RAD, pitch: Math.asin(Math.max(-1, Math.min(1, f[1] / n))) / RAD };
}

/**
 * Builds the camera state of one stored view.
 *
 * @param {{p: number[], f: number[], vf: number, a: number}} v The view.
 * @returns {{p: number[], yaw: number, pitch: number, vf: number, a: number}} Pose plus the photo's field of view.
 */
function poseOf(v) {
  const g = anglesOf(v.f);
  return { p: v.p.slice(), yaw: g.yaw, pitch: g.pitch, vf: v.vf, a: v.a };
}

/**
 * Creates the engine app, camera and our own look/move controller on a stage, then loads a .sog blob into it.
 *
 * @param {object} pc The engine module.
 * @param {HTMLElement} stage The element whose size sets the drawing size.
 * @param {object} scene The scene data.
 * @param {string} blobUrl Object URL of the downloaded .sog.
 * @param {function(): void} onInteract Called on the first user input.
 * @returns {Promise<object>} The viewer handle once the splat is in the scene.
 */
function createViewer(pc, stage, scene, blobUrl, onInteract) {
  const canvas = document.createElement('canvas');
  canvas.tabIndex = 0;
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', '3D scene: ' + scene.title);
  stage.appendChild(canvas);
  const app = new pc.Application(canvas, { graphicsDeviceOptions: { antialias: false, alpha: false } });
  app.graphicsDevice.maxPixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  app.setCanvasFillMode(pc.FILLMODE_NONE);
  app.setCanvasResolution(pc.RESOLUTION_AUTO);
  app.start();
  const camE = new pc.Entity('cam');
  camE.addComponent('camera', { clearColor: new pc.Color(0.043, 0.051, 0.059), fov: 60, nearClip: 0.01, farClip: 1000 });
  app.root.addChild(camE);

  const views = scene.views.map(poseOf);
  const S = Math.max(2, scene.scale || 10);
  let cur = Math.max(0, Math.min(views.length - 1, scene.start || 0));
  const C = JSON.parse(JSON.stringify(views[cur]));
  const T = JSON.parse(JSON.stringify(views[cur]));
  let tween = null, dead = false, frames = 0, splatIn = false, readyCb = null, t0 = performance.now();
  const keys = new Set();

  const size = () => ({ w: Math.max(1, stage.clientWidth), h: Math.max(1, stage.clientHeight) });
  const effFov = pose => {
    const { w, h } = size(), va = w / h;
    return va >= pose.a ? pose.vf : 2 * Math.atan(Math.tan(pose.vf * RAD / 2) * pose.a / va) / RAD;
  };
  const resize = () => { const s = size(); app.resizeCanvas(s.w, s.h); };
  const ro = new ResizeObserver(resize);
  ro.observe(stage);
  resize();

  const basis = () => {
    const y = C.yaw * RAD, p = C.pitch * RAD;
    const f = [-Math.cos(p) * Math.sin(y), Math.sin(p), -Math.cos(p) * Math.cos(y)];
    const r = [Math.cos(y), 0, -Math.sin(y)];
    const u = [f[1] * r[2] - f[2] * r[1], f[2] * r[0] - f[0] * r[2], f[0] * r[1] - f[1] * r[0]];
    return { f, r, u: [-u[0], -u[1], -u[2]] };
  };
  const move = (dx, dy, dz, tgt) => {
    const b = basis();
    for (let k = 0; k < 3; k++) tgt.p[k] += b.r[k] * dx + b.u[k] * dy + b.f[k] * dz;
  };
  const stopTween = () => { tween = null; Object.assign(T, JSON.parse(JSON.stringify(C))); };
  const touched = () => { stopTween(); onInteract(); };

  const ptrs = new Map();
  let pinch = null;
  const mid = () => {
    const a = [...ptrs.values()];
    return { x: (a[0].x + a[1].x) / 2, y: (a[0].y + a[1].y) / 2, d: Math.hypot(a[0].x - a[1].x, a[0].y - a[1].y) };
  };
  const look = (dx, dy) => {
    const k = effFov(C) / size().h;
    T.yaw += dx * k;
    T.pitch = Math.max(-89, Math.min(89, T.pitch + dy * k));
  };
  const slide = (dx, dy) => {
    const k = 2 * Math.tan(effFov(C) * RAD / 2) * S * 0.2 / size().h;
    move(-dx * k, dy * k, 0, T);
  };
  canvas.addEventListener('pointerdown', ev => {
    canvas.focus({ preventScroll: true });
    canvas.setPointerCapture(ev.pointerId);
    ptrs.set(ev.pointerId, { x: ev.clientX, y: ev.clientY, mode: ev.pointerType === 'mouse' && (ev.button === 2 || ev.button === 1 || ev.shiftKey) ? 'move' : 'look' });
    if (ptrs.size === 2) pinch = mid();
    touched();
  });
  canvas.addEventListener('pointermove', ev => {
    const p = ptrs.get(ev.pointerId);
    if (!p) return;
    const dx = ev.clientX - p.x, dy = ev.clientY - p.y;
    p.x = ev.clientX; p.y = ev.clientY;
    if (ptrs.size >= 2) {
      const m = mid();
      if (pinch) {
        slide(m.x - pinch.x, m.y - pinch.y);
        move(0, 0, (m.d - pinch.d) / size().h * S * 0.5, T);
      }
      pinch = m;
    } else if (p.mode === 'move') slide(dx, dy);
    else look(dx, dy);
  });
  const lift = ev => { ptrs.delete(ev.pointerId); pinch = ptrs.size === 2 ? mid() : null; };
  canvas.addEventListener('pointerup', lift);
  canvas.addEventListener('pointercancel', lift);
  canvas.addEventListener('contextmenu', ev => ev.preventDefault());
  canvas.addEventListener('wheel', ev => {
    ev.preventDefault();
    touched();
    const unit = ev.deltaMode === 1 ? 33 : 1;
    move(0, 0, -ev.deltaY * unit * S * 0.00025, T);
  }, { passive: false });
  canvas.addEventListener('keydown', ev => {
    const k = ev.key.toLowerCase();
    if (['arrowleft', 'arrowright', 'arrowup', 'arrowdown', 'w', 'a', 's', 'd'].includes(k)) {
      ev.preventDefault();
      touched();
      keys.add(k);
    }
  });
  canvas.addEventListener('keyup', ev => keys.delete(ev.key.toLowerCase()));
  canvas.addEventListener('blur', () => keys.clear());

  const apply = () => {
    camE.setPosition(C.p[0], C.p[1], C.p[2]);
    camE.setEulerAngles(C.pitch, C.yaw, 0);
    camE.camera.fov = effFov(C);
  };
  app.on('update', dt => {
    if (dead) return;
    dt = Math.min(dt, 0.1);
    if (tween) {
      const t = Math.min(1, (performance.now() - tween.start) / tween.ms), e = ease(t), a = tween.from, b = tween.to;
      for (let k = 0; k < 3; k++) T.p[k] = a.p[k] + (b.p[k] - a.p[k]) * e;
      T.yaw = a.yaw + tween.dyaw * e;
      T.pitch = a.pitch + (b.pitch - a.pitch) * e;
      T.vf = a.vf + (b.vf - a.vf) * e;
      T.a = a.a + (b.a - a.a) * e;
      Object.assign(C, JSON.parse(JSON.stringify(T)));
      if (t >= 1) tween = null;
    } else {
      if (keys.size) {
        const sp = S * 0.12 * dt;
        if (keys.has('arrowleft')) T.yaw += 45 * dt;
        if (keys.has('arrowright')) T.yaw -= 45 * dt;
        if (keys.has('arrowup')) T.pitch = Math.min(89, T.pitch + 35 * dt);
        if (keys.has('arrowdown')) T.pitch = Math.max(-89, T.pitch - 35 * dt);
        if (keys.has('w')) move(0, 0, sp, T);
        if (keys.has('s')) move(0, 0, -sp, T);
        if (keys.has('d')) move(sp, 0, 0, T);
        if (keys.has('a')) move(-sp, 0, 0, T);
      }
      const al = 1 - Math.exp(-dt * 16);
      for (let k = 0; k < 3; k++) C.p[k] += (T.p[k] - C.p[k]) * al;
      C.yaw += (T.yaw - C.yaw) * al;
      C.pitch += (T.pitch - C.pitch) * al;
    }
    apply();
    if (splatIn && readyCb && !readyCb.done && ++frames > 8 && performance.now() - t0 > 1400) { readyCb.done = true; readyCb(); }
  });
  apply();

  const viewer = {
    count: views.length,
    get index() { return cur; },
    onReady(fn) { readyCb = fn; readyCb.done = false; },
    goTo(i, instant) {
      cur = ((i % views.length) + views.length) % views.length;
      const to = views[cur];
      if (instant || reduceMotion()) {
        tween = null;
        Object.assign(T, JSON.parse(JSON.stringify(to)));
        Object.assign(C, JSON.parse(JSON.stringify(to)));
        return;
      }
      const from = JSON.parse(JSON.stringify(C));
      const dyaw = ((to.yaw - from.yaw + 540) % 360) - 180;
      const dist = Math.hypot(to.p[0] - from.p[0], to.p[1] - from.p[1], to.p[2] - from.p[2]);
      tween = { from, to, dyaw, start: performance.now(), ms: Math.round(Math.min(1600, 700 + dist / S * 2400 + Math.abs(dyaw) * 3)) };
    },
    reset() { viewer.goTo(scene.start || 0); },
    pause() { app.autoRender = false; },
    destroy() {
      dead = true;
      ro.disconnect();
      try { app.destroy(); } catch (err) { /* already gone */ }
      canvas.remove();
    }
  };

  return new Promise((ok, fail) => {
    const asset = new pc.Asset('scene.sog', 'gsplat', { url: blobUrl, filename: 'scene.sog' });
    app.assets.add(asset);
    asset.once('error', err => fail(new Error(String(err))));
    asset.once('load', () => {
      if (dead) return;
      const e = new pc.Entity('splat');
      e.addComponent('gsplat', { asset });
      e.setLocalRotation(new pc.Quat().setFromEulerAngles(0, 0, 180));
      app.root.addChild(e);
      splatIn = true;
      t0 = performance.now();
      ok(viewer);
    });
    app.assets.load(asset);
  });
}

/**
 * Wires one viewer overlay's controls and returns the open/close functions for it.
 *
 * @param {HTMLElement} el The .sv overlay element.
 * @param {object} scene The scene data.
 * @returns {{open: function(boolean): void, close: function(): void, el: HTMLElement}} The handle.
 */
function bindViewer(el, scene) {
  const q = s => el.querySelector(s);
  const stage = q('[data-role=stage]'), msg = q('[data-role=msg]'), bar = q('[data-role=bar]');
  const hint = q('[data-role=hint]'), retry = q('[data-act=retry]');
  const menu = q('[data-role=menu]'), burger = q('[data-role=burger]');
  const gal = q('[data-role=gallery]'), lb = q('[data-role=lightbox]');
  const lbImg = new Image(), lbCount = q('[data-role=lb-count]');
  lbImg.alt = '';
  let st = null, gi = 0, hintGone = false, opener = null;

  const menuOpen = () => !menu.hidden;
  const setMenu = on => {
    menu.hidden = !on;
    burger.setAttribute('aria-expanded', String(on));
    if (on) menu.querySelector('button').focus();
  };
  const showLb = i => {
    const list = scene.gallery;
    gi = (i + list.length) % list.length;
    lbImg.alt = list[gi].alt || '';
    lbImg.width = list[gi].w;
    lbImg.height = list[gi].h;
    lbImg.src = list[gi].full;
    if (!lbImg.isConnected) q('[data-role=lb-slot]').appendChild(lbImg);
    lbCount.textContent = (gi + 1) + ' / ' + list.length;
    lb.hidden = false;
    lb.querySelector('[data-act=lb-go]').focus();
  };
  const hideLb = () => {
    lb.hidden = true;
    lbImg.removeAttribute('src');
    const t = gal.querySelectorAll('.sv-thumb')[gi];
    if (t) t.focus();
  };
  const hideGallery = () => { gal.hidden = true; burger.focus(); };
  const interacted = () => {
    if (hintGone) return;
    hintGone = true;
    hint.classList.add('is-gone');
    setTimeout(() => { hint.hidden = true; }, 800);
  };

  const fail = text => {
    if (!st || st.cancelled) return;
    st.abort.abort();
    bar.hidden = true;
    msg.textContent = text;
    retry.hidden = false;
    retry.focus();
  };

  const start = async () => {
    if (st) { st.cancelled = true; st.abort.abort(); if (st.viewer) st.viewer.destroy(); if (st.blobUrl) URL.revokeObjectURL(st.blobUrl); }
    st = { cancelled: false, abort: new AbortController(), viewer: null, blobUrl: '' };
    const me = st;
    msg.textContent = '';
    retry.hidden = true;
    el.classList.remove('is-ready');
    hintGone = false;
    hint.hidden = true;
    hint.classList.remove('is-gone');
    if (!hasWebGL()) { msg.textContent = MSG_NO_WEBGL; return; }
    bar.hidden = false;
    const total = scene.sogBytes + (engineReady ? 0 : scene.engineBytes);
    let got = 0;
    bar.value = 0;
    const onBytes = n => { got += n; if (total) bar.value = Math.min(99, Math.round(got / total * 100)); else bar.removeAttribute('value'); };
    try {
      const [pc, blob] = await Promise.all([loadEngine(onBytes, me.abort.signal), download(scene.sog, onBytes, me.abort.signal)]);
      if (me.cancelled) return;
      me.blobUrl = URL.createObjectURL(blob);
      bar.removeAttribute('value');
      msg.textContent = MSG_PREPARING;
      let viewer;
      try {
        viewer = await createViewer(pc, stage, scene, me.blobUrl, interacted);
      } catch (err) {
        return fail(MSG_FAILED);
      }
      if (me.cancelled) { viewer.destroy(); return; }
      me.viewer = viewer;
      viewer.onReady(() => {
        if (me.cancelled) return;
        el.classList.add('is-ready');
        bar.hidden = true;
        msg.textContent = '';
        hint.textContent = matchMedia('(pointer: coarse)').matches ? HINT_TOUCH : HINT_MOUSE;
        hint.hidden = false;
        window.__scenes = { id: scene.id, ready: true, goTo: (i, instant) => viewer.goTo(i, instant), viewer };
      });
    } catch (err) {
      fail(MSG_FAILED);
    }
  };

  const act = {
    reset: () => { setMenu(false); st && st.viewer && st.viewer.reset(); },
    prev: () => { st && st.viewer && st.viewer.goTo(st.viewer.index - 1); },
    next: () => { st && st.viewer && st.viewer.goTo(st.viewer.index + 1); },
    gallery: () => { setMenu(false); gal.hidden = false; gal.scrollTop = 0; const t = gal.querySelector('.sv-thumb'); if (t) t.focus(); else gal.focus(); },
    'gallery-close': hideGallery,
    'lb-close': hideLb,
    'lb-prev': () => showLb(gi - 1),
    'lb-next': () => showLb(gi + 1),
    'lb-go': () => {
      const v = scene.gallery[gi].v;
      lb.hidden = true;
      gal.hidden = true;
      burger.focus();
      if (st && st.viewer) st.viewer.goTo(v);
    },
    retry: () => start()
  };

  el.addEventListener('click', ev => {
    const b = ev.target.closest('[data-act],[data-role=burger],.sv-thumb');
    if (b && el.contains(b)) {
      if (b.dataset.role === 'burger') { setMenu(!menuOpen()); return; }
      if (b.classList.contains('sv-thumb')) { showLb(Number(b.dataset.gi)); return; }
      const fn = act[b.dataset.act];
      if (fn) fn();
      return;
    }
    if (menuOpen() && !ev.target.closest('[data-role=menu]')) setMenu(false);
  });
  el.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') {
      ev.preventDefault();
      ev.stopPropagation();
      if (!lb.hidden) hideLb();
      else if (!gal.hidden) hideGallery();
      else if (menuOpen()) { setMenu(false); burger.focus(); }
      else api.requestClose();
    } else if (!lb.hidden && (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight')) {
      showLb(gi + (ev.key === 'ArrowRight' ? 1 : -1));
    } else if (menuOpen() && (ev.key === 'ArrowDown' || ev.key === 'ArrowUp')) {
      const items = [...menu.querySelectorAll('button')], i = items.indexOf(document.activeElement);
      ev.preventDefault();
      items[(i + (ev.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length].focus();
    }
  });

  const api = {
    el,
    requestClose: () => {},
    open(iris) {
      opener = document.activeElement;
      if (stage.dataset.poster && !stage.querySelector('.sv-poster')) {
        const im = new Image();
        im.className = 'sv-poster';
        im.alt = stage.dataset.posterAlt || '';
        if (stage.dataset.posterW) { im.width = Number(stage.dataset.posterW); im.height = Number(stage.dataset.posterH); }
        im.decoding = 'async';
        im.src = stage.dataset.poster;
        stage.prepend(im);
      }
      el.querySelectorAll('.sv-thumb:not(:has(img))').forEach(b => {
        const im = new Image();
        im.loading = 'lazy';
        im.decoding = 'async';
        im.alt = b.dataset.alt || '';
        im.width = Number(b.dataset.w);
        im.height = Number(b.dataset.h);
        im.src = b.dataset.src;
        b.appendChild(im);
      });
      el.hidden = false;
      el.classList.toggle('sv--iris', !!iris && !reduceMotion());
      if (iris) el.addEventListener('animationend', () => el.classList.remove('sv--iris'), { once: true });
      menu.hidden = true;
      gal.hidden = true;
      lb.hidden = true;
      burger.setAttribute('aria-expanded', 'false');
      el.focus({ preventScroll: true });
      start();
    },
    close() {
      if (st) {
        st.cancelled = true;
        st.abort.abort();
        if (st.viewer) st.viewer.destroy();
        if (st.blobUrl) URL.revokeObjectURL(st.blobUrl);
        st = null;
      }
      window.__scenes = null;
      el.hidden = true;
      el.classList.remove('is-ready', 'sv--iris');
      if (opener && opener.focus && document.contains(opener)) opener.focus();
    },
    setChrome(on) { el.querySelectorAll('.sv-top,.sv-bottom,.sv-center').forEach(n => { n.style.visibility = on ? '' : 'hidden'; }); el.classList.toggle('no-frame', !on); }
  };
  return api;
}

const viewers = {};
document.querySelectorAll('.sv[data-viewer]').forEach(el => {
  const scene = SCENES[el.dataset.viewer];
  if (!scene) return;
  document.body.appendChild(el);
  viewers[scene.id] = bindViewer(el, scene);
  viewers[scene.id].requestClose = () => closeActive(true);
});

const lockables = () => document.querySelectorAll('.skip-link,.site-header,main,.site-footer');

/**
 * Closes the open viewer and restores the page behind it.
 *
 * @param {boolean} updateUrl True to drop the #id from the address.
 */
function closeActive(updateUrl) {
  if (!active) return;
  const a = active;
  active = null;
  a.close();
  lockables().forEach(n => n.removeAttribute('inert'));
  document.documentElement.classList.remove('sv-open', 'sv-pending');
  if (updateUrl && /^#[a-z0-9-]+$/.test(location.hash)) {
    if (pushed) { pushed = false; history.back(); } else history.replaceState(null, '', location.pathname + location.search);
  }
}

/**
 * Opens the viewer for a scene id, closing any other first.
 *
 * @param {string} id The scene id.
 */
function openScene(id) {
  const v = viewers[id];
  if (!v) { document.documentElement.classList.remove('sv-pending'); return; }
  if (active === v) return;
  closeActive(false);
  let iris = false;
  try { iris = sessionStorage.getItem(EGG_FLAG) === '1'; sessionStorage.removeItem(EGG_FLAG); } catch (err) { iris = false; }
  active = v;
  lockables().forEach(n => n.setAttribute('inert', ''));
  document.documentElement.classList.add('sv-open');
  v.open(iris);
  document.documentElement.classList.remove('sv-pending');
}

/**
 * Opens or closes a viewer to match the address hash.
 */
function syncHash() {
  const id = location.hash.replace(/^#/, '');
  if (id && viewers[id]) openScene(id);
  else closeActive(false);
}

document.querySelectorAll('[data-scene] [data-action=load]').forEach(btn => {
  btn.addEventListener('click', () => {
    const id = btn.closest('[data-scene]').dataset.scene;
    if (viewers[id]) { pushed = true; location.hash = id; }
  });
});
document.querySelectorAll('.sv-other').forEach(a => a.addEventListener('click', () => { pushed = true; }));
window.addEventListener('hashchange', syncHash);
window.addEventListener('pagehide', () => closeActive(false));
window.__scenesApp = { viewers, get active() { return active; } };
syncHash();
document.documentElement.classList.remove('sv-pending');
