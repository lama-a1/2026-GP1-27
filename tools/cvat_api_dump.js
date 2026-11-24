// Reads the annotations of the three Siyaq CVAT tasks through the CVAT REST API, for tools/cvat_labels.py --api-dump.
//
// Use: log in to https://app.cvat.ai, open the browser console (F12) on that site, paste this file and press Enter.
// It reads one job every ~2 s (CVAT answers 429 "too many requests" when asked faster) and then saves
// cvat_api_dump.json. Nothing is changed in CVAT: every request is a GET.
// Then: python tools/cvat_labels.py --api-dump cvat_api_dump.json
(async () => {
  const TASKS = [2740516, 2740517, 2740522];           // siyaq_CCD_1, siyaq_CCD_2, siyaq_DADA
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const get = async url => {
    for (let i = 0; i < 8; i++) {
      const r = await fetch(url, { headers: { Accept: 'application/vnd.cvat+json' } });
      if (r.status === 429) { await sleep(20000 * (i + 1)); continue; }
      if (!r.ok) throw new Error(url + ': HTTP ' + r.status);
      return r.json();
    }
    throw new Error(url + ': too many requests');
  };
  const dump = { jobs: {}, sizes: {} };
  for (const tid of TASKS) {
    const meta = await get(`/api/tasks/${tid}/data/meta`);
    dump.sizes[tid] = [meta.frames[0].width, meta.frames[0].height];
    const labels = (await get(`/api/labels?task_id=${tid}&page_size=200`)).results;
    const L = {}, A = {};
    for (const l of labels) { L[l.id] = l.name; for (const a of (l.attributes || [])) A[a.id] = a.name; }
    const attrs = arr => Object.fromEntries((arr || []).map(a => [A[a.spec_id] || a.spec_id, a.value]));
    const jobs = (await get(`/api/jobs?task_id=${tid}&page_size=200`)).results;
    for (const jb of jobs) {
      await sleep(1800);
      const a = await get(`/api/jobs/${jb.id}/annotations`);
      const s0 = jb.start_frame;                       // frames are stored relative to the job (0-49)
      dump.jobs[jb.id] = {
        task: tid, start: s0, state: jb.state,
        tags: a.tags.map(t => [t.frame - s0, L[t.label_id], attrs(t.attributes)]),
        tracks: a.tracks.map(tr => ({
          id: tr.id, label: L[tr.label_id],
          attrs: Object.assign({}, attrs(tr.attributes), ...tr.shapes.map(s => attrs(s.attributes))),
          shapes: tr.shapes.map(s => [s.frame - s0, s.outside, s.type, ...s.points])
        })),
        shapes: a.shapes.map(s => [s.frame - s0, L[s.label_id], s.type, attrs(s.attributes), ...s.points])
      };
      console.log(`job ${jb.id} read (${Object.keys(dump.jobs).length})`);
    }
  }
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([JSON.stringify(dump)], { type: 'application/json' }));
  link.download = 'cvat_api_dump.json';
  link.click();
  console.log('saved cvat_api_dump.json');
})();
