/**
 * Easter egg (the footer link, and the Paper page menu link marked data-egg-menu): a quiet glyph that, on hover, focus or tap, gets a face-detection bracket and a "MATCH 0.64" tag
 * (0.64 is the Met's live facial recognition alert threshold). A click locks the bracket, then a dark iris grows out of
 * the glyph and the browser goes to the 3D scene named in data-egg (assets/scenes.js opens it with an iris of its own).
 * Modified clicks, keyboard activation and reduced-motion preferences all still reach the link target.
 */
(function () {
  var FLAG = 'nhcEgg';
  var eggs = document.querySelectorAll('[data-egg], [data-egg-menu]');
  Array.prototype.forEach.call(eggs, wire);
  window.NHCEgg = { wire: wire };

  function wire(egg) {
  function go() {
    window.location.href = egg.href;
  }

  egg.addEventListener('click', function (ev) {
    if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    ev.preventDefault();
    try { sessionStorage.setItem(FLAG, '1'); } catch (err) { /* storage blocked: scene opens without its iris */ }
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !document.body.animate) { go(); return; }
    egg.classList.add('is-lock');
    var box = egg.querySelector('.egg-glyph').getBoundingClientRect();
    var x = box.left + box.width / 2, y = box.top + box.height / 2;
    var cover = document.createElement('div');
    cover.className = 'egg-iris';
    cover.style.clipPath = 'circle(0px at ' + x + 'px ' + y + 'px)';
    document.body.appendChild(cover);
    var far = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y)) + 10;
    setTimeout(function () {
      var anim = cover.animate(
        [{ clipPath: 'circle(0px at ' + x + 'px ' + y + 'px)' }, { clipPath: 'circle(' + far + 'px at ' + x + 'px ' + y + 'px)' }],
        { duration: 520, easing: 'cubic-bezier(0.55, 0, 0.3, 1)', fill: 'forwards' }
      );
      anim.onfinish = go;
    }, 240);
  });

  window.addEventListener('pageshow', function (ev) {
    if (!ev.persisted) return;
    egg.classList.remove('is-lock');
    document.querySelectorAll('.egg-iris').forEach(function (n) { n.remove(); });
  });
  }
})();
