#!/usr/bin/env python3
"""Event study on FJ news vs EUR/USD and Nasdaq-100 prices.

Pipeline:
  1. Load events (with sentiment) and 1-min OHLCV prices.
  2. Detect market-closed periods automatically (gaps > 5 min between bars).
  3. Categorize events as 'intraday' (market open) or 'closed' (gap event).
  4. For intraday events: compute Δ% in windows [0,+1m], [0,+5m], [0,+15m],
     [0,+1h], [0,+4h] for both assets.
  5. Generate baseline distribution from random windows in event-free periods.
  6. Run H1 (t-test Δ% vs baseline), H2 (sentiment-direction agreement),
     H3 (sentiment × trend interaction), H4 (weekend gap regression).
  7. Write results CSV + figures.

Usage:
    python event_study.py
    python event_study.py --events outputs/events_sentiment.csv --output-dir outputs
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
import statsmodels.api as sm

WINDOWS_MIN = [1, 5, 15, 60, 240]
ASSETS = ["eurusd", "ndx"]
N_BASELINE_PER_EVENT = 30
GAP_THRESHOLD_MIN = 5
SEED = 42


def load_data(events_csv: str, prices_dir: str):
    events = pd.read_csv(events_csv, parse_dates=["timestamp_utc"])
    events["timestamp_utc"] = pd.to_datetime(events["timestamp_utc"], utc=True)
    prices = {}
    for asset in ASSETS:
        df = pd.read_csv(f"{prices_dir}/prices_{asset}.csv", parse_dates=["timestamp"], index_col="timestamp")
        df.index = pd.to_datetime(df.index, utc=True)
        prices[asset] = df.sort_index()
    return events, prices


def detect_closed_periods(prices: pd.DataFrame, threshold_min: int = GAP_THRESHOLD_MIN):
    """Return list of (close_ts, close_price, open_ts, open_price, duration_min)."""
    deltas = prices.index.to_series().diff()
    big_gaps = deltas[deltas > pd.Timedelta(minutes=threshold_min)]
    closed_periods = []
    for end_ts, delta in big_gaps.items():
        start_ts = end_ts - delta
        # last bar BEFORE the gap
        prev_idx = prices.index.get_indexer([start_ts], method="pad")[0]
        next_idx = prices.index.get_loc(end_ts)
        close_price = prices["close"].iloc[prev_idx]
        open_price = prices["open"].iloc[next_idx]
        closed_periods.append({
            "close_ts": prices.index[prev_idx],
            "close_price": close_price,
            "open_ts": end_ts,
            "open_price": open_price,
            "duration_min": delta.total_seconds() / 60,
        })
    return closed_periods


def is_event_in_closed_period(event_ts, closed_periods):
    for cp in closed_periods:
        if cp["close_ts"] < event_ts < cp["open_ts"]:
            return cp
    return None


def compute_event_window(event_ts, prices, window_min):
    """Return (base_price, target_price, Δ%, volume_in_window) or None if window out of range."""
    base_minute = event_ts.floor("min")
    target_minute = base_minute + pd.Timedelta(minutes=window_min)
    if base_minute not in prices.index or target_minute not in prices.index:
        return None
    base = prices.loc[base_minute, "close"]
    target = prices.loc[target_minute, "close"]
    pct = (target - base) / base * 100
    vol_window = prices.loc[base_minute:target_minute, "volume"].sum()
    return {"base": base, "target": target, "delta_pct": pct, "volume": vol_window}


def compute_returns_for_events(events, prices, closed_periods_by_asset):
    """For each gold event × asset × window, compute Δ%. Skip events in closed periods."""
    rows = []
    for _, ev in events.iterrows():
        ts = ev["timestamp_utc"]
        for asset in ASSETS:
            in_closed = is_event_in_closed_period(ts, closed_periods_by_asset[asset])
            for w in WINDOWS_MIN:
                row = {
                    "event_id": ev["id"],
                    "timestamp_utc": ts,
                    "asset": asset,
                    "window_min": w,
                    "category": ev.get("category", ""),
                    "sentiment_usd": ev.get("sentiment_usd", ""),
                    "sentiment_ndx": ev.get("sentiment_ndx", ""),
                    "expected_magnitude": ev.get("expected_magnitude", ""),
                    "confidence": ev.get("confidence", np.nan),
                    "is_in_closed_period": in_closed is not None,
                }
                if in_closed:
                    row.update({"base": np.nan, "target": np.nan, "delta_pct": np.nan, "volume": np.nan})
                else:
                    res = compute_event_window(ts, prices[asset], w)
                    if res is None:
                        row.update({"base": np.nan, "target": np.nan, "delta_pct": np.nan, "volume": np.nan})
                    else:
                        row.update(res)
                rows.append(row)
    return pd.DataFrame(rows)


def generate_baseline_windows(prices, event_timestamps, n_windows, window_min, rng, exclude_buffer_min=60):
    """Sample random window starts from prices index, avoiding ±buffer around any event.

    Vectorized: build excluded mask via timestamp arithmetic, then use pandas
    shift to find valid (start, target) pairs. O(N+E) instead of O(N*E).
    """
    if len(prices) == 0 or n_windows <= 0:
        return []

    # Build excluded set once with vectorized broadcasting.
    if len(event_timestamps):
        ev_arr = np.array([pd.Timestamp(t).floor("min") for t in event_timestamps], dtype="datetime64[ns]")
        deltas = np.arange(-exclude_buffer_min, exclude_buffer_min + 1) * np.timedelta64(1, "m")
        excluded_arr = (ev_arr[:, None] + deltas[None, :]).ravel()
        excluded = pd.DatetimeIndex(excluded_arr).tz_localize("UTC")
    else:
        excluded = pd.DatetimeIndex([], tz="UTC")

    # Mark each bar: valid if NOT excluded AND target bar exists in index.
    target_offset = pd.Timedelta(minutes=window_min)
    target_index = prices.index + target_offset
    has_target_mask = target_index.isin(prices.index)
    not_excluded_mask = ~prices.index.isin(excluded)
    valid_mask = has_target_mask & not_excluded_mask

    valid_starts = prices.index[valid_mask]
    if len(valid_starts) < n_windows:
        return []

    sampled_pos = rng.choice(len(valid_starts), size=n_windows, replace=False)
    starts = valid_starts[sampled_pos]
    targets = starts + target_offset
    base_prices = prices.loc[starts, "close"].to_numpy()
    tgt_prices = prices.loc[targets, "close"].to_numpy()
    pcts = (tgt_prices - base_prices) / base_prices * 100
    return list(zip(starts, pcts))


def test_h1(returns_df, prices, rng):
    """t-test (and Mann-Whitney U) on |Δ%| for events vs random baseline windows."""
    print("\n=== H1: |Δ%| events vs random baseline ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            event_returns = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & (returns_df["delta_pct"].notna())
            ]["delta_pct"].abs().values
            if len(event_returns) < 2:
                print(f"  {asset:6s} +{w:3d}m: skip (n={len(event_returns)})")
                continue
            event_ts = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & (returns_df["delta_pct"].notna())
            ]["timestamp_utc"].drop_duplicates().tolist()
            n_baseline = max(N_BASELINE_PER_EVENT * len(event_ts), 100)
            baseline = generate_baseline_windows(prices[asset], event_ts, n_baseline, w, rng)
            if not baseline:
                print(f"  {asset:6s} +{w:3d}m: skip (no baseline)")
                continue
            baseline_abs = np.abs([b[1] for b in baseline])
            t_stat, p_t = stats.ttest_ind(event_returns, baseline_abs, equal_var=False)
            u_stat, p_u = stats.mannwhitneyu(event_returns, baseline_abs, alternative="greater")
            results.append({
                "asset": asset, "window_min": w, "n_events": len(event_returns),
                "n_baseline": len(baseline_abs),
                "mean_abs_event": event_returns.mean(),
                "mean_abs_baseline": baseline_abs.mean(),
                "ratio": event_returns.mean() / baseline_abs.mean() if baseline_abs.mean() > 0 else np.nan,
                "t_stat": t_stat, "p_ttest": p_t,
                "u_stat": u_stat, "p_mwu": p_u,
            })
            print(f"  {asset:6s} +{w:3d}m: n={len(event_returns):3d}  "
                  f"|Δ%| event={event_returns.mean():.4f} vs base={baseline_abs.mean():.4f}  "
                  f"ratio={event_returns.mean()/baseline_abs.mean():5.2f}x  "
                  f"t-test p={p_t:.4f}  MWU p={p_u:.4f}")
    return pd.DataFrame(results)


def test_h2(returns_df):
    """Sentiment-direction agreement: confusion matrix + binomial test."""
    print("\n=== H2: sentiment vs realized direction ===")
    results = []
    for asset in ASSETS:
        sentiment_col = f"sentiment_{asset.replace('eurusd','usd').replace('ndx','ndx')}"
        for w in WINDOWS_MIN:
            sub = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & (returns_df["delta_pct"].notna())
                & (returns_df[sentiment_col].isin(["bull", "bear"]))
            ].copy()
            if len(sub) < 2:
                print(f"  {asset:6s} +{w:3d}m: skip (n={len(sub)} non-neutral)")
                continue
            sub["realized_dir"] = np.where(sub["delta_pct"] > 0, "bull", "bear")
            correct = (sub[sentiment_col] == sub["realized_dir"]).sum()
            n = len(sub)
            hit_rate = correct / n
            try:
                p_binom = stats.binomtest(correct, n, p=0.5, alternative="greater").pvalue
            except AttributeError:
                p_binom = stats.binom_test(correct, n, p=0.5, alternative="greater")
            results.append({
                "asset": asset, "window_min": w, "n": n,
                "correct": int(correct), "hit_rate": hit_rate, "p_binom": p_binom,
            })
            print(f"  {asset:6s} +{w:3d}m: n={n:3d}  hit_rate={hit_rate:5.1%}  ({correct}/{n})  p_binom={p_binom:.4f}")
    return pd.DataFrame(results)


def test_h3(returns_df, prices):
    """OLS regression: |Δ%| ~ sentiment + trend_zi + sentiment*trend."""
    print("\n=== H3: sentiment × trend interaction ===")
    results = []
    for asset in ASSETS:
        sentiment_col = f"sentiment_{'usd' if asset == 'eurusd' else 'ndx'}"
        for w in WINDOWS_MIN:
            sub = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & (returns_df["delta_pct"].notna())
            ].copy()
            if len(sub) < 4:
                print(f"  {asset:6s} +{w:3d}m: skip (n={len(sub)} too small)")
                continue
            sentiment_num = sub[sentiment_col].map({"bull": 1, "neutral": 0, "bear": -1})
            sub["sentiment_num"] = sentiment_num
            sub["trend_zi"] = sub["timestamp_utc"].apply(lambda t: compute_day_trend(prices[asset], t))
            sub = sub.dropna(subset=["sentiment_num", "trend_zi"])
            if len(sub) < 4:
                print(f"  {asset:6s} +{w:3d}m: skip after trend (n={len(sub)})")
                continue
            X = sub[["sentiment_num", "trend_zi"]].copy()
            X["interaction"] = X["sentiment_num"] * X["trend_zi"]
            X = sm.add_constant(X)
            y = sub["delta_pct"].abs()
            try:
                model = sm.OLS(y, X).fit()
                row = {"asset": asset, "window_min": w, "n": len(sub), "r2": model.rsquared}
                for name in ["sentiment_num", "trend_zi", "interaction"]:
                    row[f"coef_{name}"] = model.params[name]
                    row[f"p_{name}"] = model.pvalues[name]
                results.append(row)
                print(f"  {asset:6s} +{w:3d}m: n={len(sub):2d}  R²={model.rsquared:.3f}  "
                      f"β_inter={model.params['interaction']:+.4f} (p={model.pvalues['interaction']:.3f})")
            except Exception as e:
                print(f"  {asset:6s} +{w:3d}m: OLS failed: {e}")
    return pd.DataFrame(results)


def compute_day_trend(prices, event_ts, lookback_min=60):
    """Trend before event: sign of Δ% in the lookback_min minutes prior."""
    base = (event_ts - pd.Timedelta(minutes=lookback_min)).floor("min")
    end = event_ts.floor("min")
    if base not in prices.index or end not in prices.index:
        return np.nan
    p_base = prices.loc[base, "close"]
    p_end = prices.loc[end, "close"]
    return (p_end - p_base) / p_base * 100


def test_h4(events, closed_periods_by_asset, prices):
    """Weekend/closed-period gap regression on aggregate sentiment."""
    print("\n=== H4: closed-period gap vs aggregate sentiment ===")
    rows = []
    for asset in ASSETS:
        sentiment_col = "sentiment_usd" if asset == "eurusd" else "sentiment_ndx"
        for cp in closed_periods_by_asset[asset]:
            mask = (events["timestamp_utc"] > cp["close_ts"]) & (events["timestamp_utc"] < cp["open_ts"])
            ev_in = events[mask]
            n_in = len(ev_in)
            if n_in == 0:
                continue
            sentiment_num = ev_in[sentiment_col].map({"bull": 1, "neutral": 0, "bear": -1})
            confidence = pd.to_numeric(ev_in["confidence"], errors="coerce")
            agg = (sentiment_num * confidence).sum() / max(confidence.sum(), 1e-9) if not sentiment_num.empty else 0
            gap_pct = (cp["open_price"] - cp["close_price"]) / cp["close_price"] * 100
            rows.append({
                "asset": asset,
                "close_ts": cp["close_ts"], "open_ts": cp["open_ts"],
                "duration_min": cp["duration_min"],
                "n_events_in_period": n_in,
                "agg_sentiment": agg,
                "gap_pct": gap_pct,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        print("  no closed periods with events found (pilot is small).")
        return df
    print(df.to_string(index=False))
    if len(df) >= 4:
        for asset in ASSETS:
            sub = df[df["asset"] == asset]
            if len(sub) < 4:
                continue
            X = sm.add_constant(sub[["agg_sentiment"]])
            y = sub["gap_pct"]
            model = sm.OLS(y, X).fit()
            print(f"  {asset}: gap ~ sentiment  β={model.params['agg_sentiment']:+.4f} p={model.pvalues['agg_sentiment']:.4f}  R²={model.rsquared:.3f}")
    else:
        print(f"  too few closed periods with events for regression (n={len(df)}).")
    return df


def make_figures(returns_df, h1_results, output_dir):
    fig_dir = Path(output_dir) / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    if returns_df.empty:
        return
    # |Δ%| by window per asset
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = returns_df[(returns_df["asset"] == asset) & returns_df["delta_pct"].notna()]
        if sub.empty:
            ax.set_title(f"{asset.upper()} — no data")
            continue
        data_by_w = [sub[sub["window_min"] == w]["delta_pct"].abs().values for w in WINDOWS_MIN]
        ax.boxplot(data_by_w, tick_labels=[f"+{w}m" for w in WINDOWS_MIN])
        ax.set_title(f"{asset.upper()} — |Δ%| per window")
        ax.set_ylabel("|Δ%|")
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(fig_dir / "abs_returns_by_window.png", dpi=120)
    plt.close()
    print(f"\nFigures written to {fig_dir}/")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", default="outputs/events_sentiment.csv")
    p.add_argument("--prices-dir", default="outputs")
    p.add_argument("--output-dir", default="outputs")
    p.add_argument("--all-events", action="store_true",
                   help="Include all events, not only is_gold")
    args = p.parse_args()

    events, prices = load_data(args.events, args.prices_dir)
    if not args.all_events and "is_gold" in events.columns:
        events = events[events["is_gold"].astype(str) == "True"].copy()

    print(f"Loaded {len(events)} events; assets: {list(prices.keys())}")
    for asset, df in prices.items():
        print(f"  prices[{asset}]: {len(df)} bars  {df.index.min()} → {df.index.max()}")

    closed_periods_by_asset = {}
    for asset, df in prices.items():
        cps = detect_closed_periods(df)
        closed_periods_by_asset[asset] = cps
        print(f"  closed periods detected in {asset}: {len(cps)}")

    rng = np.random.default_rng(SEED)
    returns_df = compute_returns_for_events(events, prices, closed_periods_by_asset)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    returns_df.to_csv(out_dir / "event_study_windows.csv", index=False)
    print(f"\nWrote {len(returns_df)} rows to {out_dir / 'event_study_windows.csv'}")

    n_intraday = (~returns_df["is_in_closed_period"]).sum()
    n_closed = returns_df["is_in_closed_period"].sum()
    print(f"  intraday rows: {n_intraday}, closed-period rows: {n_closed}")

    h1 = test_h1(returns_df, prices, rng)
    h2 = test_h2(returns_df)
    h3 = test_h3(returns_df, prices)
    h4 = test_h4(events, closed_periods_by_asset, prices)

    if not h1.empty:
        h1.to_csv(out_dir / "h1_results.csv", index=False)
    if not h2.empty:
        h2.to_csv(out_dir / "h2_results.csv", index=False)
    if not h3.empty:
        h3.to_csv(out_dir / "h3_results.csv", index=False)
    if not h4.empty:
        h4.to_csv(out_dir / "h4_results.csv", index=False)

    make_figures(returns_df, h1, args.output_dir)
    print("\nDone.")


if __name__ == "__main__":
    main()
