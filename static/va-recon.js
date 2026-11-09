/* Siyaq - expert analysis page: "reconstruction of the accident".
   A top-down view of where Vehicle B is relative to the recording car (A), driven by the video time,
   a "now" panel in plain words, a scrubber, and the accident steps written as sentences. */
(function () {
  var NS = 'http://www.w3.org/2000/svg';
  var C = {road: '#3b4541', paint: '#f4f4f0', faint: '#8d9893', a: '#0b2e1d', b: '#d93025', zone: '#f6c34a', ink: '#17211d'};
  var W = 240, H = 340, CX = 120, FRONT = 300, CAR_W = 1.8, CAR_L = 4.5;
  // distances are measured from the dashcam (behind the windscreen); its front bumper is about CAM metres ahead of it
  var CAM = 1.6;

  function el(tag, attrs, text) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function fmt(v, d) { return v === null || v === undefined || isNaN(v) ? '—' : (+v).toFixed(d === undefined ? 1 : d); }
  function setText(id, v) { var n = document.getElementById(id); if (n) n.textContent = v; }

  window.siyaqRecon = function (D, video) {
    var svg = document.getElementById('va-road');
    if (!svg || !D.series) return;
    var S = D.series, st = D.story || {}, ch = st.chart || {}, t = S.t, n = t.length;
    var events = (st.events || []).slice().sort(function (a, b) { return a.start_t - b.start_t; });
    var coll = events.filter(function (e) { return e.type === 'collision'; })[0];
    var impact = ch.impact_t != null ? ch.impact_t : (coll ? coll.start_t : null);
    var tooClose = ch.too_close_m || 2.1, half = ch.lane_half_width_m || 1.8;
    var dist = S.b_distance_m || [];
    var lat = S.b_lateral_m || t.map(function (_, i) { var v = (st.lateral || {})[String(i)]; return v === undefined ? null : v; });
    var closing = S.b_closing_mps || (S.b_rel_speed_mps || []).map(function (v) { return v === null ? null : -v; });
    var labels = st.labels || {}, lanes = st.lanes || {};

    // B's position from above: forward distance z (to B's rear) and sideways x (+ = right)
    var pos = t.map(function (_, i) {
      var d = dist[i], x = lat[i];
      if (d === null || d === undefined || x === null || x === undefined) return null;
      return {x: x, z: Math.sqrt(Math.max(0.25, d * d - x * x)), d: d};
    });
    var zmax = Math.max.apply(null, pos.filter(Boolean).map(function (p) { return p.z; }).concat([6]));
    var span = Math.min(30, Math.max(12, zmax + CAR_L + 2));
    var FRONT_PX = FRONT;
    var s = Math.min(20, (FRONT - 18) / span);               // pixels per metre, the same both ways
    var X = function (m) { return CX + m * s; }, Y = function (m) { return FRONT - m * s; };

    // ---- static road
    function road() {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      svg.appendChild(el('rect', {x: 0, y: 0, width: W, height: H, fill: '#e9eeeb', rx: 12}));
      var rw = 3 * half * 2;
      svg.appendChild(el('rect', {x: X(-rw / 2), y: 0, width: rw * s, height: H, fill: C.road}));
      [[-3 * half, 'Solid'], [3 * half, 'Solid'], [-half, lanes.left_line], [half, lanes.right_line]].forEach(function (l) {
        var type = l[1], a = {x1: X(l[0]), x2: X(l[0]), y1: 0, y2: H, 'stroke-width': 2};
        if (type === 'Solid') { a.stroke = C.paint; }
        else if (type === 'Dashed') { a.stroke = C.paint; a['stroke-dasharray'] = (3 * s) + ' ' + (6 * s); }
        else { a.stroke = C.faint; a['stroke-dasharray'] = '4 6'; a.opacity = 0.7; }
        svg.appendChild(el('line', a));
      });
      // the safe-distance zone in front of A
      if (tooClose > CAM) svg.appendChild(el('rect', {x: X(-half) + 1, y: Y(tooClose), width: (2 * half) * s - 2, height: (tooClose - CAM) * s, fill: C.zone, opacity: 0.55}));
      // A: the recording car; the dashcam (z = 0) sits behind the windscreen, the bumper is CAM metres ahead
      car(0, CAM - CAR_L, C.a, 'A');
      svg.appendChild(el('circle', {cx: X(0), cy: Y(0), r: 3.5, fill: '#fff', stroke: C.a, 'stroke-width': 1.5}));
      svg.appendChild(el('g', {id: 'va-road-live'}));
    }
    function car(x, zRear, fill, letter, parent) {
      var g = el('g', {});
      g.appendChild(el('rect', {x: X(x - CAR_W / 2), y: Y(zRear + CAR_L), width: CAR_W * s, height: CAR_L * s, rx: 0.5 * s, fill: fill}));
      g.appendChild(el('rect', {x: X(x - CAR_W / 2) + 0.25 * s, y: Y(zRear + CAR_L) + 0.9 * s, width: (CAR_W - 0.5) * s, height: 0.8 * s, rx: 0.2 * s, fill: '#ffffff', opacity: 0.35}));
      g.appendChild(el('text', {x: X(x), y: Y(zRear + CAR_L / 2) + 5, 'text-anchor': 'middle', 'class': 'va-road-letter'}, letter));
      (parent || svg).appendChild(g);
    }

    // ---- live layer for time tt
    function nearest(tt) {
      var best = 0;
      for (var i = 1; i < n; i++) if (Math.abs(t[i] - tt) < Math.abs(t[best] - tt)) best = i;
      return best;
    }
    function lastSeen(i) {
      for (var k = i; k >= 0 && i - k <= 3; k--) if (pos[k]) return k;
      return null;
    }
    function draw(tt) {
      var live = svg.querySelector('#va-road-live'); if (!live) return;
      while (live.firstChild) live.removeChild(live.firstChild);
      var i = nearest(tt), k = lastSeen(i);
      // B's path over the last 2 s
      for (var j = Math.max(0, i - 20); j < i; j++) {
        if (!pos[j]) continue;
        live.appendChild(el('circle', {cx: X(pos[j].x), cy: Y(pos[j].z + CAR_L / 2), r: 2.2, fill: C.b, opacity: 0.15 + 0.5 * (j - i + 20) / 20}));
      }
      if (k !== null) {
        var p = pos[k];
        if (Y(p.z + CAR_L) > -40) {
          car(p.x, Math.max(p.z, CAM), C.b, 'B', live);
          // distance between A's front and B's rear
          var mx = X(Math.max(-half - 2.4, Math.min(half + 2.4, p.x))) + (p.x >= 0 ? -CAR_W * s / 2 - 10 : CAR_W * s / 2 + 10);
          live.appendChild(el('line', {x1: mx, x2: mx, y1: Y(0), y2: Y(p.z), stroke: '#ffffff', 'stroke-width': 1.5}));
          live.appendChild(el('line', {x1: mx - 4, x2: mx + 4, y1: Y(0), y2: Y(0), stroke: '#ffffff', 'stroke-width': 1.5}));
          live.appendChild(el('line', {x1: mx - 4, x2: mx + 4, y1: Y(p.z), y2: Y(p.z), stroke: '#ffffff', 'stroke-width': 1.5}));
          var ly = Math.min((Y(0) + Y(p.z)) / 2, Y(0) - 14), lx = Math.max(24, Math.min(W - 24, mx));
          live.appendChild(el('rect', {x: lx - 22, y: ly - 10, width: 44, height: 20, rx: 6, fill: '#ffffff', stroke: C.a, 'stroke-width': 1}));
          live.appendChild(el('text', {x: lx, y: ly + 5, 'text-anchor': 'middle', 'class': 'va-road-dist', direction: 'rtl'}, fmt(p.d) + ' م'));
        }
      }
      if (impact != null && Math.abs(tt - impact) < 0.16 && k !== null) {
        var cx = X(pos[k].x / 2), cy = Y(Math.max(CAM, Math.min(pos[k].z, CAM + 0.4)));
        var star = '';
        for (var a = 0; a < 16; a++) { var r = a % 2 ? 7 : 16, an = a * Math.PI / 8; star += (a ? 'L' : 'M') + (cx + r * Math.cos(an)).toFixed(1) + ' ' + (cy + r * Math.sin(an)).toFixed(1); }
        live.appendChild(el('path', {d: star + 'Z', fill: '#ffcf33', stroke: C.b, 'stroke-width': 2}));
      }
      facts(i, k, tt);
      steps(tt);
    }

    function when(tt) {
      if (impact == null) return fmt(tt) + ' ث من بداية الفيديو';
      var r = tt - impact;
      if (Math.abs(r) < 0.08) return 'لحظة الاصطدام';
      return r < 0 ? 'قبل الاصطدام بـ ' + fmt(-r) + ' ث' : 'بعد الاصطدام بـ ' + fmt(r) + ' ث';
    }
    function facts(i, k, tt) {
      setText('va-now-time', when(tt));
      var distEl = document.getElementById('va-now-dist');
      if (k === null) {
        setText('va-now-dist', '—'); setText('va-now-side', 'المركبة B غير ظاهرة في هذه اللحظة'); setText('va-now-move', '—');
        if (distEl) distEl.className = '';
      } else {
        var p = pos[k], near = p.d < tooClose;
        setText('va-now-dist', fmt(p.d) + ' م' + (near ? ' · أقرب من مسافة الأمان' : ''));
        if (distEl) distEl.className = near ? 'is-warn' : '';
        setText('va-now-side', Math.abs(p.x) <= half * 0.6 ? 'أمام صاحب الفيديو في المسار نفسه'
          : Math.abs(p.x) <= half + 0.4 ? (p.x > 0 ? 'تدخل مسار صاحب الفيديو من اليمين' : 'تدخل مسار صاحب الفيديو من اليسار')
          : (p.x > 0 ? 'على يمين صاحب الفيديو' : 'على يسار صاحب الفيديو'));
        var c = closing[k];
        setText('va-now-move', c === null || c === undefined ? '—' : c > 0.4 ? 'تقترب بسرعة ' + fmt(c * 3.6, 0) + ' كم/س'
          : c < -0.4 ? 'تبتعد بسرعة ' + fmt(-c * 3.6, 0) + ' كم/س' : 'المسافة ثابتة تقريبًا');
      }
      var now = events.filter(function (e) { return e.type !== 'collision' && tt >= e.start_t - 0.05 && tt <= Math.max(e.end_t, e.start_t + 0.3); })
        .map(function (e) { return (labels[e.type] || e.type) + (e.vehicle === 'B' ? ' (B)' : e.vehicle === 'A' ? ' (صاحب الفيديو)' : ''); });
      if (impact != null && Math.abs(tt - impact) < 0.16) now.unshift('الاصطدام');
      setText('va-now-event', now.length ? now.join('، ') : '—');
    }

    // ---- the steps as sentences
    var DIR = {left: 'اليسار', right: 'اليمين'};
    function sentence(e) {
      var m = e.m || {};
      if (e.type === 'collision') return 'الاصطدام بين السيارتين';
      if (e.type === 'lane_change') {
        var who = e.vehicle === 'A' ? 'سيارة صاحب الفيديو تغيّر مسارها' : 'المركبة B تغيّر مسارها وتدخل مسار صاحب الفيديو';
        var line = m.crossed_line_type === 'Solid' ? '، وتقطع خطًا متصلًا' : m.crossed_line_type === 'Dashed' ? '، والخط متقطع' : '';
        return who + (m.direction ? ' باتجاه ' + DIR[m.direction] : '') + line;
      }
      if (e.type === 'sudden_stop') return 'المركبة B أمام صاحب الفيديو تخفّف سرعتها فجأة';
      if (e.type === 'overtaking') return (e.vehicle === 'B' ? 'المركبة B' : 'مركبة أخرى') + ' تتجاوز صاحب الفيديو' + (m.side ? ' من ' + DIR[m.side] : '');
      if (e.type === 'following_distance') return 'المسافة إلى B ' + fmt(m.b_distance_m) + ' م: مسافة الأمان ' + (m.safe_distance === 'Maintained' ? 'محافظ عليها' : 'غير محافظ عليها');
      return labels[e.type] || e.type;
    }
    var list = document.getElementById('va-steps'), items = [];
    if (list) {
      var first = pos.findIndex(function (p) { return p; });
      var all = [];
      if (first >= 0) {
        var p0 = pos[first];
        all.push({t: t[first], text: 'تظهر المركبة B ' + (Math.abs(p0.x) <= half * 0.6 ? 'أمام صاحب الفيديو' : p0.x > 0 ? 'على يمين صاحب الفيديو' : 'على يسار صاحب الفيديو') + ' على بعد ' + fmt(p0.d) + ' م', kind: 'start'});
      }
      events.forEach(function (e) { all.push({t: e.start_t, text: sentence(e), kind: e.type}); });
      all.sort(function (a, b) { return a.t - b.t; });
      all.forEach(function (it) {
        var li = document.createElement('li'); li.className = 'step-' + it.kind;
        var b = document.createElement('button'); b.type = 'button';
        var tm = document.createElement('span'); tm.className = 'va-step-t'; tm.textContent = when(it.t);
        var tx = document.createElement('span'); tx.className = 'va-step-x'; tx.textContent = it.text;
        b.appendChild(tm); b.appendChild(tx);
        b.addEventListener('click', function () { seek(it.t); });
        li.appendChild(b); list.appendChild(li); items.push({t: it.t, li: li});
      });
    }
    function steps(tt) {
      var cur = -1;
      items.forEach(function (it, j) { if (tt >= it.t - 0.05) cur = j; });
      items.forEach(function (it, j) { it.li.classList.toggle('is-past', j < cur); it.li.classList.toggle('is-now', j === cur); });
    }

    // ---- time: follows the video; the scrubber and the steps move it
    var scrub = document.getElementById('va-scrub'), play = document.getElementById('va-play');
    var t0 = t[0], t1 = t[n - 1], cur = impact != null ? Math.max(t0, impact - 3) : t0, last = null;
    function seek(tt) {
      cur = Math.max(t0, Math.min(t1, tt));
      if (video) {
        var go = function () { try { video.currentTime = cur; } catch (e) {} video.pause(); };
        if (video.readyState >= 1) go(); else video.addEventListener('loadedmetadata', go, {once: true});
      }
      render();
    }
    function render() {
      if (scrub) scrub.value = Math.round((cur - t0) / Math.max(1e-6, t1 - t0) * 1000);
      if (cur !== last) { draw(cur); last = cur; }
    }
    if (scrub) scrub.addEventListener('input', function () { seek(t0 + scrub.value / 1000 * (t1 - t0)); });
    if (play && video) {
      play.addEventListener('click', function () {
        if (video.paused) { if (cur >= t1 - 0.05) seek(t0); video.play(); } else video.pause();
      });
      var icon = function () { play.setAttribute('aria-label', video.paused ? 'تشغيل' : 'إيقاف'); play.textContent = video.paused ? '\u25B6' : '\u275A\u275A'; };
      icon();
      video.addEventListener('play', icon); video.addEventListener('pause', icon);
    }
    (function loop() {
      if (video && video.readyState >= 1 && !video.seeking && Math.abs(video.currentTime - cur) > 0.04 && (!video.paused || document.activeElement !== scrub)) cur = video.currentTime;
      render();
      requestAnimationFrame(loop);
    })();
    road();
    seek(cur);
  };
})();
