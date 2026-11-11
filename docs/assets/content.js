(function () {
  "use strict";
  var P = window.Plotly;
  if (!P) return;
  var CONFIG = { scrollZoom: false, displayModeBar: false, responsive: true, doubleClick: false };

  function lockLayout(layout) {
    var l = layout || {};
    l.dragmode = false;
    var hasX = false, hasY = false;
    Object.keys(l).forEach(function (k) {
      if (/^xaxis\d*$/.test(k)) { l[k] = Object.assign({}, l[k], { fixedrange: true }); hasX = true; }
      if (/^yaxis\d*$/.test(k)) { l[k] = Object.assign({}, l[k], { fixedrange: true }); hasY = true; }
    });
    if (!hasX) l.xaxis = { fixedrange: true };
    if (!hasY) l.yaxis = { fixedrange: true };
    return l;
  }

  function wrap(name) {
    var orig = P[name];
    if (typeof orig !== "function") return;
    P[name] = function (gd, data, layout, config) {
      if (data && !Array.isArray(data) && typeof data === "object" && (data.data || data.layout)) {
        data.layout = lockLayout(data.layout);
        data.config = Object.assign({}, data.config, CONFIG);
        return orig.call(P, gd, data);
      }
      return orig.call(P, gd, data, lockLayout(layout), Object.assign({}, config, CONFIG));
    };
  }

  wrap("newPlot");
  wrap("react");
})();
