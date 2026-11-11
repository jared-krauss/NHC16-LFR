/**
 * Scenes page: loads one PlayCanvas gaussian-splat (.sog) scene at a time, only after a tap.
 *
 * Nothing is fetched until a Load button is pressed: the engine (vendor/playcanvas/*.js) is imported on the first tap,
 * the .sog on the same tap. Loading a second scene closes the first. Camera handling is the engine's CameraControls
 * script (orbit, damped; one finger or drag turns, pinch or wheel zooms), adapted from the dashboard's splat viewer with
 * everything specific to that dashboard removed (levelling, photo views, walk mode, ratings, page state, servers).
 */
const ENGINE_URL = new URL('../vendor/playcanvas/playcanvas.js', import.meta.url).href;
const CONTROLS_URL = new URL('../vendor/playcanvas/camera-controls.js', import.meta.url).href;
const STALL_MS = 20000;

const MSG_NO_WEBGL = 'WebGL is not available in this browser';
const MSG_FAILED = 'Could not load this scene';
const MSG_PREPARING = 'Preparing';
const HINT_TOUCH = 'Drag to turn, pinch to zoom';
const HINT_MOUSE = 'Drag to turn, scroll to zoom';

let enginePromise = null;
let engineReady = false;
let active = null;

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
 * Downloads (with progress) and imports the engine and camera script once; later calls return the same modules.
 *
 * @param {function(number): void} onBytes Progress callback for the engine bytes.
 * @param {AbortSignal} signal Aborts the download.
 * @returns {Promise<{pc: object, CameraControls: Function}>} The loaded modules.
 */
function loadEngine(onBytes, signal) {
  if (!enginePromise) {
    enginePromise = (async () => {
      await Promise.all([download(ENGINE_URL, onBytes, signal), download(CONTROLS_URL, onBytes, signal)]);
      const [pc, cc] = await Promise.all([import(ENGINE_URL), import(CONTROLS_URL)]);
      engineReady = true;
      document.querySelectorAll('[data-scene] [data-action=load]').forEach(b => {
        if (b.dataset.sogLabel) b.textContent = b.dataset.sogLabel;
      });
      return { pc, CameraControls: cc.CameraControls };
    })().catch(err => { enginePromise = null; throw err; });
  }
  return enginePromise;
}

/**
 * Picks the starting view for a loaded splat: the median splat centre as focus and a distance from the 10th-90th
 * percentile spread, so stray floaters do not push the camera out. Falls back to the bounding box.
 *
 * @param {object} pc The engine module.
 * @param {object} e The splat entity, already in the scene.
 * @param {object} res The loaded gsplat resource.
 * @returns {?{focus: object, dist: number}} The framing, or null until the bounds are ready.
 */
function frameFor(pc, e, res) {
  const c = res && res.centers, m = e.getWorldTransform();
  if (c && c.length >= 30) {
    const n = c.length / 3, stride = Math.max(1, Math.floor(n / 60000)), xs = [], ys = [], zs = [], v = new pc.Vec3();
    for (let i = 0; i < n; i += stride) {
      m.transformPoint(v.set(c[i * 3], c[i * 3 + 1], c[i * 3 + 2]), v);
      if (isFinite(v.x) && isFinite(v.y) && isFinite(v.z)) { xs.push(v.x); ys.push(v.y); zs.push(v.z); }
    }
    if (xs.length > 10) {
      const q = (a, p) => a[Math.min(a.length - 1, Math.floor(p * a.length))];
      [xs, ys, zs].forEach(a => a.sort((p, r) => p - r));
      const focus = new pc.Vec3(q(xs, .5), q(ys, .5), q(zs, .5));
      const half = new pc.Vec3(q(xs, .9) - q(xs, .1), q(ys, .9) - q(ys, .1), q(zs, .9) - q(zs, .1)).mulScalar(.5);
      return { focus, dist: Math.max(0.3, half.length() * 1.5) };
    }
  }
  const mi = e.gsplat.instance && e.gsplat.instance.meshInstance, bb = mi && mi.aabb;
  if (!bb || !isFinite(bb.halfExtents.x) || bb.halfExtents.length() === 0) return null;
  return { focus: bb.center.clone(), dist: Math.max(0.5, bb.halfExtents.length() * 0.9) };
}

