"""ByteTrack (Zhang et al., ECCV 2022) - the multi-object tracker named in Siyaq's design.

A numpy port of the official tracker (github.com/ifzhang/ByteTrack, yolox/tracker/byte_tracker.py,
MIT licence), kept step for step:
  * every track has a Kalman filter on (centre x, centre y, aspect ratio, height) that predicts where the
    vehicle will be in the next frame (constant-velocity model),
  * association 1: high-score detections <-> all tracks (tracked + lost), cost = 1 - IoU fused with the
    detection score, solved optimally with the Hungarian method,
  * association 2: low-score detections <-> tracks still unmatched (the "BYTE" idea: a blurred or partly
    hidden car near the impact gets a low score, but it is still the same car),
  * a new track starts unconfirmed and is confirmed by a second detection; a lost track is kept for
    BT_TRACK_BUFFER frames and can be found again at its predicted place.
Changes from the official code: no PyTorch, no `lap` and no scipy (Vercel's size limit), so the Hungarian
method is implemented below; the frame-rate scaling of the track buffer uses Siyaq's 10 fps; each track
also keeps the vehicle class (car / bus / truck) of its detections.
"""
import numpy as np

from . import config

# --------------------------------------------------------------------------- Kalman filter (xyah)
_CHI2 = None


class KalmanFilter:
    """Constant-velocity Kalman filter on (cx, cy, a, h) and their velocities, as in ByteTrack / DeepSORT."""

    def __init__(self):
        ndim, dt = 4, 1.0
        self._motion_mat = np.eye(2 * ndim)
        for i in range(ndim):
            self._motion_mat[i, ndim + i] = dt
        self._update_mat = np.eye(ndim, 2 * ndim)
        self._std_weight_position = 1.0 / 20
        self._std_weight_velocity = 1.0 / 160

    def initiate(self, measurement):
        mean = np.r_[measurement, np.zeros_like(measurement)]
        h = measurement[3]
        std = [2 * self._std_weight_position * h, 2 * self._std_weight_position * h, 1e-2,
               2 * self._std_weight_position * h, 10 * self._std_weight_velocity * h,
               10 * self._std_weight_velocity * h, 1e-5, 10 * self._std_weight_velocity * h]
        return mean, np.diag(np.square(std))

    def predict(self, mean, covariance):
        h = mean[3]
        std = [self._std_weight_position * h, self._std_weight_position * h, 1e-2, self._std_weight_position * h,
               self._std_weight_velocity * h, self._std_weight_velocity * h, 1e-5, self._std_weight_velocity * h]
        motion_cov = np.diag(np.square(std))
        mean = self._motion_mat @ mean
        covariance = self._motion_mat @ covariance @ self._motion_mat.T + motion_cov
        return mean, covariance

    def project(self, mean, covariance):
        h = mean[3]
        std = [self._std_weight_position * h, self._std_weight_position * h, 1e-1, self._std_weight_position * h]
        innovation_cov = np.diag(np.square(std))
        return self._update_mat @ mean, self._update_mat @ covariance @ self._update_mat.T + innovation_cov

    def update(self, mean, covariance, measurement):
        projected_mean, projected_cov = self.project(mean, covariance)
        kalman_gain = np.linalg.solve(projected_cov, (covariance @ self._update_mat.T).T).T
        innovation = measurement - projected_mean
        new_mean = mean + innovation @ kalman_gain.T
        new_covariance = covariance - kalman_gain @ projected_cov @ kalman_gain.T
        return new_mean, new_covariance


# --------------------------------------------------------------------------- Hungarian method
def _hungarian(cost):
    """Optimal assignment for a square cost matrix (O(n^3)). Returns col index for each row."""
    n = cost.shape[0]
    u, v = np.zeros(n + 1), np.zeros(n + 1)
    p, way = np.zeros(n + 1, int), np.zeros(n + 1, int)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv = np.full(n + 1, np.inf)
        used = np.zeros(n + 1, bool)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], np.inf, 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1, j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    col = np.zeros(n, int)
    for j in range(1, n + 1):
        if p[j]:
            col[p[j] - 1] = j - 1
    return col


def linear_assignment(cost, thresh):
    """Same contract as ByteTrack's matching.linear_assignment: pairs with cost <= thresh, minimal total."""
    if cost.size == 0:
        return np.empty((0, 2), int), tuple(range(cost.shape[0])), tuple(range(cost.shape[1]))
    r, c = cost.shape
    big = thresh + 1e4
    n = max(r, c)
    sq = np.full((n, n), big)
    sq[:r, :c] = np.where(cost > thresh, big, cost)
    col = _hungarian(sq)
    matches = [(i, col[i]) for i in range(r) if col[i] < c and cost[i, col[i]] <= thresh]
    mr = {m[0] for m in matches}
    mc = {m[1] for m in matches}
    return (np.array(matches, int).reshape(-1, 2), tuple(i for i in range(r) if i not in mr),
            tuple(j for j in range(c) if j not in mc))


