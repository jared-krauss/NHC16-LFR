(function () {
  "use strict";
  var B = window.BIB;
  if (!B) return;
  var root = document.documentElement;
  var VIEWS = { "works-cited": "works", "bibliography": "all" };

  function parse() {
    var h = decodeURIComponent((location.hash || "").replace(/^#/, ""));
    if (!h || h === "works-cited") return { view: "works", group: "all", entry: "" };
    if (h === "bibliography") return { view: "all", group: "all", entry: "" };
    if (B.groups.indexOf(h) >= 0) return { view: "all", group: h, entry: "" };
    if (B.ids.indexOf(h) >= 0) return { view: B.cited.indexOf(h) >= 0 ? "works" : "all", group: "all", entry: h };
    return { view: "works", group: "all", entry: "" };
  }

  function apply() {
    var s = parse();
    root.setAttribute("data-bib-view", s.view);
    root.setAttribute("data-bib-group", s.group);
    return s;
  }

  function refresh(s) {
    var key = s.view === "works" ? "works-cited" : (s.group === "all" ? "bibliography" : s.group);
    var n = 0;
    Array.prototype.forEach.call(document.querySelectorAll(".bib-entry"), function (li) {
      var on = (s.view === "all" || li.hasAttribute("data-cited")) && (s.group === "all" || li.getAttribute("data-group") === s.group);
      if (on) n++;
    });
    Array.prototype.forEach.call(document.querySelectorAll(".bib-tabs a"), function (a) {
      var tab = a.getAttribute("href").slice(1);
      if ((tab === "works-cited") === (s.view === "works")) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
    Array.prototype.forEach.call(document.querySelectorAll(".bib-filters a"), function (a) {
      var f = a.getAttribute("href").slice(1);
      if (f === key || (f === "bibliography" && s.group === "all")) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
    var c = document.querySelector(".bib-count");
    if (c) c.textContent = n + (n === 1 ? " entry" : " entries") + (s.view === "works" ? ", works cited in the talk" : "");
  }

  var state = apply();

  function onChange() {
    var s = apply();
    refresh(s);
    if (s.entry) {
      var el = document.getElementById(s.entry);
      if (el) el.scrollIntoView({ block: "center" });
    }
  }

  window.addEventListener("hashchange", onChange);
  document.addEventListener("DOMContentLoaded", function () {
    refresh(state);
    if (state.entry) {
      var el = document.getElementById(state.entry);
      if (el) setTimeout(function () { el.scrollIntoView({ block: "center" }); }, 0);
    }
  });
})();
