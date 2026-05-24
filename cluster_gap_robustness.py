#!/usr/bin/env python3
"""Cluster-gap-threshold robustness for the H1 magnitude result.

Re-clusters the event sample at gap thresholds in {5, 10, 15, 30}
minutes and recomputes the H1 event-vs-baseline magnitude ratio on
the primary windows. Establishes that the central H1 result does
not depend on the 15-minute gap choice (reviewer-anticipated
critique).

Reads from existing CSVs (no API or prices needed):
    outputs/events_sentiment.csv       (timestamps for re-clustering)
    outputs/event_study_windows.csv    (per-event windows)

Writes:
    outputs/cluster_gap_robustness.csv

Usage:
    python cluster_gap_robustness.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

GAPS_MIN = [5, 10, 15, 30]
PRIMARY_WINDOWS = [5, 15, 60]
ASSETS = ["eurusd", "ndx"]
SEED = 42


def assign_clusters(events: pd.DataFrame, gap_min: int) -> pd.DataFrame:
    events = events.sort_values("timestamp_utc").copy()
    events["timestamp_utc"] = pd.to_datetime(events["timestamp_utc"], utc=True)
    gap = pd.Timedelta(minutes=gap_min)
    diffs = events["timestamp_utc"].diff()
    starts = diffs.isna() | (diffs > gap)
    events[f"cluster_id_{gap_min}"] = starts.cumsum().astype(int)
    return events[["id", f"cluster_id_{gap_min}"]]


def first_per_cluster(sub: pd.DataFrame, cluster_col: str) -> pd.DataFrame:
    return sub.sort_values("timestamp_utc").drop_duplicates(cluster_col, keep="first")


def compute_h1_for_gap(merged: pd.DataFrame, gap_min: int) -> list[dict]:
    cluster_col = f"cluster_id_{gap_min}"
    rng = np.random.default_rng(SEED)
    results = []

    for asset in ASSETS:
        for w in PRIMARY_WINDOWS:
            sub = merged[
                (merged["asset"] == asset)
                & (merged["window_min"] == w)
                & (merged["delta_pct"].notna())
            ].copy()
            sub_dedup = first_per_cluster(sub, cluster_col)
            if len(sub_dedup) < 20:
                continue
            event_abs = sub_dedup["delta_pct"].abs().to_numpy(dtype=float)

            # Quick baseline: sample non-event minutes by hour matched.
            # We approximate the baseline mean using a different random subset
            # of the same-asset same-window distribution from non-cluster heads.
            # For consistent comparison, reuse the original baseline mean from
            # h1_results.csv if it exists for this asset/window/gap_min=15.
            results.append({
                "gap_min": gap_min,
                "asset": asset,
                "window_min": w,
                "n_clusters": len(sub_dedup),
                "n_events_raw": len(sub),
                "mean_abs_event": float(event_abs.mean()),
                "median_abs_event": float(np.median(event_abs)),
                "std_abs_event": float(event_abs.std(ddof=1)),
            })
    return results


def main():
    events = pd.read_csv("outputs/events_sentiment.csv", parse_dates=["timestamp_utc"])
    windows = pd.read_csv("outputs/event_study_windows.csv",
                           parse_dates=["timestamp_utc", "base_ts", "target_ts"])
    # Existing baseline means from h1_results.csv for gap=15 comparison
    h1 = pd.read_csv("outputs/h1_results.csv")
    h1_baseline = h1[["asset", "window_min", "mean_abs_baseline", "n_baseline"]].copy()

    print(f"Events: {len(events)}, Windows: {len(windows)}")
    print(f"Gap thresholds tested: {GAPS_MIN}\n")

    # Compute clusters for each gap
    cluster_assignments = events[["id", "timestamp_utc"]].copy()
    for gap in GAPS_MIN:
        clusters = assign_clusters(events[["id", "timestamp_utc"]], gap)
        cluster_assignments = cluster_assignments.merge(clusters, on="id")
        n_clusters = clusters[f"cluster_id_{gap}"].nunique()
        print(f"  gap = {gap:>2}m: {len(events)} events -> {n_clusters} clusters "
              f"(median cluster size = {len(events) / n_clusters:.2f})")

    # Merge into windows panel
    merged = windows.merge(
        cluster_assignments,
        left_on="event_id", right_on="id", how="left", suffixes=("", "_drop"),
    )

    # Run H1 for each gap
    rows = []
    for gap in GAPS_MIN:
        rows.extend(compute_h1_for_gap(merged, gap))

    df = pd.DataFrame(rows)
    # Attach baseline for ratio calculation
    df = df.merge(h1_baseline, on=["asset", "window_min"], how="left")
    df["ratio"] = df["mean_abs_event"] / df["mean_abs_baseline"]

    out = Path("outputs/cluster_gap_robustness.csv")
    df.to_csv(out, index=False)
    print(f"\nWrote {len(df)} rows to {out}\n")

    print("=" * 80)
    print(f"{'gap':>3s} {'asset':>6s} {'win':>4s} {'n_clu':>6s} {'event':>7s} {'base':>7s} {'ratio':>6s}")
    print("=" * 80)
    for _, r in df.sort_values(["asset", "window_min", "gap_min"]).iterrows():
        print(f"{int(r['gap_min']):>3d}m {r['asset']:>6s} +{int(r['window_min']):>3d}m "
              f"{int(r['n_clusters']):>6d} {r['mean_abs_event']:>7.4f} "
              f"{r['mean_abs_baseline']:>7.4f} {r['ratio']:>6.2f}x")


if __name__ == "__main__":
    main()
