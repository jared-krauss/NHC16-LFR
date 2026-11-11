(function () {
  "use strict";
  var btn = document.getElementById("paper-menu-btn");
  var menu = document.getElementById("paper-menu");
  var data = {};
  try { data = JSON.parse(document.getElementById("paper-figures").textContent) || {}; } catch (e) { data = {}; }

  var numbers = Object.keys(data).map(Number).sort(function (a, b) { return a - b; });
  var viewer = null;
  if (window.NHCViewer && NHCViewer.supported && numbers.length) {
    viewer = NHCViewer.create(numbers.map(function (n) { return data[n]; }));
  }

  function openFig(n, from) {
    var i = numbers.indexOf(n);
    if (!viewer || i < 0) return false;
    viewer.open(i, from);
    return true;
  }

  document.addEventListener("click", function (ev) {
    var a = ev.target.closest ? ev.target.closest("a[data-fig]") : null;
    if (!a || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
    var n = +a.getAttribute("data-fig");
    if (!viewer || numbers.indexOf(n) < 0) return;
    ev.preventDefault();
    var inMenu = menu && menu.contains(a);
    if (inMenu) closeMenu(false);
    openFig(n, inMenu ? btn : a);
  });

  if (!btn || !menu) return;
  btn.hidden = false;

  function focusables() {
    return Array.prototype.filter.call(menu.querySelectorAll("a[href], button"), function (e) { return !e.disabled; });
  }

  function openMenu() {
    menu.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    var list = focusables();
    var first = menu.querySelector(".pm-list a") || list[0];
    if (first) first.focus({ preventScroll: true });
  }

  function closeMenu(refocus) {
    if (menu.hidden) return;
    menu.hidden = true;
    btn.setAttribute("aria-expanded", "false");
    if (refocus !== false) btn.focus({ preventScroll: true });
  }

  btn.addEventListener("click", function () { if (menu.hidden) openMenu(); else closeMenu(true); });
  menu.querySelector(".paper-menu-close").addEventListener("click", function () { closeMenu(true); });

  menu.addEventListener("click", function (ev) {
    var a = ev.target.closest ? ev.target.closest("a[data-jump]") : null;
    if (a) closeMenu(false);
  });

  document.addEventListener("pointerdown", function (ev) {
    if (menu.hidden || menu.contains(ev.target) || btn.contains(ev.target)) return;
    closeMenu(false);
  });

  document.addEventListener("keydown", function (ev) {
    if (menu.hidden || (viewer && viewer.isOpen())) return;
    if (ev.key === "Escape") {
      ev.preventDefault();
      closeMenu(true);
    } else if (ev.key === "Tab") {
      var list = focusables(), first = list[0], last = list[list.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    }
  });
})();
