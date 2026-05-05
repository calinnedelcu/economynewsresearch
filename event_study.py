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
PRE_WINDOWS_MIN = [15, 60]  # for H8 pre-event drift
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
    """Return Δ% in [event, event+window_min]. Negative window_min → pre-event drift.

    For window_min < 0: measures Δ% in [event+window_min, event].
    Returns None if any required bar is missing from the index.
    """
    event_minute = event_ts.floor("min")
    if window_min >= 0:
        base_minute = event_minute
        target_minute = event_minute + pd.Timedelta(minutes=window_min)
    else:
        base_minute = event_minute + pd.Timedelta(minutes=window_min)
        target_minute = event_minute
    if base_minute not in prices.index or target_minute not in prices.index:
        return None
    base = prices.loc[base_minute, "close"]
    target = prices.loc[target_minute, "close"]
    pct = (target - base) / base * 100
    vol_window = prices.loc[base_minute:target_minute, "volume"].sum()
    return {"base": base, "target": target, "delta_pct": pct, "volume": vol_window}


def compute_baseline_volume(prices, event_ts, window_min, lookback_days=30):
    """Median cumulative volume of same-length windows in the prior lookback_days, same hour-of-day."""
    end = event_ts.floor("min")
    start = end - pd.Timedelta(days=lookback_days)
    sub = prices.loc[start:end - pd.Timedelta(minutes=1)]
    if sub.empty:
        return np.nan
    target_hour = event_ts.hour
    same_hour = sub[sub.index.hour == target_hour]
    if same_hour.empty:
        return float(sub["volume"].median())
    # Aggregate volume in window_min chunks at same hour-of-day
    rolled = same_hour["volume"].rolling(window=max(1, window_min), min_periods=1).sum()
    return float(rolled.median()) if not rolled.empty else float(same_hour["volume"].sum())


def compute_returns_for_events(events, prices, closed_periods_by_asset):
    """For each gold event × asset × window, compute Δ% + pre-event drift + volume_ratio."""
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
                    "directional_strength_usd": pd.to_numeric(ev.get("directional_strength_usd", np.nan), errors="coerce"),
                    "directional_strength_ndx": pd.to_numeric(ev.get("directional_strength_ndx", np.nan), errors="coerce"),
                    "expected_magnitude": ev.get("expected_magnitude", ""),
                    "surprise_level": ev.get("surprise_level", ""),
                    "confidence": pd.to_numeric(ev.get("confidence", np.nan), errors="coerce"),
                    "hour_utc": ts.hour,
                    "dow": ts.dayofweek,
                    "is_in_closed_period": in_closed is not None,
                }
                if in_closed:
                    row.update({"base": np.nan, "target": np.nan, "delta_pct": np.nan,
                                "volume": np.nan, "volume_ratio": np.nan,
                                "pre_delta_pct_15": np.nan, "pre_delta_pct_60": np.nan})
                else:
                    res = compute_event_window(ts, prices[asset], w)
                    if res is None:
                        row.update({"base": np.nan, "target": np.nan, "delta_pct": np.nan,
                                    "volume": np.nan, "volume_ratio": np.nan})
                    else:
                        row.update(res)
                        baseline_vol = compute_baseline_volume(prices[asset], ts, w)
                        row["volume_ratio"] = (res["volume"] / baseline_vol) if baseline_vol and baseline_vol > 0 else np.nan
                    # pre-event drift (only computed once per event×asset, but stored on each window row)
                    for pw in PRE_WINDOWS_MIN:
                        pre = compute_event_window(ts, prices[asset], -pw)
                        row[f"pre_delta_pct_{pw}"] = pre["delta_pct"] if pre else np.nan
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


