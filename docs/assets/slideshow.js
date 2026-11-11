(function () {
  var root = document.getElementById('slideshow');
  if (!root) return;
  var slides = [].slice.call(root.querySelectorAll('.slide'));
  var n = slides.length;
  var bar = root.querySelector('.slide-bar');
  if (!n || !bar) return;
  var stage = root.querySelector('.slide-stage');
  var counter = root.querySelector('.slide-counter');
  var bPause = root.querySelector('[data-action=pause]');
  var bFull = root.querySelector('[data-action=fullscreen]');
  var params = new URLSearchParams(location.search);
  var reduced = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var paused = reduced || root.dataset.autoplay === '0' || params.get(root.dataset.pauseKey) === root.dataset.pauseVal;
  var idx = 0, timer = 0;

  function fsEl() { return document.fullscreenElement || document.webkitFullscreenElement || null; }

  var hovering = false, focusHeld = false, exiting = false;

  function held() { return hovering || focusHeld; }

  function barFocus() {
    try {
      var a = document.activeElement;
      return !!(a && a !== document.body && bar.contains(a) && a.matches(':focus-visible'));
    } catch (e) { return false; }
  }

  function clear() { if (timer) { clearTimeout(timer); timer = 0; } }

  function schedule() {
    clear();
    if (paused || held()) return;
    var d = parseFloat(slides[idx].dataset.dwell) || 0;
    if (!d) return;
    timer = setTimeout(function () {
      timer = 0;
      if (!paused && !held()) go(idx + 1); else schedule();
    }, d * 1000);
  }

  function syncVideo() {
    var v = slides[idx].querySelector('video');
    if (!v) return;
    if (paused || held()) { v.pause(); return; }
    var p = v.play();
    if (p && p.catch) p.catch(function () {});
  }

  function setUrl() {
    if (exiting) return;
    try { history.replaceState(null, '', location.pathname + location.search + '#' + (idx + 1)); } catch (e) {}
  }

  function go(i) {
    i = ((i % n) + n) % n;
    slides.forEach(function (s, k) {
      s.hidden = k !== i;
      if (k !== i) { var v = s.querySelector('video'); if (v) { v.pause(); v.currentTime = 0; } }
    });
    idx = i;
    counter.textContent = (i + 1) + ' / ' + n;
    [i + 1, i - 1].forEach(function (k) {
      var im = slides[((k % n) + n) % n].querySelector('img');
      if (im) { var pre = new Image(); pre.src = im.currentSrc || im.src; }
    });
    setUrl();
    syncVideo();
    schedule();
  }

  function render() {
    bPause.textContent = paused ? 'Play' : 'Pause';
    stage.setAttribute('aria-live', paused ? 'polite' : 'off');
  }

  function setPaused(p) { paused = p; render(); syncVideo(); schedule(); }

  function fsLabel() { bFull.textContent = fsEl() ? 'Close full screen' : 'Full screen'; }

  function toggleFull() {
    if (fsEl()) { (document.exitFullscreen || document.webkitExitFullscreen).call(document); return; }
    var f = root.requestFullscreen || root.webkitRequestFullscreen;
    if (!f) return;
    try {
      var p = f.call(root);
      if (p && p.catch) p.catch(function () {});
    } catch (e) {}
  }

  function exit() {
    if (exiting) return;
    exiting = true;
    clear();
    var same = false;
    try {
      var r = document.referrer ? new URL(document.referrer) : null;
      same = !!r && r.origin === location.origin && r.pathname !== location.pathname;
    } catch (e) {}
    if (!same) location.href = 'index.html';
    else history.back();
  }

  root.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-action]');
    if (!b || !root.contains(b)) return;
    var a = b.dataset.action;
    if (a === 'pause') setPaused(!paused);
    else if (a === 'prev') go(idx - 1);
    else if (a === 'next') go(idx + 1);
    else if (a === 'fullscreen') toggleFull();
    else if (a === 'exit') exit();
  });

  document.addEventListener('keydown', function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    var tag = e.target && e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    var k = e.key;
    if (k === 'ArrowRight') go(idx + 1);
    else if (k === 'ArrowLeft') go(idx - 1);
    else if (k === 'Home') go(0);
    else if (k === 'End') go(n - 1);
    else if (k === ' ' || k === 'Spacebar') {
      if (tag === 'BUTTON' || tag === 'A') return;
      setPaused(!paused);
    } else if (k === 'Escape') {
      if (!fsEl()) exit();
    } else return;
    e.preventDefault();
  });

  var sx = 0, sy = 0, down = false;
  stage.addEventListener('pointerdown', function (e) {
    if (e.pointerType === 'mouse') return;
    down = true; sx = e.clientX; sy = e.clientY;
  });
  stage.addEventListener('pointerup', function (e) {
    if (!down) return;
    down = false;
    var dx = e.clientX - sx, dy = e.clientY - sy;
    if (Math.abs(dx) > 50 && Math.abs(dx) > 1.5 * Math.abs(dy)) go(dx < 0 ? idx + 1 : idx - 1);
  });
  stage.addEventListener('pointercancel', function () { down = false; });

  function hover(on) {
    return function (e) {
      if (e.pointerType !== 'mouse') return;
      hovering = on;
      if (on) clear(); else schedule();
      syncVideo();
    };
  }
  [stage, bar].forEach(function (el) {
    el.addEventListener('pointerenter', hover(true));
    el.addEventListener('pointerleave', hover(false));
  });
  bar.addEventListener('focusin', function () {
    focusHeld = barFocus();
    if (focusHeld) clear();
    syncVideo();
  });
  bar.addEventListener('focusout', function () {
    setTimeout(function () { focusHeld = barFocus(); syncVideo(); schedule(); }, 0);
  });
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) { exiting = false; hovering = false; focusHeld = false; schedule(); }
  });
  slides.forEach(function (s) {
    var v = s.querySelector('video');
    if (v) v.addEventListener('ended', function () { if (!paused) go(idx + 1); });
  });
  document.addEventListener('fullscreenchange', fsLabel);
  document.addEventListener('webkitfullscreenchange', fsLabel);

  root.classList.add('is-live');
  
  ['.site-header', '.site-footer .footer-links'].forEach(function (q) { var e = document.querySelector(q); if (e) e.inert = true; });
  if (!(root.requestFullscreen || root.webkitRequestFullscreen)) bFull.hidden = true;
  bar.hidden = false;
  var h = parseInt(location.hash.slice(1), 10);
  render();
  go(h >= 1 && h <= n ? h - 1 : 0);
})();
