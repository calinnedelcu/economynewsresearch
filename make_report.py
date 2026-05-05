#!/usr/bin/env python3
"""Build a visual HTML report of the event study results.

Reads event_study output CSVs + prices and produces:
  - per-event timeline charts (price + window markers)
  - aggregate plots for H1/H2/H3
  - a single HTML page that embeds all of them, with summary tables.

Opens the report in the default browser at the end.
"""

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


def fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def img_tag(b64, alt=""):
    return f'<img src="data:image/png;base64,{b64}" alt="{alt}" style="max-width:100%;height:auto;border:1px solid #ddd;border-radius:6px;"/>'


def plot_event_timeline(event_row, prices_eur, prices_ndx, lookback_min=30, lookahead_min=240):
    ts = pd.to_datetime(event_row["timestamp_utc"], utc=True)
    start = ts - pd.Timedelta(minutes=lookback_min)
    end = ts + pd.Timedelta(minutes=lookahead_min)

    eur = prices_eur.loc[start:end] if not prices_eur.empty else pd.DataFrame()
    ndx = prices_ndx.loc[start:end] if not prices_ndx.empty else pd.DataFrame()

    fig, axes = plt.subplots(2, 1, figsize=(11, 5.5), sharex=True)
    fig.subplots_adjust(hspace=0.08)

    for ax, df, asset, color in [
        (axes[0], eur, "EUR/USD", "#1f77b4"),
        (axes[1], ndx, "NQ-100", "#d62728"),
    ]:
        if df.empty:
            ax.text(0.5, 0.5, "no data in window", transform=ax.transAxes, ha="center")
            ax.set_ylabel(asset)
            continue
        ax.plot(df.index, df["close"], color=color, linewidth=1.2)
        ax.axvline(ts, color="black", linestyle="--", linewidth=1, alpha=0.7, label="event")
        # mark windows
        for w, lbl_color in zip([1, 5, 15, 60, 240], ["#666"] * 5):
            tw = ts + pd.Timedelta(minutes=w)
            if df.index.min() <= tw <= df.index.max():
                ax.axvline(tw, color="#999", linestyle=":", linewidth=0.7, alpha=0.5)
        ax.set_ylabel(asset, fontsize=10)
        ax.grid(True, alpha=0.25)
        ax.tick_params(labelsize=8)

    sentiment_usd = event_row.get("sentiment_usd", "?")
    sentiment_ndx = event_row.get("sentiment_ndx", "?")
    conf = event_row.get("confidence", float("nan"))
    cat = event_row.get("category", "?")
    content_preview = (event_row.get("content", "") or "").splitlines()[0][:130]

    title = (f"{ts.strftime('%Y-%m-%d %H:%M')} UTC  ·  {cat}  ·  "
             f"USD={sentiment_usd}, NDX={sentiment_ndx}  ·  conf={conf:.2f}\n"
             f"{content_preview}")
    fig.suptitle(title, fontsize=10, y=0.995)
    axes[1].set_xlabel("UTC time", fontsize=9)
    return fig


def plot_h1(h1_df):
    if h1_df.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = h1_df[h1_df["asset"] == asset].sort_values("window_min")
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        x = np.arange(len(sub))
        width = 0.35
        ax.bar(x - width / 2, sub["mean_abs_event"], width, label="events |Δ%|", color="#d62728")
        ax.bar(x + width / 2, sub["mean_abs_baseline"], width, label="baseline |Δ%|", color="#7f7f7f")
        ax.set_xticks(x)
        ax.set_xticklabels([f"+{w}m" for w in sub["window_min"]])
        ax.set_title(f"{asset.upper()} — mean |Δ%|: events vs baseline (H1)")
        ax.set_ylabel("|Δ%|")
        ax.legend(fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)
        # annotate p-values
        for i, (_, row) in enumerate(sub.iterrows()):
            ax.text(x[i], max(row["mean_abs_event"], row["mean_abs_baseline"]) * 1.05,
                    f"p={row['p_mwu']:.2f}", ha="center", fontsize=8, color="#333")
    plt.tight_layout()
    return fig


