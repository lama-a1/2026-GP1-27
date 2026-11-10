"""Generate the Section 5.1 result tables and figures from experiment outputs.

    python tools/report_tables.py --exp EXP-007                      # one experiment (baseline)
    python tools/report_tables.py --exp EXP-008 --baseline EXP-007   # before / after table

Reads   results/<EXP>_SUMMARY/metrics.json and results/<EXP>_<clip>/comparison.json
Writes  docs/gp_report/tables/5.1_<EXP>_*.md and docs/gp_report/figures/fig_5.1_<EXP>_*.png
Every table states the evidence level and the number of clips behind each value.
"""
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "docs" / "gp_report" / "tables"
F = ROOT / "docs" / "gp_report" / "figures"
PENDING = "Pending approved Ground Truth"


def load(exp):
    m = json.loads((ROOT / "results" / f"{exp}_SUMMARY" / "metrics.json").read_text())
    comps = [json.loads(p.read_text()) for p in sorted((ROOT / "results").glob(f"{exp}_*/comparison.json"))]
    return m, comps


def fmt(x, pct=False, nd=2):
    if x is None:
        return "—"
    if isinstance(x, str):
        return x
    return f"{100 * x:.1f} %" if pct else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def table_collision(m, exp):
    L = [f"Table X. Collision timing of {exp} against the source annotations (dataset crash frames; not team-reviewed).", "",
         "| Split | Clips (n) | No prediction | Hit rate (|error| ≤ 0.5 s) | MAE (s) | Median |error| (s) | Mean signed error (s) |",
         "|---|---:|---:|---:|---:|---:|---:|"]
    for s in ("train", "val"):
        c = m.get(s, {}).get("collision_vs_source_annotation")
        if c:
            L.append(f"| {s} | {c['n']} | {c['n_no_prediction']} | {fmt(c['hit_rate_within_0_5s'], True)} | {fmt(c['mae_s'])} | "
                     f"{fmt(c['median_abs_error_s'])} | {fmt(c['mean_signed_error_s'])} |")
    L += ["", "Human-reviewed collision frames:"]
    for s in ("train", "val"):
        h = m.get(s, {}).get("collision_vs_human_gt")
        L.append(f"- {s}: " + (PENDING if not isinstance(h, dict) else f"{h['hits']}/{h['n']} within ±0.5 s; errors (frames): {h['errors_frames']}"))
    return "\n".join(L) + "\n"


def table_vehicle_b(m, exp):
    L = [f"Table X. Vehicle B identification of {exp} (human-reviewed clips only; correct = box IoU ≥ 0.5 with the reviewed box).", "",
         "| Split | Reviewed clips (n) | Correct | Clips |", "|---|---:|---:|---|"]
    for s in ("train", "val"):
        v = m.get(s, {}).get("vehicle_b_identification")
        if isinstance(v, dict):
            L.append(f"| {s} | {v['n']} | {v['correct']} | " + ", ".join(f"`{k}` {'✓' if ok else '✗'}" for k, ok in v["clips"].items()) + " |")
        else:
            L.append(f"| {s} | 0 | — | {PENDING} |")
    return "\n".join(L) + "\n"


