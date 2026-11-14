// Renders <canvas data-chart='{...}'> with Chart.js (local vendor file -> CDN) and falls back to a
// small built-in canvas renderer so charts still work with no Chart.js and no internet.
(function () {
  'use strict';
  var PALETTE = ['#6366f1', '#22c55e', '#f59e0b', '#ec4899', '#06b6d4', '#a855f7', '#ef4444', '#84cc16', '#f97316', '#14b8a6'];
  var CDN = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js';
  var instances = [];
  var css = function (v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); };
  var short = function (s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

  function datasetsOf(cfg) {
    return cfg.datasets || [{ label: cfg.label || '', values: cfg.values }];
  }

  function chartJsConfig(cfg) {
    var doughnut = cfg.type === 'doughnut', text = css('--muted'), grid = css('--border');
    var sets = datasetsOf(cfg).map(function (d, i) {
      return {
        label: d.label, data: d.values,
        backgroundColor: doughnut ? PALETTE : PALETTE[i % PALETTE.length],
        borderColor: doughnut ? css('--surface') : undefined, borderWidth: doughnut ? 2 : 0, borderRadius: doughnut ? 0 : 6
      };
    });
    var opts = { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: doughnut || sets.length > 1, position: doughnut ? 'bottom' : 'top', labels: { color: text, boxWidth: 12 } } } };
    if (!doughnut) {
      opts.indexAxis = cfg.horizontal ? 'y' : 'x';
      var valueAxis = { beginAtZero: true, max: cfg.max, grid: { color: grid }, ticks: { color: text, precision: 0 } };
      var labelAxis = { grid: { display: false }, ticks: { color: text } };
      opts.scales = cfg.horizontal ? { x: valueAxis, y: labelAxis } : { y: valueAxis, x: labelAxis };
    } else { opts.cutout = '62%'; }
    return { type: doughnut ? 'doughnut' : 'bar', data: { labels: cfg.labels, datasets: sets }, options: opts };
  }

  // ---- minimal fallback renderer (bar / horizontal bar / doughnut) ----
  function fallback(canvas, cfg) {
    var box = canvas.parentElement, dpr = window.devicePixelRatio || 1;
    var w = box.clientWidth, h = box.clientHeight || 260;
    canvas.width = w * dpr; canvas.height = h * dpr; canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
    var ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, w, h);
    ctx.font = '12px system-ui, sans-serif'; ctx.textBaseline = 'middle';
    var text = css('--muted'), grid = css('--border'), sets = datasetsOf(cfg), labels = cfg.labels || [];

    if (cfg.type === 'doughnut') {
      var vals = sets[0].values, total = vals.reduce(function (a, b) { return a + b; }, 0) || 1;
      var r = Math.min(w * 0.35, h / 2 - 8), cx = Math.min(r + 12, w / 3), cy = h / 2, a0 = -Math.PI / 2;
      vals.forEach(function (v, i) {
        var a1 = a0 + (v / total) * Math.PI * 2;
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, r, a0, a1); ctx.closePath();
        ctx.fillStyle = PALETTE[i % PALETTE.length]; ctx.fill(); a0 = a1;
      });
      ctx.beginPath(); ctx.arc(cx, cy, r * 0.6, 0, Math.PI * 2); ctx.fillStyle = css('--surface'); ctx.fill();
      labels.forEach(function (l, i) {
        var y = 20 + i * 20; if (y > h - 8) return;
        ctx.fillStyle = PALETTE[i % PALETTE.length]; ctx.fillRect(cx * 2 + 24, y - 5, 10, 10);
        ctx.fillStyle = text; ctx.textAlign = 'left'; ctx.fillText(short(l, 18) + '  (' + vals[i] + ')', cx * 2 + 40, y);
      });
      return;
    }
    var max = cfg.max || Math.max.apply(null, [1].concat.apply([], sets.map(function (s) { return s.values; }))) * 1.1;
    var n = labels.length, horizontal = !!cfg.horizontal;
    if (horizontal) {
      var left = Math.min(150, w * 0.35), rowH = (h - 10) / Math.max(n, 1), bh = Math.min(22, rowH * 0.6);
      labels.forEach(function (l, i) {
        var y = 5 + rowH * i + rowH / 2; ctx.fillStyle = text; ctx.textAlign = 'right'; ctx.fillText(short(l, 22), left - 8, y);
        sets.forEach(function (s, k) {
          var bw = (s.values[i] / max) * (w - left - 40);
          ctx.fillStyle = PALETTE[k % PALETTE.length]; ctx.fillRect(left, y - bh / 2 + k * 0, Math.max(bw, 1), bh);
          ctx.fillStyle = text; ctx.textAlign = 'left'; ctx.fillText(s.values[i], left + bw + 6, y);
        });
      });
    } else {
      var bottom = 34, top = 14, colW = (w - 40) / Math.max(n, 1), inner = h - bottom - top;
      ctx.strokeStyle = grid; ctx.beginPath(); ctx.moveTo(30, top + inner); ctx.lineTo(w - 6, top + inner); ctx.stroke();
      labels.forEach(function (l, i) {
        var gw = colW * 0.7 / sets.length;
        sets.forEach(function (s, k) {
          var bh2 = (s.values[i] / max) * inner, x = 34 + colW * i + colW * 0.15 + gw * k;
          ctx.fillStyle = PALETTE[k % PALETTE.length]; ctx.fillRect(x, top + inner - bh2, gw - 2, bh2);
          ctx.fillStyle = text; ctx.textAlign = 'center'; ctx.fillText(s.values[i], x + gw / 2, top + inner - bh2 - 8);
        });
        ctx.fillStyle = text; ctx.textAlign = 'center'; ctx.fillText(short(l, Math.max(6, Math.floor(colW / 7))), 34 + colW * i + colW / 2, h - 16);
      });
      if (sets.length > 1) sets.forEach(function (s, k) {
        ctx.fillStyle = PALETTE[k]; ctx.fillRect(w - 130, 4 + k * 14, 8, 8); ctx.fillStyle = text; ctx.textAlign = 'left'; ctx.fillText(s.label, w - 118, 8 + k * 14);
      });
    }
  }

  function render(useChartJs) {
    instances.forEach(function (c) { c.destroy(); }); instances = [];
    Array.prototype.forEach.call(document.querySelectorAll('canvas[data-chart]'), function (canvas) {
      var cfg; try { cfg = JSON.parse(canvas.getAttribute('data-chart')); } catch (e) { return; }
      if (useChartJs) {
        if (window.Chart.defaults) window.Chart.defaults.font.family = 'system-ui, sans-serif';
        instances.push(new window.Chart(canvas, chartJsConfig(cfg)));
      } else { fallback(canvas, cfg); }
    });
  }

  function start() {
    if (!document.querySelector('canvas[data-chart]')) return;
    var mode = null;
    var go = function (m) { mode = m; render(m); };
    if (window.Chart) { go(true); }
    else {
      var s = document.createElement('script'); s.src = CDN;
      s.onload = function () { go(!!window.Chart); }; s.onerror = function () { go(false); };
      document.head.appendChild(s);
    }
    document.addEventListener('themechange', function () { if (mode !== null) render(mode); });
    window.addEventListener('resize', function () { if (mode === false) render(false); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
