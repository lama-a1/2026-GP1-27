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
  // a video with black bars (portrait phone recording): show only the picture the engine analysed.
  // The native controls would fall inside the hidden bars, so a small control row is added under the picture.
  var P = D.picture, cropped = !!(P && D.size);
  if (cropped) {
    var player = video.parentElement, stage = document.createElement('div');
    player.classList.add('va-cropped');
    stage.className = 'va-stage';                    // holds the picture at its own aspect ratio, also in full screen
    var ar = (P[2] * D.size[0]) / (P[3] * D.size[1]);
    stage.style.aspectRatio = String(ar); stage.style.setProperty('--ar', ar);
    player.insertBefore(stage, video); stage.appendChild(video); stage.appendChild(canvas);
    video.removeAttribute('controls');
    video.style.cssText = 'position:absolute;max-height:none;object-fit:fill;width:' + (100 / P[2]) + '%;height:' + (100 / P[3]) +
      '%;left:' + (-P[0] / P[2] * 100) + '%;top:' + (-P[1] / P[3] * 100) + '%';
    var bar = document.createElement('div');
    bar.className = 'va-controls';
    bar.innerHTML = '<button type="button" class="va-play" aria-label="تشغيل">▶</button>' +
      '<input type="range" min="0" max="1000" value="0" dir="ltr" aria-label="موضع الفيديو"><span class="va-clock" dir="ltr">0:00</span>';
    player.insertAdjacentElement('afterend', bar);
    player = stage;
    var play = bar.querySelector('.va-play'), seek = bar.querySelector('input'), clock = bar.querySelector('.va-clock');
    var fmt = function (t) { t = Math.max(0, t || 0); return Math.floor(t / 60) + ':' + ('0' + Math.floor(t % 60)).slice(-2); };
    play.addEventListener('click', function () { if (video.paused) video.play(); else video.pause(); });
    video.addEventListener('click', function () { play.click(); });
    video.addEventListener('play', function () { play.textContent = '❚❚'; play.setAttribute('aria-label', 'إيقاف'); });
    video.addEventListener('pause', function () { play.textContent = '▶'; play.setAttribute('aria-label', 'تشغيل'); });
    video.addEventListener('timeupdate', function () {
      if (video.duration) seek.value = Math.round(video.currentTime / video.duration * 1000);
      clock.textContent = fmt(video.currentTime) + ' / ' + fmt(video.duration);
    });
    seek.addEventListener('input', function () { if (video.duration) video.currentTime = seek.value / 1000 * video.duration; });
  }
  // full screen shows the player box, so the boxes stay on the video (the browser's own full screen shows the bare video)
  var playerBox = cropped ? video.parentElement.parentElement : video.parentElement;
  video.setAttribute('controlsList', 'nofullscreen');
  var fsEl = function () { return document.fullscreenElement || document.webkitFullscreenElement; };
  var goFull = function () {
    if (fsEl()) { (document.exitFullscreen || document.webkitExitFullscreen).call(document); return; }
    var req = playerBox.requestFullscreen || playerBox.webkitRequestFullscreen;
    if (req) req.call(playerBox); else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen();   // iPhone: video only
  };
  var fsBtn = root.querySelector('#va-full');
  if (fsBtn) fsBtn.addEventListener('click', goFull);
  ['fullscreenchange', 'webkitfullscreenchange'].forEach(function (ev) {
    document.addEventListener(ev, function () {
      if (fsEl() === video) {               // the browser's button was used: move the full screen to the player box
        var exit = document.exitFullscreen || document.webkitExitFullscreen;
        Promise.resolve(exit.call(document)).then(goFull, goFull);
      }
    });
  });
  function draw() {
    // the canvas covers the whole player box (also in full screen); find where the picture is drawn inside it
    var player = video.parentElement, w = player.clientWidth, h = player.clientHeight;
    var dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    var pw, ph, ox, oy;
    if (cropped) { pw = w; ph = h; ox = 0; oy = 0; }     // cropped: the player box shows exactly the analysed picture
    else {                                               // the video is letter-boxed inside its element
      var ew = video.clientWidth, eh = video.clientHeight, vw = video.videoWidth || 16, vh = video.videoHeight || 9;
      var s = Math.min(ew / vw, eh / vh); pw = vw * s; ph = vh * s;
      ox = video.offsetLeft + (ew - pw) / 2; oy = video.offsetTop + (eh - ph) / 2;
    }
    var f = Math.round((video.currentTime - D.start) * D.fps);
    if (playhead) playhead.style.width = Math.max(0, Math.min(100, f / nFrames * 100)) + '%';
    if (!show.checked) return;
    (byFrame[f] || byFrame[f - 1] || []).forEach(function (b) {
      var isB = b[0] === D.b;
      ctx.strokeStyle = isB ? '#d93025' : '#2fae66'; ctx.lineWidth = isB ? 3 : 1.5;
      // boxes are relative to the analysed picture; black bars cut off before the analysis are added back
      var P = (!cropped && D.picture) || [0, 0, 1, 1];
      var x = ox + (P[0] + b[1] * P[2]) * pw, y = oy + (P[1] + b[2] * P[3]) * ph, bw = (b[3] - b[1]) * P[2] * pw, bh = (b[4] - b[2]) * P[3] * ph;
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
