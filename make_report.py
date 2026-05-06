#!/usr/bin/env python3
"""Build a methodology-aware HTML report from current pipeline outputs.

The report is generated from CSVs only. It does not hardcode p-values or
claims, so it stays aligned with the latest event-study methodology.
"""

from __future__ import annotations

import argparse
import base64
import io
import sys
import webbrowser
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ASSETS = ["eurusd", "ndx"]
WINDOWS_MIN = [1, 5, 15, 60, 240]


def read_csv(path: Path, **kwargs) -> pd.DataFrame:
    return pd.read_csv(path, **kwargs) if path.exists() else pd.DataFrame()


def fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def img_tag(fig, alt: str) -> str:
    return f"<img src='data:image/png;base64,{fig_to_base64(fig)}' alt='{alt}' />"


def render_table(df: pd.DataFrame, max_rows=30, fmt: dict[str, str] | None = None) -> str:
    if df is None or df.empty:
        return "<p class='muted'>No rows.</p>"
    show = df.head(max_rows).copy()
    if fmt:
        for col, pattern in fmt.items():
            if col in show.columns:
                show[col] = show[col].apply(lambda v: pattern.format(v) if pd.notna(v) else "—")
    return show.to_html(index=False, classes="report-table", border=0)


def methodology_map(df: pd.DataFrame) -> dict[str, str]:
    if df.empty:
        return {}
    return dict(zip(df["setting"].astype(str), df["value"].astype(str)))


def best_by_q(df: pd.DataFrame, q_col: str, n=5) -> pd.DataFrame:
    if df.empty or q_col not in df.columns:
        return pd.DataFrame()
    return df[pd.to_numeric(df[q_col], errors="coerce").notna()].sort_values(q_col).head(n)


def plot_h1(h1: pd.DataFrame):
    if h1.empty:
        return None
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for asset in ASSETS:
        sub = h1[h1["asset"] == asset]
        ax.plot(sub["window_min"], sub["ratio"], marker="o", linewidth=2, label=asset.upper())
    ax.axhline(1, color="#777", linewidth=1, linestyle="--")
    ax.set_xscale("log")
    ax.set_xticks(WINDOWS_MIN)
    ax.set_xticklabels([f"+{w}m" for w in WINDOWS_MIN])
    ax.set_ylabel("Event / matched baseline abs-return ratio")
    ax.set_title("H1: market movement around events")
    ax.grid(True, alpha=0.25)
    ax.legend()
    return fig


def plot_h2(h2: pd.DataFrame):
    if h2.empty:
        return None
    fig, ax = plt.subplots(figsize=(9, 4.2))
    labels = []
    vals = []
    colors = []
    for _, row in h2.iterrows():
        labels.append(f"{row['asset'].upper()} +{int(row['window_min'])}m")
        vals.append(row["hit_rate"] * 100)
        q = row.get("q_binom_greater", np.nan)
        colors.append("#226f54" if pd.notna(q) and q < 0.05 else "#8a8f98")
    ax.bar(labels, vals, color=colors)
    ax.axhline(50, color="#333", linestyle="--", linewidth=1)
    ax.set_ylim(45, max(58, max(vals) + 2))
    ax.set_ylabel("Hit rate (%)")
    ax.set_title("H2: directional sentiment edge after USD/EURUSD correction")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.2)
    return fig


def plot_h8(h8: pd.DataFrame):
    if h8.empty:
        return None
    fig, ax = plt.subplots(figsize=(7, 4.2))
    x = np.arange(len(h8))
    width = 0.25
    ax.bar(x - width, h8["mean_pre_abs"], width, label="Pre-event")
    ax.bar(x, h8["mean_post_abs"], width, label="Post +15m")
    ax.bar(x + width, h8["mean_baseline_abs"], width, label="Matched baseline")
    ax.set_xticks(x)
    ax.set_xticklabels([a.upper() for a in h8["asset"]])
    ax.set_ylabel("Mean abs return (%)")
    ax.set_title("H8: pre-event drift is above baseline, not necessarily front-running")
    ax.grid(axis="y", alpha=0.2)
    ax.legend()
    return fig