/**
 * Creates a viewer on a canvas and loads a .sog blob into it.
 *
 * @param {{pc: object, CameraControls: Function}} eng The loaded engine modules.
 * @param {HTMLCanvasElement} canvas The canvas; its parent sets the drawing size.
 * @param {string} blobUrl Object URL of the downloaded file.
 * @returns {Promise<{reset: function(): void, destroy: function(): void}>} Resolves once the splat is in the scene.
 */
function createViewer(eng, canvas, blobUrl) {
  const { pc, CameraControls } = eng;
  const app = new pc.Application(canvas, { graphicsDeviceOptions: { antialias: false, alpha: false } });
  app.graphicsDevice.maxPixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  app.setCanvasFillMode(pc.FILLMODE_NONE);
  app.setCanvasResolution(pc.RESOLUTION_AUTO);
  app.start();
  const camE = new pc.Entity('cam');
  camE.addComponent('camera', { clearColor: new pc.Color(0.07, 0.07, 0.08), fov: 60, nearClip: 0.01, farClip: 1000 });
  camE.setPosition(0, 0, 6);
  app.root.addChild(camE);
  camE.addComponent('script');
  const cc = camE.script.create(CameraControls);
  cc.enableFly = false;
  cc.zoomRange = new pc.Vec2(0.02, 0);
  cc.pitchRange = new pc.Vec2(-89, 89);

  const stage = canvas.parentElement;
  const ro = new ResizeObserver(() => app.resizeCanvas(stage.clientWidth, stage.clientHeight));
  ro.observe(stage);
  app.resizeCanvas(stage.clientWidth, stage.clientHeight);

  let home = null, dead = false;
  const viewer = {
    reset() { if (home) cc.reset(home.focus, home.position); },
    destroy() {
      dead = true;
      ro.disconnect();
      try { app.destroy(); } catch (err) { /* already gone */ }
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
      const fit = () => {
        if (dead) { app.off('update', fit); return; }
        const f = frameFor(pc, e, asset.resource);
        if (!f) return;
        app.off('update', fit);
        const dir = new pc.Vec3(0, Math.sin(15 * Math.PI / 180), Math.cos(15 * Math.PI / 180));
        home = { focus: f.focus, position: dir.mulScalar(f.dist).add(f.focus) };
        cc.moveSpeed = f.dist * 0.35;
        cc.moveFastSpeed = f.dist * 1.2;
        cc.moveSlowSpeed = f.dist * 0.1;
        cc.reset(home.focus, home.position);
      };
      app.on('update', fit);
      ok(viewer);
    });
    app.assets.load(asset);
  });
}

/**
 * Puts a scene card back to its not-loaded state.
 *
 * @param {HTMLElement} card The scene block.
 */
function resetCard(card) {
  card.querySelector('[data-action=load]').hidden = false;
  card.querySelector('[data-action=load]').disabled = false;
  card.querySelector('[data-action=close]').hidden = true;
  card.querySelector('[data-action=retry]').hidden = true;
  card.querySelector('[data-action=reset]').disabled = true;
  const stage = card.querySelector('[data-role=stage]');
  stage.hidden = true;
  stage.textContent = '';
  const hint = card.querySelector('[data-role=hint]');
  hint.hidden = true;
  const old = card.querySelector('.scene-progress');
  if (old) old.remove();
}

/**
 * Closes whichever scene is loaded: stops its renderer, removes its canvas and restores its card.
 *
 * @param {boolean} [returnFocus] True to put keyboard focus back on that scene's Load button.
 */