def _ious(a, b):
    """IoU matrix between boxes a (N,4) and b (M,4) in tlbr."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    a, b = np.asarray(a, float), np.asarray(b, float)
    # +1 pixel convention of cython_bbox, which the official ByteTrack uses
    ix1 = np.maximum(a[:, None, 0], b[None, :, 0]); iy1 = np.maximum(a[:, None, 1], b[None, :, 1])
    ix2 = np.minimum(a[:, None, 2], b[None, :, 2]); iy2 = np.minimum(a[:, None, 3], b[None, :, 3])
    iw, ih = ix2 - ix1 + 1, iy2 - iy1 + 1
    inter = np.where((iw > 0) & (ih > 0), iw * ih, 0.0)
    area_a = (a[:, 2] - a[:, 0] + 1) * (a[:, 3] - a[:, 1] + 1)
    area_b = (b[:, 2] - b[:, 0] + 1) * (b[:, 3] - b[:, 1] + 1)
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)


def iou_distance(tracks, dets):
    return 1 - _ious([t.tlbr for t in tracks], [d.tlbr for d in dets])


def fuse_score(cost, dets):
    if cost.size == 0:
        return cost
    sim = (1 - cost) * np.array([d.score for d in dets])[None, :]
    return 1 - sim


# --------------------------------------------------------------------------- tracks
NEW, TRACKED, LOST, REMOVED = 0, 1, 2, 3


class STrack:
    shared_kalman = KalmanFilter()

    def __init__(self, tlwh, score, cls):
        self._tlwh = np.asarray(tlwh, float)
        self.kalman_filter = None
        self.mean = self.covariance = None
        self.is_activated = False
        self.score, self.cls = float(score), cls
        self.tracklet_len = 0
        self.state = NEW
        self.track_id = 0
        self.frame_id = self.start_frame = 0
        self.history = {}               # frame -> (x1, y1, x2, y2, score)
        self.classes = [cls]

    # ---- geometry
    @property
    def tlwh(self):
        if self.mean is None:
            return self._tlwh.copy()
        ret = self.mean[:4].copy()
        ret[2] *= ret[3]
        ret[:2] -= ret[2:] / 2
        return ret

    @property
    def tlbr(self):
        ret = self.tlwh
        ret[2:] += ret[:2]
        return ret

    @staticmethod
    def tlwh_to_xyah(tlwh):
        ret = np.asarray(tlwh, float).copy()
        ret[:2] += ret[2:] / 2
        ret[2] /= ret[3]
        return ret

    # ---- life cycle
    def predict(self):
        mean = self.mean.copy()
        if self.state != TRACKED:
            mean[7] = 0
        self.mean, self.covariance = self.kalman_filter.predict(mean, self.covariance)

    def activate(self, kalman_filter, frame_id, track_id):
        self.kalman_filter = kalman_filter
        self.track_id = track_id
        self.mean, self.covariance = kalman_filter.initiate(self.tlwh_to_xyah(self._tlwh))
        self.tracklet_len = 0
        self.state = TRACKED
        self.is_activated = frame_id == 1
        self.frame_id = self.start_frame = frame_id
        self._record()

    def re_activate(self, new_track, frame_id):
        self.mean, self.covariance = self.kalman_filter.update(self.mean, self.covariance,
                                                               self.tlwh_to_xyah(new_track.tlwh))
        self.tracklet_len = 0
        self.state = TRACKED
        self.is_activated = True
        self.frame_id = frame_id
        self.score = new_track.score
        self.classes.append(new_track.cls)
        self._record(new_track)

    def update(self, new_track, frame_id):
        self.frame_id = frame_id
        self.tracklet_len += 1
        self.mean, self.covariance = self.kalman_filter.update(self.mean, self.covariance,
                                                               self.tlwh_to_xyah(new_track.tlwh))
        self.state = TRACKED
        self.is_activated = True
        self.score = new_track.score
        self.classes.append(new_track.cls)
        self._record(new_track)

    def _record(self, det=None):
        # the official tracker reports the Kalman-filtered box; config.BT_BOX = "detection" keeps YOLO's box instead
        x1, y1, x2, y2 = det.tlbr if det is not None and config.BT_BOX == "detection" else self.tlbr
        self.history[self.frame_id] = (float(x1), float(y1), float(x2), float(y2), self.score)

    @property
    def end_frame(self):
        return self.frame_id


class BYTETracker:
    def __init__(self, frame_rate=10):
        self.tracked, self.lost, self.removed = [], [], []
        self.frame_id = 0
        self.det_thresh = config.BT_TRACK_THRESH + 0.1
        # the official buffer is 30 frames at 30 fps: scale it to Siyaq's frame rate
        self.max_time_lost = int(frame_rate / 30.0 * config.BT_TRACK_BUFFER)
        self.kalman = KalmanFilter()
        self._next_id = 0

    def _new_id(self):
        self._next_id += 1
        return self._next_id

    def update(self, dets):
        """dets: list of (x1, y1, x2, y2, score, class). Returns the tracks updated in this frame."""
        self.frame_id += 1
        activated, refind, lost, removed = [], [], [], []
        high = [STrack([d[0], d[1], d[2] - d[0], d[3] - d[1]], d[4], d[5]) for d in dets if d[4] > config.BT_TRACK_THRESH]
        low = [STrack([d[0], d[1], d[2] - d[0], d[3] - d[1]], d[4], d[5]) for d in dets
               if config.BT_LOW_THRESH < d[4] < config.BT_TRACK_THRESH]

        unconfirmed = [t for t in self.tracked if not t.is_activated]
        tracked = [t for t in self.tracked if t.is_activated]

        # step 2: first association, high-score detections
        pool = _join(tracked, self.lost)
        for t in pool:
            t.predict()
        dists = fuse_score(iou_distance(pool, high), high)
        matches, u_track, u_det = linear_assignment(dists, config.BT_MATCH_THRESH)
        for it, idet in matches:
            t, d = pool[it], high[idet]
            if t.state == TRACKED:
                t.update(d, self.frame_id); activated.append(t)
            else:
                t.re_activate(d, self.frame_id); refind.append(t)

        # step 3: second association, low-score detections (the BYTE step)
        r_tracked = [pool[i] for i in u_track if pool[i].state == TRACKED]
        dists = iou_distance(r_tracked, low)
        matches, u_track, _ = linear_assignment(dists, 0.5)
        for it, idet in matches:
            t, d = r_tracked[it], low[idet]
            if t.state == TRACKED:
                t.update(d, self.frame_id); activated.append(t)
            else:
                t.re_activate(d, self.frame_id); refind.append(t)
        for it in u_track:
            t = r_tracked[it]
            if t.state != LOST:
                t.state = LOST; lost.append(t)

        # unconfirmed tracks (one frame old) with the remaining high-score detections
        high = [high[i] for i in u_det]
        dists = fuse_score(iou_distance(unconfirmed, high), high)
        matches, u_unconf, u_det = linear_assignment(dists, 0.7)
        for it, idet in matches:
            unconfirmed[it].update(high[idet], self.frame_id); activated.append(unconfirmed[it])
        for it in u_unconf:
            unconfirmed[it].state = REMOVED; removed.append(unconfirmed[it])

        # step 4: new tracks
        for inew in u_det:
            t = high[inew]
            if t.score < self.det_thresh:
                continue
            t.activate(self.kalman, self.frame_id, self._new_id()); activated.append(t)

        # step 5: forget tracks lost for too long
        for t in self.lost:
            if self.frame_id - t.end_frame > self.max_time_lost:
                t.state = REMOVED; removed.append(t)

        self.tracked = [t for t in self.tracked if t.state == TRACKED]
        self.tracked = _join(self.tracked, activated)
        self.tracked = _join(self.tracked, refind)
        self.lost = _sub(self.lost, self.tracked)
        self.lost.extend(lost)
        self.lost = _sub(self.lost, self.removed)
        self.removed.extend(removed)
        self.tracked, self.lost = _remove_duplicates(self.tracked, self.lost)
        return [t for t in self.tracked if t.is_activated]


def _join(a, b):
    seen, out = set(), []
    for t in a + b:
        if t.track_id not in seen:
            seen.add(t.track_id); out.append(t)
    return out


def _sub(a, b):
    ids = {t.track_id for t in b}
    return [t for t in a if t.track_id not in ids]


def _remove_duplicates(a, b):
    d = iou_distance(a, b)
    dupa, dupb = set(), set()
    for p, q in zip(*np.where(d < 0.15)):
        ta, tb = a[p].frame_id - a[p].start_frame, b[q].frame_id - b[q].start_frame
        (dupb if ta > tb else dupa).add(q if ta > tb else p)
    return [t for i, t in enumerate(a) if i not in dupa], [t for i, t in enumerate(b) if i not in dupb]


def track(detections_per_frame, frame_rate=10):
    """Run ByteTrack over a clip. detections_per_frame[f] = [(x1, y1, x2, y2, score, cls), ...]
    Returns ({track_id: {frame: (x1, y1, x2, y2, score)}}, {track_id: class}) with 0-based frames."""
    bt = BYTETracker(frame_rate)
    every = {}
    for dets in detections_per_frame:
        for t in bt.update(dets):
            every[t.track_id] = t
    every.update({t.track_id: t for t in bt.lost + bt.removed if t.is_activated})
    tracks, classes = {}, {}
    for tid, t in every.items():
        if not t.is_activated:
            continue
        tracks[tid] = {f - 1: b for f, b in t.history.items()}
        classes[tid] = max(set(t.classes), key=t.classes.count)
    return tracks, classes