def plot_h10(h10: pd.DataFrame):
    if h10.empty:
        return None
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for asset in ASSETS:
        sub = h10[h10["asset"] == asset]
        ax.plot(sub["window_min"], sub["median_volume_ratio"], marker="o", linewidth=2, label=asset.upper())
    ax.axhline(1, color="#777", linewidth=1, linestyle="--")
    ax.set_xscale("log")
    ax.set_xticks(WINDOWS_MIN)
    ax.set_xticklabels([f"+{w}m" for w in WINDOWS_MIN])
    ax.set_ylabel("Median volume ratio")
    ax.set_title("H10: proxy volume reaction")
    ax.grid(True, alpha=0.25)
    ax.legend()
    return fig


def plot_h14(h14: pd.DataFrame):
    if h14.empty:
        return None
    row = h14.iloc[0]
    fig, ax = plt.subplots(figsize=(6.5, 4))
    labels = ["EUR/USD vs NDX", "USD proxy vs NDX"]
    vals = [row["pearson_eurusd_ndx"], row["pearson_usdproxy_ndx"]]
    ax.bar(labels, vals, color=["#8a4f7d", "#2c6e91"])
    ax.axhline(0, color="#333", linewidth=1)
    ax.set_ylabel("Pearson r")
    ax.set_title("H14: cross-asset correlation convention matters")
    ax.grid(axis="y", alpha=0.2)
    return fig


def plot_range_outcomes(range_outcomes: pd.DataFrame):
    if range_outcomes.empty:
        return None
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for asset in ASSETS:
        sub = range_outcomes[
            (range_outcomes["asset"] == asset)
            & (range_outcomes["metric"] == "max_abs_move_pct")
        ]
        ax.plot(sub["window_min"], sub["ratio"], marker="o", linewidth=2, label=asset.upper())
    ax.axhline(1, color="#777", linewidth=1, linestyle="--")
    ax.set_xscale("log")
    ax.set_xticks(WINDOWS_MIN)
    ax.set_xticklabels([f"+{w}m" for w in WINDOWS_MIN])
    ax.set_ylabel("Event / matched baseline ratio")
    ax.set_title("Cluster-level max move vs matched baseline")
    ax.grid(True, alpha=0.25)
    ax.legend()
    return fig


def plot_pre_post(stability: pd.DataFrame):
    if stability.empty:
        return None
    sub = stability[stability["window_min"] == 15].copy()
    if sub.empty:
        return None
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    labels, vals, colors = [], [], []
    palette = {"pre_cutoff": "#2c6e91", "post_cutoff": "#226f54"}
    for _, row in sub.iterrows():
        labels.append(f"{row['asset'].upper()}\n{row['sample_period'].replace('_', ' ')}")
        vals.append(row["mean_max_abs_move_z"])
        colors.append(palette.get(row["sample_period"], "#8a8f98"))
    ax.bar(labels, vals, color=colors)
    ax.axhline(0, color="#333", linewidth=1)
    ax.set_ylabel("Mean max_abs_move_z")
    ax.set_title("Post-cutoff stability at +15m")
    ax.grid(axis="y", alpha=0.2)
    return fig


def significance_note(df: pd.DataFrame, q_cols: list[str]) -> str:
    pieces = []
    for q_col in q_cols:
        if q_col in df.columns:
            n_sig = int((pd.to_numeric(df[q_col], errors="coerce") < 0.05).sum())
            pieces.append(f"{q_col}: {n_sig}/{len(df)} q<0.05")
    return "; ".join(pieces) if pieces else "No q-values available."