function closeActive(returnFocus) {
  if (!active) return;
  const a = active;
  active = null;
  a.cancelled = true;
  if (a.abort) a.abort.abort();
  if (a.viewer) a.viewer.destroy();
  if (a.blobUrl) URL.revokeObjectURL(a.blobUrl);
  resetCard(a.card);
  a.card.querySelector('[data-role=msg]').textContent = '';
  if (returnFocus) a.card.querySelector('[data-action=load]').focus();
}

/**
 * Loads one scene after a tap, closing any other first.
 *
 * @param {HTMLElement} card The scene block that was tapped.
 */
async function loadScene(card) {
  closeActive(false);
  const msg = card.querySelector('[data-role=msg]');
  const stage = card.querySelector('[data-role=stage]');
  const loadBtn = card.querySelector('[data-action=load]');
  const closeBtn = card.querySelector('[data-action=close]');
  const retryBtn = card.querySelector('[data-action=retry]');
  const title = card.dataset.title || card.dataset.scene;
  msg.textContent = '';
  retryBtn.hidden = true;
  if (!hasWebGL()) { msg.textContent = MSG_NO_WEBGL; return; }

  const st = { card, cancelled: false, abort: new AbortController(), viewer: null, blobUrl: '' };
  active = st;
  loadBtn.hidden = true;
  closeBtn.hidden = false;
  closeBtn.focus();
  card.querySelector('[data-action=reset]').disabled = false;
  stage.hidden = false;
  const canvas = document.createElement('canvas');
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', '3D scene: ' + title);
  stage.appendChild(canvas);
  const bar = document.createElement('progress');
  bar.className = 'scene-progress';
  bar.max = 100;
  bar.setAttribute('aria-label', 'Loading ' + title);
  card.querySelector('.scene-controls').after(bar);
  const fail = text => {
    if (st.cancelled) return;
    st.abort.abort();
    bar.remove();
    msg.textContent = text;
    retryBtn.hidden = false;
    retryBtn.focus();
  };

  const total = Number(card.dataset.sogBytes || 0) + (engineReady ? 0 : Number(card.dataset.engineBytes || 0));
  let got = 0;
  const onBytes = n => {
    got += n;
    if (total) bar.value = Math.min(99, Math.round(got / total * 100));
    else bar.removeAttribute('value');
  };
  if (!total) bar.removeAttribute('value');

  try {
    const [eng, blob] = await Promise.all([
      loadEngine(onBytes, st.abort.signal),
      download(card.dataset.src, onBytes, st.abort.signal)
    ]);
    if (st.cancelled) return;
    st.blobUrl = URL.createObjectURL(blob);
    bar.removeAttribute('value');
    msg.textContent = MSG_PREPARING;
    let viewer;
    try {
      viewer = await createViewer(eng, canvas, st.blobUrl);
    } catch (err) {
      return fail(MSG_FAILED);
    }
    if (st.cancelled) { viewer.destroy(); return; }
    st.viewer = viewer;
    bar.remove();
    msg.textContent = '';
    const hint = card.querySelector('[data-role=hint]');
    hint.textContent = matchMedia('(pointer: coarse)').matches ? HINT_TOUCH : HINT_MOUSE;
    hint.hidden = false;
  } catch (err) {
    fail(MSG_FAILED);
  }
}

document.querySelectorAll('[data-scene]').forEach(card => {
  card.addEventListener('click', ev => {
    const btn = ev.target.closest('button[data-action]');
    if (!btn || !card.contains(btn)) return;
    const act = btn.dataset.action;
    if (act === 'load' || act === 'retry') loadScene(card);
    else if (act === 'close') closeActive(true);
    else if (act === 'reset' && active && active.card === card && active.viewer) active.viewer.reset();
  });
});

document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape' && active) closeActive(true);
});

window.addEventListener('pagehide', () => closeActive(false));
