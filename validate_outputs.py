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
            "cluster_event_study_windows.csv",
            "methodology_summary.csv",
            "h1_results.csv",
            "h2_results.csv",
            "h3_results.csv",
            "h4_results.csv",
            "h4_periods.csv",
            "h8_results.csv",
            "h10_results.csv",
            "h14_results.csv",
            "cluster_sentiment_results.csv",
            "range_outcomes_results.csv",
            "abnormal_z_results.csv",
            "targeted_category_results.csv",
            "pre_post_stability_results.csv",
            "multivariate_results.csv",
            "outlier_robustness_results.csv",
            "model_consensus_results.csv",
        ]
        for name in required:
            require_file(OUT / name)

        methodology = pd.read_csv(OUT / "methodology_summary.csv")
        settings = dict(zip(methodology["setting"], methodology["value"]))
        if settings.get("eurusd_sentiment_convention") != "sentiment_usd evaluated against USD proxy = -EUR/USD return":
            raise AssertionError("EUR/USD sentiment convention not recorded as USD proxy")
        for setting in [
            "cluster_level_outputs",
            "abnormal_return_standardization",
            "range_outcomes",
            "pre_post_cutoff_utc",
            "multivariate_controls",
        ]:
            if setting not in settings:
                raise AssertionError(f"methodology summary missing {setting}")
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
                "range_pct",
                "max_abs_move_pct",
                "target_max_abs_move_pct",
                "abnormal_return_pct",
                "abs_return_z",
                "range_z",
                "max_abs_move_z",
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
        if windows["max_abs_move_z"].notna().sum() == 0:
            raise AssertionError("standardized max_abs_move_z is entirely missing")

        clusters = pd.read_csv(OUT / "cluster_event_study_windows.csv", parse_dates=["timestamp_utc"])
        require_columns(
            clusters,
            [
                "event_cluster_id",
                "asset",
                "window_min",
                "n_headlines",
                "dominant_category",
                "cluster_target_sentiment",
                "cluster_abs_target_strength",
                "max_abs_move_z",
            ],
            "cluster_event_study_windows.csv",
        )
        if len(clusters) >= len(windows):
            raise AssertionError("cluster-level output did not reduce the event-window table")
        duplicated_cluster_windows = clusters.duplicated(["event_cluster_id", "asset", "window_min"]).sum()
        if duplicated_cluster_windows:
            raise AssertionError(f"cluster output has duplicate cluster/asset/window rows: {duplicated_cluster_windows}")

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

        cluster_sentiment = pd.read_csv(OUT / "cluster_sentiment_results.csv")
        require_columns(cluster_sentiment, ["hit_rate", "q_binom_greater"], "cluster_sentiment_results.csv")

        range_outcomes = pd.read_csv(OUT / "range_outcomes_results.csv")
        require_columns(
            range_outcomes,
            ["metric", "ratio", "q_mwu_greater"],
            "range_outcomes_results.csv",
        )
        if pd.to_numeric(range_outcomes["ratio"], errors="coerce").isna().any():
            raise AssertionError("range/max move outcomes contain missing ratios")
        if (pd.to_numeric(range_outcomes["ratio"], errors="coerce") <= 1).any():
            warn("some range/max move outcomes are not above matched baseline")

        abnormal_z = pd.read_csv(OUT / "abnormal_z_results.csv")
        require_columns(abnormal_z, ["metric", "mean_z", "q_wilcoxon_gt0"], "abnormal_z_results.csv")
        if not {"abs_return_z", "range_z", "max_abs_move_z"}.issubset(set(abnormal_z["metric"])):
            raise AssertionError("abnormal_z_results.csv missing core z-score metrics")

        targeted = pd.read_csv(OUT / "targeted_category_results.csv")
        require_columns(
            targeted,
            ["hypothesis", "category", "mean_max_abs_move_z", "q_max_abs_move_z_wilcoxon_gt0"],
            "targeted_category_results.csv",
        )

        stability = pd.read_csv(OUT / "pre_post_stability_results.csv")
        require_columns(
            stability,
            ["sample_period", "mean_max_abs_move_z", "q_max_abs_move_z_wilcoxon_gt0"],
            "pre_post_stability_results.csv",
        )
        if set(stability["sample_period"]) != {"pre_cutoff", "post_cutoff"}:
            raise AssertionError("pre/post stability output does not contain both sample periods")

        multivariate = pd.read_csv(OUT / "multivariate_results.csv")
        require_columns(multivariate, ["outcome", "term", "coef", "se", "p_value", "q_value"], "multivariate_results.csv")
        if not multivariate["cov_type"].eq("HC3").all():
            raise AssertionError("multivariate controls are not using HC3 robust covariance")

        robustness = pd.read_csv(OUT / "outlier_robustness_results.csv")
        require_columns(
            robustness,
            ["metric", "mean_raw", "mean_winsor_1pct", "q_winsor_wilcoxon_gt0"],
            "outlier_robustness_results.csv",
        )

        consensus = pd.read_csv(OUT / "model_consensus_results.csv")
        require_columns(consensus, ["hit_rate", "q_binom_greater"], "model_consensus_results.csv")

    except Exception as exc:
        return fail(str(exc))

    print("OK: outputs passed methodology sanity checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
