/* Siyaq - expert analysis page: "what happened before the impact".
   Small multiples on ONE time axis (seconds from the impact), synced with the video:
   events, distance to B, time-to-collision, B's sideways position. One crosshair + one tooltip for all rows,
   click to jump the video, a red line at the impact and a green playhead that follows the video. */
(function () {
  var NS = 'http://www.w3.org/2000/svg';
  var COL = {line: '#006c35', ink: '#17211d', muted: '#6b7f73', grid: '#e6ede9', impact: '#d93025', play: '#0b2e1d',
             warnFill: '#fff1cf', warnInk: '#7a5200', dangerFill: '#fbe3e1', dangerInk: '#a12c22', laneFill: '#eef2f0',
             ev: {lane_change: '#1f5c99', sudden_stop: '#b26a00', overtaking: '#7b4fb3', following_distance: '#6b7f73'}};
  var M = {l: 46, r: 14};

  function el(tag, attrs, text) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function median3(a) {
    return a.map(function (v, i) {
      if (v === null || v === undefined) return null;
      var w = [a[i - 1], v, a[i + 1]].filter(function (x) { return x !== null && x !== undefined; }).sort(function (x, y) { return x - y; });
      return w[Math.floor(w.length / 2)];
    });
  }
  function fmt(v, d) { return v === null || v === undefined || isNaN(v) ? '—' : (+v).toFixed(d === undefined ? 1 : d); }

  window.siyaqStory = function (D, video) {
    var box = document.getElementById('va-rows');
    if (!box || !D.series) return;
    var S = D.series, st = D.story || {}, ch = st.chart || {};
    var t = S.t, n = t.length;
    var events = st.events || [];
    var coll = events.filter(function (e) { return e.type === 'collision'; })[0];
    var impact = ch.impact_t != null ? ch.impact_t : (coll ? coll.start_t : null);
    var tooClose = ch.too_close_m || 2.1, danger = ch.ttc_danger_s || 1.6, half = ch.lane_half_width_m || 1.8;
    // older results have no b_lateral_m series: rebuild it from B's per-frame measures
    var lat = S.b_lateral_m || t.map(function (_, i) { var v = (st.lateral || {})[String(i)]; return v === undefined ? null : v; });
    var dist = (S.b_distance_m || []).slice();   // already smoothed by the engine; same numbers as the event cards
    var closing0 = S.b_closing_mps || (S.b_rel_speed_mps || []).map(function (v) { return v === null ? null : -v; });
    // TTC only means something while B is getting closer
    var ttcRaw = (S.b_ttc_s || []).map(function (v, i) { return v !== null && v > 0 && (closing0[i] === null || closing0[i] > 0.2) ? v : null; });
    var ttc = ttcRaw;   // one dot per frame: noisy, so not joined into a line
    var closing = closing0;
    var latS = median3(lat);
    var range = 'impact', hover = null;
    var rel = function (x) { return impact == null ? x : x - impact; };

    function domain() {
      var a = t[0], b = t[n - 1];
      if (range === 'impact' && impact != null) { a = Math.max(a, impact - 5); b = Math.min(b, impact + 1.5); }
      return [a, Math.max(b, a + 0.5)];
    }

    function render() {
      var dom = domain(), rows = box.querySelectorAll('.va-row');
      rows.forEach(function (row, ri) {
        var svg = row.querySelector('svg'), kind = row.dataset.row, last = ri === rows.length - 1;
        var W = Math.max(280, svg.clientWidth || box.clientWidth), H = kind === 'events' ? 0 : 112;
        var lanes = [];
        if (kind === 'events') {
          // one lane per overlapping group of interval events
          events.filter(function (e) { return e.type !== 'collision' && e.type !== 'following_distance'; }).forEach(function (e) {
            var end = Math.max(e.end_t, e.start_t + 0.15), li = 0;
            while (lanes[li] && lanes[li] > e.start_t) li++;
            lanes[li] = end; e._lane = li;
          });
          events.filter(function (e) { return e.type === 'following_distance'; }).forEach(function (e) { e._lane = lanes.length; });
          if (events.some(function (e) { return e.type === 'following_distance'; })) lanes.push(0);
          H = Math.max(1, lanes.length) * 24 + 10;
        }
        var narrow = W < 560;
        var bot = last ? 40 : 6, top = ri === 0 ? 18 : 6;
        H += top + bot - 12;
        svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H); svg.setAttribute('height', H);
        while (svg.firstChild) svg.removeChild(svg.firstChild);
        var x = function (v) { return M.l + (v - dom[0]) / (dom[1] - dom[0]) * (W - M.l - M.r); };
        var y0 = top, y1 = H - bot;
        svg.appendChild(el('rect', {x: M.l, y: y0, width: W - M.l - M.r, height: y1 - y0, fill: '#fff'}));

        var yScale = null, label = null;
        if (kind === 'distance') {
          var dmax = Math.max(4, tooClose * 2, Math.ceil(Math.max.apply(null, dist.filter(function (v, i) { return v !== null && t[i] >= dom[0] && t[i] <= dom[1]; }).concat([0])) + 0.5));
          dmax = Math.min(dmax, 40);
          yScale = function (v) { return y1 - Math.min(v, dmax) / dmax * (y1 - y0); };
          band(0, tooClose, COL.warnFill, narrow ? 'قريب جدًا' : 'أقرب من مسافة الأمان (≈' + fmt(tooClose) + ' م)', COL.warnInk);
          ticks([0, dmax / 2, dmax], function (v) { return fmt(v, v < 10 ? 1 : 0) + ' م'; });
          series(dist);
          if (impact != null) note(impact - 1, dist, function (v) { return 'قبل الاصطدام بثانية: ' + fmt(v) + ' م'; });
        } else if (kind === 'ttc') {
          var cap = 6;
          yScale = function (v) { return y1 - Math.min(v, cap) / cap * (y1 - y0); };
          band(0, danger, COL.dangerFill, narrow ? 'خطر' : 'خطر: أقل من ' + fmt(danger) + ' ث', COL.dangerInk);
          ticks([0, 3, cap], function (v) { return v === cap ? '+' + cap + ' ث' : fmt(v, 0) + ' ث'; });
          var anyT = false;
          ttc.forEach(function (v, i) {
            if (v === null || t[i] < dom[0] || t[i] > dom[1]) return;
            anyT = true;
            svg.appendChild(el('circle', {cx: x(t[i]), cy: yScale(Math.min(v, cap)), r: 3.5, fill: v < danger ? COL.dangerInk : COL.line}));
          });
          if (!anyT) svg.appendChild(el('text', {x: (M.l + W - M.r) / 2, y: (y0 + y1) / 2, 'text-anchor': 'middle', 'class': 'va-st-tick'}, 'المركبة B لا تقترب في هذه المدة'));
          if (impact != null) {
            var best = null;
            t.forEach(function (tt, i) { if (tt >= impact - 1.05 && tt < impact && ttc[i] !== null && (best === null || ttc[i] < ttc[best])) best = i; });
            if (best !== null) dot(t[best], Math.min(ttc[best], cap), 'أقل قيمة في آخر ثانية: ' + fmt(ttc[best]) + ' ث');
          }
        } else if (kind === 'lateral') {
          var lim = 4;
          yScale = function (v) { return (y0 + y1) / 2 - Math.max(-lim, Math.min(lim, v)) / lim * (y1 - y0) / 2; };
          band(-half, half, COL.laneFill, narrow ? 'المسار' : 'مسار صاحب الفيديو', COL.muted);
          svg.appendChild(el('text', {x: M.l - 6, y: y0 + 10, 'text-anchor': 'end', 'class': 'va-st-tick'}, 'يمين'));
          svg.appendChild(el('text', {x: M.l - 6, y: y1 - 2, 'text-anchor': 'end', 'class': 'va-st-tick'}, 'يسار'));
          series(latS);
        } else if (kind === 'events') {
          events.filter(function (e) { return e.type !== 'collision'; }).forEach(function (e) {
            var a = Math.max(dom[0], e.start_t), b = Math.min(dom[1], Math.max(e.end_t, e.start_t + 0.15));
            if (b < dom[0] || a > dom[1]) return;
            var yy = y0 + 4 + e._lane * 24, c = COL.ev[e.type] || COL.muted;
            if (e.type === 'following_distance') {
              svg.appendChild(el('circle', {cx: x(e.start_t), cy: yy + 9, r: 5, fill: c, stroke: '#fff', 'stroke-width': 2}));
            } else {
              svg.appendChild(el('rect', {x: x(a), y: yy + 2, width: Math.max(4, x(b) - x(a)), height: 14, rx: 4, fill: c}));
            }
            var name = (st.labels || {})[e.type] || e.type, who = e.vehicle === 'B' ? ' · B' : (e.vehicle === 'A' ? ' · صاحب الفيديو' : '');
            var isPoint = e.type === 'following_distance';
            var tx = el('text', {y: yy + 13, 'class': 'va-st-ev', direction: 'rtl'}, name + who);
            svg.appendChild(tx);
            var bw = x(b) - x(a), tw = tx.getComputedTextLength ? tx.getComputedTextLength() : 80;
            if (!isPoint && bw > tw + 12) {
              // inside the bar, white on the event colour
              tx.setAttribute('x', x(a) + bw / 2); tx.setAttribute('text-anchor', 'middle'); tx.style.fill = '#fff';
            } else {
              // beside the mark: right of it when there is room, otherwise left of it
              // (RTL text: anchor "end" is the left edge of the label, "start" its right edge)
              var after = (isPoint ? x(e.start_t) + 9 : x(b) + 6);
              if (after + tw < W - M.r) { tx.setAttribute('x', after); tx.setAttribute('text-anchor', 'end'); }
              else { tx.setAttribute('x', (isPoint ? x(e.start_t) : x(a)) - 8); tx.setAttribute('text-anchor', 'start'); }
            }
          });
          if (!events.some(function (e) { return e.type !== 'collision'; }))
            svg.appendChild(el('text', {x: (M.l + W - M.r) / 2, y: (y0 + y1) / 2 + 4, 'text-anchor': 'middle', 'class': 'va-st-tick'}, 'لا أحداث غير الاصطدام'));
        }

        // impact line, playhead, crosshair
        if (impact != null && impact >= dom[0] && impact <= dom[1]) {
          svg.appendChild(el('line', {x1: x(impact), x2: x(impact), y1: y0 - (ri === 0 ? 4 : 0), y2: y1, stroke: COL.impact, 'stroke-width': 2}));
          if (ri === 0) svg.appendChild(el('text', {x: x(impact), y: 11, 'text-anchor': 'middle', 'class': 'va-st-impact'}, 'الاصطدام'));
        }
        svg.appendChild(el('line', {x1: 0, x2: 0, y1: y0, y2: y1, stroke: COL.play, 'stroke-width': 1.5, 'class': 'va-st-play', visibility: 'hidden'}));
        svg.appendChild(el('line', {x1: 0, x2: 0, y1: y0, y2: y1, stroke: COL.muted, 'stroke-width': 1, 'class': 'va-st-cross', visibility: 'hidden'}));
        if (last) {
          var step = (dom[1] - dom[0]) > 12 ? 5 : 1, s0 = Math.ceil(rel(dom[0]) / step) * step;
          for (var s = s0; s <= rel(dom[1]) + 1e-6; s += step) {
            var xv = x(impact == null ? s : s + impact);
            svg.appendChild(el('line', {x1: xv, x2: xv, y1: y1, y2: y1 + 4, stroke: COL.muted}));
            svg.appendChild(el('text', {x: xv, y: y1 + 16, 'text-anchor': 'middle', 'class': 'va-st-tick', direction: 'ltr', 'unicode-bidi': 'embed'}, s === 0 && impact != null ? '0' : (s > 0 ? '+' : '\u2212') + Math.abs(s)));
          }
          svg.appendChild(el('text', {x: (M.l + W - M.r) / 2, y: y1 + 32, 'text-anchor': 'middle', 'class': 'va-st-tick', direction: 'rtl'}, impact == null ? 'الوقت (ث)' : 'الثواني قبل الاصطدام (−) وبعده (+)'));
        }
        svg._x = x; svg._dom = dom;

        function band(a, b, fill, text, ink) {
          var ya = yScale(b), yb = yScale(a);
          svg.appendChild(el('rect', {x: M.l, y: ya, width: W - M.l - M.r, height: Math.max(0, yb - ya), fill: fill}));
          svg.appendChild(el('text', {x: W - M.r - 6, y: ya + 13, 'text-anchor': 'start', 'class': 'va-st-band', fill: ink, direction: 'rtl'}, text));
        }
        function ticks(vals, f) {
          vals.forEach(function (v) {
            var yy = yScale(v);
            svg.appendChild(el('line', {x1: M.l, x2: W - M.r, y1: yy, y2: yy, stroke: COL.grid}));
            svg.appendChild(el('text', {x: M.l - 6, y: yy + 4, 'text-anchor': 'end', 'class': 'va-st-tick', direction: 'ltr', 'unicode-bidi': 'embed'}, f(v)));
          });
        }
        function series(vals) {
          var d = '', pen = false, any = false;
          vals.forEach(function (v, i) {
            if (v === null || t[i] < dom[0] || t[i] > dom[1]) { pen = false; return; }
            d += (pen ? 'L' : 'M') + x(t[i]).toFixed(1) + ' ' + yScale(v).toFixed(1); pen = true; any = true;
          });
          if (any) svg.appendChild(el('path', {d: d, fill: 'none', stroke: COL.line, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}));
          else svg.appendChild(el('text', {x: (M.l + W - M.r) / 2, y: (y0 + y1) / 2, 'text-anchor': 'middle', 'class': 'va-st-tick'}, 'المركبة B غير ظاهرة في هذه المدة'));
        }
        function dot(tt, v, text) {
          if (tt < dom[0] || tt > dom[1]) return;
          var cx = x(tt), cy = yScale(v);
          svg.appendChild(el('circle', {cx: cx, cy: cy, r: 7, fill: 'none', stroke: COL.ink, 'stroke-width': 1.5}));
          if (narrow) return;   // the tooltip and the table carry the value on small screens
          svg.appendChild(el('text', {x: M.l + 8, y: y0 + 13, 'text-anchor': 'end', 'class': 'va-st-note', direction: 'rtl'}, '◯ ' + text));
        }
        function note(tt, vals, f) {
          var i = nearest(tt);
          if (i !== null && vals[i] !== null && Math.abs(t[i] - tt) < 0.3) dot(t[i], vals[i], f(vals[i]));
        }
      });
      table();
      sync();
    }

    function nearest(tt) {
      var best = null;
      t.forEach(function (v, i) { if (best === null || Math.abs(v - tt) < Math.abs(t[best] - tt)) best = i; });
      return best;
    }

    function sync() {
      box.querySelectorAll('.va-row svg').forEach(function (svg) {
        var p = svg.querySelector('.va-st-play'), c = svg.querySelector('.va-st-cross'), x = svg._x, dom = svg._dom;
        if (!x) return;
        var ct = video ? video.currentTime : null;
        if (p) { if (ct !== null && ct >= dom[0] && ct <= dom[1]) { p.setAttribute('x1', x(ct)); p.setAttribute('x2', x(ct)); p.setAttribute('visibility', 'visible'); } else p.setAttribute('visibility', 'hidden'); }
        if (c) { if (hover !== null) { c.setAttribute('x1', x(t[hover])); c.setAttribute('x2', x(t[hover])); c.setAttribute('visibility', 'visible'); } else c.setAttribute('visibility', 'hidden'); }
      });
    }

    var tip = document.getElementById('va-tip');
    function showTip(i, clientX, clientY) {
      hover = i; sync();
      if (!tip) return;
      while (tip.firstChild) tip.removeChild(tip.firstChild);
      var head = document.createElement('div'); head.className = 'va-tip-h';
      var r = rel(t[i]);
      head.textContent = impact == null ? fmt(t[i]) + ' ث' : (Math.abs(r) < 0.05 ? 'لحظة الاصطدام' : (r < 0 ? 'قبل الاصطدام بـ ' + fmt(-r) + ' ث' : 'بعد الاصطدام بـ ' + fmt(r) + ' ث'));
      tip.appendChild(head);
      [['المسافة إلى B', dist[i], 'م'], ['الوقت المتبقي للاصطدام', ttc[i], 'ث'],
       ['سرعة الاقتراب', closing[i] == null ? null : closing[i] * 3.6, 'كم/س'],
       ['مكان B', latS[i] == null ? null : Math.abs(latS[i]), latS[i] == null ? '' : (Math.abs(latS[i]) <= half ? 'م من منتصف المسار' : (latS[i] > 0 ? 'م يمينًا' : 'م يسارًا'))]
      ].forEach(function (r) {
        var row = document.createElement('div'); row.className = 'va-tip-r';
        var v = document.createElement('b'); v.textContent = fmt(r[1]) + (r[1] == null ? '' : ' ' + r[2]); v.dir = 'auto';
        var k = document.createElement('span'); k.textContent = r[0];
        row.appendChild(k); row.appendChild(v); tip.appendChild(row);
      });
      tip.hidden = false;
      var host = box.parentElement.getBoundingClientRect(), tw = tip.offsetWidth;
      var left = clientX - host.left + 14; if (left + tw > host.width - 8) left = clientX - host.left - tw - 14;
      tip.style.left = Math.max(8, left) + 'px'; tip.style.top = (clientY - host.top + 12) + 'px';
    }
    function hideTip() { hover = null; if (tip) tip.hidden = true; sync(); }
    function timeAt(ev) {
      var svg = box.querySelector('.va-row svg'), r = svg.getBoundingClientRect(), dom = svg._dom;
      var W = r.width, frac = (ev.clientX - r.left - M.l * W / svg.viewBox.baseVal.width) / ((W - (M.l + M.r) * W / svg.viewBox.baseVal.width));
      return dom[0] + Math.max(0, Math.min(1, frac)) * (dom[1] - dom[0]);
    }
    box.addEventListener('pointermove', function (ev) { showTip(nearest(timeAt(ev)), ev.clientX, ev.clientY); });
    box.addEventListener('pointerleave', hideTip);
    box.addEventListener('click', function (ev) {
      if (!video) return;
      var go = function () { video.currentTime = timeAt(ev); video.pause(); };
      if (video.readyState >= 1) go(); else video.addEventListener('loadedmetadata', go, {once: true});
    });
    box.tabIndex = 0;
    box.setAttribute('aria-label', 'الرسوم على خط الزمن: استخدمي السهمين يمين ويسار للتنقل');
    box.addEventListener('keydown', function (ev) {
      if (ev.key !== 'ArrowLeft' && ev.key !== 'ArrowRight') return;
      ev.preventDefault();
      var dom = domain(), i = hover === null ? nearest(impact != null ? impact : dom[0]) : hover + (ev.key === 'ArrowRight' ? 1 : -1);
      i = Math.max(0, Math.min(n - 1, i));
      var svg = box.querySelector('.va-row svg'), r = svg.getBoundingClientRect(), x = svg._x(t[i]) * r.width / svg.viewBox.baseVal.width;
      showTip(i, r.left + x, r.top + 40);
    });
    box.addEventListener('blur', hideTip);

    function table() {
      var tb = document.getElementById('va-values');
      if (!tb || tb.dataset.done) return;
      tb.dataset.done = '1';
      var head = tb.createTHead().insertRow();
      ['الوقت', 'المسافة إلى B (م)', 'الوقت المتبقي للاصطدام (ث)', 'سرعة الاقتراب (كم/س)', 'مكان B من منتصف المسار (م، + يمين)'].forEach(function (h) {
        var th = document.createElement('th'); th.textContent = h; head.appendChild(th);
      });
      var body = tb.createTBody(), lastT = -1e9;
      t.forEach(function (tt, i) {
        if (tt - lastT < 0.49) return;
        lastT = tt;
        var r = body.insertRow(), rv = rel(tt);
        [impact == null ? fmt(tt) : (Math.abs(rv) < 0.05 ? 'الاصطدام' : fmt(rv)), fmt(dist[i]), fmt(ttc[i]), closing[i] == null ? '—' : fmt(closing[i] * 3.6), fmt(latS[i])].forEach(function (v) {
          var td = r.insertCell(); td.textContent = v; td.dir = 'ltr';
        });
      });
    }

    document.querySelectorAll('.va-range button').forEach(function (b) {
      b.addEventListener('click', function () {
        range = b.dataset.range;
        document.querySelectorAll('.va-range button').forEach(function (o) { o.classList.toggle('is-on', o === b); o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); });
        render();
      });
    });
    if (impact == null) { var g = document.querySelector('.va-range'); if (g) g.hidden = true; range = 'all'; }
    if (video) video.addEventListener('timeupdate', sync);
    (function loop() { sync(); requestAnimationFrame(loop); })();
    var lastW = 0;
    function onResize() { if (Math.abs(box.clientWidth - lastW) > 2) { lastW = box.clientWidth; render(); } }
    if ('ResizeObserver' in window) new ResizeObserver(onResize).observe(box); else window.addEventListener('resize', onResize);
    lastW = box.clientWidth;
    render();
  };
})();