def test_h5_magnitude(returns_df):
    """ANOVA: |Δ%| ~ expected_magnitude (low/med/high). Per asset × window."""
    print("\n=== H5: expected_magnitude predicts |Δ%| ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & returns_df["delta_pct"].notna()
                & returns_df["expected_magnitude"].isin(["low", "med", "high"])
            ].copy()
            if len(sub) < 6:
                continue
            sub["abs_pct"] = sub["delta_pct"].abs()
            groups = [sub[sub["expected_magnitude"] == g]["abs_pct"].values
                      for g in ("low", "med", "high")]
            groups = [g for g in groups if len(g) >= 2]
            if len(groups) < 2:
                continue
            f_stat, p = stats.f_oneway(*groups)
            means = {g: sub[sub["expected_magnitude"] == g]["abs_pct"].mean()
                     for g in ("low", "med", "high") if (sub["expected_magnitude"] == g).any()}
            row = {"asset": asset, "window_min": w, "n": len(sub),
                   "n_low": (sub["expected_magnitude"] == "low").sum(),
                   "n_med": (sub["expected_magnitude"] == "med").sum(),
                   "n_high": (sub["expected_magnitude"] == "high").sum(),
                   "mean_low": means.get("low", np.nan),
                   "mean_med": means.get("med", np.nan),
                   "mean_high": means.get("high", np.nan),
                   "f_stat": f_stat, "p_anova": p}
            results.append(row)
            print(f"  {asset:6s} +{w:3d}m: low={row['mean_low']:.4f} med={row['mean_med']:.4f} high={row['mean_high']:.4f}  F={f_stat:.2f} p={p:.4g}")
    return pd.DataFrame(results)


def test_h6_calibration(returns_df):
    """Calibration of `confidence`: bucket by confidence → realized hit rate.

    Buckets: [0,0.4), [0.4,0.6), [0.6,0.8), [0.8,1.0]. Brier score.
    Uses NDX +15m (best H2 result) as the reference.
    """
    print("\n=== H6: confidence calibration (NDX +15m) ===")
    sub = returns_df[
        (returns_df["asset"] == "ndx")
        & (returns_df["window_min"] == 15)
        & returns_df["delta_pct"].notna()
        & returns_df["sentiment_ndx"].isin(["bull", "bear"])
        & returns_df["confidence"].notna()
    ].copy()
    if len(sub) < 5:
        print("  not enough rows")
        return pd.DataFrame()
    sub["realized"] = (sub["delta_pct"] > 0).astype(int)
    sub["predicted"] = (sub["sentiment_ndx"] == "bull").astype(int)
    sub["correct"] = (sub["realized"] == sub["predicted"]).astype(int)
    # Brier: predicted prob = confidence if predicted bull else (1-confidence)
    pred_prob = np.where(sub["predicted"] == 1, sub["confidence"], 1 - sub["confidence"])
    brier = float(np.mean((pred_prob - sub["realized"]) ** 2))
    edges = [0.0, 0.4, 0.6, 0.8, 1.0001]
    labels = ["[0,0.4)", "[0.4,0.6)", "[0.6,0.8)", "[0.8,1.0]"]
    sub["bucket"] = pd.cut(sub["confidence"], bins=edges, labels=labels, right=False, include_lowest=True)
    rows = []
    for lab in labels:
        bk = sub[sub["bucket"] == lab]
        if bk.empty:
            continue
        rows.append({
            "bucket": lab, "n": len(bk),
            "mean_confidence": bk["confidence"].mean(),
            "hit_rate": bk["correct"].mean(),
            "brier_overall": brier,
        })
        print(f"  conf {lab:<10s}: n={len(bk):3d}  mean_conf={bk['confidence'].mean():.3f}  hit_rate={bk['correct'].mean():.1%}")
    print(f"  Brier score: {brier:.4f}  (lower=better; 0.25=random)")
    return pd.DataFrame(rows)