def plot_h2(h2_df):
    if h2_df.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = h2_df[h2_df["asset"] == asset].sort_values("window_min")
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        x = np.arange(len(sub))
        bars = ax.bar(x, sub["hit_rate"] * 100, color="#2ca02c", alpha=0.8)
        ax.axhline(50, color="black", linestyle="--", linewidth=1, label="random (50%)")
        ax.set_xticks(x)
        ax.set_xticklabels([f"+{w}m" for w in sub["window_min"]])
        ax.set_ylabel("hit rate (%)")
        ax.set_ylim(0, 110)
        ax.set_title(f"{asset.upper()} — sentiment-direction hit rate (H2)")
        ax.legend(fontsize=9, loc="upper left")
        ax.grid(True, axis="y", alpha=0.3)
        for i, (_, row) in enumerate(sub.iterrows()):
            color = "#1a1a1a" if row["p_binom"] < 0.05 else "#666"
            weight = "bold" if row["p_binom"] < 0.05 else "normal"
            ax.text(x[i], row["hit_rate"] * 100 + 3,
                    f"{int(row['correct'])}/{int(row['n'])}\np={row['p_binom']:.3f}",
                    ha="center", fontsize=8, color=color, fontweight=weight)
    plt.tight_layout()
    return fig


def plot_h5_magnitude(h5_df, returns_df):
    if h5_df.empty:
        return None
    sub_15 = h5_df[h5_df["window_min"] == 15]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        row = sub_15[sub_15["asset"] == asset]
        if row.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        r = row.iloc[0]
        means = [r["mean_low"], r["mean_med"], r["mean_high"]]
        ns = [int(r["n_low"]), int(r["n_med"]), int(r["n_high"])]
        bars = ax.bar(["low", "med", "high"], means, color=["#7fb3d5", "#f4a261", "#e63946"])
        for i, b in enumerate(bars):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                    f"n={ns[i]}", ha="center", va="bottom", fontsize=9)
        ax.set_title(f"{asset.upper()} +15m — |Δ%| by predicted magnitude\n(ANOVA p={r['p_anova']:.4g})")
        ax.set_ylabel("mean |Δ%|")
        ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    return fig


def plot_h6_calibration(h6_df):
    if h6_df.empty:
        return None
    fig, ax = plt.subplots(figsize=(6.5, 5))
    xs = h6_df["mean_confidence"].values
    ys = h6_df["hit_rate"].values
    ns = h6_df["n"].values
    ax.plot([0, 1], [0, 1], "--", color="#888", label="perfect calibration")
    ax.plot(xs, ys, "o-", color="#1f77b4", markersize=10, linewidth=2, label="observed")
    for x, y, n in zip(xs, ys, ns):
        ax.annotate(f"n={int(n)}", (x, y), textcoords="offset points", xytext=(8, 6), fontsize=9)
    brier = h6_df["brier_overall"].iloc[0]
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("predicted probability (mean confidence)")
    ax.set_ylabel("observed hit rate")
    ax.set_title(f"H6 — confidence calibration (NDX +15m)  ·  Brier={brier:.4f}")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    return fig


def plot_h7_category(h7_df):
    if h7_df.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, asset in zip(axes, ASSETS):
        sub = h7_df[h7_df["asset"] == asset].sort_values("mean_abs_pct", ascending=True)
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        bars = ax.barh(sub["category"], sub["mean_abs_pct"], color="#2ca02c", alpha=0.8)
        for i, (_, r) in enumerate(sub.iterrows()):
            ax.text(r["mean_abs_pct"], i, f"  n={int(r['n'])}", va="center", fontsize=9)
        p_anova = sub["p_anova"].iloc[0]
        ax.set_title(f"{asset.upper()} +15m — mean |Δ%| by category  (ANOVA p={p_anova:.4g})")
        ax.set_xlabel("mean |Δ%|")
        ax.grid(True, axis="x", alpha=0.3)
    plt.tight_layout()
    return fig


def plot_h8_drift(h8_df):
    if h8_df.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = np.arange(len(h8_df))
    width = 0.28
    ax.bar(x - width, h8_df["mean_pre_abs"], width, label="pre [-15m, 0]", color="#9467bd")
    ax.bar(x, h8_df["mean_post_abs"], width, label="post [0, +15m]", color="#d62728")
    ax.bar(x + width, h8_df["mean_baseline_abs"], width, label="random baseline", color="#7f7f7f")
    ax.set_xticks(x)
    ax.set_xticklabels(h8_df["asset"].str.upper())
    ax.set_ylabel("mean |Δ%|")
    ax.set_title("H8 — pre-event drift vs post vs baseline (15m windows)")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    for i, (_, r) in enumerate(h8_df.iterrows()):
        ax.text(i, max(r["mean_pre_abs"], r["mean_post_abs"]) * 1.05,
                f"pre>base p={r['p_pre_vs_baseline_mwu']:.3f}", ha="center", fontsize=8)
    plt.tight_layout()
    return fig


