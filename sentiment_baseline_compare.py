#!/usr/bin/env python3
"""Three-way comparison: LLM vs Loughran-McDonald vs FinBERT.

Runs the H2-equivalent direction test (binomial one-sided vs 0.5) on
each sentiment source over identical event windows. Reports side-by-side
hit rates with Wilson 95% CI and BH-FDR q-values.

Requires:
    outputs/events_sentiment.csv           (LLM)
    outputs/events_sentiment_baseline.csv  (Loughran-McDonald dictionary)
    outputs/events_sentiment_finbert.csv   (FinBERT-tone, optional)
    outputs/event_study_windows.csv

If the FinBERT file is missing, only LLM vs LM is reported.

Usage:
    python sentiment_baseline_compare.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

WINDOWS_MIN = [1, 5, 15, 60, 240]
ASSETS = ["eurusd", "ndx"]


def target_col(asset: str) -> str:
    return "target_delta_pct"


def sentiment_col(asset: str, source: str) -> str:
    if source == "llm":
        return "sentiment_usd" if asset == "eurusd" else "sentiment_ndx"
    if source == "lm":
        return "sentiment_usd_lm" if asset == "eurusd" else "sentiment_ndx_lm"
    if source == "finbert":
        return "sentiment_usd_finbert" if asset == "eurusd" else "sentiment_ndx_finbert"
    raise ValueError(f"unknown sentiment source: {source}")


def first_per_cluster(sub: pd.DataFrame) -> pd.DataFrame:
    if "event_cluster_id" not in sub.columns:
        return sub
    return sub.sort_values("timestamp_utc").drop_duplicates("event_cluster_id", keep="first")


def hit_rate_test(sub: pd.DataFrame, asset: str, source: str):
    sent_col = sentiment_col(asset, source)
    if sent_col not in sub.columns:
        return None
    rows = sub[
        sub[sent_col].isin(["bull", "bear"])
        & sub["target_delta_pct"].notna()
        & (sub["target_delta_pct"] != 0)
    ].copy()
    rows = first_per_cluster(rows)
    if len(rows) < 5:
        return None
    realized = np.where(rows["target_delta_pct"] > 0, "bull", "bear")
    correct = int((rows[sent_col].to_numpy() == realized).sum())
    n = len(rows)
    p_binom = stats.binomtest(correct, n, p=0.5, alternative="greater").pvalue
    ci = stats.binomtest(correct, n, p=0.5).proportion_ci(method="wilson")
    return {
        "source": source.upper(),
        "asset": asset,
        "n": n,
        "correct": correct,
        "hit_rate": correct / n,
        "ci95_low": ci.low,
        "ci95_high": ci.high,
        "p_binom_greater": p_binom,
    }


def bh_qvalues(pvalues):
    p = np.asarray(pvalues, dtype=float)
    q = np.full(len(p), np.nan)
    valid = np.isfinite(p)
    if not valid.any():
        return q
    p_valid = p[valid]
    order = np.argsort(p_valid)
    ranked = p_valid[order]
    m = len(ranked)
    adjusted = ranked * m / np.arange(1, m + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0, 1)
    q_valid = np.empty_like(adjusted)
    q_valid[order] = adjusted
    q[valid] = q_valid
    return q


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", default="outputs/events_sentiment.csv")
    parser.add_argument("--lm", default="outputs/events_sentiment_baseline.csv")
    parser.add_argument("--finbert", default="outputs/events_sentiment_finbert.csv")
    parser.add_argument("--windows", default="outputs/event_study_windows.csv")
    parser.add_argument("-o", "--output", default="outputs/sentiment_baseline_compare.csv")
    args = parser.parse_args()

    llm_df = pd.read_csv(args.llm)
    lm_df = pd.read_csv(args.lm)[["id", "sentiment_usd_lm", "sentiment_ndx_lm",
                                   "polarity_lm", "pos_count_lm", "neg_count_lm"]]
    win_df = pd.read_csv(args.windows)

    merged = win_df.merge(llm_df[["id", "sentiment_usd", "sentiment_ndx"]],
                          left_on="event_id", right_on="id", how="left", suffixes=("", "_llm"))
    if "sentiment_usd" not in merged.columns:
        merged = merged.rename(columns={"sentiment_usd_llm": "sentiment_usd",
                                         "sentiment_ndx_llm": "sentiment_ndx"})
    merged = merged.merge(lm_df, left_on="event_id", right_on="id", how="left", suffixes=("", "_lm_dup"))

    sources = ["llm", "lm"]
    finbert_path = Path(args.finbert)
    if finbert_path.exists():
        finbert_df = pd.read_csv(finbert_path)[["id", "sentiment_usd_finbert", "sentiment_ndx_finbert"]]
        merged = merged.merge(finbert_df, left_on="event_id", right_on="id",
                              how="left", suffixes=("", "_finbert_dup"))
        sources.append("finbert")
        print(f"Including FinBERT from {finbert_path}")
    else:
        print(f"FinBERT file not found at {finbert_path}, skipping")

    rows = []
    for w in WINDOWS_MIN:
        for asset in ASSETS:
            sub = merged[(merged["window_min"] == w) & (merged["asset"] == asset)]
            for source in sources:
                res = hit_rate_test(sub, asset, source)
                if res is None:
                    continue
                res["window_min"] = w
                rows.append(res)

    results = pd.DataFrame(rows)
    if not results.empty:
        results["q_binom_greater"] = bh_qvalues(results["p_binom_greater"].tolist())

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.output, index=False)
    print(f"Wrote {len(results)} rows to {args.output}\n")

    source_labels = [s.upper() for s in sources] if "sources" in dir() else ["LLM", "LM", "FINBERT"]
    print("=" * 100)
    print(f"{'src':>8s} {'asset':>6s} {'win':>4s} {'n':>5s} {'hit':>7s} {'CI95':>17s} {'p':>10s} {'q':>10s}")
    print("=" * 100)
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            for source_label in ["LLM", "LM", "FINBERT"]:
                row = results[
                    (results["asset"] == asset)
                    & (results["window_min"] == w)
                    & (results["source"] == source_label)
                ]
                if row.empty:
                    continue
                r = row.iloc[0]
                ci = f"[{r['ci95_low']:.3f},{r['ci95_high']:.3f}]"
                print(f"{source_label:>8s} {asset:>6s} {w:>4d} {int(r['n']):>5d} "
                      f"{r['hit_rate']:>7.1%} {ci:>17s} {r['p_binom_greater']:>10.4g} "
                      f"{r['q_binom_greater']:>10.4g}")

    print("\n--- Headline summary (LLM vs LM, LLM vs FinBERT) ---")
    for asset in ASSETS:
        for w in [5, 15, 60]:
            llm_row = results[(results["asset"] == asset) & (results["window_min"] == w) & (results["source"] == "LLM")]
            lm_row = results[(results["asset"] == asset) & (results["window_min"] == w) & (results["source"] == "LM")]
            fb_row = results[(results["asset"] == asset) & (results["window_min"] == w) & (results["source"] == "FINBERT")]
            if llm_row.empty:
                continue
            llm_hit = llm_row.iloc[0]["hit_rate"]
            lm_hit = lm_row.iloc[0]["hit_rate"] if not lm_row.empty else None
            fb_hit = fb_row.iloc[0]["hit_rate"] if not fb_row.empty else None
            parts = [f"LLM {llm_hit:.1%}"]
            if lm_hit is not None:
                parts.append(f"LM {lm_hit:.1%} ({(llm_hit-lm_hit)*100:+.1f}pp)")
            if fb_hit is not None:
                parts.append(f"FinBERT {fb_hit:.1%} ({(llm_hit-fb_hit)*100:+.1f}pp)")
            print(f"  {asset:6s} +{w:3d}m: " + "  vs  ".join(parts))


if __name__ == "__main__":
    main()