def test_h7_category(returns_df):
    """ANOVA |Δ%| ~ category. Identifies which categories produce the largest moves."""
    print("\n=== H7: per-category effect on |Δ%| (window +15m) ===")
    results = []
    for asset in ASSETS:
        sub = returns_df[
            (returns_df["asset"] == asset)
            & (returns_df["window_min"] == 15)
            & returns_df["delta_pct"].notna()
            & returns_df["category"].notna()
            & (returns_df["category"] != "")
        ].copy()
        if len(sub) < 10:
            continue
        sub["abs_pct"] = sub["delta_pct"].abs()
        cat_groups = sub.groupby("category")["abs_pct"]
        # Skip categories with <5 events
        valid_cats = [c for c, g in cat_groups if len(g) >= 5]
        if len(valid_cats) < 2:
            continue
        groups_data = [sub[sub["category"] == c]["abs_pct"].values for c in valid_cats]
        f_stat, p = stats.f_oneway(*groups_data)
        for c in valid_cats:
            results.append({
                "asset": asset, "category": c,
                "n": int((sub["category"] == c).sum()),
                "mean_abs_pct": float(sub[sub["category"] == c]["abs_pct"].mean()),
                "median_abs_pct": float(sub[sub["category"] == c]["abs_pct"].median()),
                "f_anova": f_stat, "p_anova": p,
            })
        print(f"  {asset:6s}: ANOVA F={f_stat:.2f} p={p:.4g}")
        for c in sorted(valid_cats, key=lambda c: -float(sub[sub["category"] == c]["abs_pct"].mean())):
            mean_v = sub[sub["category"] == c]["abs_pct"].mean()
            n_c = (sub["category"] == c).sum()
            print(f"    {c:18s}: n={n_c:4d}  mean|Δ%|={mean_v:.4f}")
    return pd.DataFrame(results)


def test_h8_pre_event_drift(returns_df, prices, rng):
    """Pre-event drift: |Δ%[-15m,0]| events vs |Δ%[-15m,0]| baseline (no event).

    Tests market efficiency / information leakage hypothesis.
    """
    print("\n=== H8: pre-event drift (|Δ%[-15m,0]| events vs baseline) ===")
    results = []
    for asset in ASSETS:
        sub = returns_df[
            (returns_df["asset"] == asset)
            & (returns_df["window_min"] == 15)
            & returns_df["pre_delta_pct_15"].notna()
        ].drop_duplicates("event_id").copy()
        if len(sub) < 10:
            continue
        pre_abs = sub["pre_delta_pct_15"].abs().values
        post_abs = sub["delta_pct"].abs().values  # +15m forward
        # Compare directly: pre vs post within same events
        t_stat, p_t = stats.ttest_rel(pre_abs, post_abs)
        # Also baseline test: pre |Δ%| vs random 15m baseline
        event_ts = sub["timestamp_utc"].drop_duplicates().tolist()
        baseline = generate_baseline_windows(prices[asset], event_ts, max(2000, 30 * len(event_ts)), 15, rng)
        baseline_abs = np.abs([b[1] for b in baseline]) if baseline else np.array([])
        if len(baseline_abs) > 0:
            t_b, p_b = stats.ttest_ind(pre_abs, baseline_abs, equal_var=False)
            u_b, p_mwu = stats.mannwhitneyu(pre_abs, baseline_abs, alternative="greater")
        else:
            t_b = p_b = p_mwu = np.nan
        results.append({
            "asset": asset, "n_events": len(sub),
            "mean_pre_abs": float(pre_abs.mean()),
            "mean_post_abs": float(post_abs.mean()),
            "mean_baseline_abs": float(baseline_abs.mean()) if len(baseline_abs) else np.nan,
            "p_pre_vs_post_paired": p_t,
            "p_pre_vs_baseline_t": p_b,
            "p_pre_vs_baseline_mwu": p_mwu,
        })
        base_mean_str = f"{baseline_abs.mean():.4f}" if len(baseline_abs) else "n/a"
        print(f"  {asset:6s}: pre |Δ%|={pre_abs.mean():.4f}  vs post |Δ%|={post_abs.mean():.4f}  vs base |Δ%|={base_mean_str}"
              f"  pre>baseline MWU p={p_mwu:.4g}")
    return pd.DataFrame(results)


