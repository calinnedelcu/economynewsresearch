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


def build_html(events, returns_df, h1_df, h2_df, h3_df, h4_df, prices_eur, prices_ndx, output_path):
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

    parts.append("<div class='warn'><strong>⚠️ Notă pilot:</strong> rezultatele sunt pe 1 zi de date (n mic). "
                 "Pe export-ul complet (~1000 events × 13 luni) puterea statistică va fi mult mai mare.</div>")

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
        }))

    parts.append("<h2>🔍 Per-event timelines</h2>")
    parts.append("<p>Pentru fiecare event gold, prețul EUR/USD și NQ-100 cu 30 min înainte și 4 ore după. Linia neagră întreruptă = momentul evenimentului. Liniile gri punctate = ferestrele [+1m, +5m, +15m, +1h, +4h].</p>")

    for _, ev in events.iterrows():
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

    h1 = safe_read(f"{args.results_dir}/h1_results.csv")
    h2 = safe_read(f"{args.results_dir}/h2_results.csv")
    h3 = safe_read(f"{args.results_dir}/h3_results.csv")
    h4 = safe_read(f"{args.results_dir}/h4_results.csv")

    print(f"Building report from {len(events)} events ...")
    build_html(events, returns_df, h1, h2, h3, h4, prices_eur, prices_ndx, args.output)
    print(f"Wrote {args.output}")
    if not args.no_open:
        webbrowser.open(f"file:///{Path(args.output).resolve()}")
        print("Opened in browser.")


if __name__ == "__main__":
    main()
