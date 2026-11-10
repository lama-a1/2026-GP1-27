"""Build docs/gp_report/evidence_registry.csv: every substantive claim or number in the GP report sections,
with the experiment, commit, data, review status, result file and verification status behind it.

    python tools/build_evidence_registry.py --baseline EXP-007

Fixed claims are listed below; result numbers are read from results/<EXP>_SUMMARY/metrics.json so they cannot
drift from the outputs. Statuses: Verified, Preliminary, Pending Review, Not Evaluated.
"""
import argparse, csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
F = ["claim_id", "report_section", "claim_or_metric", "value", "experiment_id", "git_commit", "data_split_or_source",
     "ground_truth_status", "result_file", "citation", "verification_status", "notes"]

FIXED = [
    ("D-01", "4.4.3", "Final dataset size and composition", "137 clips: 76 rear-end, 61 lane-change; 70 CCD, 67 DADA-2000; 91/22/24 train/val/test",
     "", "", "experiments/dataset/dataset_index.csv (MD5 1b0ca89e...)", "n/a (file count)", "docs/gp_report/tables/table_dataset_distribution.md", "", "Verified",
     "Matches the team's final split manifests of 10 Nov 2026; all 137 video files exist"),
    ("D-01b", "4.4.3", "Excluded weather clips", "12 clips removed (snow/rain seen); exactly the 12 flagged in clip_job_map.csv; no remaining clip changed split",
     "", "", "experiments/dataset/excluded_clips.csv", "team decision", "", "", "Verified", ""),
    ("D-02", "4.4.3", "Splits are disjoint and match the index", "0 shared clip IDs; 0 duplicates within a split; 0 index/split mismatches", "", "", "experiments/dataset/splits/*.txt",
     "n/a", "", "", "Verified", ""),
    ("D-03", "4.4.3", "No exact or near-duplicate footage across splits", "0 identical files (MD5); min cross-split dHash distance 66/256 bits; 0 pairs < 15 bits",
     "", "", "137 clips", "n/a", "experiments/dataset/leakage_check_v2.json", "", "Verified",
     "Cannot detect two clips cut from different moments of the same source video"),
    ("D-03b", "4.4.3", "DADA file-name partition differs from the Siyaq split", "37 of 67 DADA clips are in a different Siyaq split than their file name suggests; no shared (type, id); no code infers split from names",
     "", "", "67 DADA clips", "n/a", "experiments/dataset/leakage_check_v2.json", "", "Verified", "Confusion risk, not leakage"),
    ("D-03c", "4.4.3", "CCD clips from the same YouTube upload in different splits", "not checked", "", "", "70 CCD clips", "n/a", "", "", "Not Evaluated",
     "Needs Crash-1500.txt (youtubeID, startframe)"),
    ("D-04", "4.4.3", "Test split was viewed during early development", "draft-label agreement and YOLOv8n/s comparison computed on test (4 Nov); HIST-02 also ran on test",
     "HIST-01, HIST-02", "9c51805", "test", "draft_unreviewed", "experiments/EXPERIMENT_LOG.csv", "", "Verified", "Threat to validity"),
    ("D-05", "4.4.3", "CVAT exports contain no human annotation", "1,226 imported tracks, all role 'Other vehicle', 0 tags",
     "", "", "Task1-3.zip (exported 2026-11-04)", "pre-annotation", "", "", "Verified", ""),
    ("D-06", "4.4.3", "Human-reviewed ground truth available", "3 train clips (000023, 000152, dada_training_type11_53), each partial; 0 val; 0 test; Batch 1 (20 train clips) prepared",
     "", "", "train", "human_reviewed", "experiments/ground_truth/human_reviewed.json", "", "Verified", ""),
    ("D-07", "4.4.3", "Accident type per clip", "assigned during curation with GenAI assistance", "", "", "all", "draft_unreviewed",
     "dataset_index.csv", "", "Pending Review", "Not yet confirmed clip by clip"),
    ("D-08", "4.4.3", "CCD licence", "repository MIT; no separate video terms stated", "", "", "CCD", "n/a", "", "ccd2020github",
     "Verified", "Checked on GitHub 2026-11-10"),
    ("D-09", "4.4.3", "DADA-2000 licence", "not stated in the paper or pages checked", "", "", "DADA-2000", "n/a", "", "fang2019dada",
     "Pending Review", "Team must obtain the terms from the download page"),
    ("I-01", "4.6", "ByteTrack port equals the official implementation", "149/149 clips identical (box difference <= 0.05 px)",
     "HIST-02", "0807320", "all 149 clips (same detections)", "n/a", "experiments/history/HIST-02_bytetrack_vs_iou_trainval.json",
     "zhang2022bytetrack", "Verified", "Re-checked 2026-11-10"),
    ("I-02", "4.6", "No neural network was trained or fine-tuned", "YOLOv8n (COCO) and TwinLiteNet (BDD100K) used with published weights",
     "", "d3ea9c2", "", "n/a", "siyaq_cv/models/*.onnx (SHA-256 in run_metadata.json)", "jocher2023yolov8; che2023twinlitenet", "Verified", ""),
    ("I-03", "4.6", "TwinLiteNet ONNX equals the official checkpoint", "ONNX export compared with the official PyTorch weights",
     "", "ecadb55", "", "n/a", "", "che2023twinlitenet", "Preliminary", "Comparison was done during development; no stored record"),
    ("I-04", "4.6", "Recording-car speed from optical flow is unreliable", "correlation about 0.5 with GPS speed on 4 CCD clips",
     "HIST-01", "9c51805", "4 CCD clips", "on-screen GPS", "", "", "Preliminary", "Development record; not re-run"),
    ("I-05", "4.6", "Monocular lateral offset overstated at long range", "about 40 % at about 14 m (box-size vs lane-line geometry)",
     "EXP-006", "d3ea9c2", "000152 (train)", "n/a", "docs/EXPERIMENT_LOG.md#exp-006", "stein2003vision", "Preliminary", "One clip"),
    ("M-01", "4.6.1", "ByteTrack vs IoU tracker (train+val)", "tracks/clip 7.55 -> 4.92; mean length 20.7 -> 22.6; collision hit 0.699 -> 0.691",
     "HIST-02", "0807320", "train+val (123)", "source_annotation; draft_unreviewed",
     "experiments/history/HIST-02_bytetrack_vs_iou_trainval.json", "", "Preliminary", "Before SIYAQ-BUG-001"),
    ("M-02", "4.6.1", "SIYAQ-BUG-001 collision fix", "impact 6.234 s -> 5.037 s on the reported clip", "SIYAQ-BUG-001", "f2ffda1",
     "team-reported clip", "human_reviewed (team-reported)", "tests/test_collision_time.py", "", "Preliminary", "Single clip"),
    ("M-03", "4.6.1", "EXP-004 lane-change bounds (human clip)", "10-19 -> 14-21 (reference 15-22)", "EXP-004", "7135e3c",
     "dada_training_type11_53 (train)", "human_reviewed", "docs/EXPERIMENT_LOG.md#exp-004", "", "Verified", "n = 1"),
    ("M-04", "4.6.1", "EXP-004 lane-change bounds (draft)", "tIoU train 0.380 -> 0.512 (n=22); val 0.330 -> 0.407 (n=4)", "EXP-004",
     "7135e3c", "train+val", "draft_unreviewed", "docs/EXPERIMENT_LOG.md#exp-004", "", "Preliminary", "Draft-label agreement, not accuracy"),
    ("M-05", "4.6.1", "EXP-005 impact-anchored Vehicle B selection", "reviewed B 1/2 (both rules); val collision hits 18 -> 16",
     "EXP-005", "5492f6b", "train+val", "human_reviewed (2); source_annotation", "docs/EXPERIMENT_LOG.md#exp-005", "", "Preliminary", "Not adopted"),
    ("M-06", "4.6.1", "EXP-006 lane-entry onset", "human start MAE 7.5 -> 0.5 frames (in-sample, n=2); draft train tIoU 0.510 -> 0.499",
     "EXP-006", "d3ea9c2", "train", "human_reviewed (in-sample); draft_unreviewed", "docs/EXPERIMENT_LOG.md#exp-006",
     "izquierdo2019prevention", "Preliminary", "Not adopted"),
    ("M-07", "4.6.1", "Regression test suite", "75 passed, 3 expected failures (70 engine tests at d3ea9c2 + 5 experiment-tool tests)", "", "d3ea9c2", "", "n/a", "tests/", "", "Verified", ""),
]


