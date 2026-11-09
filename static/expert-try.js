/* Siyaq - expert trial page: upload a video, analyse it, show the result. Nothing is stored:
   the server deletes its copy after the analysis and the page plays the video from the expert's own file. */
(function () {
  var form = document.getElementById('try-form');
  if (!form) return;
  var input = document.getElementById('try-video'), out = document.getElementById('try-result');
  var status = document.getElementById('try-status'), bar = document.getElementById('try-progress');
  var message = document.getElementById('try-message'), go = document.getElementById('try-go');
  var csrf = form.querySelector('[name="csrf_token"]').value, maxMb = +form.dataset.maxMb, localUrl = null;
  var say = function (text, pct) { status.hidden = false; message.textContent = text; if (pct !== undefined) bar.style.width = pct + '%'; };

  input.addEventListener('change', function () {
    var f = input.files[0];
    document.getElementById('try-file-name').textContent = f ? f.name : 'اختر فيديو الحادث';
  });

  function upload(ticket, file) {
    // the same chunked, signed upload as the case wizard (Vercel cannot take large request bodies)
    var chunk = 20 * 1024 * 1024, id = 'siyaq-try-' + Date.now(), offset = 0;
    function next() {
      if (offset >= file.size) return Promise.resolve();
      var end = Math.min(file.size, offset + chunk), body = new FormData();
      body.append('file', file.slice(offset, end), file.name);
      body.append('api_key', ticket.api_key); body.append('timestamp', String(ticket.timestamp));
      body.append('signature', ticket.signature); body.append('public_id', ticket.public_id); body.append('type', ticket.delivery_type);
      return new Promise(function (resolve, reject) {
        var xhr = new XMLHttpRequest();
        xhr.open('POST', ticket.upload_url);
        xhr.setRequestHeader('X-Unique-Upload-Id', id);
        xhr.setRequestHeader('Content-Range', 'bytes ' + offset + '-' + (end - 1) + '/' + file.size);
        xhr.upload.onprogress = function (ev) { if (ev.lengthComputable) { var p = Math.round((offset + ev.loaded) / file.size * 100); say('جارٍ رفع الفيديو… ' + p + '٪', p); } };
        xhr.onload = function () {
          var r = {}; try { r = JSON.parse(xhr.responseText); } catch (e) {}
          if (xhr.status >= 200 && xhr.status < 300 && !r.error) resolve(); else reject(new Error((r.error && r.error.message) || 'تعذر رفع الفيديو.'));
        };
        xhr.onerror = function () { reject(new Error('تعذر الاتصال بخدمة رفع الفيديو.')); };
        xhr.send(body);
      }).then(function () { offset = end; return next(); });
    }
    return next();
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var file = input.files[0], kind = (form.querySelector('[name="accident_type"]:checked') || {}).value;
    if (!file) { say('اختر فيديو أولًا.'); return; }
    if (file.size > maxMb * 1024 * 1024) { say('حجم الفيديو أكبر من ' + maxMb + ' ميجابايت.'); return; }
    go.disabled = true; out.innerHTML = '';
    if (localUrl) { URL.revokeObjectURL(localUrl); localUrl = null; }
    say('جارٍ تجهيز الفيديو…', 0);
    fetch('/expert/try/presign', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
                                  body: JSON.stringify({filename: file.name, size: file.size})})
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || 'تعذر بدء الرفع.'); return j; }); })
      .then(function (ticket) {
        var body;
        if (ticket.provider === 'cloudinary') {
          return upload(ticket, file).then(function () {
            body = JSON.stringify({accident_type: kind});
            return {body: body, headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}};
          });
        }
        body = new FormData(); body.append('video', file); body.append('accident_type', kind);
        return {body: body, headers: {'X-CSRF-Token': csrf}};
      })
      .then(function (req) {
        say('جارٍ تحليل الفيديو… يستغرق عادةً أقل من دقيقة.', 100);
        return fetch('/expert/try/analyse', {method: 'POST', credentials: 'same-origin', headers: req.headers, body: req.body});
      })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || 'تعذر تحليل الفيديو.'); return j; }); })
      .then(function (res) {
        out.innerHTML = res.html;
        localUrl = URL.createObjectURL(file);
        var video = out.querySelector('#va-video');
        if (video) video.src = localUrl;          // played from the expert's own file, never from the server
        if (window.siyaqAnalysisView) window.siyaqAnalysisView(out);
        if (window.lucide) window.lucide.createIcons();
        say('اكتمل التحليل في ' + res.seconds + ' ث: ' + res.events + ' أحداث. حُذف الفيديو من الخادم.', 100);
        out.scrollIntoView({behavior: 'smooth', block: 'start'});
      })
      .catch(function (e) { say(e.message || 'حدث خطأ.'); })
      .then(function () { go.disabled = false; });
  });
})();
