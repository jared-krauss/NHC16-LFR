(function () {
  "use strict";

  function create(items) {
  var root, stage, box, img, label, btns = {};
  var idx = 0, opener = null, fullImg = null, savedY = 0;
  var st = { s: 1, x: 0, y: 0, fw: 0, fh: 0, sw: 0, sh: 0, max: 8, ar: 1.5 };
  var pts = {}, gesture = null, lastTap = 0;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  function button(name, text, aria) {
    var b = el("button", "viewer-btn", text);
    b.type = "button";
    b.setAttribute("aria-label", aria);
    b.addEventListener("click", function (ev) { ev.stopPropagation(); actions[name](); });
    btns[name] = b;
    return b;
  }

  var actions = {
    close: close,
    prev: function () { show(idx - 1); },
    next: function () { show(idx + 1); },
    zin: function () { zoomAt(st.s * 1.6, st.sw / 2, st.sh / 2); },
    zout: function () { zoomAt(st.s / 1.6, st.sw / 2, st.sh / 2); },
    fit: function () { st.s = 1; st.x = 0; st.y = 0; apply(); }
  };

  function build() {
    root = el("div", "viewer");
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    var bar = el("div", "viewer-bar");
    label = el("p", "viewer-label");
    var tools = el("div", "viewer-tools");
    tools.appendChild(button("prev", "←", "Previous figure"));
    tools.appendChild(button("next", "→", "Next figure"));
    tools.appendChild(button("zout", "−", "Zoom out"));
    tools.appendChild(button("zin", "+", "Zoom in"));
    tools.appendChild(button("fit", "Fit", "Fit to screen"));
    tools.appendChild(button("close", "Close", "Close viewer"));
    bar.appendChild(label);
    bar.appendChild(tools);
    stage = el("div", "viewer-stage");
    box = el("div", "viewer-box");
    img = el("img", "viewer-img");
    img.draggable = false;
    img.alt = "";
    box.appendChild(img);
    stage.appendChild(box);
    root.appendChild(bar);
    root.appendChild(stage);
    document.body.appendChild(root);
    stage.addEventListener("pointerdown", down);
    stage.addEventListener("pointermove", move);
    stage.addEventListener("pointerup", up);
    stage.addEventListener("pointercancel", up);
    stage.addEventListener("wheel", wheel, { passive: false });
    window.addEventListener("resize", function () { if (root && !root.hidden) layout(true); });
    document.addEventListener("keydown", keys);
  }

  function layout(keep) {
    var r = stage.getBoundingClientRect();
    st.sw = r.width; st.sh = r.height;
    var w = Math.min(r.width, r.height * st.ar), h = w / st.ar;
    st.fw = w; st.fh = h;
    box.style.width = w + "px";
    box.style.height = h + "px";
    box.style.left = ((r.width - w) / 2) + "px";
    box.style.top = ((r.height - h) / 2) + "px";
    var nat = fullImg && fullImg.naturalWidth ? fullImg.naturalWidth : w * 4;
    st.max = Math.max(4, Math.min(24, nat / w * 2));
    if (!keep) { st.s = 1; st.x = 0; st.y = 0; }
    apply();
  }

  function clamp() {
    st.s = Math.min(st.max, Math.max(1, st.s));
    var mx = Math.max(0, (st.fw * st.s - st.sw) / 2) + st.sw * 0.15 * (st.s > 1 ? 1 : 0);
    var my = Math.max(0, (st.fh * st.s - st.sh) / 2) + st.sh * 0.15 * (st.s > 1 ? 1 : 0);
    st.x = Math.min(mx, Math.max(-mx, st.x));
    st.y = Math.min(my, Math.max(-my, st.y));
    if (st.s === 1) { st.x = 0; st.y = 0; }
  }

  function apply() {
    clamp();
    box.style.transform = "translate(" + st.x + "px," + st.y + "px) scale(" + st.s + ")";
  }

  function zoomAt(ns, cx, cy) {
    ns = Math.min(st.max, Math.max(1, ns));
    var ox = cx - st.sw / 2, oy = cy - st.sh / 2, k = ns / st.s;
    st.x = ox - (ox - st.x) * k;
    st.y = oy - (oy - st.y) * k;
    st.s = ns;
    apply();
  }

  function local(ev) {
    var r = stage.getBoundingClientRect();
    return { x: ev.clientX - r.left, y: ev.clientY - r.top };
  }

  function down(ev) {
    if (ev.target.closest && ev.target.closest(".viewer-bar")) return;
    stage.setPointerCapture(ev.pointerId);
    pts[ev.pointerId] = local(ev);
    var ids = Object.keys(pts);
    if (ids.length === 2) {
      var a = pts[ids[0]], b = pts[ids[1]];
      gesture = { d: Math.hypot(a.x - b.x, a.y - b.y), s: st.s, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
    } else {
      gesture = { moved: 0, px: pts[ev.pointerId].x, py: pts[ev.pointerId].y };
    }
  }

  function move(ev) {
    if (!pts[ev.pointerId]) return;
    var p = local(ev), ids = Object.keys(pts);
    if (ids.length >= 2 && gesture && gesture.d) {
      pts[ev.pointerId] = p;
      var a = pts[ids[0]], b = pts[ids[1]];
      var d = Math.hypot(a.x - b.x, a.y - b.y), mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      st.x += mx - gesture.mx; st.y += my - gesture.my;
      gesture.mx = mx; gesture.my = my;
      zoomAt(gesture.s * d / gesture.d, mx, my);
    } else if (gesture) {
      st.x += p.x - pts[ev.pointerId].x;
      st.y += p.y - pts[ev.pointerId].y;
      gesture.moved += Math.abs(p.x - pts[ev.pointerId].x) + Math.abs(p.y - pts[ev.pointerId].y);
      pts[ev.pointerId] = p;
      apply();
    }
  }

  function up(ev) {
    var p = pts[ev.pointerId];
    var tap = gesture && !gesture.d && gesture.moved < 6 && Object.keys(pts).length === 1;
    delete pts[ev.pointerId];
    if (Object.keys(pts).length < 2 && gesture && gesture.d) gesture = null;
    if (tap && p) {
      var now = Date.now();
      if (now - lastTap < 320) {
        if (st.s > 1.05) { st.s = 1; st.x = 0; st.y = 0; apply(); }
        else zoomAt(Math.min(st.max, 2.5), p.x, p.y);
        lastTap = 0;
      } else {
        lastTap = now;
      }
    }
    if (!Object.keys(pts).length) gesture = null;
  }

  function wheel(ev) {
    ev.preventDefault();
    var p = local(ev), f = Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0018));
    zoomAt(st.s * f, p.x, p.y);
  }

  function keys(ev) {
    if (!root || root.hidden) return;
    if (ev.key === "Escape") close();
    else if (ev.key === "ArrowLeft") show(idx - 1);
    else if (ev.key === "ArrowRight") show(idx + 1);
    else if (ev.key === "+" || ev.key === "=") actions.zin();
    else if (ev.key === "-") actions.zout();
    else if (ev.key === "0") actions.fit();
    else if (ev.key === "Tab") {
      var list = Array.prototype.filter.call(root.querySelectorAll("button"), function (b) { return !b.disabled; });
      var first = list[0], last = list[list.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    }
  }

  function show(i) {
    if (i < 0 || i >= items.length) return;
    idx = i;
    var it = items[i], w = it.w || 1600, h = it.h || 1000;
    st.ar = w / h;
    label.textContent = it.label || it.alt;
    root.setAttribute("aria-label", label.textContent + ", full size");
    img.alt = it.alt || "";
    img.src = it.web || it.full;
    fullImg = null;
    btns.prev.disabled = i === 0;
    btns.next.disabled = i === items.length - 1;
    layout(false);
    var big = new Image();
    big.onload = function () {
      if (idx !== i) return;
      fullImg = big;
      img.src = big.src;
      layout(true);
    };
    big.src = it.full || it.web;
  }

  var pushed = false;

  function open(i, from) {
    if (!root) build();
    opener = from;
    savedY = window.pageYOffset || document.documentElement.scrollTop || 0;
    root.hidden = false;
    document.documentElement.classList.add("viewer-open");
    show(i);
    btns.close.focus();
    if (!pushed && location.hash !== "#viewer") {
      pushed = true;
      location.hash = "viewer";
    }
  }

  window.addEventListener("hashchange", function () {
    if (root && !root.hidden && location.hash !== "#viewer") { pushed = false; hide(); }
  });

  function close() {
    if (!root || root.hidden) return;
    var wasPushed = pushed;
    pushed = false;
    hide();
    if (wasPushed) history.back();
  }

  function hide() {
    if (!root || root.hidden) return;
    root.hidden = true;
    document.documentElement.classList.remove("viewer-open");
    pts = {}; gesture = null;
    window.scrollTo(0, savedY);
    if (opener && opener.focus) opener.focus({ preventScroll: true });
    window.scrollTo(0, savedY);
  }

  return { open: open, close: close, isOpen: function () { return !!root && !root.hidden; } };
  }

  window.NHCViewer = { supported: !!window.PointerEvent, create: create };
})();
