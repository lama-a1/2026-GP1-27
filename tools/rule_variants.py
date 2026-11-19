"""Rule-variant experiments (report Section 5.1), with the same repeated stratified 5x5 CV as tools/cross_validate.py.

    python tools/rule_variants.py . <variant> <out.json>        (needs the engine cache .cv_cache from cross_validate.py)

variants:
  base           one set of thresholds for all clips
  gate           base + lateral-speed check for B's lane change (LANE_DETECT_MPS)
  min_ttc        base + safe distance may use the minimum TTC before the reference moment (SAFE_TTC_MODE)
  pertype        lane-change thresholds chosen separately per report type (the engine's choice: LANE_BY_TYPE)
  pertype_all    all thresholds chosen separately per report type
"Default" thresholds are the values used before cross-validation.
Per fold it records the thresholds chosen on the training folds, the training accuracy of each element, and the
held-out per-clip scores, so that a variant can also be chosen inside each fold afterwards.
"""
import sys, json, csv, itertools, os
repo, variant, outp = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, repo); sys.path.insert(0, repo + "/tools")
from siyaq_cv import config
from siyaq_cv.threshold_grid import GRID, STAGES
import cross_validate as cv
from sklearn.model_selection import RepeatedStratifiedKFold

OLD = {"LANE_SIDE_M": 2.2, "LANE_SHIFT_M": 0.4, "LANE_IN_M": 0.8, "LANE_ONSET_MPS": 0.4, "EGO_YAW_DEG": 20.0,
       "TTC_SUDDEN_STOP_S": 1.6, "SAFE_TTC_S": 2.0, "SAFE_REF_S": 2.0, "LANE_DETECT_MPS": None, "SAFE_TTC_MODE": "at_ref"}
NEW = {"LANE_LINE_RULE", "COLLISION_LOST_WIN", "LANE_REQUIRE_IN", "LANE_END_AT_IMPACT", "LANE_FALLBACK_S", "SAFE_RULE",
       "SAFE_DRAC_MPS2", "SAFE_UNKNOWN", "SAFE_SUDDEN_STOP", "SAFE_FALLBACK_S"}   # options compared by cross_validate.py
G = {k: v for k, v in GRID.items() if k not in NEW}
STAGES = [(tuple(keys), m) for keys, m, *_ in STAGES if not any(k in NEW for k in keys)]
G["LANE_DETECT_MPS"] = [None, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]
G["SAFE_TTC_MODE"] = ["at_ref", "min_before_ref"] if variant == "min_ttc" else ["at_ref"]
LC_STAGES = [s for s in STAGES if s[1] == "lane_change"]
if variant == "gate":
    LC_STAGES = LC_STAGES[:1] + [(("LANE_SIDE_M", "LANE_DETECT_MPS"), "lane_change")] + LC_STAGES[1:]
OTHER = [s for s in STAGES if s[1] != "lane_change"]
OTHER = [((("SAFE_TTC_MODE",) + k) if m == "safe_distance" else k, m) for k, m in OTHER]
PERTYPE = variant.startswith("pertype")

idx = {r["clip_id"]: r for r in csv.DictReader(open(repo + "/data/dataset/dataset_index.csv"))}
refs = json.load(open(repo + "/data/ground_truth/cvat_labels.json"))["clips"]
clips = sorted(c for c in refs if c in idx)
runs = {c: json.load(open(f"{repo}/.cv_cache/{c}.json")) for c in clips}
typ = {c: idx[c]["accident_type"] for c in clips}
memo = {}

def thr_key(th):
    return tuple(sorted((k, th[k]) for k in OLD))

def score_clip(c, th):
    key = (c, thr_key(th))
    if key not in memo:
        for k in ("LANE_DETECT_MPS", "SAFE_TTC_MODE"):
            setattr(config, k, th[k])
        try:
            memo[key] = cv.score(refs[c], cv.replay(runs[c], {k: v for k, v in th.items() if k not in ("LANE_DETECT_MPS", "SAFE_TTC_MODE")}))
        finally:
            config.LANE_DETECT_MPS, config.SAFE_TTC_MODE = None, "at_ref"
    return memo[key]

def acc(cs, thf, m):
    v = [score_clip(c, thf(c))[m] for c in cs]
    v = [x for x in v if x is not None]
    return sum(v) / len(v) if v else None

def search(cs, stages, start, thf_builder):
    th = dict(start)
    for keys, m in stages:
        best = None
        for vals in itertools.product(*[G[k] for k in keys]):
            cand = dict(th, **dict(zip(keys, vals)))
            a = acc(cs, thf_builder(cand), m)
            if a is not None and (best is None or a > best[0] + 1e-9):
                best = (a, dict(zip(keys, vals)))
        if best:
            th.update(best[1])
    return th

def choose(train):
    if not PERTYPE:
        th = search(train, LC_STAGES, OLD, lambda t: (lambda c: t))
        th = search(train, OTHER, th, lambda t: (lambda c: t))
        return {"Rear-end": th, "Lane-change": th}
    if variant == "pertype_all":
        return {ty: search([c for c in train if typ[c] == ty], LC_STAGES + OTHER, OLD, lambda t: (lambda c: t))
                for ty in ("Rear-end", "Lane-change")}
    per = {}
    for ty in ("Rear-end", "Lane-change"):
        per[ty] = search([c for c in train if typ[c] == ty], LC_STAGES, OLD, lambda t: (lambda c: t))
    lc_keys = {k for s, _ in LC_STAGES for k in s}
    def build(t):
        full = {ty: dict(t, **{k: per[ty][k] for k in lc_keys}) for ty in per}
        return lambda c: full[typ[c]]
    th = search(train, OTHER, OLD, build)
    return {ty: dict(th, **{k: per[ty][k] for k in lc_keys}) for ty in per}

group = [f"{idx[c]['source']}|{typ[c]}" for c in clips]
folds = []
for f, (tr, te) in enumerate(RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=42).split(clips, group)):
    train, test = [clips[i] for i in tr], [clips[i] for i in te]
    ths = choose(train)
    thf = lambda c: ths[typ[c]]
    folds.append({"fold": f, "thresholds": ths,
                  "train_acc": {m: acc(train, thf, m) for m in cv.METRICS},
                  "test": {c: {k: v for k, v in score_clip(c, thf(c)).items()} for c in test}})
    print(variant, f, {m: round(acc(test, thf, m) or 0, 3) for m in cv.METRICS}, flush=True)
final = choose(clips)
json.dump({"variant": variant, "folds": folds, "final": final}, open(outp, "w"), default=str)
print("done", variant)
