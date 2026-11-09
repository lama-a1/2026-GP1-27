/* Siyaq - the analysis result of one video: boxes drawn over the video and the event timeline.
   Used by the case analysis page and by the expert's trial page (after the result is inserted). */
window.siyaqAnalysisView = function (root) {
  var dataEl = root.querySelector('#va-data');
  if (!dataEl) return;
  var D = JSON.parse(dataEl.textContent);
  var video = root.querySelector('#va-video'), canvas = root.querySelector('#va-overlay'), ctx = canvas.getContext('2d');
  var show = root.querySelector('#va-show-boxes'), playhead = root.querySelector('#va-playhead');
  var byFrame = {};
  Object.keys(D.tracks).forEach(function (tid) {
    D.tracks[tid].forEach(function (b) { (byFrame[b[0]] = byFrame[b[0]] || []).push([tid].concat(b.slice(1))); });
  });
  var nFrames = D.series.t.length;
  function draw() {
    var w = video.clientWidth, h = video.clientHeight, vw = video.videoWidth || 16, vh = video.videoHeight || 9;
    var dpr = window.devicePixelRatio || 1;
    // resize when the video's box changes in either direction (its height is only known once the video has loaded)
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    // the video is letter-boxed inside the element: find the drawn picture
    var s = Math.min(w / vw, h / vh), pw = vw * s, ph = vh * s, ox = (w - pw) / 2, oy = (h - ph) / 2;
    var f = Math.round((video.currentTime - D.start) * D.fps);
    if (playhead) playhead.style.width = Math.max(0, Math.min(100, f / nFrames * 100)) + '%';
    if (!show.checked) return;
    (byFrame[f] || byFrame[f - 1] || []).forEach(function (b) {
      var isB = b[0] === D.b;
      ctx.strokeStyle = isB ? '#d93025' : '#2fae66'; ctx.lineWidth = isB ? 3 : 1.5;
      var x = ox + b[1] * pw, y = oy + b[2] * ph, bw = (b[3] - b[1]) * pw, bh = (b[4] - b[2]) * ph;
      ctx.strokeRect(x, y, bw, bh);
      ctx.fillStyle = isB ? '#d93025' : '#2fae66'; ctx.font = 'bold 12px Tajawal, system-ui, sans-serif';
      ctx.fillText(isB ? 'B' : b[0], x + 3, Math.max(12, y - 4));
    });
  }
  (function loop() { if (video.isConnected) { draw(); requestAnimationFrame(loop); } })();
  root.querySelectorAll('[data-t]').forEach(function (el) {
    el.addEventListener('click', function () {
      var go = function () { video.currentTime = parseFloat(el.dataset.t) || 0; video.pause(); };
      video.scrollIntoView({behavior: 'smooth', block: 'center'});
      if (video.readyState >= 1) go(); else video.addEventListener('loadedmetadata', go, {once: true});
    });
  });
};