def test_h9_decay(returns_df):
    """Decay/persistence: do moves at +15m persist to +4h or revert?

    For each event compute sign agreement between +15m and +4h, and
    relative magnitude (|Δ%|[+4h] / |Δ%|[+15m]).
    """
    print("\n=== H9: news impact persistence (+15m vs +4h) ===")
    results = []
    for asset in ASSETS:
        wide = returns_df[
            (returns_df["asset"] == asset)
            & returns_df["delta_pct"].notna()
            & returns_df["window_min"].isin([15, 240])
        ].pivot_table(index="event_id", columns="window_min", values="delta_pct", aggfunc="first").dropna()
        if len(wide) < 10:
            continue
        sign_match = (np.sign(wide[15]) == np.sign(wide[240]))
        match_rate = sign_match.mean()
        # binomial test: same direction at chance 50%?
        try:
            p_binom = stats.binomtest(int(sign_match.sum()), len(wide), p=0.5, alternative="two-sided").pvalue
        except AttributeError:
            p_binom = stats.binom_test(int(sign_match.sum()), len(wide), p=0.5, alternative="two-sided")
        ratio = (wide[240].abs() / wide[15].abs().replace(0, np.nan)).median()
        results.append({
            "asset": asset, "n_events": int(len(wide)),
            "sign_match_rate": float(match_rate),
            "p_binom_persistence": p_binom,
            "median_ratio_4h_to_15m": float(ratio),
        })
        print(f"  {asset:6s}: n={len(wide):4d}  sign-match(15m,4h)={match_rate:.1%}  p={p_binom:.4g}  "
              f"median(|Δ4h|/|Δ15m|)={ratio:.2f}")
    return pd.DataFrame(results)


def test_h10_volume(returns_df):
    """Volume reaction: volume_ratio events > 1 (Mann-Whitney U vs ratio=1)."""
    print("\n=== H10: volume_ratio events vs baseline ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & returns_df["volume_ratio"].notna()
                & np.isfinite(returns_df["volume_ratio"])
            ]
            if len(sub) < 10:
                continue
            ratios = sub["volume_ratio"].values
            # Test if median > 1 with Wilcoxon signed-rank against 1
            try:
                stat, p_wilcoxon = stats.wilcoxon(ratios - 1.0, alternative="greater")
            except ValueError:
                stat, p_wilcoxon = (np.nan, np.nan)
            results.append({
                "asset": asset, "window_min": w, "n": len(sub),
                "mean_volume_ratio": float(np.mean(ratios)),
                "median_volume_ratio": float(np.median(ratios)),
                "p_wilcoxon_gt1": p_wilcoxon,
            })
            print(f"  {asset:6s} +{w:3d}m: median_ratio={np.median(ratios):.2f}  mean_ratio={np.mean(ratios):.2f}  p_Wilcoxon>1: {p_wilcoxon:.4g}")
    return pd.DataFrame(results)


