#!/usr/bin/env python3
"""Validate core research outputs after running the pipeline.

This is a lightweight guardrail, not a full test suite. It catches the
methodology failures that are easy to reintroduce: unaligned price coverage,
wrong EUR/USD sentiment convention, missing robust outputs, stale H8 NaNs,
and absent FDR q-values.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


OUT = Path("outputs")


def fail(message: str):
    print(f"FAIL: {message}")
    return 1


def warn(message: str):
    print(f"WARN: {message}")


def require_file(path: Path):
    if not path.exists():
        raise AssertionError(f"missing {path}")


def require_columns(df: pd.DataFrame, columns: list[str], name: str):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise AssertionError(f"{name} missing columns: {missing}")


def main():
    try:
        required = [
            "events.csv",
            "events_sentiment.csv",
            "event_study_windows.csv",
            "methodology_summary.csv",
            "h1_results.csv",
            "h2_results.csv",
            "h3_results.csv",
            "h4_results.csv",
            "h4_periods.csv",
            "h8_results.csv",
            "h10_results.csv",
            "h14_results.csv",
        ]
        for name in required:
            require_file(OUT / name)

        methodology = pd.read_csv(OUT / "methodology_summary.csv")
        settings = dict(zip(methodology["setting"], methodology["value"]))
        if settings.get("eurusd_sentiment_convention") != "sentiment_usd evaluated against USD proxy = -EUR/USD return":
            raise AssertionError("EUR/USD sentiment convention not recorded as USD proxy")
        dropped = int(settings.get("events_after_common_range_dropped", "0"))
        if dropped:
            warn(f"{dropped} events were outside common price coverage and were dropped")

        windows = pd.read_csv(OUT / "event_study_windows.csv", parse_dates=["timestamp_utc"])
        require_columns(
            windows,
            [
                "event_cluster_id",
                "asset_target",
                "target_sentiment",
                "target_delta_pct",
                "base_ts",
                "target_ts",
                "volume_ratio",
            ],
            "event_study_windows.csv",
        )
        eur_targets = set(windows.loc[windows["asset"] == "eurusd", "asset_target"].dropna().unique())
        if eur_targets != {"USD proxy (-EUR/USD)"}:
            raise AssertionError(f"unexpected EUR/USD target labels: {eur_targets}")
        if windows["event_cluster_id"].nunique() >= windows["event_id"].nunique():
            raise AssertionError("event clustering did not reduce event count")
        if windows["volume_ratio"].notna().sum() == 0:
            raise AssertionError("volume_ratio is entirely missing")

        h1 = pd.read_csv(OUT / "h1_results.csv")
        require_columns(h1, ["n_events_raw", "n_events_used", "q_mwu_greater"], "h1_results.csv")
        if not (h1["n_events_used"] <= h1["n_events_raw"]).all():
            raise AssertionError("H1 used event count exceeds raw count")

        h2 = pd.read_csv(OUT / "h2_results.csv")
        require_columns(h2, ["asset_target", "q_binom_greater"], "h2_results.csv")
        eur_h2 = h2[h2["asset"] == "eurusd"]
        if not eur_h2["asset_target"].eq("USD proxy (-EUR/USD)").all():
            raise AssertionError("H2 EUR/USD rows are not labeled as USD proxy")

        h3 = pd.read_csv(OUT / "h3_results.csv")
        require_columns(h3, ["cov_type", "se_interaction", "q_interaction"], "h3_results.csv")
        if not h3["cov_type"].isin(["cluster", "HC3"]).all():
            raise AssertionError("H3 does not report robust/cluster covariance")

        h4 = pd.read_csv(OUT / "h4_results.csv")
        require_columns(
            h4,
            ["coef_agg_target_sentiment", "se_agg_target_sentiment", "p_agg_target_sentiment", "q_agg_target_sentiment"],
            "h4_results.csv",
        )

        h8 = pd.read_csv(OUT / "h8_results.csv")
        require_columns(h8, ["mean_pre_abs", "mean_post_abs", "mean_baseline_abs"], "h8_results.csv")
        if h8[["mean_pre_abs", "mean_post_abs", "mean_baseline_abs"]].isna().any().any():
            raise AssertionError("H8 still contains NaNs in core means")

        h10 = pd.read_csv(OUT / "h10_results.csv")
        if "volume_caveat" not in h10.columns:
            raise AssertionError("H10 does not carry the volume proxy caveat")

        h14 = pd.read_csv(OUT / "h14_results.csv")
        require_columns(
            h14,
            ["pearson_eurusd_ndx", "pearson_usdproxy_ndx", "sign_match_usdproxy_ndx"],
            "h14_results.csv",
        )

    except Exception as exc:
        return fail(str(exc))

    print("OK: outputs passed methodology sanity checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