def plot_h9_decay(h9_df, returns_df):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if h9_df.empty:
        ax.set_title("no decay data")
        return fig
    # Actual curves: median |Δ%| at each window
    for asset, color in zip(ASSETS, ["#1f77b4", "#d62728"]):
        sub = returns_df[(returns_df["asset"] == asset) & returns_df["delta_pct"].notna()]
        medians = []
        for w in WINDOWS_MIN:
            v = sub[sub["window_min"] == w]["delta_pct"].abs()
            medians.append(float(v.median()) if not v.empty else np.nan)
        ax.plot(WINDOWS_MIN, medians, "o-", color=color, label=asset.upper(), linewidth=2, markersize=8)
    ax.set_xscale("log")
    ax.set_xlabel("window (minutes, log scale)")
    ax.set_ylabel("median |Δ%|")
    ax.set_title("H9 — magnitude decay/persistence across windows")
    ax.legend()
    ax.grid(True, alpha=0.3)
    return fig


def plot_h10_volume(h10_df):
    if h10_df.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = h10_df[h10_df["asset"] == asset].sort_values("window_min")
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        x = np.arange(len(sub))
        ax.bar(x, sub["median_volume_ratio"], color="#ff9800", alpha=0.85)
        ax.axhline(1.0, color="black", linestyle="--", linewidth=1, label="baseline (=1)")
        ax.set_xticks(x)
        ax.set_xticklabels([f"+{w}m" for w in sub["window_min"]])
        ax.set_ylabel("median volume_ratio")
        ax.set_title(f"{asset.upper()} — H10 volume reaction")
        ax.legend(fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)
        for i, (_, r) in enumerate(sub.iterrows()):
            ax.text(x[i], r["median_volume_ratio"] * 1.02,
                    f"p={r['p_wilcoxon_gt1']:.3f}", ha="center", fontsize=8)
    plt.tight_layout()
    return fig


def plot_h11_tod(returns_df):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = returns_df[
            (returns_df["asset"] == asset)
            & (returns_df["window_min"] == 15)
            & returns_df["delta_pct"].notna()
        ]
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        h_means = sub.groupby("hour_utc")["delta_pct"].apply(lambda s: s.abs().mean())
        ax.bar(h_means.index, h_means.values, color="#17becf", alpha=0.85)
        ax.set_xticks(range(0, 24, 2))
        ax.set_xlabel("hour of day (UTC)")
        ax.set_ylabel("mean |Δ%|")
        ax.set_title(f"{asset.upper()} — H11 hour-of-day effect (+15m)")
        ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    return fig


def plot_h12_asymmetric(h12_df):
    if h12_df.empty:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = h12_df[h12_df["asset"] == asset].sort_values("window_min")
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        x = np.arange(len(sub))
        width = 0.35
        ax.bar(x - width / 2, sub["mean_abs_bear"], width, color="#d62728", label="bear")
        ax.bar(x + width / 2, sub["mean_abs_bull"], width, color="#2ca02c", label="bull")
        ax.set_xticks(x)
        ax.set_xticklabels([f"+{w}m" for w in sub["window_min"]])
        ax.set_ylabel("mean |Δ%|")
        ax.set_title(f"{asset.upper()} — H12 asymmetric (bear vs bull)")
        ax.legend()
        ax.grid(True, axis="y", alpha=0.3)
        for i, (_, r) in enumerate(sub.iterrows()):
            ax.text(x[i], max(r["mean_abs_bear"], r["mean_abs_bull"]) * 1.05,
                    f"p={r['p_mwu_bear_gt_bull']:.3f}", ha="center", fontsize=8)
    plt.tight_layout()
    return fig


def plot_h13_surprise(h13_df):
    if h13_df.empty:
        return None
    sub_15 = h13_df[h13_df["window_min"] == 15]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        row = sub_15[sub_15["asset"] == asset]
        if row.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        r = row.iloc[0]
        means = [r["mean_expected"], r["mean_surprise"], r["mean_shock"]]
        ns = [int(r["n_expected"]), int(r["n_surprise"]), int(r["n_shock"])]
        bars = ax.bar(["expected", "surprise", "shock"], means,
                      color=["#7fb3d5", "#f4a261", "#a4133c"])
        for i, b in enumerate(bars):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                    f"n={ns[i]}", ha="center", va="bottom", fontsize=9)
        ax.set_title(f"{asset.upper()} +15m — H13 surprise_level\n(ANOVA p={r['p_anova']:.4g})")
        ax.set_ylabel("mean |Δ%|")
        ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    return fig