def table_lane(m, exp, level, title):
    L = [f"Table X. Lane-change detection of {exp} — {title}.", "",
         "| Split | Clips with a reference row | Matched pairs | TP | FP | FN | Precision | Recall | F1 | Mean tIoU | Start MAE (frames) | Start mean error | End MAE (frames) | Direction acc. |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in ("train", "val"):
        x = m.get(s, {}).get("lane_change_" + level)
        if isinstance(x, dict):
            L.append(f"| {s} | {x['n_clips_with_reference_row']} | {x['n_matched_pairs']} | {x['tp']} | {x['fp']} | {x['fn']} | "
                     f"{fmt(x['precision'])} | {fmt(x['recall'])} | {fmt(x['f1'])} | {fmt(x['mean_tiou'], nd=3)} | "
                     f"{fmt(x['start_mae_frames'])} | {fmt(x['start_mean_error_frames'])} | {fmt(x['end_mae_frames'])} | {fmt(x['direction_accuracy'])} |")
        else:
            L.append(f"| {s} | 0 | | | | | {PENDING} | | | | | | | |")
    return "\n".join(L) + "\n"


def table_draft_other(m, exp):
    L = [f"Table X. Sudden stop and following distance of {exp} — agreement with UNREVIEWED draft labels (not accuracy).", "",
         "| Split | Sudden stop: clips | TP | FP | FN | Agreement | Safe distance: clips with a clear draft value | Agreement | No prediction |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in ("train", "val"):
        a = m.get(s, {}).get("sudden_stop_presence_draft_unreviewed") or {}
        b = m.get(s, {}).get("safe_distance_draft_unreviewed") or {}
        L.append(f"| {s} | {a.get('n', '—')} | {a.get('tp', '—')} | {a.get('fp', '—')} | {a.get('fn', '—')} | {fmt(a.get('agreement'), True)} | "
                 f"{b.get('n_with_clear_draft_value', '—')} | {fmt(b.get('agreement'), True)} | {b.get('n_no_prediction', '—')} |")
    L += ["", f"Human-reviewed sudden-stop and safe-distance labels: {PENDING}."]
    return "\n".join(L) + "\n"


def table_perf(m, exp):
    r = m["_run"]
    env = r["environment"]
    L = [f"Table X. Processing time of {exp} per 5-second clip (CPU only).", "",
         "| Split | Clips | Mean total (s) | Median total (s) | Max total (s) | Mean detection + tracking (s) | Mean lane model (s) |",
         "|---|---:|---:|---:|---:|---:|---:|"]
    for s in ("train", "val"):
        p = m.get(s, {}).get("processing_time_s")
        if p:
            L.append(f"| {s} | {p['n']} | {p['mean_total']} | {p['median_total']} | {p['max_total']} | {p['mean_detection_tracking']} | {p['mean_lanes']} |")
    L += ["", f"Environment: {env.get('platform')}, {env.get('cpu_count')} CPU cores, Python {env.get('python')}, "
              f"NumPy {env.get('numpy')}, OpenCV {env.get('cv2')}, ONNX Runtime {env.get('onnxruntime')}. "
              f"Model files (SHA-256, first 16 hex): {r.get('models_sha256_16')}. Code commit {r.get('code_commit')} "
              f"(fingerprint {r.get('code_fingerprint')})."]
    return "\n".join(L) + "\n"


def table_pending(m):
    L = ["Table X. Metrics that cannot be measured yet.", "", "| Metric | Status |", "|---|---|"]
    for k, v in m.get("not_measurable_yet", {}).items():
        L.append(f"| {k.replace('_', ' ')} | {v} |")
    return "\n".join(L) + "\n"


def table_before_after(mb, ma, base, exp):
    rows = [("Collision hit rate ±0.5 s (source annotation)", lambda S: (S.get("collision_vs_source_annotation") or {}).get("hit_rate_within_0_5s"), True),
            ("Collision MAE s (source annotation)", lambda S: (S.get("collision_vs_source_annotation") or {}).get("mae_s"), False),
            ("Vehicle B correct (human)", lambda S: (lambda v: f"{v['correct']}/{v['n']}" if isinstance(v, dict) else PENDING)(S.get("vehicle_b_identification")), False),
            ("Lane change F1 (human)", lambda S: (S.get("lane_change_human_reviewed") or {}).get("f1") if isinstance(S.get("lane_change_human_reviewed"), dict) else PENDING, False),
            ("Lane change mean tIoU (human)", lambda S: (S.get("lane_change_human_reviewed") or {}).get("mean_tiou") if isinstance(S.get("lane_change_human_reviewed"), dict) else PENDING, False),
            ("Lane change F1 (draft, unreviewed)", lambda S: (S.get("lane_change_draft_unreviewed") or {}).get("f1"), False),
            ("Lane change mean tIoU (draft, unreviewed)", lambda S: (S.get("lane_change_draft_unreviewed") or {}).get("mean_tiou"), False)]
    L = [f"Table X. Before ({base}) and after ({exp}).", "", f"| Metric | Split | {base} | {exp} |", "|---|---|---:|---:|"]
    for name, fn, pct in rows:
        for s in ("train", "val"):
            if s in mb and s in ma:
                L.append(f"| {name} | {s} | {fmt(fn(mb[s]), pct)} | {fmt(fn(ma[s]), pct)} |")
    return "\n".join(L) + "\n"


def figure_collision(comps, exp):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2), dpi=200, sharey=True)
    for ax, s in zip(axes, ("train", "val")):
        e = [c["collision"]["vs_source_annotation"]["error_frames"] / 10 for c in comps
             if c["split"] == s and c["collision"].get("vs_source_annotation") and c["collision"]["vs_source_annotation"]["error_frames"] is not None]
        if not e:
            continue
        lim = 4.0
        e = [max(-lim, min(lim, x)) for x in e]
        ax.axvspan(-0.55, 0.55, color="#e6f2ea", zorder=0)
        ax.hist(e, bins=[(x - 0.5) / 10 for x in range(-40, 42)], color="#2f6b45", edgecolor="white", linewidth=0.3)
        ax.set_title(f"{'Training' if s == 'train' else 'Validation'} (n = {len(e)})", fontsize=10)
        ax.set_xlabel("Predicted − annotated collision time (s)\n(errors beyond ±4 s drawn at ±4 s)", fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Clips")
    fig.tight_layout()
    out = F / f"fig_5.1_{exp}_collision_error.png"
    fig.savefig(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True)
    ap.add_argument("--baseline", default="")
    a = ap.parse_args()
    T.mkdir(parents=True, exist_ok=True); F.mkdir(parents=True, exist_ok=True)
    m, comps = load(a.exp)
    parts = [table_collision(m, a.exp), table_vehicle_b(m, a.exp),
             table_lane(m, a.exp, "human_reviewed", "HUMAN-REVIEWED ground truth"),
             table_lane(m, a.exp, "draft_unreviewed", "agreement with UNREVIEWED draft labels (not accuracy)"),
             table_draft_other(m, a.exp), table_perf(m, a.exp), table_pending(m)]
    names = ["collision", "vehicle_b", "lane_change_human", "lane_change_draft", "draft_other_events", "performance", "pending"]
    for n, p in zip(names, parts):
        (T / f"5.1_{a.exp}_{n}.md").write_text(p)
    if a.baseline:
        mb, _ = load(a.baseline)
        (T / f"5.1_{a.exp}_vs_{a.baseline}.md").write_text(table_before_after(mb, m, a.baseline, a.exp))
    fig = figure_collision(comps, a.exp)
    print("\n".join(parts)); print("figure:", fig)


if __name__ == "__main__":
    main()
