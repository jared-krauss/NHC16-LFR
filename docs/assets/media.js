(function () {
  "use strict";
  var links = Array.prototype.slice.call(document.querySelectorAll("a.fig-image"));
  if (!links.length || !window.NHCViewer || !NHCViewer.supported) return;

  var items = links.map(function (a) {
    var img = a.querySelector("img"), card = a.closest("article");
    var head = card ? card.querySelector(".card-title") : null;
    var alt = img ? img.alt : "";
    return {
      label: head ? head.textContent.replace(/\s+/g, " ").trim().replace(/^(Fig\. \d+) /, "$1: ") : alt,
      alt: alt,
      web: a.dataset.web || (img ? img.src : ""),
      full: a.getAttribute("href"),
      w: +a.dataset.w || 1600,
      h: +a.dataset.h || 1000
    };
  });
  var viewer = NHCViewer.create(items);

  links.forEach(function (a, i) {
    a.addEventListener("click", function (ev) {
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
      ev.preventDefault();
      viewer.open(i, a);
    });
  });
})();