def g(d, *ks):
    for k in ks:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default="EXP-008")
    a = ap.parse_args()
    rows = [dict(zip(F, r)) for r in FIXED]
    mp = ROOT / "results" / f"{a.baseline}_SUMMARY" / "metrics.json"
    if mp.exists():
        m = json.loads(mp.read_text())
        commit = m["_run"]["code_commit"]
        res = f"results/{a.baseline}_SUMMARY/metrics.json"
        i = 1
        for s in ("train", "val"):
            S = m.get(s, {})
            c = S.get("collision_vs_source_annotation") or {}
            rows.append(dict(zip(F, [f"R-{i:02d}", "5.1", f"Collision hit rate within 0.5 s ({s})",
                                     f"{c.get('hit_rate_within_0_5s')} (n={c.get('n')}); MAE {c.get('mae_s')} s",
                                     a.baseline, commit, s, "source_annotation", res, "", "Preliminary",
                                     "Source crash frames, not team-reviewed"]))); i += 1
            vb = S.get("vehicle_b_identification")
            rows.append(dict(zip(F, [f"R-{i:02d}", "5.1", f"Vehicle B identification ({s})",
                                     f"{vb['correct']}/{vb['n']}" if isinstance(vb, dict) else "Pending approved Ground Truth",
                                     a.baseline, commit, s, "human_reviewed", res, "",
                                     "Verified" if isinstance(vb, dict) else "Not Evaluated",
                                     "Very small sample" if isinstance(vb, dict) else ""]))); i += 1
            for lvl, st in (("human_reviewed", "Verified"), ("draft_unreviewed", "Preliminary")):
                x = S.get("lane_change_" + lvl)
                val = (f"P={x['precision']} R={x['recall']} F1={x['f1']} tIoU={x['mean_tiou']} (pairs={x['n_matched_pairs']}, rows={x['n_clips_with_reference_row']})"
                       if isinstance(x, dict) else "Pending approved Ground Truth")
                rows.append(dict(zip(F, [f"R-{i:02d}", "5.1", f"Lane-change detection vs {lvl} ({s})", val, a.baseline, commit, s, lvl, res, "",
                                         (st if isinstance(x, dict) else "Not Evaluated"),
                                         "Draft-label agreement, not accuracy" if lvl == "draft_unreviewed" else "Very small sample"]))); i += 1
            p = S.get("processing_time_s")
            if p:
                rows.append(dict(zip(F, [f"R-{i:02d}", "5.1", f"Processing time per clip ({s})",
                                         f"mean {p['mean_total']} s, max {p['max_total']} s (n={p['n']})", a.baseline, commit, s, "n/a", res, "",
                                         "Verified", "Measured on the experiment machine (see run_metadata.json)"]))); i += 1
        for k, v in m.get("not_measurable_yet", {}).items():
            rows.append(dict(zip(F, [f"R-{i:02d}", "5.1", k.replace("_", " "), v, "", "", "", "none", "", "", "Not Evaluated", ""]))); i += 1
    out = ROOT / "docs" / "gp_report" / "evidence_registry.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=F); w.writeheader(); w.writerows(rows)
    print(out, len(rows), "rows")


if __name__ == "__main__":
    main()