def test_h11_time_of_day(returns_df):
    """OLS |Δ%| ~ hour_utc + dow. Window +15m, both assets."""
    print("\n=== H11: time-of-day & day-of-week effect (+15m) ===")
    results = []
    for asset in ASSETS:
        sub = returns_df[
            (returns_df["asset"] == asset)
            & (returns_df["window_min"] == 15)
            & returns_df["delta_pct"].notna()
        ].copy()
        if len(sub) < 20:
            continue
        sub["abs_pct"] = sub["delta_pct"].abs()
        # ANOVA per hour
        hour_groups = [sub[sub["hour_utc"] == h]["abs_pct"].values for h in range(24)]
        hour_groups = [g for g in hour_groups if len(g) >= 3]
        if len(hour_groups) >= 2:
            f_h, p_h = stats.f_oneway(*hour_groups)
        else:
            f_h, p_h = (np.nan, np.nan)
        dow_groups = [sub[sub["dow"] == d]["abs_pct"].values for d in range(7)]
        dow_groups = [g for g in dow_groups if len(g) >= 3]
        if len(dow_groups) >= 2:
            f_d, p_d = stats.f_oneway(*dow_groups)
        else:
            f_d, p_d = (np.nan, np.nan)
        results.append({
            "asset": asset, "n": len(sub),
            "f_hour": f_h, "p_hour": p_h,
            "f_dow": f_d, "p_dow": p_d,
        })
        print(f"  {asset:6s}: ANOVA hour F={f_h:.2f} p={p_h:.4g}  ·  dow F={f_d:.2f} p={p_d:.4g}")
        # Top hours
        hour_means = sub.groupby("hour_utc")["abs_pct"].agg(["mean", "count"]).query("count >= 5")
        if not hour_means.empty:
            top3 = hour_means.sort_values("mean", ascending=False).head(3)
            for h, r in top3.iterrows():
                print(f"    hour {int(h):02d}:00 UTC: mean|Δ%|={r['mean']:.4f}  (n={int(r['count'])})")
    return pd.DataFrame(results)


def test_h12_asymmetric(returns_df):
    """Asymmetric response: |Δ%|_bear-events vs |Δ%|_bull-events (loss aversion)."""
    print("\n=== H12: asymmetric response (bear vs bull events) ===")
    results = []
    for asset in ASSETS:
        sentiment_col = "sentiment_usd" if asset == "eurusd" else "sentiment_ndx"
        for w in WINDOWS_MIN:
            sub = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & returns_df["delta_pct"].notna()
                & returns_df[sentiment_col].isin(["bull", "bear"])
            ].copy()
            if len(sub) < 10:
                continue
            sub["abs_pct"] = sub["delta_pct"].abs()
            bear = sub[sub[sentiment_col] == "bear"]["abs_pct"].values
            bull = sub[sub[sentiment_col] == "bull"]["abs_pct"].values
            if len(bear) < 3 or len(bull) < 3:
                continue
            t, p_t = stats.ttest_ind(bear, bull, equal_var=False)
            u, p_u = stats.mannwhitneyu(bear, bull, alternative="greater")
            results.append({
                "asset": asset, "window_min": w,
                "n_bear": len(bear), "n_bull": len(bull),
                "mean_abs_bear": float(bear.mean()), "mean_abs_bull": float(bull.mean()),
                "ratio_bear_to_bull": float(bear.mean() / bull.mean()) if bull.mean() > 0 else np.nan,
                "p_ttest": p_t, "p_mwu_bear_gt_bull": p_u,
            })
            print(f"  {asset:6s} +{w:3d}m: bear n={len(bear):3d} mean={bear.mean():.4f}  bull n={len(bull):3d} mean={bull.mean():.4f}  "
                  f"ratio={bear.mean()/bull.mean():4.2f}x  MWU p={p_u:.4g}")
    return pd.DataFrame(results)


