#!/usr/bin/env python3
"""Subsample analysis: H1 magnitude and H2 direction by LLM sentiment label.

Reviewer-anticipated question: does the magnitude amplification differ
between bull-events, bear-events, and neutral-events? Does the
direction hit rate differ?

Reads:
    outputs/event_study_windows.csv

Writes:
    outputs/sentiment_subsample_results.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PRIMARY_WINDOWS = [5, 15, 60]
ASSETS = ["eurusd", "ndx"]
SEED = 42


def first_per_cluster(sub: pd.DataFrame) -> pd.DataFrame:
    return sub.sort_values("timestamp_utc").drop_duplicates("event_cluster_id", keep="first")


def magnitude_by_sentiment(windows: pd.DataFrame) -> list[dict]:
    rows = []
    for asset in ASSETS:
        for w in PRIMARY_WINDOWS:
            sub_all = windows[(windows["asset"] == asset) & (windows["window_min"] == w)].copy()
            sub_all = first_per_cluster(sub_all)
            for label in ["bull", "bear", "neutral"]:
                sub = sub_all[sub_all["target_sentiment"] == label]
                if len(sub) < 30:
                    continue
                event_abs = sub["delta_pct"].abs().dropna().to_numpy(dtype=float)
                if len(event_abs) < 30:
                    continue
                rows.append({
                    "asset": asset,
                    "window_min": w,
                    "sentiment": label,
                    "n_clusters": len(sub),
                    "mean_abs_event": float(event_abs.mean()),
                    "median_abs_event": float(np.median(event_abs)),
                    "p25_abs_event": float(np.percentile(event_abs, 25)),
                    "p75_abs_event": float(np.percentile(event_abs, 75)),
                })
    return rows


def direction_by_sentiment(windows: pd.DataFrame) -> list[dict]:
    rows = []
    for asset in ASSETS:
        for w in PRIMARY_WINDOWS:
            sub_all = windows[
                (windows["asset"] == asset)
                & (windows["window_min"] == w)
                & (windows["target_delta_pct"].notna())
                & (windows["target_delta_pct"] != 0)
                & (windows["target_sentiment"].isin(["bull", "bear"]))
            ].copy()
            sub_all = first_per_cluster(sub_all)
            for label in ["bull", "bear"]:
                sub = sub_all[sub_all["target_sentiment"] == label]
                if len(sub) < 30:
                    continue
                # For bull: hit if realized > 0; for bear: hit if realized < 0
                realized = sub["target_delta_pct"].to_numpy()
                if label == "bull":
                    correct = int((realized > 0).sum())
                else:
                    correct = int((realized < 0).sum())
                n = len(sub)
                p_binom = stats.binomtest(correct, n, p=0.5, alternative="greater").pvalue
                ci = stats.binomtest(correct, n, p=0.5).proportion_ci(method="wilson")
                rows.append({
                    "asset": asset,
                    "window_min": w,
                    "sentiment": label,
                    "n_clusters": n,
                    "correct": correct,
                    "hit_rate": correct / n,
                    "ci95_low": ci.low,
                    "ci95_high": ci.high,
                    "p_binom_greater": p_binom,
                })
    return rows


def main():
    windows = pd.read_csv("outputs/event_study_windows.csv",
                           parse_dates=["timestamp_utc"])
    print(f"Windows: {len(windows)}\n")

    print("=== Magnitude by sentiment ===")
    mag = pd.DataFrame(magnitude_by_sentiment(windows))
    print(mag.to_string(index=False))
    print()

    print("=== Direction by sentiment (own-side hit rate) ===")
    dir_ = pd.DataFrame(direction_by_sentiment(windows))
    print(dir_.to_string(index=False))
    print()

    # Combined output: mag + dir merged
    out_mag = Path("outputs/sentiment_subsample_magnitude.csv")
    out_dir = Path("outputs/sentiment_subsample_direction.csv")
    mag.to_csv(out_mag, index=False)
    dir_.to_csv(out_dir, index=False)
    print(f"Wrote {out_mag} ({len(mag)} rows)")
    print(f"Wrote {out_dir} ({len(dir_)} rows)")


if __name__ == "__main__":
    main()
