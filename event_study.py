#!/usr/bin/env python3
"""Event-study pipeline for FJ news vs EUR/USD and Nasdaq-100 prices.

The analysis is intentionally conservative:
  * events are filtered to the common event/price coverage;
  * event windows start at the first full minute after the Discord timestamp;
  * EUR/USD is evaluated both as a price return and, where sentiment is USD
    targeted, as a USD proxy return (-EUR/USD);
  * clustered news bursts are handled by default in non-regression tests;
  * OLS tests use robust/clustered covariance;
  * all reported p-values receive Benjamini-Hochberg FDR q-values.

Usage:
    python event_study.py
    python event_study.py --events outputs/events_sentiment.csv --output-dir outputs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

WINDOWS_MIN = [1, 5, 15, 60, 240]
PRE_WINDOWS_MIN = [15, 60]
ASSETS = ["eurusd", "ndx"]
DEFAULT_BASELINE_PER_EVENT = 30
DEFAULT_EXCLUDE_BUFFER_MIN = 60
DEFAULT_CLUSTER_GAP_MIN = 15
GAP_THRESHOLD_MIN = 5
SEED = 42


# ---------------------------------------------------------------------------
# Loading, time alignment, and target conventions
# ---------------------------------------------------------------------------


def load_data(events_csv: str, prices_dir: str):
    events = pd.read_csv(events_csv, parse_dates=["timestamp_utc"])
    events["timestamp_utc"] = pd.to_datetime(events["timestamp_utc"], utc=True)

    prices = {}
    for asset in ASSETS:
        path = Path(prices_dir) / f"prices_{asset}.csv"
        df = pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")
        df.index = pd.to_datetime(df.index, utc=True)
        df = df.sort_index()
        missing = {"open", "high", "low", "close", "volume"} - set(df.columns)
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")
        prices[asset] = df
    return events, prices


def filter_events_to_common_price_range(events: pd.DataFrame, prices: dict[str, pd.DataFrame]):
    common_start = max(df.index.min() for df in prices.values())
    common_end = min(df.index.max() for df in prices.values())
    before = len(events)
    events = events[
        (events["timestamp_utc"] >= common_start)
        & (events["timestamp_utc"] <= common_end)
    ].copy()
    dropped = before - len(events)
    return events, common_start, common_end, dropped


def assign_event_clusters(events: pd.DataFrame, gap_min: int = DEFAULT_CLUSTER_GAP_MIN) -> pd.DataFrame:
    """Assign cluster ids to bursts of news separated by <= gap_min minutes."""
    events = events.sort_values("timestamp_utc").copy()
    gap = pd.Timedelta(minutes=gap_min)
    diffs = events["timestamp_utc"].diff()
    starts = diffs.isna() | (diffs > gap)
    events["event_cluster_id"] = starts.cumsum().astype(int)
    events["event_cluster_pos"] = events.groupby("event_cluster_id").cumcount() + 1
    events["event_cluster_size"] = events.groupby("event_cluster_id")["id"].transform("size")
    return events


def post_event_start(event_ts: pd.Timestamp) -> pd.Timestamp:
    """First full 1-minute bar not before the event timestamp."""
    return pd.Timestamp(event_ts).ceil("min")


def pre_event_end(event_ts: pd.Timestamp) -> pd.Timestamp:
    """Last full 1-minute bar before the event timestamp."""
    return pd.Timestamp(event_ts).floor("min") - pd.Timedelta(minutes=1)


def orient_delta(asset: str, value):
    """Return target-aligned return.

    For NDX, target return equals price return. For EUR/USD, the sentiment
    target is USD, so USD strength is approximated by -EUR/USD.
    """
    if asset == "eurusd":
        return -value
    return value


def sentiment_col_for_asset(asset: str) -> str:
    return "sentiment_usd" if asset == "eurusd" else "sentiment_ndx"


def strength_col_for_asset(asset: str) -> str:
    return "directional_strength_usd" if asset == "eurusd" else "directional_strength_ndx"


def target_label_for_asset(asset: str) -> str:
    return "USD proxy (-EUR/USD)" if asset == "eurusd" else "NDX price"


def has_full_window(prices: pd.DataFrame, start_ts: pd.Timestamp, end_ts: pd.Timestamp, expected_bars: int) -> bool:
    if start_ts not in prices.index or end_ts not in prices.index:
        return False
    return len(prices.loc[start_ts:end_ts]) == expected_bars


def compute_event_window(event_ts, prices: pd.DataFrame, window_min: int):
    """Compute a full-minute OHLC return around an event.

    Forward windows use the first full bar at/after the event timestamp.
    For example, an event at 18:40:27 uses the 18:41 bar as the first
    post-event minute. Pre-event windows end at the last full minute before
    the event, avoiding contamination from the event minute.
    """
    event_ts = pd.Timestamp(event_ts)
    if window_min == 0:
        raise ValueError("window_min cannot be 0")

    if window_min > 0:
        n_bars = window_min
        start_ts = post_event_start(event_ts)
        end_ts = start_ts + pd.Timedelta(minutes=n_bars - 1)
    else:
        n_bars = abs(window_min)
        end_ts = pre_event_end(event_ts)
        start_ts = end_ts - pd.Timedelta(minutes=n_bars - 1)

    if not has_full_window(prices, start_ts, end_ts, n_bars):
        return None

    base = float(prices.loc[start_ts, "open"])
    target = float(prices.loc[end_ts, "close"])
    pct = (target - base) / base * 100
    vol_window = float(prices.loc[start_ts:end_ts, "volume"].sum())
    return {
        "base_ts": start_ts,
        "target_ts": end_ts,
        "base": base,
        "target": target,
        "delta_pct": pct,
        "volume": vol_window,
    }


# ---------------------------------------------------------------------------
# Closed periods, baseline pools, and volume baselines
# ---------------------------------------------------------------------------


def detect_closed_periods(prices: pd.DataFrame, threshold_min: int = GAP_THRESHOLD_MIN):
    """Return list of market-closed gaps inferred from price timestamps."""
    deltas = prices.index.to_series().diff()
    big_gaps = deltas[deltas > pd.Timedelta(minutes=threshold_min)]
    closed_periods = []
    for open_ts, delta in big_gaps.items():
        gap_start_nominal = open_ts - delta
        prev_idx = prices.index.get_indexer([gap_start_nominal], method="pad")[0]
        next_idx = prices.index.get_loc(open_ts)
        close_ts = prices.index[prev_idx]
        closed_periods.append({
            "close_ts": close_ts,
            "close_price": float(prices["close"].iloc[prev_idx]),
            "open_ts": open_ts,
            "open_price": float(prices["open"].iloc[next_idx]),
            "duration_min": float(delta.total_seconds() / 60),
        })
    return closed_periods


def is_event_in_closed_period(event_ts, closed_periods):
    for cp in closed_periods:
        if cp["close_ts"] < event_ts < cp["open_ts"]:
            return cp
    return None


def build_excluded_starts(event_timestamps, window_min: int, exclude_buffer_min: int):
    if not len(event_timestamps):
        return pd.DatetimeIndex([], tz="UTC")
    event_minutes = pd.DatetimeIndex([pd.Timestamp(t).floor("min") for t in event_timestamps])
    left = window_min - 1 + exclude_buffer_min
    right = exclude_buffer_min
    deltas = np.arange(-left, right + 1) * np.timedelta64(1, "m")
    excluded = (event_minutes.to_numpy(dtype="datetime64[ns]")[:, None] + deltas[None, :]).ravel()
    return pd.DatetimeIndex(excluded).tz_localize("UTC")


def build_baseline_pool(
    prices: pd.DataFrame,
    event_timestamps,
    window_min: int,
    exclude_buffer_min: int = DEFAULT_EXCLUDE_BUFFER_MIN,
) -> pd.DataFrame:
    """All valid non-event windows for one asset/window."""
    starts = prices.index
    ends = starts + pd.Timedelta(minutes=window_min - 1)
    has_end = ends.isin(prices.index)
    excluded = build_excluded_starts(event_timestamps, window_min, exclude_buffer_min)
    valid = has_end & ~starts.isin(excluded)

    starts = starts[valid]
    ends = starts + pd.Timedelta(minutes=window_min - 1)
    if len(starts) == 0:
        return pd.DataFrame(columns=["start_ts", "end_ts", "delta_pct", "hour_utc", "dow"])

    base = prices.loc[starts, "open"].to_numpy(dtype=float)
    target = prices.loc[ends, "close"].to_numpy(dtype=float)
    start_pos = prices.index.get_indexer(starts)
    end_pos = prices.index.get_indexer(ends)
    cum_volume = np.r_[0.0, prices["volume"].to_numpy(dtype=float).cumsum()]
    volume = cum_volume[end_pos + 1] - cum_volume[start_pos]
    delta_pct = (target - base) / base * 100
    return pd.DataFrame({
        "start_ts": starts,
        "end_ts": ends,
        "delta_pct": delta_pct,
        "volume": volume,
        "hour_utc": starts.hour,
        "dow": starts.dayofweek,
    })


def sample_matched_baseline(
    pool: pd.DataFrame,
    reference_timestamps,
    window_min: int,
    rng: np.random.Generator,
    n_per_event: int,
) -> np.ndarray:
    """Sample baseline returns matched by same hour and day-of-week when possible."""
    if pool.empty or len(reference_timestamps) == 0:
        return np.array([])

    by_hour_dow = {
        key: group["delta_pct"].to_numpy(dtype=float)
        for key, group in pool.groupby(["hour_utc", "dow"])
    }
    by_hour = {
        key: group["delta_pct"].to_numpy(dtype=float)
        for key, group in pool.groupby("hour_utc")
    }
    all_values = pool["delta_pct"].to_numpy(dtype=float)

    sampled = []
    for ts in reference_timestamps:
        ref = post_event_start(pd.Timestamp(ts))
        candidates = by_hour_dow.get((ref.hour, ref.dayofweek))
        if candidates is None or len(candidates) < max(10, n_per_event):
            candidates = by_hour.get(ref.hour)
        if candidates is None or len(candidates) == 0:
            candidates = all_values
        replace = len(candidates) < n_per_event
        idx = rng.choice(len(candidates), size=n_per_event, replace=replace)
        sampled.extend(candidates[idx])
    return np.asarray(sampled, dtype=float)


def attach_volume_ratios(returns_df: pd.DataFrame, baseline_pools: dict[tuple[str, int], pd.DataFrame]):
    """Attach volume ratios using precomputed matched baseline pools.

    This replaces the old per-event rolling volume calculation. It is both
    faster and more consistent with the H1/H8 matched baseline design.
    """
    returns_df = returns_df.copy()
    returns_df["volume_ratio"] = np.nan
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            mask = (
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & returns_df["volume"].notna()
                & returns_df["base_ts"].notna()
            )
            if not mask.any():
                continue
            pool = baseline_pools.get((asset, w), pd.DataFrame())
            if pool.empty or "volume" not in pool:
                continue
            med_hour_dow = pool.groupby(["hour_utc", "dow"])["volume"].median()
            med_hour = pool.groupby("hour_utc")["volume"].median()
            med_all = float(pool["volume"].median())

            sub = returns_df.loc[mask, ["base_ts", "volume"]].copy()
            base_ts = pd.to_datetime(sub["base_ts"], utc=True)
            hours = base_ts.dt.hour.to_numpy()
            dows = base_ts.dt.dayofweek.to_numpy()
            baselines = []
            for h, d in zip(hours, dows):
                val = med_hour_dow.get((h, d), np.nan)
                if pd.isna(val):
                    val = med_hour.get(h, np.nan)
                if pd.isna(val):
                    val = med_all
                baselines.append(val)
            baselines = np.asarray(baselines, dtype=float)
            ratios = sub["volume"].to_numpy(dtype=float) / baselines
            ratios[~np.isfinite(ratios)] = np.nan
            returns_df.loc[mask, "volume_ratio"] = ratios
    return returns_df


# ---------------------------------------------------------------------------
# Event-window generation
# ---------------------------------------------------------------------------


def compute_returns_for_events(events, prices, closed_periods_by_asset):
    rows = []
    for _, ev in events.iterrows():
        ts = ev["timestamp_utc"]
        for asset in ASSETS:
            in_closed = is_event_in_closed_period(ts, closed_periods_by_asset[asset])
            sentiment_col = sentiment_col_for_asset(asset)
            strength_col = strength_col_for_asset(asset)
            for w in WINDOWS_MIN:
                row = {
                    "event_id": ev.get("id", ""),
                    "event_cluster_id": ev.get("event_cluster_id", np.nan),
                    "event_cluster_pos": ev.get("event_cluster_pos", np.nan),
                    "event_cluster_size": ev.get("event_cluster_size", np.nan),
                    "timestamp_utc": ts,
                    "asset": asset,
                    "asset_target": target_label_for_asset(asset),
                    "window_min": w,
                    "category": ev.get("category", ""),
                    "sentiment_usd": ev.get("sentiment_usd", ""),
                    "sentiment_ndx": ev.get("sentiment_ndx", ""),
                    "target_sentiment": ev.get(sentiment_col, ""),
                    "directional_strength_usd": pd.to_numeric(ev.get("directional_strength_usd", np.nan), errors="coerce"),
                    "directional_strength_ndx": pd.to_numeric(ev.get("directional_strength_ndx", np.nan), errors="coerce"),
                    "target_directional_strength": pd.to_numeric(ev.get(strength_col, np.nan), errors="coerce"),
                    "expected_magnitude": ev.get("expected_magnitude", ""),
                    "surprise_level": ev.get("surprise_level", ""),
                    "confidence": pd.to_numeric(ev.get("confidence", np.nan), errors="coerce"),
                    "hour_utc": ts.hour,
                    "dow": ts.dayofweek,
                    "is_in_closed_period": in_closed is not None,
                }

                if in_closed:
                    row.update({
                        "base_ts": pd.NaT,
                        "target_ts": pd.NaT,
                        "base": np.nan,
                        "target": np.nan,
                        "delta_pct": np.nan,
                        "target_delta_pct": np.nan,
                        "volume": np.nan,
                        "volume_ratio": np.nan,
                        "pre_delta_pct_15": np.nan,
                        "pre_target_delta_pct_15": np.nan,
                        "pre_delta_pct_60": np.nan,
                        "pre_target_delta_pct_60": np.nan,
                    })
                else:
                    res = compute_event_window(ts, prices[asset], w)
                    if res is None:
                        row.update({
                            "base_ts": pd.NaT,
                            "target_ts": pd.NaT,
                            "base": np.nan,
                            "target": np.nan,
                            "delta_pct": np.nan,
                            "target_delta_pct": np.nan,
                            "volume": np.nan,
                            "volume_ratio": np.nan,
                        })
                    else:
                        row.update(res)
                        row["target_delta_pct"] = orient_delta(asset, res["delta_pct"])
                        row["volume_ratio"] = np.nan
                    for pw in PRE_WINDOWS_MIN:
                        pre = compute_event_window(ts, prices[asset], -pw)
                        if pre is None:
                            row[f"pre_delta_pct_{pw}"] = np.nan
                            row[f"pre_target_delta_pct_{pw}"] = np.nan
                        else:
                            row[f"pre_delta_pct_{pw}"] = pre["delta_pct"]
                            row[f"pre_target_delta_pct_{pw}"] = orient_delta(asset, pre["delta_pct"])
                rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


def first_per_cluster(sub: pd.DataFrame) -> pd.DataFrame:
    if "event_cluster_id" not in sub.columns:
        return sub
    return sub.sort_values("timestamp_utc").drop_duplicates("event_cluster_id", keep="first")


def n_clusters(sub: pd.DataFrame) -> int:
    if "event_cluster_id" not in sub.columns:
        return len(sub)
    return int(sub["event_cluster_id"].nunique())


def ttest_ind_greater(a, b):
    try:
        return stats.ttest_ind(a, b, equal_var=False, alternative="greater")
    except TypeError:
        stat, p_two = stats.ttest_ind(a, b, equal_var=False)
        p = p_two / 2 if stat > 0 else 1 - p_two / 2
        return stat, p


def fit_ols_robust(y: pd.Series, X: pd.DataFrame, groups: pd.Series | None = None):
    model = sm.OLS(y, X)
    if groups is not None and pd.Series(groups).nunique() >= 2:
        return model.fit(cov_type="cluster", cov_kwds={"groups": groups})
    return model.fit(cov_type="HC3")


def bh_qvalues(pvalues: list[float]) -> np.ndarray:
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


def add_fdr_corrections(frames: dict[str, pd.DataFrame]):
    records = []
    for name, df in frames.items():
        if df is None or df.empty:
            continue
        for col in [c for c in df.columns if c.startswith("p_")]:
            vals = pd.to_numeric(df[col], errors="coerce")
            for idx, val in vals.items():
                if pd.notna(val):
                    records.append((name, idx, col, float(val)))

    if not records:
        return frames

    qvals = bh_qvalues([r[3] for r in records])
    for (name, idx, col, _), q in zip(records, qvals):
        q_col = f"q_{col[2:]}"
        frames[name].loc[idx, q_col] = q
    return frames


# ---------------------------------------------------------------------------
# Hypothesis tests
# ---------------------------------------------------------------------------


def test_h1(returns_df, baseline_pools, rng, baseline_per_event, cluster_dedupe=True):
    print("\n=== H1: abs returns events vs matched random baseline ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub_raw = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & (returns_df["delta_pct"].notna())
            ].copy()
            sub = first_per_cluster(sub_raw) if cluster_dedupe else sub_raw
            if len(sub) < 2:
                continue
            event_abs = sub["delta_pct"].abs().to_numpy(dtype=float)
            baseline = sample_matched_baseline(
                baseline_pools[(asset, w)],
                sub["timestamp_utc"].tolist(),
                w,
                rng,
                baseline_per_event,
            )
            baseline_abs = np.abs(baseline)
            if len(baseline_abs) < 10:
                continue
            t_stat, p_t = ttest_ind_greater(event_abs, baseline_abs)
            u_stat, p_u = stats.mannwhitneyu(event_abs, baseline_abs, alternative="greater")
            results.append({
                "asset": asset,
                "asset_target": target_label_for_asset(asset),
                "window_min": w,
                "n_events_raw": len(sub_raw),
                "n_events_used": len(sub),
                "n_clusters": n_clusters(sub),
                "n_baseline": len(baseline_abs),
                "mean_abs_event": float(event_abs.mean()),
                "mean_abs_baseline": float(baseline_abs.mean()),
                "ratio": float(event_abs.mean() / baseline_abs.mean()) if baseline_abs.mean() > 0 else np.nan,
                "t_stat": float(t_stat),
                "p_ttest_greater": float(p_t),
                "u_stat": float(u_stat),
                "p_mwu_greater": float(p_u),
            })
            print(
                f"  {asset:6s} +{w:3d}m: used={len(sub):4d}/{len(sub_raw):4d} "
                f"event={event_abs.mean():.4f} base={baseline_abs.mean():.4f} "
                f"ratio={event_abs.mean()/baseline_abs.mean():.2f}x p_MWU={p_u:.4g}"
            )
    return pd.DataFrame(results)


def test_h2(returns_df, cluster_dedupe=True):
    print("\n=== H2: target sentiment vs realized target direction ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub_raw = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & (returns_df["target_delta_pct"].notna())
                & (returns_df["target_sentiment"].isin(["bull", "bear"]))
                & (returns_df["target_delta_pct"] != 0)
            ].copy()
            sub = first_per_cluster(sub_raw) if cluster_dedupe else sub_raw
            if len(sub) < 2:
                continue
            realized = np.where(sub["target_delta_pct"] > 0, "bull", "bear")
            correct = int((sub["target_sentiment"].to_numpy() == realized).sum())
            n = len(sub)
            p_binom = stats.binomtest(correct, n, p=0.5, alternative="greater").pvalue
            results.append({
                "asset": asset,
                "asset_target": target_label_for_asset(asset),
                "window_min": w,
                "n_raw": len(sub_raw),
                "n": n,
                "n_clusters": n_clusters(sub),
                "correct": correct,
                "hit_rate": correct / n,
                "p_binom_greater": float(p_binom),
            })
            print(
                f"  {asset:6s} +{w:3d}m: n={n:4d} hit={correct/n:5.1%} "
                f"({correct}/{n}) p={p_binom:.4g}"
            )
    return pd.DataFrame(results)


def compute_day_trend(prices, event_ts, lookback_min=60):
    end = pre_event_end(event_ts)
    start = end - pd.Timedelta(minutes=lookback_min - 1)
    if not has_full_window(prices, start, end, lookback_min):
        return np.nan
    base = float(prices.loc[start, "open"])
    target = float(prices.loc[end, "close"])
    return (target - base) / base * 100


def test_h3(returns_df, prices):
    print("\n=== H3: sentiment x prior trend interaction (robust OLS) ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & (returns_df["delta_pct"].notna())
            ].copy()
            if len(sub) < 20:
                continue
            sub["sentiment_num"] = sub["target_sentiment"].map({"bull": 1, "neutral": 0, "bear": -1})
            sub["price_trend_60m"] = sub["timestamp_utc"].apply(lambda t: compute_day_trend(prices[asset], t))
            sub["target_trend_60m"] = orient_delta(asset, sub["price_trend_60m"])
            sub = sub.dropna(subset=["sentiment_num", "target_trend_60m"])
            if len(sub) < 20:
                continue
            X = sub[["sentiment_num", "target_trend_60m"]].copy()
            X["interaction"] = X["sentiment_num"] * X["target_trend_60m"]
            X = sm.add_constant(X)
            y = sub["delta_pct"].abs()
            try:
                model = fit_ols_robust(y, X, groups=sub["event_cluster_id"])
            except Exception as exc:
                print(f"  {asset:6s} +{w:3d}m: OLS failed: {exc}")
                continue
            row = {
                "asset": asset,
                "asset_target": target_label_for_asset(asset),
                "window_min": w,
                "n": len(sub),
                "n_clusters": n_clusters(sub),
                "r2": float(model.rsquared),
                "cov_type": str(model.cov_type),
            }
            for name in ["sentiment_num", "target_trend_60m", "interaction"]:
                row[f"coef_{name}"] = float(model.params[name])
                row[f"se_{name}"] = float(model.bse[name])
                row[f"p_{name}"] = float(model.pvalues[name])
            results.append(row)
            print(
                f"  {asset:6s} +{w:3d}m: n={len(sub):4d} clusters={n_clusters(sub):4d} "
                f"R2={model.rsquared:.3f} beta_inter={model.params['interaction']:+.4f} "
                f"p={model.pvalues['interaction']:.4g}"
            )
    return pd.DataFrame(results)


def test_h4(events, closed_periods_by_asset):
    print("\n=== H4: closed-period gap vs aggregate target sentiment ===")
    period_rows = []
    for asset in ASSETS:
        sentiment_col = sentiment_col_for_asset(asset)
        for cp in closed_periods_by_asset[asset]:
            mask = (events["timestamp_utc"] > cp["close_ts"]) & (events["timestamp_utc"] < cp["open_ts"])
            ev_in_raw = events[mask].copy()
            if ev_in_raw.empty:
                continue
            ev_in = first_per_cluster(ev_in_raw) if "event_cluster_id" in ev_in_raw.columns else ev_in_raw
            sentiment_num = ev_in[sentiment_col].map({"bull": 1, "neutral": 0, "bear": -1})
            confidence = pd.to_numeric(ev_in["confidence"], errors="coerce").fillna(0)
            if confidence.sum() > 0:
                agg = float((sentiment_num.fillna(0) * confidence).sum() / confidence.sum())
            else:
                agg = float(sentiment_num.fillna(0).mean()) if len(sentiment_num) else 0.0
            price_gap_pct = (cp["open_price"] - cp["close_price"]) / cp["close_price"] * 100
            target_gap_pct = orient_delta(asset, price_gap_pct)
            period_rows.append({
                "asset": asset,
                "asset_target": target_label_for_asset(asset),
                "close_ts": cp["close_ts"],
                "open_ts": cp["open_ts"],
                "duration_min": cp["duration_min"],
                "n_events_raw": len(ev_in_raw),
                "n_events_used": len(ev_in),
                "agg_target_sentiment": agg,
                "price_gap_pct": float(price_gap_pct),
                "target_gap_pct": float(target_gap_pct),
            })

    periods = pd.DataFrame(period_rows)
    if periods.empty:
        return pd.DataFrame(), periods

    summaries = []
    for asset in ASSETS:
        sub = periods[periods["asset"] == asset].copy()
        if len(sub) < 4:
            continue
        X = sm.add_constant(sub[["agg_target_sentiment"]])
        y = sub["target_gap_pct"]
        model = fit_ols_robust(y, X)
        summaries.append({
            "asset": asset,
            "asset_target": target_label_for_asset(asset),
            "n_periods": len(sub),
            "mean_abs_price_gap_pct": float(sub["price_gap_pct"].abs().mean()),
            "coef_agg_target_sentiment": float(model.params["agg_target_sentiment"]),
            "se_agg_target_sentiment": float(model.bse["agg_target_sentiment"]),
            "p_agg_target_sentiment": float(model.pvalues["agg_target_sentiment"]),
            "r2": float(model.rsquared),
            "cov_type": str(model.cov_type),
        })
        print(
            f"  {asset:6s}: periods={len(sub):3d} beta={model.params['agg_target_sentiment']:+.4f} "
            f"p={model.pvalues['agg_target_sentiment']:.4g} R2={model.rsquared:.3f}"
        )
    return pd.DataFrame(summaries), periods


def test_h5_magnitude(returns_df, cluster_dedupe=True):
    print("\n=== H5: expected_magnitude predicts abs returns ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub_raw = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & returns_df["delta_pct"].notna()
                & returns_df["expected_magnitude"].isin(["low", "med", "high"])
            ].copy()
            sub = first_per_cluster(sub_raw) if cluster_dedupe else sub_raw
            if len(sub) < 10:
                continue
            sub["abs_pct"] = sub["delta_pct"].abs()
            groups = [
                sub[sub["expected_magnitude"] == g]["abs_pct"].to_numpy(dtype=float)
                for g in ("low", "med", "high")
            ]
            groups_valid = [g for g in groups if len(g) >= 2]
            if len(groups_valid) < 2:
                continue
            f_stat, p_anova = stats.f_oneway(*groups_valid)
            k_stat, p_kruskal = stats.kruskal(*groups_valid)
            means = {
                g: float(sub[sub["expected_magnitude"] == g]["abs_pct"].mean())
                for g in ("low", "med", "high")
                if (sub["expected_magnitude"] == g).any()
            }
            row = {
                "asset": asset,
                "asset_target": target_label_for_asset(asset),
                "window_min": w,
                "n_raw": len(sub_raw),
                "n": len(sub),
                "n_clusters": n_clusters(sub),
                "n_low": int((sub["expected_magnitude"] == "low").sum()),
                "n_med": int((sub["expected_magnitude"] == "med").sum()),
                "n_high": int((sub["expected_magnitude"] == "high").sum()),
                "mean_low": means.get("low", np.nan),
                "mean_med": means.get("med", np.nan),
                "mean_high": means.get("high", np.nan),
                "f_stat": float(f_stat),
                "p_anova": float(p_anova),
                "kruskal_stat": float(k_stat),
                "p_kruskal": float(p_kruskal),
            }
            results.append(row)
            print(
                f"  {asset:6s} +{w:3d}m: n={len(sub):4d} "
                f"low={row['mean_low']:.4f} med={row['mean_med']:.4f} "
                f"high={row['mean_high']:.4f} pK={p_kruskal:.4g}"
            )
    return pd.DataFrame(results)


def test_h6_calibration(returns_df, cluster_dedupe=True):
    print("\n=== H6: confidence calibration (NDX +15m) ===")
    sub_raw = returns_df[
        (returns_df["asset"] == "ndx")
        & (returns_df["window_min"] == 15)
        & returns_df["target_delta_pct"].notna()
        & returns_df["target_sentiment"].isin(["bull", "bear"])
        & returns_df["confidence"].notna()
        & (returns_df["target_delta_pct"] != 0)
    ].copy()
    sub = first_per_cluster(sub_raw) if cluster_dedupe else sub_raw
    if len(sub) < 20:
        return pd.DataFrame()

    sub["realized_up"] = (sub["target_delta_pct"] > 0).astype(int)
    sub["predicted_up"] = (sub["target_sentiment"] == "bull").astype(int)
    sub["correct"] = (sub["realized_up"] == sub["predicted_up"]).astype(int)
    pred_prob_up = np.where(sub["predicted_up"] == 1, sub["confidence"], 1 - sub["confidence"])
    brier = float(np.mean((pred_prob_up - sub["realized_up"]) ** 2))

    edges = [0.0, 0.4, 0.6, 0.8, 1.0001]
    labels = ["[0,0.4)", "[0.4,0.6)", "[0.6,0.8)", "[0.8,1.0]"]
    sub["bucket"] = pd.cut(sub["confidence"], bins=edges, labels=labels, right=False, include_lowest=True)

    rows = []
    for lab in labels:
        bk = sub[sub["bucket"] == lab]
        if bk.empty:
            continue
        rows.append({
            "asset": "ndx",
            "asset_target": target_label_for_asset("ndx"),
            "window_min": 15,
            "bucket": lab,
            "n_raw": len(sub_raw),
            "n": len(bk),
            "mean_confidence": float(bk["confidence"].mean()),
            "hit_rate": float(bk["correct"].mean()),
            "brier_overall": brier,
        })
        print(
            f"  conf {lab:<10s}: n={len(bk):4d} mean_conf={bk['confidence'].mean():.3f} "
            f"hit={bk['correct'].mean():.1%}"
        )
    print(f"  Brier score: {brier:.4f}")
    return pd.DataFrame(rows)


def test_h7_category(returns_df, cluster_dedupe=True):
    print("\n=== H7: category effect on abs returns (+15m) ===")
    results = []
    for asset in ASSETS:
        sub_raw = returns_df[
            (returns_df["asset"] == asset)
            & (returns_df["window_min"] == 15)
            & returns_df["delta_pct"].notna()
            & returns_df["category"].notna()
            & (returns_df["category"] != "")
        ].copy()
        sub = first_per_cluster(sub_raw) if cluster_dedupe else sub_raw
        if len(sub) < 20:
            continue
        sub["abs_pct"] = sub["delta_pct"].abs()
        valid_cats = [
            c for c, g in sub.groupby("category")["abs_pct"]
            if len(g) >= 5
        ]
        if len(valid_cats) < 2:
            continue
        groups = [sub[sub["category"] == c]["abs_pct"].to_numpy(dtype=float) for c in valid_cats]
        f_stat, p_anova = stats.f_oneway(*groups)
        k_stat, p_kruskal = stats.kruskal(*groups)
        print(f"  {asset:6s}: categories={len(valid_cats)} pK={p_kruskal:.4g}")
        for c in valid_cats:
            vals = sub[sub["category"] == c]["abs_pct"]
            results.append({
                "asset": asset,
                "asset_target": target_label_for_asset(asset),
                "category": c,
                "n_raw": int((sub_raw["category"] == c).sum()),
                "n": int((sub["category"] == c).sum()),
                "mean_abs_pct": float(vals.mean()),
                "median_abs_pct": float(vals.median()),
                "f_anova": float(f_stat),
                "p_anova": float(p_anova),
                "kruskal_stat": float(k_stat),
                "p_kruskal": float(p_kruskal),
            })
    return pd.DataFrame(results)


def test_h8_pre_event_drift(returns_df, baseline_pools, rng, baseline_per_event, cluster_dedupe=True):
    print("\n=== H8: pre-event drift vs matched baseline ===")
    results = []
    for asset in ASSETS:
        sub_raw = returns_df[
            (returns_df["asset"] == asset)
            & (returns_df["window_min"] == 15)
            & returns_df["pre_delta_pct_15"].notna()
        ].copy()
        sub = first_per_cluster(sub_raw) if cluster_dedupe else sub_raw
        if len(sub) < 20:
            continue
        pre_abs = sub["pre_delta_pct_15"].abs().to_numpy(dtype=float)
        paired = sub[sub["delta_pct"].notna()].copy()
        post_abs = paired["delta_pct"].abs().to_numpy(dtype=float)
        pre_paired_abs = paired["pre_delta_pct_15"].abs().to_numpy(dtype=float)
        if len(paired) >= 2:
            t_pair, p_pair = stats.ttest_rel(pre_paired_abs, post_abs)
        else:
            t_pair, p_pair = (np.nan, np.nan)

        baseline = sample_matched_baseline(
            baseline_pools[(asset, 15)],
            sub["timestamp_utc"].tolist(),
            15,
            rng,
            baseline_per_event,
        )
        baseline_abs = np.abs(baseline)
        if len(baseline_abs) >= 10:
            t_b, p_b = ttest_ind_greater(pre_abs, baseline_abs)
            u_b, p_mwu = stats.mannwhitneyu(pre_abs, baseline_abs, alternative="greater")
        else:
            t_b = p_b = u_b = p_mwu = np.nan
        results.append({
            "asset": asset,
            "asset_target": target_label_for_asset(asset),
            "n_raw": len(sub_raw),
            "n_events": len(sub),
            "n_clusters": n_clusters(sub),
            "n_paired_post": len(paired),
            "mean_pre_abs": float(np.mean(pre_abs)),
            "mean_post_abs": float(np.mean(post_abs)) if len(post_abs) else np.nan,
            "mean_baseline_abs": float(np.mean(baseline_abs)) if len(baseline_abs) else np.nan,
            "t_pre_vs_post_paired": float(t_pair) if pd.notna(t_pair) else np.nan,
            "p_pre_vs_post_paired": float(p_pair) if pd.notna(p_pair) else np.nan,
            "t_pre_vs_baseline": float(t_b) if pd.notna(t_b) else np.nan,
            "p_pre_vs_baseline_t_greater": float(p_b) if pd.notna(p_b) else np.nan,
            "u_pre_vs_baseline": float(u_b) if pd.notna(u_b) else np.nan,
            "p_pre_vs_baseline_mwu_greater": float(p_mwu) if pd.notna(p_mwu) else np.nan,
        })
        print(
            f"  {asset:6s}: n={len(sub):4d} pre={np.mean(pre_abs):.4f} "
            f"post={np.mean(post_abs) if len(post_abs) else np.nan:.4f} "
            f"base={np.mean(baseline_abs) if len(baseline_abs) else np.nan:.4f} "
            f"p_MWU={p_mwu:.4g}"
        )
    return pd.DataFrame(results)


def test_h9_decay(returns_df, cluster_dedupe=True):
    print("\n=== H9: impact persistence (+15m vs +4h) ===")
    results = []
    for asset in ASSETS:
        sub = returns_df[
            (returns_df["asset"] == asset)
            & returns_df["delta_pct"].notna()
            & returns_df["window_min"].isin([15, 240])
        ].copy()
        if cluster_dedupe:
            sub = sub.sort_values("timestamp_utc").drop_duplicates(["event_cluster_id", "window_min"], keep="first")
            index_col = "event_cluster_id"
        else:
            index_col = "event_id"
        wide = sub.pivot_table(index=index_col, columns="window_min", values="delta_pct", aggfunc="first").dropna()
        if len(wide) < 20:
            continue
        sign_match = np.sign(wide[15]) == np.sign(wide[240])
        p_binom = stats.binomtest(int(sign_match.sum()), len(wide), p=0.5, alternative="two-sided").pvalue
        ratio = (wide[240].abs() / wide[15].abs().replace(0, np.nan)).median()
        results.append({
            "asset": asset,
            "asset_target": target_label_for_asset(asset),
            "n_events": int(len(wide)),
            "sign_match_rate": float(sign_match.mean()),
            "p_binom_persistence": float(p_binom),
            "median_ratio_4h_to_15m": float(ratio),
        })
        print(
            f"  {asset:6s}: n={len(wide):4d} sign-match={sign_match.mean():.1%} "
            f"p={p_binom:.4g} ratio={ratio:.2f}"
        )
    return pd.DataFrame(results)


def test_h10_volume(returns_df, cluster_dedupe=True):
    print("\n=== H10: volume ratio vs prior matched baseline ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub_raw = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & returns_df["volume_ratio"].notna()
                & np.isfinite(returns_df["volume_ratio"])
            ].copy()
            sub = first_per_cluster(sub_raw) if cluster_dedupe else sub_raw
            if len(sub) < 20:
                continue
            ratios = sub["volume_ratio"].to_numpy(dtype=float)
            try:
                stat, p_wilcoxon = stats.wilcoxon(ratios - 1.0, alternative="greater")
            except ValueError:
                stat, p_wilcoxon = (np.nan, np.nan)
            results.append({
                "asset": asset,
                "asset_target": target_label_for_asset(asset),
                "window_min": w,
                "n_raw": len(sub_raw),
                "n": len(sub),
                "n_clusters": n_clusters(sub),
                "mean_volume_ratio": float(np.mean(ratios)),
                "median_volume_ratio": float(np.median(ratios)),
                "wilcoxon_stat": float(stat) if pd.notna(stat) else np.nan,
                "p_wilcoxon_gt1": float(p_wilcoxon) if pd.notna(p_wilcoxon) else np.nan,
                "volume_caveat": "Dukascopy volume is proxy/tick volume, not consolidated exchange/interbank volume.",
            })
            print(
                f"  {asset:6s} +{w:3d}m: n={len(sub):4d} median={np.median(ratios):.2f} "
                f"p={p_wilcoxon:.4g}"
            )
    return pd.DataFrame(results)


def test_h11_time_of_day(returns_df, cluster_dedupe=True):
    print("\n=== H11: time-of-day and day-of-week effect (+15m) ===")
    results = []
    for asset in ASSETS:
        sub_raw = returns_df[
            (returns_df["asset"] == asset)
            & (returns_df["window_min"] == 15)
            & returns_df["delta_pct"].notna()
        ].copy()
        sub = first_per_cluster(sub_raw) if cluster_dedupe else sub_raw
        if len(sub) < 50:
            continue
        sub["abs_pct"] = sub["delta_pct"].abs()
        hour_groups = [g["abs_pct"].to_numpy(dtype=float) for _, g in sub.groupby("hour_utc") if len(g) >= 3]
        dow_groups = [g["abs_pct"].to_numpy(dtype=float) for _, g in sub.groupby("dow") if len(g) >= 3]
        f_h, p_h = stats.f_oneway(*hour_groups) if len(hour_groups) >= 2 else (np.nan, np.nan)
        f_d, p_d = stats.f_oneway(*dow_groups) if len(dow_groups) >= 2 else (np.nan, np.nan)
        k_h, pk_h = stats.kruskal(*hour_groups) if len(hour_groups) >= 2 else (np.nan, np.nan)
        k_d, pk_d = stats.kruskal(*dow_groups) if len(dow_groups) >= 2 else (np.nan, np.nan)
        results.append({
            "asset": asset,
            "asset_target": target_label_for_asset(asset),
            "n_raw": len(sub_raw),
            "n": len(sub),
            "n_clusters": n_clusters(sub),
            "f_hour": float(f_h),
            "p_hour": float(p_h),
            "kruskal_hour": float(k_h),
            "p_kruskal_hour": float(pk_h),
            "f_dow": float(f_d),
            "p_dow": float(p_d),
            "kruskal_dow": float(k_d),
            "p_kruskal_dow": float(pk_d),
        })
        print(f"  {asset:6s}: n={len(sub):4d} p_hour={p_h:.4g} p_dow={p_d:.4g}")
    return pd.DataFrame(results)


def test_h12_asymmetric(returns_df, cluster_dedupe=True):
    print("\n=== H12: asymmetric response (bear vs bull target sentiment) ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub_raw = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & returns_df["delta_pct"].notna()
                & returns_df["target_sentiment"].isin(["bull", "bear"])
            ].copy()
            sub = first_per_cluster(sub_raw) if cluster_dedupe else sub_raw
            if len(sub) < 20:
                continue
            sub["abs_pct"] = sub["delta_pct"].abs()
            bear = sub[sub["target_sentiment"] == "bear"]["abs_pct"].to_numpy(dtype=float)
            bull = sub[sub["target_sentiment"] == "bull"]["abs_pct"].to_numpy(dtype=float)
            if len(bear) < 5 or len(bull) < 5:
                continue
            t, p_t = ttest_ind_greater(bear, bull)
            u, p_u = stats.mannwhitneyu(bear, bull, alternative="greater")
            results.append({
                "asset": asset,
                "asset_target": target_label_for_asset(asset),
                "window_min": w,
                "n_bear": len(bear),
                "n_bull": len(bull),
                "mean_abs_bear": float(bear.mean()),
                "mean_abs_bull": float(bull.mean()),
                "ratio_bear_to_bull": float(bear.mean() / bull.mean()) if bull.mean() > 0 else np.nan,
                "t_stat": float(t),
                "p_ttest_bear_gt_bull": float(p_t),
                "u_stat": float(u),
                "p_mwu_bear_gt_bull": float(p_u),
            })
            print(
                f"  {asset:6s} +{w:3d}m: bear={bear.mean():.4f} bull={bull.mean():.4f} "
                f"ratio={bear.mean()/bull.mean():.2f} p={p_u:.4g}"
            )
    return pd.DataFrame(results)


def test_h13_surprise(returns_df, cluster_dedupe=True):
    print("\n=== H13: surprise_level predicts abs returns ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub_raw = returns_df[
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & returns_df["delta_pct"].notna()
                & returns_df["surprise_level"].isin(["expected", "surprise", "shock"])
            ].copy()
            sub = first_per_cluster(sub_raw) if cluster_dedupe else sub_raw
            if len(sub) < 20:
                continue
            sub["abs_pct"] = sub["delta_pct"].abs()
            groups = [
                sub[sub["surprise_level"] == s]["abs_pct"].to_numpy(dtype=float)
                for s in ("expected", "surprise", "shock")
            ]
            groups_valid = [g for g in groups if len(g) >= 2]
            if len(groups_valid) < 2:
                continue
            f, p_anova = stats.f_oneway(*groups_valid)
            k, p_kruskal = stats.kruskal(*groups_valid)
            means = {
                s: float(sub[sub["surprise_level"] == s]["abs_pct"].mean())
                for s in ("expected", "surprise", "shock")
                if (sub["surprise_level"] == s).any()
            }
            ns = {s: int((sub["surprise_level"] == s).sum()) for s in ("expected", "surprise", "shock")}
            results.append({
                "asset": asset,
                "asset_target": target_label_for_asset(asset),
                "window_min": w,
                "n_raw": len(sub_raw),
                "n": len(sub),
                "n_clusters": n_clusters(sub),
                "n_expected": ns.get("expected", 0),
                "n_surprise": ns.get("surprise", 0),
                "n_shock": ns.get("shock", 0),
                "mean_expected": means.get("expected", np.nan),
                "mean_surprise": means.get("surprise", np.nan),
                "mean_shock": means.get("shock", np.nan),
                "f_anova": float(f),
                "p_anova": float(p_anova),
                "kruskal_stat": float(k),
                "p_kruskal": float(p_kruskal),
            })
            print(
                f"  {asset:6s} +{w:3d}m: n={len(sub):4d} "
                f"exp={means.get('expected', np.nan):.4f} shock={means.get('shock', np.nan):.4f} "
                f"pK={p_kruskal:.4g}"
            )
    return pd.DataFrame(results)


def test_h14_spillover(returns_df, cluster_dedupe=True):
    print("\n=== H14: cross-asset spillover (+15m) ===")
    sub = returns_df[
        (returns_df["window_min"] == 15)
        & returns_df["delta_pct"].notna()
        & returns_df["target_delta_pct"].notna()
    ].copy()
    if cluster_dedupe:
        sub = sub.sort_values("timestamp_utc").drop_duplicates(["event_cluster_id", "asset"], keep="first")
        index_col = "event_cluster_id"
    else:
        index_col = "event_id"

    price = sub.pivot_table(index=index_col, columns="asset", values="delta_pct", aggfunc="first").dropna()
    target = sub.pivot_table(index=index_col, columns="asset", values="target_delta_pct", aggfunc="first").dropna()
    common = price.index.intersection(target.index)
    price = price.loc[common]
    target = target.loc[common]
    if len(price) < 20:
        return pd.DataFrame()

    eur, ndx = price["eurusd"].to_numpy(dtype=float), price["ndx"].to_numpy(dtype=float)
    usd_proxy, ndx_target = target["eurusd"].to_numpy(dtype=float), target["ndx"].to_numpy(dtype=float)
    pearson_price, p_pearson_price = stats.pearsonr(eur, ndx)
    spearman_price, p_spearman_price = stats.spearmanr(eur, ndx)
    pearson_target, p_pearson_target = stats.pearsonr(usd_proxy, ndx_target)
    spearman_target, p_spearman_target = stats.spearmanr(usd_proxy, ndx_target)
    sign_match_price = np.sign(eur) == np.sign(ndx)
    sign_match_target = np.sign(usd_proxy) == np.sign(ndx_target)
    p_sign_price = stats.binomtest(int(sign_match_price.sum()), len(price), p=0.5).pvalue
    p_sign_target = stats.binomtest(int(sign_match_target.sum()), len(target), p=0.5).pvalue

    out = pd.DataFrame([{
        "n_events": int(len(price)),
        "pearson_eurusd_ndx": float(pearson_price),
        "p_pearson_eurusd_ndx": float(p_pearson_price),
        "spearman_eurusd_ndx": float(spearman_price),
        "p_spearman_eurusd_ndx": float(p_spearman_price),
        "sign_match_eurusd_ndx": float(sign_match_price.mean()),
        "p_binom_sign_eurusd_ndx": float(p_sign_price),
        "pearson_usdproxy_ndx": float(pearson_target),
        "p_pearson_usdproxy_ndx": float(p_pearson_target),
        "spearman_usdproxy_ndx": float(spearman_target),
        "p_spearman_usdproxy_ndx": float(p_spearman_target),
        "sign_match_usdproxy_ndx": float(sign_match_target.mean()),
        "sign_opposite_usdproxy_ndx": float(1 - sign_match_target.mean()),
        "p_binom_sign_usdproxy_ndx": float(p_sign_target),
    }])
    print(
        f"  n={len(price):4d} EURUSDxNDX r={pearson_price:+.3f}; "
        f"USDproxyxNDX r={pearson_target:+.3f}"
    )
    return out


# ---------------------------------------------------------------------------
# Figures and summary metadata
# ---------------------------------------------------------------------------


def make_figures(returns_df, output_dir):
    fig_dir = Path(output_dir) / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    if returns_df.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, asset in zip(axes, ASSETS):
        sub = returns_df[(returns_df["asset"] == asset) & returns_df["delta_pct"].notna()]
        if sub.empty:
            ax.set_title(f"{asset.upper()} - no data")
            continue
        data_by_w = [sub[sub["window_min"] == w]["delta_pct"].abs().to_numpy() for w in WINDOWS_MIN]
        ax.boxplot(data_by_w, tick_labels=[f"+{w}m" for w in WINDOWS_MIN])
        ax.set_title(f"{asset.upper()} - abs price return by window")
        ax.set_ylabel("abs return (%)")
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(fig_dir / "abs_returns_by_window.png", dpi=120)
    plt.close()
    print(f"\nFigures written to {fig_dir}/")


def build_methodology_summary(args, events, prices, common_start, common_end, dropped_common, cluster_dedupe):
    rows = [
        {"setting": "event_window_alignment", "value": "first full minute after event timestamp"},
        {"setting": "pre_event_alignment", "value": "last full minute before event timestamp"},
        {"setting": "eurusd_sentiment_convention", "value": "sentiment_usd evaluated against USD proxy = -EUR/USD return"},
        {"setting": "common_price_start_utc", "value": str(common_start)},
        {"setting": "common_price_end_utc", "value": str(common_end)},
        {"setting": "events_after_common_range_dropped", "value": dropped_common},
        {"setting": "events_used", "value": len(events)},
        {"setting": "event_clusters", "value": int(events["event_cluster_id"].nunique()) if "event_cluster_id" in events else ""},
        {"setting": "cluster_gap_min", "value": args.cluster_gap_min},
        {"setting": "cluster_dedupe_for_non_regression_tests", "value": cluster_dedupe},
        {"setting": "baseline_matching", "value": "same hour UTC and day-of-week when possible"},
        {"setting": "baseline_exclude_buffer_min", "value": args.exclude_buffer_min},
        {"setting": "baseline_per_event", "value": args.baseline_per_event},
        {"setting": "multiple_testing_correction", "value": "Benjamini-Hochberg FDR across all p_* result columns"},
    ]
    for asset, df in prices.items():
        rows.append({"setting": f"prices_{asset}_rows", "value": len(df)})
        rows.append({"setting": f"prices_{asset}_start", "value": str(df.index.min())})
        rows.append({"setting": f"prices_{asset}_end", "value": str(df.index.max())})
    return pd.DataFrame(rows)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", default="outputs/events_sentiment.csv")
    parser.add_argument("--prices-dir", default="outputs")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--all-events", action="store_true", help="Include all events, not only is_gold")
    parser.add_argument("--no-common-range-filter", action="store_true", help="Do not drop events outside common price coverage")
    parser.add_argument("--cluster-gap-min", type=int, default=DEFAULT_CLUSTER_GAP_MIN)
    parser.add_argument("--no-cluster-dedupe", action="store_true", help="Use raw events in non-regression tests")
    parser.add_argument("--baseline-per-event", type=int, default=DEFAULT_BASELINE_PER_EVENT)
    parser.add_argument("--exclude-buffer-min", type=int, default=DEFAULT_EXCLUDE_BUFFER_MIN)
    args = parser.parse_args()

    events, prices = load_data(args.events, args.prices_dir)
    if not args.all_events and "is_gold" in events.columns:
        events = events[events["is_gold"].astype(str) == "True"].copy()

    common_start = max(df.index.min() for df in prices.values())
    common_end = min(df.index.max() for df in prices.values())
    dropped_common = 0
    if not args.no_common_range_filter:
        events, common_start, common_end, dropped_common = filter_events_to_common_price_range(events, prices)

    events = assign_event_clusters(events, gap_min=args.cluster_gap_min)
    cluster_dedupe = not args.no_cluster_dedupe

    print(f"Loaded {len(events)} events after filters; clusters={events['event_cluster_id'].nunique()}")
    if dropped_common:
        print(f"  dropped {dropped_common} events outside common price range {common_start} -> {common_end}")
    for asset, df in prices.items():
        print(f"  prices[{asset}]: {len(df)} bars  {df.index.min()} -> {df.index.max()}")

    closed_periods_by_asset = {}
    for asset, df in prices.items():
        cps = detect_closed_periods(df)
        closed_periods_by_asset[asset] = cps
        print(f"  closed periods detected in {asset}: {len(cps)}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(SEED)
    returns_df = compute_returns_for_events(events, prices, closed_periods_by_asset)

    print("\nBuilding matched baseline pools ...")
    event_timestamps = events["timestamp_utc"].tolist()
    baseline_pools = {}
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            pool = build_baseline_pool(
                prices[asset],
                event_timestamps,
                w,
                exclude_buffer_min=args.exclude_buffer_min,
            )
            baseline_pools[(asset, w)] = pool
            print(f"  baseline[{asset} +{w}m]: {len(pool):,} candidate windows")

    returns_df = attach_volume_ratios(returns_df, baseline_pools)
    returns_path = out_dir / "event_study_windows.csv"
    returns_df.to_csv(returns_path, index=False)
    print(f"\nWrote {len(returns_df)} rows to {returns_path}")
    print(f"  rows with price returns: {int(returns_df['delta_pct'].notna().sum())}")
    print(f"  closed-period rows: {int(returns_df['is_in_closed_period'].sum())}")

    h1 = test_h1(returns_df, baseline_pools, rng, args.baseline_per_event, cluster_dedupe)
    h2 = test_h2(returns_df, cluster_dedupe)
    h3 = test_h3(returns_df, prices)
    h4, h4_periods = test_h4(events, closed_periods_by_asset)
    h5 = test_h5_magnitude(returns_df, cluster_dedupe)
    h6 = test_h6_calibration(returns_df, cluster_dedupe)
    h7 = test_h7_category(returns_df, cluster_dedupe)
    h8 = test_h8_pre_event_drift(returns_df, baseline_pools, rng, args.baseline_per_event, cluster_dedupe)
    h9 = test_h9_decay(returns_df, cluster_dedupe)
    h10 = test_h10_volume(returns_df, cluster_dedupe)
    h11 = test_h11_time_of_day(returns_df, cluster_dedupe)
    h12 = test_h12_asymmetric(returns_df, cluster_dedupe)
    h13 = test_h13_surprise(returns_df, cluster_dedupe)
    h14 = test_h14_spillover(returns_df, cluster_dedupe)

    frames = {
        "h1": h1,
        "h2": h2,
        "h3": h3,
        "h4": h4,
        "h5": h5,
        "h6": h6,
        "h7": h7,
        "h8": h8,
        "h9": h9,
        "h10": h10,
        "h11": h11,
        "h12": h12,
        "h13": h13,
        "h14": h14,
    }
    frames = add_fdr_corrections(frames)

    for name, df in frames.items():
        if df is not None and not df.empty:
            df.to_csv(out_dir / f"{name}_results.csv", index=False)
    if h4_periods is not None and not h4_periods.empty:
        h4_periods.to_csv(out_dir / "h4_periods.csv", index=False)

    methodology = build_methodology_summary(
        args, events, prices, common_start, common_end, dropped_common, cluster_dedupe
    )
    methodology.to_csv(out_dir / "methodology_summary.csv", index=False)

    make_figures(returns_df, args.output_dir)
    print("\nDone.")


if __name__ == "__main__":
    main()