def plot_h14_spillover(returns_df):
    pivot = returns_df[
        (returns_df["window_min"] == 15)
        & returns_df["delta_pct"].notna()
    ].pivot_table(index="event_id", columns="asset", values="delta_pct", aggfunc="first").dropna()
    fig, ax = plt.subplots(figsize=(7, 6))
    if pivot.empty:
        ax.set_title("no spillover data")
        return fig
    eur, ndx = pivot["eurusd"].values, pivot["ndx"].values
    ax.scatter(eur, ndx, alpha=0.4, s=20, color="#1f77b4")
    # Quadrant lines
    ax.axhline(0, color="black", linewidth=0.6)
    ax.axvline(0, color="black", linewidth=0.6)
    # Linear fit
    if len(eur) >= 2:
        slope, intercept = np.polyfit(eur, ndx, 1)
        xs = np.linspace(eur.min(), eur.max(), 50)
        ax.plot(xs, slope * xs + intercept, "r--", linewidth=2,
                label=f"OLS: slope={slope:+.2f}")
    from scipy.stats import pearsonr
    r_p, p_p = pearsonr(eur, ndx)
    ax.set_xlabel("EUR/USD Δ% [+15m]")
    ax.set_ylabel("NQ-100 Δ% [+15m]")
    ax.set_title(f"H14 — cross-asset spillover\nPearson r={r_p:+.3f} (p={p_p:.4g}), n={len(pivot)}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    return fig


def plot_h3_scatter(returns_df):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sentiment_col = "sentiment_usd" if asset == "eurusd" else "sentiment_ndx"
        sub = returns_df[
            (returns_df["asset"] == asset)
            & (returns_df["window_min"] == 15)
            & returns_df["delta_pct"].notna()
        ].copy()
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        sentiment_num = sub[sentiment_col].map({"bull": 1, "neutral": 0, "bear": -1})
        sub["sentiment_num"] = sentiment_num
        for sentiment_label, color, marker in [("bull", "#2ca02c", "^"), ("bear", "#d62728", "v"), ("neutral", "#7f7f7f", "o")]:
            sel = sub[sub[sentiment_col] == sentiment_label]
            if not sel.empty:
                ax.scatter(sel["sentiment_num"] + np.random.normal(0, 0.05, len(sel)),
                           sel["delta_pct"], color=color, marker=marker, s=80, alpha=0.7,
                           label=f"{sentiment_label} (n={len(sel)})")
        ax.axhline(0, color="black", linewidth=0.6, alpha=0.4)
        ax.axvline(0, color="black", linewidth=0.6, alpha=0.4)
        ax.set_xticks([-1, 0, 1])
        ax.set_xticklabels(["bear", "neutral", "bull"])
        ax.set_xlabel("predicted sentiment")
        ax.set_ylabel(f"realized Δ% [0,+15m]")
        ax.set_title(f"{asset.upper()} — predicted vs realized (window 15m)")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


def render_table(df, max_rows=20, fmt=None):
    if df.empty:
        return "<p style='color:#888'>no rows</p>"
    df = df.head(max_rows).copy()
    if fmt:
        for col, f in fmt.items():
            if col in df.columns:
                df[col] = df[col].apply(lambda v: f.format(v) if pd.notna(v) else "—")
    return df.to_html(index=False, classes="report-table", border=0)


def build_html(events, returns_df, hyp_dfs, prices_eur, prices_ndx, output_path):
    h1_df = hyp_dfs.get("h1", pd.DataFrame())
    h2_df = hyp_dfs.get("h2", pd.DataFrame())
    h3_df = hyp_dfs.get("h3", pd.DataFrame())
    h4_df = hyp_dfs.get("h4", pd.DataFrame())
    h5_df = hyp_dfs.get("h5", pd.DataFrame())
    h6_df = hyp_dfs.get("h6", pd.DataFrame())
    h7_df = hyp_dfs.get("h7", pd.DataFrame())
    h8_df = hyp_dfs.get("h8", pd.DataFrame())
    h9_df = hyp_dfs.get("h9", pd.DataFrame())
    h10_df = hyp_dfs.get("h10", pd.DataFrame())
    h11_df = hyp_dfs.get("h11", pd.DataFrame())
    h12_df = hyp_dfs.get("h12", pd.DataFrame())
    h13_df = hyp_dfs.get("h13", pd.DataFrame())
    h14_df = hyp_dfs.get("h14", pd.DataFrame())
    n_events = len(events)
    intraday_n = (~returns_df["is_in_closed_period"]).any() and (~returns_df["is_in_closed_period"]).sum()

    parts = []
    parts.append("""<!DOCTYPE html>
<html lang="ro"><head><meta charset="utf-8">
<title>Event Study Report — FJ News × FX/NDX</title>
<style>
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; max-width: 1200px; margin: 24px auto; padding: 0 24px; color:#222; }
h1 { border-bottom: 3px solid #d62728; padding-bottom: 8px; margin-top: 32px; }
h2 { color: #1f77b4; border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 28px; }
h3 { color: #555; margin-top: 22px; }
.report-table { border-collapse: collapse; font-size: 13px; margin: 12px 0; }
.report-table th, .report-table td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
.report-table th { background: #f5f5f5; font-weight: 600; }
.report-table tr:nth-child(even) { background: #fafafa; }
.kpi { display: inline-block; background: #f0f4ff; border-left: 4px solid #1f77b4; padding: 10px 16px; margin: 8px 12px 8px 0; border-radius: 4px; }
.kpi-val { font-size: 22px; font-weight: 700; color: #1f77b4; }
.kpi-label { font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: 0.5px; }
.signal { background: #e8f5e9; padding: 12px; border-left: 4px solid #2ca02c; border-radius: 4px; margin: 12px 0; }
.warn { background: #fff3cd; padding: 12px; border-left: 4px solid #ff9800; border-radius: 4px; margin: 12px 0; }
.event-card { border: 1px solid #e0e0e0; border-radius: 8px; padding: 14px; margin-bottom: 18px; background: #fcfcfc; }
.muted { color: #888; font-size: 12px; }
code { background: #f0f0f0; padding: 2px 5px; border-radius: 3px; font-size: 12px; }
</style></head><body>""")

    parts.append(f"<h1>Event Study Report — FJ News vs EUR/USD &amp; Nasdaq-100</h1>")
    parts.append(f"<p class='muted'>Generated {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} · Pilot data, validation run</p>")

    parts.append("<h2>📊 Sumar</h2>")
    parts.append(f"<div class='kpi'><div class='kpi-val'>{n_events}</div><div class='kpi-label'>events analizate</div></div>")
    parts.append(f"<div class='kpi'><div class='kpi-val'>{len(prices_eur):,}</div><div class='kpi-label'>EUR/USD bars</div></div>")
    parts.append(f"<div class='kpi'><div class='kpi-val'>{len(prices_ndx):,}</div><div class='kpi-label'>NQ-100 bars</div></div>")
    if not h2_df.empty:
        best_h2 = h2_df.loc[h2_df["hit_rate"].idxmax()]
        parts.append(f"<div class='kpi'><div class='kpi-val'>{best_h2['hit_rate']*100:.0f}%</div>"
                     f"<div class='kpi-label'>best hit rate ({best_h2['asset']} +{int(best_h2['window_min'])}m)</div></div>")

    sig_h2 = h2_df[h2_df["p_binom"] < 0.05] if not h2_df.empty else pd.DataFrame()
    if not sig_h2.empty:
        for _, row in sig_h2.iterrows():
            parts.append(f"<div class='signal'><strong>🎯 Semnal H2 semnificativ:</strong> "
                         f"{row['asset'].upper()} la fereastra +{int(row['window_min'])}m — hit rate "
                         f"<strong>{row['hit_rate']*100:.0f}%</strong> ({int(row['correct'])}/{int(row['n'])}), "
                         f"p_binom = <strong>{row['p_binom']:.4f}</strong></div>")

    if not events.empty:
        date_min = events["timestamp_utc"].min()
        date_max = events["timestamp_utc"].max()
        days_span = (date_max - date_min).days
        if days_span < 7:
            parts.append("<div class='warn'><strong>⚠️ Notă pilot:</strong> rezultatele sunt pe "
                         f"{days_span+1} zi/zile de date (n mic). Pe export-ul complet puterea statistică va fi mult mai mare.</div>")
        else:
            parts.append(f"<div class='signal'><strong>📅 Full dataset:</strong> "
                         f"{n_events} events analizate pe {days_span} zile "
                         f"({date_min.strftime('%Y-%m-%d')} → {date_max.strftime('%Y-%m-%d')}). "
                         f"Putere statistică completă.</div>")

    parts.append("<h2>📋 Events analizate</h2>")
    show_cols = ["timestamp_utc", "category", "sentiment_usd", "sentiment_ndx",
                 "expected_magnitude", "confidence", "content"]
    available = [c for c in show_cols if c in events.columns]
    ev_show = events[available].copy()
    if "content" in ev_show.columns:
        ev_show["content"] = ev_show["content"].apply(lambda s: (s or "").splitlines()[0][:120])
    if "timestamp_utc" in ev_show.columns:
        ev_show["timestamp_utc"] = pd.to_datetime(ev_show["timestamp_utc"]).dt.strftime("%Y-%m-%d %H:%M")
    parts.append(render_table(ev_show))

    parts.append("<h2>📈 H1 — magnitudine events vs random baseline</h2>")
    parts.append("<p>Compară |Δ%| pe ferestre fixe între evenimente și ferestre random din zile fără știri (one-sided Mann-Whitney U).</p>")
    fig = plot_h1(h1_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H1 events vs baseline"))
    parts.append("<h3>Tabel detaliat H1</h3>")
    parts.append(render_table(h1_df, fmt={
        "mean_abs_event": "{:.4f}", "mean_abs_baseline": "{:.4f}",
        "ratio": "{:.2f}", "t_stat": "{:.3f}", "p_ttest": "{:.4f}",
        "u_stat": "{:.0f}", "p_mwu": "{:.4f}",
    }))

    parts.append("<h2>🎯 H2 — sentiment prezice direcția?</h2>")
    parts.append("<p>Hit rate = procent evenimente unde sentiment_pred (bull/bear) coincide cu sign(Δ%) realizat. Liniuța 50% = pură întâmplare.</p>")
    fig = plot_h2(h2_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H2 hit rates"))
    parts.append("<h3>Tabel detaliat H2</h3>")
    parts.append(render_table(h2_df, fmt={
        "hit_rate": "{:.1%}", "p_binom": "{:.4f}",
    }))

    parts.append("<h2>🔬 H3 — sentiment × trend interaction (OLS)</h2>")
    parts.append("<p>Regresie <code>|Δ%| ~ sentiment + trend_zi + sentiment×trend_zi</code>. Coeficient β_interaction semnificativ → trendul moderează impactul știrii.</p>")
    fig = plot_h3_scatter(returns_df)
    parts.append(img_tag(fig_to_base64(fig), "H3 scatter sentiment vs realized"))
    parts.append("<h3>Tabel detaliat H3</h3>")
    parts.append(render_table(h3_df, fmt={
        "r2": "{:.3f}",
        "coef_sentiment_num": "{:+.4f}", "p_sentiment_num": "{:.3f}",
        "coef_trend_zi": "{:+.4f}", "p_trend_zi": "{:.3f}",
        "coef_interaction": "{:+.4f}", "p_interaction": "{:.3f}",
    }))

    parts.append("<h2>🌙 H4 — closed-period gap regression</h2>")
    if h4_df.empty:
        parts.append("<p class='muted'>Pilot are 0 events în closed periods (toate sunt intraday luni 20 apr 2026). "
                     "Pe export-ul complet — weekend FX (~52/an) + overnight NDX (~280/an) — H4 va avea date suficiente.</p>")
    else:
        parts.append(render_table(h4_df, fmt={
            "duration_min": "{:.0f}", "agg_sentiment": "{:+.3f}", "gap_pct": "{:+.4f}",
        }, max_rows=200))

    # ----- H5 magnitude -----
    parts.append("<h2>📐 H5 — `expected_magnitude` prezice |Δ%|</h2>")
    parts.append("<p>Modelul DeepSeek prezice categoria de magnitudine (low/med/high). Verificăm dacă coincide empiric cu |Δ%| realizat.</p>")
    fig = plot_h5_magnitude(h5_df, returns_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H5"))
    parts.append(render_table(h5_df, max_rows=20, fmt={
        "mean_low": "{:.4f}", "mean_med": "{:.4f}", "mean_high": "{:.4f}",
        "f_stat": "{:.2f}", "p_anova": "{:.4g}",
    }))

    # ----- H6 calibration -----
    parts.append("<h2>🎯 H6 — calibrare confidence (NDX +15m)</h2>")
    parts.append("<p>Buckets de confidence vs hit rate observat. Diagrama de fiabilitate trebuie să fie aproape de diagonală.</p>")
    fig = plot_h6_calibration(h6_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H6 calibration"))
    parts.append(render_table(h6_df, fmt={
        "mean_confidence": "{:.3f}", "hit_rate": "{:.1%}", "brier_overall": "{:.4f}",
    }))

    # ----- H7 category -----
    parts.append("<h2>🗂️ H7 — efect per categorie</h2>")
    parts.append("<p>Care categorii de știri produc cele mai mari mișcări? ANOVA pe |Δ%| la fereastra +15m.</p>")
    fig = plot_h7_category(h7_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H7 category"))
    parts.append(render_table(h7_df, max_rows=30, fmt={
        "mean_abs_pct": "{:.4f}", "median_abs_pct": "{:.4f}",
        "f_anova": "{:.2f}", "p_anova": "{:.4g}",
    }))

    # ----- H8 pre-event drift -----
    parts.append("<h2>⏪ H8 — pre-event drift (market efficiency)</h2>")
    parts.append("<p>Compară |Δ%| în [-15m, 0] înainte de event vs post-event +15m vs random baseline. Pre &gt; baseline = leakage / front-running posibil.</p>")
    fig = plot_h8_drift(h8_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H8 drift"))
    parts.append(render_table(h8_df, fmt={
        "mean_pre_abs": "{:.4f}", "mean_post_abs": "{:.4f}",
        "mean_baseline_abs": "{:.4f}",
        "p_pre_vs_post_paired": "{:.4g}",
        "p_pre_vs_baseline_t": "{:.4g}",
        "p_pre_vs_baseline_mwu": "{:.4g}",
    }))

    # ----- H9 decay -----
    parts.append("<h2>📉 H9 — persistență vs decay</h2>")
    parts.append("<p>Mișcarea la +15m persistă spre +4h sau revertește? Sign agreement între ferestre.</p>")
    fig = plot_h9_decay(h9_df, returns_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H9 decay"))
    parts.append(render_table(h9_df, fmt={
        "sign_match_rate": "{:.1%}", "p_binom_persistence": "{:.4g}",
        "median_ratio_4h_to_15m": "{:.2f}",
    }))

    # ----- H10 volume -----
    parts.append("<h2>📊 H10 — reacție de volum</h2>")
    parts.append("<p>Volumul tradat în fereastra eveniment vs volum mediu pe baseline (medie pe 30 zile, aceeași oră). Wilcoxon &gt;1.</p>")
    fig = plot_h10_volume(h10_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H10 volume"))
    parts.append(render_table(h10_df, fmt={
        "mean_volume_ratio": "{:.2f}", "median_volume_ratio": "{:.2f}",
        "p_wilcoxon_gt1": "{:.4g}",
    }))

    # ----- H11 time of day -----
    parts.append("<h2>🕐 H11 — efect time-of-day</h2>")
    parts.append("<p>Distribuția |Δ%| pe ora UTC (+15m). ANOVA pe ore + zile săptămânii.</p>")
    fig = plot_h11_tod(returns_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H11 time-of-day"))
    parts.append(render_table(h11_df, fmt={
        "f_hour": "{:.2f}", "p_hour": "{:.4g}",
        "f_dow": "{:.2f}", "p_dow": "{:.4g}",
    }))

    # ----- H12 asymmetric -----
    parts.append("<h2>⚖️ H12 — asimetrie bear vs bull</h2>")
    parts.append("<p>Loss aversion / fear premium: news bear produc mișcări mai mari decât news bull?</p>")
    fig = plot_h12_asymmetric(h12_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H12 asymmetric"))
    parts.append(render_table(h12_df, fmt={
        "mean_abs_bear": "{:.4f}", "mean_abs_bull": "{:.4f}",
        "ratio_bear_to_bull": "{:.2f}",
        "p_ttest": "{:.4g}", "p_mwu_bear_gt_bull": "{:.4g}",
    }))

    # ----- H13 surprise -----
    parts.append("<h2>💥 H13 — surprise_level → magnitudine</h2>")
    parts.append("<p>Câmp nou de sentiment: `expected / surprise / shock`. Verificăm corelația cu |Δ%|.</p>")
    fig = plot_h13_surprise(h13_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H13 surprise"))
    parts.append(render_table(h13_df, max_rows=20, fmt={
        "mean_expected": "{:.4f}", "mean_surprise": "{:.4f}", "mean_shock": "{:.4f}",
        "f_anova": "{:.2f}", "p_anova": "{:.4g}",
    }))

    # ----- H14 spillover -----
    parts.append("<h2>🔀 H14 — cross-asset spillover</h2>")
    parts.append("<p>Per-event corelație între Δ% NDX și Δ% EUR/USD la +15m. Scatter cu fit OLS.</p>")
    fig = plot_h14_spillover(returns_df)
    if fig is not None:
        parts.append(img_tag(fig_to_base64(fig), "H14 spillover"))
    parts.append(render_table(h14_df, fmt={
        "pearson_r": "{:+.3f}", "p_pearson": "{:.4g}",
        "spearman_r": "{:+.3f}", "p_spearman": "{:.4g}",
        "sign_match_rate": "{:.1%}", "p_binom_sign": "{:.4g}",
    }))

    parts.append("<h2>🔍 Top-10 case studies (cele mai mari mișcări)</h2>")
    parts.append("<p>Cele mai mari mișcări absolute pe NDX la fereastra +15m. Linia neagră întreruptă = momentul evenimentului. Liniile gri punctate = ferestrele [+1m, +5m, +15m, +1h, +4h].</p>")

    # Pick top events by abs delta_pct on NDX +15m
    top_15m = returns_df[
        (returns_df["asset"] == "ndx")
        & (returns_df["window_min"] == 15)
        & returns_df["delta_pct"].notna()
    ].copy()
    top_15m["abs_pct"] = top_15m["delta_pct"].abs()
    top_15m = top_15m.sort_values("abs_pct", ascending=False).head(10)
    top_event_ids = set(top_15m["event_id"].astype(str))
    top_events = events[events["id"].astype(str).isin(top_event_ids)].copy()

    for _, ev in top_events.iterrows():
        parts.append("<div class='event-card'>")
        fig = plot_event_timeline(ev, prices_eur, prices_ndx)
        parts.append(img_tag(fig_to_base64(fig), f"event {ev['id']}"))
        parts.append("</div>")

    parts.append(f"<h2>📁 Fișiere generate</h2><ul>")
    parts.append("<li><code>outputs/event_study_windows.csv</code> — Δ% pentru fiecare event × asset × fereastră</li>")
    parts.append("<li><code>outputs/h1_results.csv</code>, <code>h2_results.csv</code>, <code>h3_results.csv</code></li>")
    parts.append("<li><code>outputs/figures/abs_returns_by_window.png</code></li>")
    parts.append(f"<li><code>{output_path}</code> — acest raport</li>")
    parts.append("</ul>")

    parts.append("<p class='muted' style='margin-top:40px;border-top:1px solid #eee;padding-top:12px'>"
                 "Raport generat de <code>make_report.py</code> · pipeline complet pe "
                 "<a href='https://github.com/calinnedelcu/economynewsresearch'>github.com/calinnedelcu/economynewsresearch</a></p>")

    parts.append("</body></html>")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", default="outputs/events_sentiment.csv")
    p.add_argument("--prices-dir", default="outputs")
    p.add_argument("--results-dir", default="outputs")
    p.add_argument("--output", default="outputs/report.html")
    p.add_argument("--no-open", action="store_true", help="Don't open browser")
    args = p.parse_args()

    events = pd.read_csv(args.events, parse_dates=["timestamp_utc"])
    if "is_gold" in events.columns:
        events = events[events["is_gold"].astype(str) == "True"].copy()
    events["timestamp_utc"] = pd.to_datetime(events["timestamp_utc"], utc=True)

    prices_eur = pd.read_csv(f"{args.prices_dir}/prices_eurusd.csv",
                             parse_dates=["timestamp"], index_col="timestamp")
    prices_eur.index = pd.to_datetime(prices_eur.index, utc=True)
    prices_ndx = pd.read_csv(f"{args.prices_dir}/prices_ndx.csv",
                             parse_dates=["timestamp"], index_col="timestamp")
    prices_ndx.index = pd.to_datetime(prices_ndx.index, utc=True)

    returns_df = pd.read_csv(f"{args.results_dir}/event_study_windows.csv",
                             parse_dates=["timestamp_utc"])
    returns_df["timestamp_utc"] = pd.to_datetime(returns_df["timestamp_utc"], utc=True)

    def safe_read(path):
        if Path(path).exists():
            return pd.read_csv(path)
        return pd.DataFrame()

    hyp_dfs = {f"h{i}": safe_read(f"{args.results_dir}/h{i}_results.csv") for i in range(1, 15)}

    print(f"Building report from {len(events)} events ...")
    build_html(events, returns_df, hyp_dfs, prices_eur, prices_ndx, args.output)
    print(f"Wrote {args.output}")
    if not args.no_open:
        webbrowser.open(f"file:///{Path(args.output).resolve()}")
        print("Opened in browser.")


if __name__ == "__main__":
    main()
