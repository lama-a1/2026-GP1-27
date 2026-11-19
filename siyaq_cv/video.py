"""Read a dashcam video at 10 fps and 640 px width. For long videos keep only the window around the impact."""
import cv2
import numpy as np

from . import config


def _frames(path, start_s=0.0, end_s=None):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError("cannot open the video")
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not src_fps or src_fps != src_fps or src_fps > 240:
        src_fps = 30.0
    step = src_fps / config.FPS
    i, nxt = 0, start_s * src_fps
    if start_s > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_s * src_fps))
        i = int(start_s * src_fps)
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if end_s is not None and i / src_fps > end_s:
            break
        if i >= nxt - 1e-6:
            yield i / src_fps, fr, src_fps
            nxt += step
        i += 1
    cap.release()


def _small(fr):
    return cv2.cvtColor(cv2.resize(fr, (160, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)


def _bars(peak_rows, peak_cols):
    """(top, bottom, left, right) of the picture inside black bars (a phone recording of a screen, a portrait
    TikTok repost). A bar row/column is dark in every sampled frame; night sky still has lamps or noise."""
    def span(v):
        on = np.nonzero(v > config.BAR_LEVEL)[0]
        return (int(on[0]), int(on[-1]) + 1) if on.size else (0, len(v))
    (t, b), (l, r) = span(peak_rows), span(peak_cols)
    H, W = len(peak_rows), len(peak_cols)
    if (b - t) < config.BAR_MIN_KEEP * H or H - (b - t) < config.BAR_MIN_CUT * H:
        t, b = 0, H                          # no bars, or only a few dark edge rows: keep the full height
    if (r - l) < config.BAR_MIN_KEEP * W or W - (r - l) < config.BAR_MIN_CUT * W:
        l, r = 0, W
    return t, b, l, r


def load(path):
    """Returns {frames (BGR, 640 px), times (s, original video time), fps, width, height, src_*}."""
    # pass 1: cheap scan of the whole video (tiny grayscale) to find the strongest jolt
    times, jolt, prev, meta = [], [], None, {}
    peak_rows = peak_cols = None
    for k, (t, fr, src_fps) in enumerate(_frames(path)):
        if k % 5 == 0:                       # brightest value per row / column over a sample of frames
            g8 = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            pr, pc = np.percentile(g8, 99, axis=1), np.percentile(g8, 99, axis=0)
            peak_rows = pr if peak_rows is None else np.maximum(peak_rows, pr)
            peak_cols = pc if peak_cols is None else np.maximum(peak_cols, pc)
        g = _small(fr)
        jolt.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
        prev = g
        times.append(t)
        meta = {"src_fps": src_fps, "src_width": fr.shape[1], "src_height": fr.shape[0]}
    if not times:
        raise ValueError("the video has no frames")
    top, bot, lef, rig = _bars(peak_rows, peak_cols)
    meta["crop"] = [top, bot, lef, rig] if (top, bot, lef, rig) != (0, meta["src_height"], 0, meta["src_width"]) else None
    duration = times[-1] + 1 / config.FPS
    start, end = 0.0, None
    if duration > config.MAX_SECONDS:
        peak = times[int(np.argmax(jolt))]
        end = min(duration, max(peak + config.POST_IMPACT_S, config.MAX_SECONDS))
        start = max(0.0, end - config.MAX_SECONDS)
    # pass 2: the frames we analyse
    frames, ftimes = [], []
    for t, fr, _ in _frames(path, start, end):
        fr = fr[top:bot, lef:rig]           # drop black bars, so the models see the road picture only
        s = config.WORK_WIDTH / fr.shape[1]
        frames.append(cv2.resize(fr, (config.WORK_WIDTH, int(round(fr.shape[0] * s))), interpolation=cv2.INTER_AREA))
        ftimes.append(round(t, 3))
        if len(frames) >= config.MAX_SECONDS * config.FPS:
            break
    h, w = frames[0].shape[:2]
    return {"frames": frames, "times": ftimes, "fps": config.FPS, "width": w, "height": h,
            "duration_s": round(duration, 2), "window_start_s": round(start, 2), **meta}


def quality(frames):
    """Brightness of the road area and sharpness - night or blurred videos are flagged, not judged."""
    pick = frames[:: max(1, len(frames) // 10)]
    gray = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in pick]
    h = gray[0].shape[0]
    bright = float(np.mean([g[: int(0.6 * h)].mean() for g in gray]))
    sharp = float(np.median([cv2.Laplacian(g, cv2.CV_64F).var() for g in gray]))
    flags = (["dark_or_night"] if bright < 55 else []) + (["blurred"] if sharp < 15 else [])
    return {"brightness": round(bright, 1), "sharpness": round(sharp, 1), "flags": flags}