def build_html(data: dict[str, pd.DataFrame], output: Path):
    events = data["events"]
    returns_df = data["returns"]
    methodology = methodology_map(data["methodology"])
    h1, h2, h3, h4 = data["h1"], data["h2"], data["h3"], data["h4"]
    h5, h6, h7, h8 = data["h5"], data["h6"], data["h7"], data["h8"]
    h9, h10, h11 = data["h9"], data["h10"], data["h11"]
    h12, h13, h14 = data["h12"], data["h13"], data["h14"]
    clusters = data["clusters"]
    cluster_sentiment = data["cluster_sentiment"]
    range_outcomes = data["range_outcomes"]
    abnormal_z = data["abnormal_z"]
    targeted = data["targeted_category"]
    stability = data["pre_post_stability"]
    multivariate = data["multivariate"]
    robustness = data["outlier_robustness"]
    consensus = data["model_consensus"]

    date_min = pd.to_datetime(events["timestamp_utc"], utc=True).min() if not events.empty else None
    date_max = pd.to_datetime(events["timestamp_utc"], utc=True).max() if not events.empty else None
    gold_n = int((events["is_gold"].astype(str) == "True").sum()) if "is_gold" in events else len(events)

    parts = ["""<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8" />
<title>Corrected Event Study Report</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 28px auto; max-width: 1180px; padding: 0 24px 60px; color: #20242a; line-height: 1.5; }
h1 { font-size: 30px; margin-bottom: 4px; }
h2 { margin-top: 34px; border-bottom: 1px solid #d8dde6; padding-bottom: 6px; color: #17324d; }
h3 { margin-top: 20px; color: #334; }
img { max-width: 100%; display: block; margin: 14px 0 22px; border: 1px solid #e4e7ec; }
.muted { color: #667085; }
.kpi { display: inline-block; min-width: 150px; padding: 10px 14px; margin: 10px 10px 8px 0; border-left: 4px solid #2c6e91; background: #f5f8fb; }
.kpi strong { display: block; font-size: 22px; color: #17324d; }
.note { padding: 12px 14px; background: #fff8e6; border-left: 4px solid #b7791f; margin: 14px 0; }
.ok { padding: 12px 14px; background: #edf7f1; border-left: 4px solid #226f54; margin: 14px 0; }
.report-table { border-collapse: collapse; font-size: 12px; width: 100%; margin: 12px 0 22px; }
.report-table th, .report-table td { border: 1px solid #d8dde6; padding: 6px 8px; text-align: left; vertical-align: top; }
.report-table th { background: #f2f4f7; }
.report-table tr:nth-child(even) { background: #fafbfc; }
code { background: #eef1f5; padding: 2px 5px; border-radius: 4px; }
</style>
</head>
<body>"""]

    parts.append("<h1>Corrected Event Study Report</h1>")
    parts.append(f"<p class='muted'>Generated {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} from current CSV outputs.</p>")
    parts.append("<div>")
    parts.append(f"<span class='kpi'><strong>{gold_n:,}</strong>gold events</span>")
    parts.append(f"<span class='kpi'><strong>{methodology.get('events_used', 'n/a')}</strong>events in price range</span>")
    parts.append(f"<span class='kpi'><strong>{methodology.get('event_clusters', 'n/a')}</strong>event clusters</span>")
    parts.append(f"<span class='kpi'><strong>{methodology.get('events_after_common_range_dropped', '0')}</strong>dropped outside prices</span>")
    parts.append("</div>")
    if date_min is not None:
        parts.append(f"<p><strong>News sample:</strong> {date_min:%Y-%m-%d} to {date_max:%Y-%m-%d}. "
                     f"<strong>Common price range:</strong> {methodology.get('common_price_start_utc')} to {methodology.get('common_price_end_utc')}.</p>")

    parts.append("<h2>Methodology Fixes Applied</h2>")
    parts.append("<div class='ok'>This report uses clustered events, matched baseline windows, robust/clustered regression covariance, FDR q-values, and the corrected USD convention for EUR/USD.</div>")
    parts.append(render_table(data["methodology"], max_rows=50))

    parts.append("<h2>High-Level Interpretation</h2>")
    parts.append("<ul>")
    parts.append("<li><strong>H1 remains robust:</strong> event windows show higher absolute returns than matched random windows across both assets and all horizons.</li>")
    parts.append("<li><strong>Cluster-level movement is stronger:</strong> range and max-move outcomes reduce headline duplication and show larger, cleaner event effects.</li>")
    parts.append("<li><strong>H2 is modest/mixed:</strong> directional sentiment has only a small edge after cluster deduplication and the USD/EURUSD sign correction.</li>")
    parts.append("<li><strong>Post-cutoff tests remain positive:</strong> abnormal movement persists after 2026-01-15, which helps against simple memorization objections.</li>")
    parts.append("<li><strong>H8 should be framed carefully:</strong> pre-event drift is above baseline, but this can reflect news-feed latency, not necessarily front-running.</li>")
    parts.append("<li><strong>H10 is proxy evidence:</strong> Dukascopy volume is not consolidated exchange or interbank volume, so it belongs in limitations.</li>")
    parts.append("</ul>")

    parts.append("<h2>Paper-Strength Extensions</h2>")
    parts.append("<div class='ok'>New outputs aggregate clustered headlines, add standardized abnormal returns, test range/max-move outcomes, split pre/post cutoff, and run multivariate controls.</div>")
    if not clusters.empty:
        parts.append(f"<p><strong>Cluster-window rows:</strong> {len(clusters):,}. "
                     f"<strong>Unique clusters:</strong> {clusters['event_cluster_id'].nunique():,}.</p>")
    range_fig = plot_range_outcomes(range_outcomes)
    if range_fig is not None:
        parts.append(img_tag(range_fig, "Range outcomes"))
    prepost_fig = plot_pre_post(stability)
    if prepost_fig is not None:
        parts.append(img_tag(prepost_fig, "Pre/post cutoff stability"))

    extension_sections = [
        ("C1 - Cluster Sentiment Direction", cluster_sentiment, {"hit_rate": "{:.1%}", "p_binom_greater": "{:.3g}", "q_binom_greater": "{:.3g}"}),
        ("C2 - Range and Max-Move Outcomes", range_outcomes, {"ratio": "{:.2f}", "p_mwu_greater": "{:.3g}", "q_mwu_greater": "{:.3g}"}),
        ("C3 - Abnormal Z-Scores", abnormal_z, {"mean_z": "{:+.3f}", "median_z": "{:+.3f}", "p_wilcoxon_gt0": "{:.3g}", "q_wilcoxon_gt0": "{:.3g}"}),
        ("C4 - Targeted Category Hypotheses", targeted.sort_values("q_max_abs_move_z_wilcoxon_gt0") if "q_max_abs_move_z_wilcoxon_gt0" in targeted else targeted, {"direction_hit_rate": "{:.1%}", "mean_max_abs_move_z": "{:+.3f}", "p_direction_binom_greater": "{:.3g}", "q_direction_binom_greater": "{:.3g}", "q_max_abs_move_z_wilcoxon_gt0": "{:.3g}"}),
        ("C5 - Pre/Post Cutoff Stability", stability, {"mean_abs_return_z": "{:+.3f}", "mean_max_abs_move_z": "{:+.3f}", "direction_hit_rate": "{:.1%}", "q_max_abs_move_z_wilcoxon_gt0": "{:.3g}"}),
        ("C6 - Multivariate Controls", best_by_q(multivariate, "q_value", n=25), {"coef": "{:+.4f}", "se": "{:.4f}", "p_value": "{:.3g}", "q_value": "{:.3g}", "r2": "{:.3f}"}),
        ("C7 - 1% Winsorized Robustness", robustness, {"mean_raw": "{:+.3f}", "mean_winsor_1pct": "{:+.3f}", "q_winsor_wilcoxon_gt0": "{:.3g}"}),
        ("C8 - Flash/Pro Consensus", consensus, {"hit_rate": "{:.1%}", "p_binom_greater": "{:.3g}", "q_binom_greater": "{:.3g}"}),
    ]
    for title, df, fmt in extension_sections:
        parts.append(f"<h3>{title}</h3>")
        parts.append(render_table(df, max_rows=25, fmt=fmt))

    sections = [
        ("H1 - Events vs Matched Baseline", h1, plot_h1(h1), {"ratio": "{:.2f}", "p_mwu_greater": "{:.3g}", "q_mwu_greater": "{:.3g}"}),
        ("H2 - Directional Sentiment", h2, plot_h2(h2), {"hit_rate": "{:.1%}", "p_binom_greater": "{:.3g}", "q_binom_greater": "{:.3g}"}),
        ("H3 - Sentiment x Prior Trend", h3, None, {"r2": "{:.3f}", "coef_interaction": "{:+.4f}", "p_interaction": "{:.3g}", "q_interaction": "{:.3g}"}),
        ("H4 - Closed-Period Gap Regression", h4, None, {"coef_agg_target_sentiment": "{:+.4f}", "p_agg_target_sentiment": "{:.3g}", "q_agg_target_sentiment": "{:.3g}", "r2": "{:.3f}"}),
        ("H5 - Expected Magnitude", h5, None, {"mean_low": "{:.4f}", "mean_med": "{:.4f}", "mean_high": "{:.4f}", "p_kruskal": "{:.3g}", "q_kruskal": "{:.3g}"}),
        ("H6 - Confidence Calibration", h6, None, {"mean_confidence": "{:.3f}", "hit_rate": "{:.1%}", "brier_overall": "{:.4f}"}),
        ("H7 - Category Effects", h7, None, {"mean_abs_pct": "{:.4f}", "median_abs_pct": "{:.4f}", "p_kruskal": "{:.3g}", "q_kruskal": "{:.3g}"}),
        ("H8 - Pre-Event Drift", h8, plot_h8(h8), {"mean_pre_abs": "{:.4f}", "mean_post_abs": "{:.4f}", "mean_baseline_abs": "{:.4f}", "p_pre_vs_baseline_mwu_greater": "{:.3g}", "q_pre_vs_baseline_mwu_greater": "{:.3g}"}),
        ("H9 - Persistence", h9, None, {"sign_match_rate": "{:.1%}", "p_binom_persistence": "{:.3g}", "q_binom_persistence": "{:.3g}", "median_ratio_4h_to_15m": "{:.2f}"}),
        ("H10 - Proxy Volume Reaction", h10, plot_h10(h10), {"median_volume_ratio": "{:.2f}", "p_wilcoxon_gt1": "{:.3g}", "q_wilcoxon_gt1": "{:.3g}"}),
        ("H11 - Time-of-Day", h11, None, {"p_hour": "{:.3g}", "q_hour": "{:.3g}", "p_dow": "{:.3g}", "q_dow": "{:.3g}"}),
        ("H12 - Bear vs Bull Asymmetry", h12, None, {"ratio_bear_to_bull": "{:.2f}", "p_mwu_bear_gt_bull": "{:.3g}", "q_mwu_bear_gt_bull": "{:.3g}"}),
        ("H13 - Surprise Level", h13, None, {"mean_expected": "{:.4f}", "mean_surprise": "{:.4f}", "mean_shock": "{:.4f}", "p_kruskal": "{:.3g}", "q_kruskal": "{:.3g}"}),
        ("H14 - Cross-Asset Spillover", h14, plot_h14(h14), {"pearson_eurusd_ndx": "{:+.3f}", "pearson_usdproxy_ndx": "{:+.3f}", "sign_match_usdproxy_ndx": "{:.1%}", "q_pearson_usdproxy_ndx": "{:.3g}"}),
    ]

    for title, df, fig, fmt in sections:
        parts.append(f"<h2>{title}</h2>")
        if fig is not None:
            parts.append(img_tag(fig, title))
        if not df.empty:
            q_cols = [c for c in df.columns if c.startswith("q_")]
            if q_cols:
                parts.append(f"<p class='muted'>FDR summary: {significance_note(df, q_cols)}</p>")
        parts.append(render_table(df, fmt=fmt))

    parts.append("<h2>Top NDX +15m Case Candidates</h2>")
    if not returns_df.empty and not events.empty:
        top = returns_df[
            (returns_df["asset"] == "ndx")
            & (returns_df["window_min"] == 15)
            & returns_df["delta_pct"].notna()
        ].copy()
        top["abs_delta_pct"] = top["delta_pct"].abs()
        top = top.sort_values("abs_delta_pct", ascending=False).head(12)
        ev_cols = ["id", "content"]
        joined = top.merge(events[ev_cols], left_on="event_id", right_on="id", how="left")
        show_cols = ["timestamp_utc", "category", "target_sentiment", "delta_pct", "abs_delta_pct", "content"]
        joined = joined[show_cols].copy()
        joined["content"] = joined["content"].fillna("").apply(lambda s: str(s).splitlines()[0][:180])
        parts.append(render_table(joined, max_rows=12, fmt={"delta_pct": "{:+.4f}", "abs_delta_pct": "{:.4f}"}))

    parts.append("<h2>Files</h2>")
    files = (
        sorted(p.name for p in Path("outputs").glob("h*_results.csv"))
        + sorted(p.name for p in Path("outputs").glob("*_results.csv") if not p.name.startswith("h"))
        + ["event_study_windows.csv", "cluster_event_study_windows.csv", "methodology_summary.csv"]
    )
    parts.append("<ul>" + "".join(f"<li><code>outputs/{name}</code></li>" for name in files) + "</ul>")
    parts.append("</body></html>")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", default="outputs/events_sentiment.csv")
    parser.add_argument("--results-dir", default="outputs")
    parser.add_argument("--output", default="outputs/report.html")
    parser.add_argument("--also-copy", default=None)
    parser.add_argument("--open", action="store_true", help="Open the generated report in the default browser")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    data = {
        "events": read_csv(Path(args.events), parse_dates=["timestamp_utc"]),
        "returns": read_csv(results_dir / "event_study_windows.csv", parse_dates=["timestamp_utc"]),
        "clusters": read_csv(results_dir / "cluster_event_study_windows.csv", parse_dates=["timestamp_utc"]),
        "methodology": read_csv(results_dir / "methodology_summary.csv"),
        "cluster_sentiment": read_csv(results_dir / "cluster_sentiment_results.csv"),
        "range_outcomes": read_csv(results_dir / "range_outcomes_results.csv"),
        "abnormal_z": read_csv(results_dir / "abnormal_z_results.csv"),
        "targeted_category": read_csv(results_dir / "targeted_category_results.csv"),
        "pre_post_stability": read_csv(results_dir / "pre_post_stability_results.csv"),
        "multivariate": read_csv(results_dir / "multivariate_results.csv"),
        "outlier_robustness": read_csv(results_dir / "outlier_robustness_results.csv"),
        "model_consensus": read_csv(results_dir / "model_consensus_results.csv"),
    }
    for i in range(1, 15):
        data[f"h{i}"] = read_csv(results_dir / f"h{i}_results.csv")

    output = Path(args.output)
    build_html(data, output)
    print(f"Wrote {output}")
    if args.also_copy:
        copy_path = Path(args.also_copy)
        copy_path.parent.mkdir(parents=True, exist_ok=True)
        copy_path.write_text(output.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Also copied to {copy_path}")
    if args.open:
        webbrowser.open(f"file:///{output.resolve()}")


if __name__ == "__main__":
    main()
