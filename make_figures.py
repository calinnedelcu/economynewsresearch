#!/usr/bin/env python3
"""Generate publication-quality PDF figures from analysis CSVs.

Produces figures under paper/figures/ matching the layout described
in paper/style_guide_and_improvement_plan.md:

    F1  Event-time abnormal return profile
    F2  Event timeline density
    F3  Distribution of event-window returns vs baseline
    F4  Range/max-move ratios by window (bar)
    F5  Hit rate comparison LLM vs LM vs FinBERT (bar with CI)
    F6  Sentiment heatmap by category and asset
    F7  Pre vs post-event drift profile
    F8  Sign persistence scatter

All figures are saved as PDF (vector) plus PNG (300 dpi) for HTML
viewing. Default font is sans-serif at 10 pt, grayscale-friendly
palette.

Run:
    python make_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter

OUTPUTS = Path("outputs")
FIGURES = Path("paper/figures")
FIGURES.mkdir(parents=True, exist_ok=True)

# ---------- Visual defaults (publication-grade) ----------
plt.rcParams.update({
    "figure.dpi": 100,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "font.family": "serif",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "lines.linewidth": 1.4,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.4,
})

COLOR_EVENT = "#1f3a5f"     # dark blue
COLOR_BASELINE = "#a0a0a0"  # mid gray
COLOR_LLM = "#1f3a5f"
COLOR_LM = "#c0392b"
COLOR_FINBERT = "#27ae60"

ASSETS = ["eurusd", "ndx"]
ASSET_LABEL = {"eurusd": "EUR/USD (USD proxy)", "ndx": "Nasdaq-100"}
PRIMARY_WINDOWS = [5, 15, 60]


def save(fig, name):
    pdf = FIGURES / f"{name}.pdf"
    png = FIGURES / f"{name}.png"
    fig.savefig(pdf)
    fig.savefig(png, dpi=300)
    print(f"  wrote {pdf} and {png}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# F1: Event-time abnormal absolute return profile (-60 to +240 minutes)
# ---------------------------------------------------------------------------


def figure_1_event_time_profile():
    print("F1: event-time profile (computing from prices) ...")
    events = pd.read_csv(OUTPUTS / "events_sentiment.csv", parse_dates=["timestamp_utc"])
    events["timestamp_utc"] = pd.to_datetime(events["timestamp_utc"], utc=True)

    pre_min, post_min = 60, 240
    offsets = np.arange(-pre_min, post_min + 1)  # in minutes

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6), sharey=False)

    for ax, asset in zip(axes, ASSETS):
        prices = pd.read_csv(OUTPUTS / f"prices_{asset}.csv", parse_dates=["timestamp"], index_col="timestamp")
        prices.index = pd.to_datetime(prices.index, utc=True)
        prices = prices.sort_index()
        log_close = np.log(prices["close"]).rename("log_close")

        # Build a centered-on-event matrix of |log return| from event minute
        all_event_abs_r = []
        # Sample baseline matched on hour-of-day from non-event times
        rng = np.random.default_rng(42)
        n_baseline = 200  # baseline events sampled randomly with same offsets
        baseline_times = rng.choice(prices.index[60:-241], size=n_baseline, replace=False)
        baseline_abs = []

        for _, ev in events.iterrows():
            t = ev["timestamp_utc"].ceil("min")
            start = t - pd.Timedelta(minutes=pre_min)
            end = t + pd.Timedelta(minutes=post_min)
            seg = log_close.reindex(pd.date_range(start, end, freq="1min", tz="UTC"))
            if seg.isna().any():
                continue
            base = seg.loc[t]
            r = (seg.values - base) * 100  # log return from event time, in %
            all_event_abs_r.append(np.abs(r))

        for bt in baseline_times:
            bt = pd.Timestamp(bt).tz_convert("UTC") if pd.Timestamp(bt).tzinfo else pd.Timestamp(bt, tz="UTC")
            seg = log_close.reindex(pd.date_range(bt - pd.Timedelta(minutes=pre_min),
                                                    bt + pd.Timedelta(minutes=post_min), freq="1min", tz="UTC"))
            if seg.isna().any():
                continue
            base = seg.loc[bt] if bt in seg.index else seg.iloc[pre_min]
            r = (seg.values - base) * 100
            baseline_abs.append(np.abs(r))

        if not all_event_abs_r:
            ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
            continue

        event_mat = np.vstack(all_event_abs_r)
        baseline_mat = np.vstack(baseline_abs)
        event_mean = event_mat.mean(axis=0)
        baseline_mean = baseline_mat.mean(axis=0)
        event_se = event_mat.std(axis=0) / np.sqrt(event_mat.shape[0])

        ax.fill_between(offsets, event_mean - 1.96 * event_se, event_mean + 1.96 * event_se,
                        color=COLOR_EVENT, alpha=0.18, linewidth=0)
        ax.plot(offsets, event_mean, color=COLOR_EVENT, label=f"Events (n={event_mat.shape[0]:,})", linewidth=1.6)
        ax.plot(offsets, baseline_mean, color=COLOR_BASELINE, linestyle="--",
                label=f"Baseline (n={baseline_mat.shape[0]})", linewidth=1.2)
        ax.axvline(0, color="black", linewidth=0.6, alpha=0.7)
        ax.set_xlabel("Minutes from event timestamp")
        ax.set_ylabel("Mean $|r|$ from event minute (\\%)")
        ax.set_title(ASSET_LABEL[asset])
        ax.set_xlim(-pre_min, post_min)
        ax.legend(loc="upper left", frameon=False)

    fig.suptitle(r"Average absolute log-return profile around news events", y=1.02)
    save(fig, "figure_1_event_time_profile")


# ---------------------------------------------------------------------------
# F2: Event timeline density
# ---------------------------------------------------------------------------


def figure_2_event_timeline():
    print("F2: event timeline density ...")
    events = pd.read_csv(OUTPUTS / "events_sentiment.csv", parse_dates=["timestamp_utc"])
    events["timestamp_utc"] = pd.to_datetime(events["timestamp_utc"], utc=True)
    events["date"] = events["timestamp_utc"].dt.date
    daily = events.groupby("date").size().rename("count")

    # Stack categories
    cat_daily = events.pivot_table(index="date", columns="category", values="id", aggfunc="count").fillna(0)
    # Order categories by total volume
    cat_order = cat_daily.sum().sort_values(ascending=False).index.tolist()
    cat_daily = cat_daily[cat_order]

    fig, ax = plt.subplots(figsize=(9.5, 3.4))
    bottoms = np.zeros(len(cat_daily))
    palette = plt.get_cmap("tab10").colors
    for i, cat in enumerate(cat_order):
        ax.bar(cat_daily.index, cat_daily[cat], bottom=bottoms, color=palette[i % 10],
               label=cat, width=1.0, linewidth=0)
        bottoms += cat_daily[cat].values
    ax.set_ylabel("Gold events per day")
    ax.set_xlabel("Date (UTC)")
    ax.legend(loc="upper left", ncol=4, frameon=False, fontsize=8)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.set_title(f"Gold event arrival rate by category ($N$ = {len(events):,})")
    save(fig, "figure_2_event_timeline")


# ---------------------------------------------------------------------------
# F4: Range/max-move ratios by window
# ---------------------------------------------------------------------------


def figure_4_range_ratios():
    print("F4: range/max-move ratios ...")
    h1 = pd.read_csv(OUTPUTS / "h1_results.csv")
    rng = pd.read_csv(OUTPUTS / "range_outcomes_results.csv")

    metrics = [
        ("$|r|$ close-to-close", h1, None),
        ("Range", rng, "range_pct"),
        ("Max abs move", rng, "max_abs_move_pct"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6), sharey=True)
    width = 0.25
    x = np.arange(len(PRIMARY_WINDOWS))

    for ax, asset in zip(axes, ASSETS):
        for i, (label, df, metric) in enumerate(metrics):
            ratios = []
            for w in PRIMARY_WINDOWS:
                if metric is None:
                    r = df[(df["asset"] == asset) & (df["window_min"] == w)]
                    ratio = r["ratio"].iloc[0] if not r.empty else np.nan
                else:
                    r = df[(df["asset"] == asset) & (df["window_min"] == w) & (df["metric"] == metric)]
                    ratio = r["ratio"].iloc[0] if not r.empty else np.nan
                ratios.append(ratio)
            ax.bar(x + (i - 1) * width, ratios, width, label=label,
                   color=[COLOR_EVENT, "#c0392b", "#27ae60"][i])
        ax.axhline(1.0, color="black", linewidth=0.7, linestyle=":")
        ax.set_xticks(x)
        ax.set_xticklabels([f"+{w}m" for w in PRIMARY_WINDOWS])
        ax.set_xlabel("Window")
        ax.set_title(ASSET_LABEL[asset])
        if asset == "eurusd":
            ax.set_ylabel("Event / baseline ratio")
            ax.legend(loc="upper right", frameon=False)
    fig.suptitle("Magnitude amplification around news events", y=1.02)
    save(fig, "figure_4_range_ratios")


# ---------------------------------------------------------------------------
# F5: Hit rate comparison LLM vs LM vs FinBERT with Wilson CI
# ---------------------------------------------------------------------------


def figure_5_hit_rate_compare():
    print("F5: hit rate comparison ...")
    cmp = pd.read_csv(OUTPUTS / "sentiment_baseline_compare.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6), sharey=True)
    width = 0.25
    x = np.arange(len(PRIMARY_WINDOWS))
    sources = [("LLM", COLOR_LLM), ("LM", COLOR_LM), ("FINBERT", COLOR_FINBERT)]

    for ax, asset in zip(axes, ASSETS):
        for i, (src, col) in enumerate(sources):
            hits, errs_low, errs_high = [], [], []
            for w in PRIMARY_WINDOWS:
                r = cmp[(cmp["asset"] == asset) & (cmp["window_min"] == w) & (cmp["source"] == src)]
                if r.empty:
                    hits.append(np.nan); errs_low.append(0); errs_high.append(0)
                else:
                    r = r.iloc[0]
                    hits.append(r["hit_rate"])
                    errs_low.append(r["hit_rate"] - r["ci95_low"])
                    errs_high.append(r["ci95_high"] - r["hit_rate"])
            ax.bar(x + (i - 1) * width, hits, width, label=src, color=col,
                   yerr=[errs_low, errs_high], capsize=3, ecolor="black", error_kw={"linewidth": 0.8})
        ax.axhline(0.5, color="black", linewidth=0.7, linestyle=":")
        ax.set_xticks(x)
        ax.set_xticklabels([f"+{w}m" for w in PRIMARY_WINDOWS])
        ax.set_xlabel("Window")
        ax.set_title(ASSET_LABEL[asset])
        if asset == "eurusd":
            ax.set_ylabel("Direction hit rate")
            ax.yaxis.set_major_formatter(PercentFormatter(1.0))
            ax.legend(loc="lower right", frameon=False)
        ax.set_ylim(0.4, 0.6)
    fig.suptitle("LLM vs Loughran-McDonald vs FinBERT: direction hit rate", y=1.02)
    save(fig, "figure_5_hit_rate_compare")


# ---------------------------------------------------------------------------
# F6: Sentiment heatmap by category x asset
# ---------------------------------------------------------------------------


def figure_6_sentiment_heatmap():
    print("F6: sentiment heatmap ...")
    events = pd.read_csv(OUTPUTS / "events_sentiment.csv")
    cats = ["central_bank", "geopolitical", "politics", "energy", "corporate", "macro_release"]
    events = events[events["category"].isin(cats)]

    # Build matrix: rows = category, columns = (asset x bull/bear share)
    rows = []
    for cat in cats:
        sub = events[events["category"] == cat]
        n = len(sub)
        if n == 0:
            rows.append([np.nan]*4); continue
        row = [
            (sub["sentiment_usd"] == "bull").mean(),
            (sub["sentiment_usd"] == "bear").mean(),
            (sub["sentiment_ndx"] == "bull").mean(),
            (sub["sentiment_ndx"] == "bear").mean(),
        ]
        rows.append(row)
    M = np.array(rows)

    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    im = ax.imshow(M, cmap="RdBu_r", vmin=0, vmax=0.8, aspect="auto")
    ax.set_xticks(range(4))
    ax.set_xticklabels(["USD bull", "USD bear", "NDX bull", "NDX bear"])
    ax.set_yticks(range(len(cats)))
    ax.set_yticklabels([f"{c} (n={(events['category']==c).sum()})" for c in cats])
    ax.set_title("LLM sentiment share by category and asset")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if not np.isnan(M[i, j]):
                ax.text(j, i, f"{M[i, j]:.0%}", ha="center", va="center",
                        color="black" if M[i, j] < 0.4 else "white", fontsize=9)
    plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label="Share of events")
    save(fig, "figure_6_sentiment_heatmap")


# ---------------------------------------------------------------------------
# F7: Pre vs post event drift (symmetric profile around event)
# ---------------------------------------------------------------------------


def figure_7_pre_post_drift():
    print("F7: pre vs post event drift ...")
    events = pd.read_csv(OUTPUTS / "events_sentiment.csv", parse_dates=["timestamp_utc"])
    events["timestamp_utc"] = pd.to_datetime(events["timestamp_utc"], utc=True)
    pre, post = 30, 30  # ±30 minutes
    offsets = np.arange(-pre, post + 1)

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6), sharey=False)

    for ax, asset in zip(axes, ASSETS):
        prices = pd.read_csv(OUTPUTS / f"prices_{asset}.csv", parse_dates=["timestamp"], index_col="timestamp")
        prices.index = pd.to_datetime(prices.index, utc=True)
        prices = prices.sort_index()
        log_close = np.log(prices["close"])

        per_minute_abs_returns = []
        for _, ev in events.iterrows():
            t = ev["timestamp_utc"].ceil("min")
            start = t - pd.Timedelta(minutes=pre)
            end = t + pd.Timedelta(minutes=post)
            seg = log_close.reindex(pd.date_range(start, end, freq="1min", tz="UTC"))
            if seg.isna().any():
                continue
            # 1-minute log returns
            r = np.diff(seg.values) * 100  # in percent
            per_minute_abs_returns.append(np.abs(r))

        if not per_minute_abs_returns:
            continue
        mat = np.vstack(per_minute_abs_returns)  # n_events x (pre+post)
        mean_r = mat.mean(axis=0)
        se_r = mat.std(axis=0) / np.sqrt(mat.shape[0])
        # x = midpoint of each 1-min return interval
        x = np.arange(-pre + 0.5, post + 0.5)

        ax.fill_between(x, mean_r - 1.96 * se_r, mean_r + 1.96 * se_r,
                        color=COLOR_EVENT, alpha=0.18, linewidth=0)
        ax.plot(x, mean_r, color=COLOR_EVENT, linewidth=1.5, label=f"Mean (n={mat.shape[0]:,})")
        ax.axvline(0, color="black", linewidth=0.7, alpha=0.8)
        ax.set_xlabel("Minutes from event")
        ax.set_ylabel("Mean per-minute $|r|$ (\\%)")
        ax.set_title(ASSET_LABEL[asset])
        ax.legend(loc="upper left", frameon=False)
        ax.set_xlim(-pre, post)
    fig.suptitle("Per-minute absolute log-return: pre vs post event drift", y=1.02)
    save(fig, "figure_7_pre_post_drift")


# ---------------------------------------------------------------------------
# F8: Sign persistence scatter
# ---------------------------------------------------------------------------


def figure_8_sign_persistence():
    print("F8: sign persistence scatter ...")
    win = pd.read_csv(OUTPUTS / "event_study_windows.csv")
    # join on event_id: +15m and +240m target_delta_pct
    w15 = win[(win["window_min"] == 15)][["event_id", "asset", "target_delta_pct"]].rename(columns={"target_delta_pct": "r15"})
    w240 = win[(win["window_min"] == 240)][["event_id", "asset", "target_delta_pct"]].rename(columns={"target_delta_pct": "r240"})
    m = w15.merge(w240, on=["event_id", "asset"]).dropna()

    fig, ax = plt.subplots(figsize=(6.5, 5.0))
    colors = {"eurusd": COLOR_EVENT, "ndx": COLOR_LM}
    for asset in ASSETS:
        sub = m[m["asset"] == asset]
        if len(sub) > 600:
            sub = sub.sample(600, random_state=42)
        ax.scatter(sub["r15"], sub["r240"], s=8, alpha=0.5, c=colors[asset], label=ASSET_LABEL[asset])
    ax.axhline(0, color="black", linewidth=0.6, alpha=0.7)
    ax.axvline(0, color="black", linewidth=0.6, alpha=0.7)
    ax.set_xlabel("Target return +15m (\\%)")
    ax.set_ylabel("Target return +4h (\\%)")
    ax.set_title("Sign persistence: $+15$m vs $+4$h target returns")
    ax.legend(loc="upper left", frameon=False)
    # Symmetric limits clipped to 99th pct for readability
    lim = max(np.percentile(m["r15"].abs(), 99), np.percentile(m["r240"].abs(), 99))
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim*2, lim*2)
    save(fig, "figure_8_sign_persistence")


def main():
    print(f"Writing figures to {FIGURES}/ ...")
    # F2/F4/F5/F6/F8 are fast; F1/F7 require price data and are slower
    figure_2_event_timeline()
    figure_4_range_ratios()
    figure_5_hit_rate_compare()
    figure_6_sentiment_heatmap()
    figure_8_sign_persistence()
    # Slow ones last
    figure_1_event_time_profile()
    figure_7_pre_post_drift()
    print("Done.")


if __name__ == "__main__":
    main()
