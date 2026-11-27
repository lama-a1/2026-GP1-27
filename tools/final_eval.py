"""Evaluation of the FINAL Siyaq engine on the whole dataset (all labelled clips).

    python tools/final_eval.py --videos <folder with the clip videos> --out final_eval_output

The final engine is the one the website runs: the thresholds in siyaq_cv/config.py (the values chosen on all
clips by tools/cross_validate.py, per report type in config.LANE_BY_TYPE). Every clip is scored once with these
thresholds, with the same scoring rules as the cross-validation (tools/scoring.py, tools/cross_validate.score).

Important: the final thresholds were chosen on these same clips, so these numbers are an IN-SAMPLE result and are
expected to be higher than the cross-validated ones. The cross-validated results (held-out clips) stay the estimate
of the accuracy on new videos; this file reports what the final system does on the whole dataset.

For comparison the same clips are scored with the engine's settings before cross-validation (DEFAULTS) and with
the majority-class / median-impact baseline fitted on all clips.

Outputs (in --out): final_results.json, final_results.xlsx, final_per_clip.csv
"""
import argparse
import csv
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from siyaq_cv import config, events  # noqa: E402
import cross_validate as cv  # noqa: E402


def final_thresholds():
    """Thresholds of the deployed engine per report type: config.py values, replaced by config.LANE_BY_TYPE."""
    base = {k: getattr(config, k) for k in cv.TUNED}
    return {t: dict(base, **{k: v for k, v in config.LANE_BY_TYPE.get(t, {}).items() if k in cv.TUNED})
            for t in cv.TYPES}


def summarise(rows):
    out = {}
    for m in cv.METRICS:
        vals = [r[m] for r in rows if r.get(m) is not None]
        lo, hi = cv.bootstrap_ci(vals)
        out[m] = {"n_clips": len(vals), "correct": sum(vals), "accuracy": (sum(vals) / len(vals)) if vals else None,
                  "ci95_low": lo, "ci95_high": hi}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", required=True, help="folder with the clip videos (column 'file' of dataset_index.csv)")
    ap.add_argument("--labels", default=str(ROOT / "data" / "ground_truth" / "cvat_labels.json"))
    ap.add_argument("--index", default=str(ROOT / "data" / "dataset" / "dataset_index.csv"))
    ap.add_argument("--cache", default=str(ROOT / ".cv_cache"))
    ap.add_argument("--out", default=str(ROOT / "final_eval_output"))
    a = ap.parse_args()

    idx = {r["clip_id"]: r for r in csv.DictReader(open(a.index))}
    refs = json.loads(Path(a.labels).read_text())["clips"]
    clips = sorted(c for c in refs if c in idx)
    cache = Path(a.cache); cache.mkdir(parents=True, exist_ok=True)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    runs = {}
    for k, c in enumerate(clips, 1):
        runs[c] = cv.run_engine(c, Path(a.videos) / idx[c]["file"], cache)
        print(f"\rengine {k}/{len(clips)}", end="", flush=True)
    print()
    types = {c: events.report_type(idx[c]["accident_type"]) for c in clips}

    final = final_thresholds()
    # check: the thresholds in config.py are the ones the cross-validation chooses on all clips
    chosen_all = cv.choose(clips, None, refs, runs, types)
    mismatch = {t: {k: (final[t][k], chosen_all[t][k]) for k in cv.TUNED if final[t][k] != chosen_all[t][k]}
                for t in cv.TYPES}

    systems = {"final engine": final, "default thresholds": {t: dict(cv.DEFAULTS) for t in cv.TYPES}}
    per_clip = []
    for name, th in systems.items():
        for c in clips:
            r = cv.score(refs[c], cv.replay(runs[c], th[types[c]]))
            r.update(system=name, clip_id=c, source=idx[c]["source"], accident_type=idx[c]["accident_type"])
            per_clip.append(r)
    for b in cv.baseline_rows(clips, clips, refs):
        b.update(system="baseline", source=idx[b["clip_id"]]["source"], accident_type=idx[b["clip_id"]]["accident_type"])
        per_clip.append(b)

    summary = {s: summarise([r for r in per_clip if r["system"] == s]) for s in ("final engine", "default thresholds", "baseline")}
    fin = [r for r in per_clip if r["system"] == "final engine"]
    by_type = {t: summarise([r for r in fin if r["accident_type"] == t]) for t in sorted({idx[c]["accident_type"] for c in clips})}
    prf = {"lane_change": cv.prf(fin, "_lc_ref", "_lc_pred", "lane_change"),
           "sudden_stop": cv.prf(fin, "_ss_ref", "_ss_pred", "sudden_stop"),
           "reversing": cv.prf(fin, "_rv_ref", "_rv_pred", "reversing")}
    result = {"n_clips": len(clips), "engine": cv.engine_fingerprint(), "in_sample": True,
              "note": "thresholds chosen on these clips: in-sample result, higher than the cross-validated one",
              "final_thresholds": final, "config_matches_choice_on_all_clips": not any(mismatch.values()),
              "mismatch_config_vs_choice": mismatch, "summary": summary, "final_by_accident_type": by_type,
              "final_prf": {k: dict(zip(("precision", "recall", "f1"), v)) for k, v in prf.items()}}
    (out / "final_results.json").write_text(json.dumps(result, indent=1, default=str))
    cols = ["system", "clip_id", "source", "accident_type"] + cv.METRICS
    with open(out / "final_per_clip.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(per_clip)
    try:
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = "Summary"
        ws.append(["system", "measure", "n_clips", "correct", "accuracy", "ci95_low", "ci95_high"])
        for s, d in summary.items():
            for m, v in d.items():
                ws.append([s, m, v["n_clips"], v["correct"], v["accuracy"], v["ci95_low"], v["ci95_high"]])
        ws2 = wb.create_sheet("FinalByType")
        ws2.append(["accident_type", "measure", "n_clips", "correct", "accuracy"])
        for t, d in by_type.items():
            for m, v in d.items():
                ws2.append([t, m, v["n_clips"], v["correct"], v["accuracy"]])
        ws3 = wb.create_sheet("PerClip"); ws3.append(cols)
        for r in per_clip:
            ws3.append([r.get(c) for c in cols])
        wb.save(out / "final_results.xlsx")
    except ImportError:
        pass
    for s in summary:
        print(s + ": " + ", ".join(f"{m} {v['accuracy'] * 100:.1f}%" for m, v in summary[s].items() if v["accuracy"] is not None))
    print("config matches the choice on all clips:", result["config_matches_choice_on_all_clips"], mismatch)
    print("written:", out)


if __name__ == "__main__":
    main()