def test_h13_surprise(returns_df):
    """ANOVA |Δ%| ~ surprise_level (expected/surprise/shock)."""
    print("\n=== H13: surprise_level → |Δ%| ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & returns_df["delta_pct"].notna()
                & returns_df["surprise_level"].isin(["expected", "surprise", "shock"])
            ].copy()
            if len(sub) < 10:
                continue
            sub["abs_pct"] = sub["delta_pct"].abs()
            groups = [sub[sub["surprise_level"] == s]["abs_pct"].values
                      for s in ("expected", "surprise", "shock")]
            groups = [g for g in groups if len(g) >= 2]
            if len(groups) < 2:
                continue
            f, p = stats.f_oneway(*groups)
            means = {s: float(sub[sub["surprise_level"] == s]["abs_pct"].mean())
                     for s in ("expected", "surprise", "shock")
                     if (sub["surprise_level"] == s).any()}
            ns = {s: int((sub["surprise_level"] == s).sum())
                  for s in ("expected", "surprise", "shock")}
            results.append({
                "asset": asset, "window_min": w, "n": len(sub),
                "n_expected": ns.get("expected", 0),
                "n_surprise": ns.get("surprise", 0),
                "n_shock": ns.get("shock", 0),
                "mean_expected": means.get("expected", np.nan),
                "mean_surprise": means.get("surprise", np.nan),
                "mean_shock": means.get("shock", np.nan),
                "f_anova": f, "p_anova": p,
            })
            print(f"  {asset:6s} +{w:3d}m: exp={means.get('expected',np.nan):.4f}  surp={means.get('surprise',np.nan):.4f}  shock={means.get('shock',np.nan):.4f}  F={f:.2f} p={p:.4g}")
    return pd.DataFrame(results)


def test_h14_spillover(returns_df):
    """Cross-asset spillover: per-event correlation NDX vs EUR/USD on +15m window."""
    print("\n=== H14: cross-asset spillover (NDX × EUR/USD, +15m) ===")
    pivot = returns_df[
        (returns_df["window_min"] == 15)
        & returns_df["delta_pct"].notna()
    ].pivot_table(index="event_id", columns="asset", values="delta_pct", aggfunc="first").dropna()
    if len(pivot) < 10:
        print("  too few events with both assets present")
        return pd.DataFrame()
    eur, ndx = pivot["eurusd"].values, pivot["ndx"].values
    r_pearson, p_p = stats.pearsonr(eur, ndx)
    r_spearman, p_s = stats.spearmanr(eur, ndx)
    # Direction agreement: same sign on both?
    sign_match = (np.sign(eur) == np.sign(ndx))
    match_rate = float(sign_match.mean())
    try:
        p_binom = stats.binomtest(int(sign_match.sum()), len(eur), p=0.5).pvalue
    except AttributeError:
        p_binom = stats.binom_test(int(sign_match.sum()), len(eur), p=0.5)
    out = pd.DataFrame([{
        "n_events": int(len(pivot)),
        "pearson_r": float(r_pearson), "p_pearson": float(p_p),
        "spearman_r": float(r_spearman), "p_spearman": float(p_s),
        "sign_match_rate": match_rate, "p_binom_sign": float(p_binom),
    }])
    print(f"  n={len(pivot)}  Pearson r={r_pearson:+.3f} (p={p_p:.4g})  Spearman r={r_spearman:+.3f} (p={p_s:.4g})  "
          f"sign-match={match_rate:.1%} (p={p_binom:.4g})")
    return out


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
    h5 = test_h5_magnitude(returns_df)
    h6 = test_h6_calibration(returns_df)
    h7 = test_h7_category(returns_df)
    h8 = test_h8_pre_event_drift(returns_df, prices, rng)
    h9 = test_h9_decay(returns_df)
    h10 = test_h10_volume(returns_df)
    h11 = test_h11_time_of_day(returns_df)
    h12 = test_h12_asymmetric(returns_df)
    h13 = test_h13_surprise(returns_df)
    h14 = test_h14_spillover(returns_df)

    for name, df in [("h1", h1), ("h2", h2), ("h3", h3), ("h4", h4),
                     ("h5", h5), ("h6", h6), ("h7", h7), ("h8", h8),
                     ("h9", h9), ("h10", h10), ("h11", h11), ("h12", h12),
                     ("h13", h13), ("h14", h14)]:
        if df is not None and not df.empty:
            df.to_csv(out_dir / f"{name}_results.csv", index=False)

    make_figures(returns_df, h1, args.output_dir)
    print("\nDone.")


if __name__ == "__main__":
    main()
