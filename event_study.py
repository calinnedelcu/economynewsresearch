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
KNOWLEDGE_CUTOFF_TS = pd.Timestamp("2026-01-15", tz="UTC")
MAGNITUDE_SCORE = {"low": 0.0, "med": 1.0, "high": 2.0}
SURPRISE_SCORE = {"expected": 0.0, "surprise": 1.0, "shock": 2.0}


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


def orient_extreme_moves(asset: str, max_up_pct, max_down_pct):
    """Return target-aligned intrawindow favorable/adverse extremes."""
    if asset == "eurusd":
        return -max_down_pct, -max_up_pct
    return max_up_pct, max_down_pct


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
    window = prices.loc[start_ts:end_ts]
    high = float(window["high"].max())
    low = float(window["low"].min())
    pct = (target - base) / base * 100
    max_up_pct = (high - base) / base * 100
    max_down_pct = (low - base) / base * 100
    range_pct = (high - low) / base * 100
    max_abs_move_pct = max(abs(max_up_pct), abs(max_down_pct))
    vol_window = float(prices.loc[start_ts:end_ts, "volume"].sum())
    return {
        "base_ts": start_ts,
        "target_ts": end_ts,
        "base": base,
        "target": target,
        "delta_pct": pct,
        "abs_delta_pct": abs(pct),
        "range_pct": range_pct,
        "max_up_pct": max_up_pct,
        "max_down_pct": max_down_pct,
        "max_abs_move_pct": max_abs_move_pct,
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
    start_pos_all = np.arange(len(starts))
    end_pos_all = prices.index.get_indexer(ends)
    has_end = end_pos_all >= 0
    is_contiguous = has_end & ((end_pos_all - start_pos_all) == (window_min - 1))
    excluded = build_excluded_starts(event_timestamps, window_min, exclude_buffer_min)
    valid = is_contiguous & ~starts.isin(excluded)

    starts = starts[valid]
    ends = starts + pd.Timedelta(minutes=window_min - 1)
    if len(starts) == 0:
        return pd.DataFrame(columns=[
            "start_ts",
            "end_ts",
            "delta_pct",
            "abs_delta_pct",
            "range_pct",
            "max_up_pct",
            "max_down_pct",
            "max_abs_move_pct",
            "volume",
            "hour_utc",
            "dow",
        ])

    base = prices.loc[starts, "open"].to_numpy(dtype=float)
    target = prices.loc[ends, "close"].to_numpy(dtype=float)
    start_pos = prices.index.get_indexer(starts)
    end_pos = prices.index.get_indexer(ends)
    high_roll = (
        prices["high"]
        .rolling(window_min, min_periods=window_min)
        .max()
        .shift(-(window_min - 1))
        .to_numpy(dtype=float)
    )
    low_roll = (
        prices["low"]
        .rolling(window_min, min_periods=window_min)
        .min()
        .shift(-(window_min - 1))
        .to_numpy(dtype=float)
    )
    high = high_roll[start_pos]
    low = low_roll[start_pos]
    cum_volume = np.r_[0.0, prices["volume"].to_numpy(dtype=float).cumsum()]
    volume = cum_volume[end_pos + 1] - cum_volume[start_pos]
    delta_pct = (target - base) / base * 100
    max_up_pct = (high - base) / base * 100
    max_down_pct = (low - base) / base * 100
    range_pct = (high - low) / base * 100
    max_abs_move_pct = np.maximum(np.abs(max_up_pct), np.abs(max_down_pct))
    return pd.DataFrame({
        "start_ts": starts,
        "end_ts": ends,
        "delta_pct": delta_pct,
        "abs_delta_pct": np.abs(delta_pct),
        "range_pct": range_pct,
        "max_up_pct": max_up_pct,
        "max_down_pct": max_down_pct,
        "max_abs_move_pct": max_abs_move_pct,
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
    metric: str = "delta_pct",
) -> np.ndarray:
    """Sample baseline returns matched by same hour and day-of-week when possible."""
    if pool.empty or len(reference_timestamps) == 0 or metric not in pool.columns:
        return np.array([])

    by_hour_dow = {
        key: group[metric].dropna().to_numpy(dtype=float)
        for key, group in pool.groupby(["hour_utc", "dow"])
    }
    by_hour = {
        key: group[metric].dropna().to_numpy(dtype=float)
        for key, group in pool.groupby("hour_utc")
    }
    all_values = pool[metric].dropna().to_numpy(dtype=float)
    if len(all_values) == 0:
        return np.array([])

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


def matched_baseline_moments(pool: pd.DataFrame, metric: str, reference_times: pd.Series):
    """Return mean/std arrays matched by same hour and day-of-week when possible."""
    if pool.empty or metric not in pool.columns:
        n = len(reference_times)
        return np.full(n, np.nan), np.full(n, np.nan)

    vals = pd.to_numeric(pool[metric], errors="coerce")
    valid_pool = pool.loc[vals.notna(), ["hour_utc", "dow"]].copy()
    valid_pool[metric] = vals[vals.notna()].to_numpy(dtype=float)
    if valid_pool.empty:
        n = len(reference_times)
        return np.full(n, np.nan), np.full(n, np.nan)

    by_hour_dow = valid_pool.groupby(["hour_utc", "dow"])[metric].agg(["mean", "std"])
    by_hour = valid_pool.groupby("hour_utc")[metric].agg(["mean", "std"])
    all_mean = float(valid_pool[metric].mean())
    all_std = float(valid_pool[metric].std(ddof=1))
    if not np.isfinite(all_std) or all_std <= 0:
        all_std = np.nan

    reference_times = pd.to_datetime(reference_times, utc=True)
    means, stds = [], []
    for ts in reference_times:
        if pd.isna(ts):
            means.append(np.nan)
            stds.append(np.nan)
            continue
        h, d = ts.hour, ts.dayofweek
        mean = std = np.nan
        if (h, d) in by_hour_dow.index:
            mean = by_hour_dow.loc[(h, d), "mean"]
            std = by_hour_dow.loc[(h, d), "std"]
        if (not np.isfinite(std) or std <= 0) and h in by_hour.index:
            mean = by_hour.loc[h, "mean"]
            std = by_hour.loc[h, "std"]
        if not np.isfinite(mean):
            mean = all_mean
        if not np.isfinite(std) or std <= 0:
            std = all_std
        means.append(mean)
        stds.append(std)
    return np.asarray(means, dtype=float), np.asarray(stds, dtype=float)


def attach_abnormal_scores(returns_df: pd.DataFrame, baseline_pools: dict[tuple[str, int], pd.DataFrame]):
    """Attach matched-baseline abnormal returns and standardized movement scores."""
    returns_df = returns_df.copy()
    returns_df["abs_delta_pct"] = pd.to_numeric(returns_df["delta_pct"], errors="coerce").abs()
    metrics = {
        "delta_pct": "return_z",
        "abs_delta_pct": "abs_return_z",
        "range_pct": "range_z",
        "max_abs_move_pct": "max_abs_move_z",
    }
    for metric, z_col in metrics.items():
        returns_df[f"baseline_{metric}_mean"] = np.nan
        returns_df[f"baseline_{metric}_std"] = np.nan
        returns_df[z_col] = np.nan
    returns_df["abnormal_return_pct"] = np.nan

    for asset in ASSETS:
        for w in WINDOWS_MIN:
            mask = (
                (returns_df["asset"] == asset)
                & (returns_df["window_min"] == w)
                & returns_df["base_ts"].notna()
            )
            if not mask.any():
                continue
            pool = baseline_pools.get((asset, w), pd.DataFrame())
            base_ts = returns_df.loc[mask, "base_ts"]
            idx = returns_df.index[mask]
            for metric, z_col in metrics.items():
                if metric not in returns_df.columns:
                    continue
                means, stds = matched_baseline_moments(pool, metric, base_ts)
                observed = pd.to_numeric(returns_df.loc[idx, metric], errors="coerce").to_numpy(dtype=float)
                z = (observed - means) / stds
                z[~np.isfinite(z)] = np.nan
                returns_df.loc[idx, f"baseline_{metric}_mean"] = means
                returns_df.loc[idx, f"baseline_{metric}_std"] = stds
                returns_df.loc[idx, z_col] = z
                if metric == "delta_pct":
                    abnormal = observed - means
                    abnormal[~np.isfinite(abnormal)] = np.nan
                    returns_df.loc[idx, "abnormal_return_pct"] = abnormal
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
                        "abs_delta_pct": np.nan,
                        "target_delta_pct": np.nan,
                        "range_pct": np.nan,
                        "max_up_pct": np.nan,
                        "max_down_pct": np.nan,
                        "max_abs_move_pct": np.nan,
                        "target_max_up_pct": np.nan,
                        "target_max_down_pct": np.nan,
                        "target_max_abs_move_pct": np.nan,
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
                            "abs_delta_pct": np.nan,
                            "target_delta_pct": np.nan,
                            "range_pct": np.nan,
                            "max_up_pct": np.nan,
                            "max_down_pct": np.nan,
                            "max_abs_move_pct": np.nan,
                            "target_max_up_pct": np.nan,
                            "target_max_down_pct": np.nan,
                            "target_max_abs_move_pct": np.nan,
                            "volume": np.nan,
                            "volume_ratio": np.nan,
                        })
                    else:
                        row.update(res)
                        row["target_delta_pct"] = orient_delta(asset, res["delta_pct"])
                        target_max_up, target_max_down = orient_extreme_moves(
                            asset,
                            res["max_up_pct"],
                            res["max_down_pct"],
                        )
                        row["target_max_up_pct"] = target_max_up
                        row["target_max_down_pct"] = target_max_down
                        row["target_max_abs_move_pct"] = res["max_abs_move_pct"]
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
# Paper-strength extensions: cluster aggregation and robustness tests
# ---------------------------------------------------------------------------


def mode_nonempty(series: pd.Series):
    vals = series.dropna().astype(str)
    vals = vals[vals != ""]
    if vals.empty:
        return ""
    return vals.value_counts().index[0]


def score_label(score, labels: dict[float, str]):
    if pd.isna(score):
        return ""
    rounded = float(round(score))
    return labels.get(rounded, "")


def weighted_average(values: pd.Series, weights: pd.Series):
    values = pd.to_numeric(values, errors="coerce")
    weights = pd.to_numeric(weights, errors="coerce").fillna(0)
    mask = values.notna() & weights.notna() & (weights > 0)
    if mask.any():
        return float(np.average(values[mask], weights=weights[mask]))
    if values.notna().any():
        return float(values.mean())
    return np.nan


def build_cluster_windows(events: pd.DataFrame, returns_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse bursty headlines into one outcome per event cluster/asset/window."""
    if returns_df.empty or "event_cluster_id" not in returns_df.columns:
        return pd.DataFrame()

    ev = events.copy()
    ev["headline_length"] = ev["content"].astype(str).str.len() if "content" in ev.columns else 0
    ev["confidence"] = pd.to_numeric(ev["confidence"], errors="coerce") if "confidence" in ev.columns else np.nan
    ev["_magnitude_score"] = ev["expected_magnitude"].map(MAGNITUDE_SCORE)
    ev["_surprise_score"] = ev["surprise_level"].map(SURPRISE_SCORE)

    cluster_base = ev.groupby("event_cluster_id").agg(
        cluster_start_ts=("timestamp_utc", "min"),
        cluster_end_ts=("timestamp_utc", "max"),
        n_headlines=("id", "size"),
        headline_length_mean=("headline_length", "mean"),
        cluster_confidence_mean=("confidence", "mean"),
        cluster_magnitude_score_max=("_magnitude_score", "max"),
        cluster_magnitude_score_mean=("_magnitude_score", "mean"),
        cluster_surprise_score_max=("_surprise_score", "max"),
        cluster_surprise_score_mean=("_surprise_score", "mean"),
    ).reset_index()
    category = ev.groupby("event_cluster_id")["category"].apply(mode_nonempty).reset_index(name="dominant_category")
    cluster_base = cluster_base.merge(category, on="event_cluster_id", how="left")
    cluster_base["cluster_expected_magnitude"] = cluster_base["cluster_magnitude_score_max"].apply(
        lambda s: score_label(s, {0.0: "low", 1.0: "med", 2.0: "high"})
    )
    cluster_base["cluster_surprise_level"] = cluster_base["cluster_surprise_score_max"].apply(
        lambda s: score_label(s, {0.0: "expected", 1.0: "surprise", 2.0: "shock"})
    )

    asset_rows = []
    for asset in ASSETS:
        sentiment_col = sentiment_col_for_asset(asset)
        strength_col = strength_col_for_asset(asset)
        sentiment_num = ev[sentiment_col].map({"bull": 1.0, "neutral": 0.0, "bear": -1.0})
        strength = pd.to_numeric(ev[strength_col], errors="coerce")
        confidence = pd.to_numeric(ev["confidence"], errors="coerce")
        tmp = ev[["event_cluster_id"]].copy()
        tmp["_sentiment_num"] = sentiment_num
        tmp["_strength"] = strength
        tmp["_confidence"] = confidence
        tmp["_sentiment_label"] = ev[sentiment_col].astype(str)

        for cid, group in tmp.groupby("event_cluster_id"):
            weighted_strength = weighted_average(group["_strength"], group["_confidence"])
            weighted_sentiment = weighted_average(group["_sentiment_num"], group["_confidence"])
            if pd.notna(weighted_strength) and abs(weighted_strength) > 0.05:
                cluster_sentiment = "bull" if weighted_strength > 0 else "bear"
            elif pd.notna(weighted_sentiment) and abs(weighted_sentiment) > 0.05:
                cluster_sentiment = "bull" if weighted_sentiment > 0 else "bear"
            else:
                cluster_sentiment = "neutral"
            label_counts = group["_sentiment_label"].replace("", np.nan).dropna().value_counts()
            agreement = float(label_counts.iloc[0] / label_counts.sum()) if label_counts.sum() else np.nan
            asset_rows.append({
                "event_cluster_id": cid,
                "asset": asset,
                "cluster_target_sentiment": cluster_sentiment,
                "cluster_target_sentiment_score": weighted_sentiment,
                "cluster_target_strength_mean": float(group["_strength"].mean()) if group["_strength"].notna().any() else np.nan,
                "cluster_target_strength_conf_weighted": weighted_strength,
                "cluster_sentiment_agreement_share": agreement,
            })

    asset_cluster = pd.DataFrame(asset_rows)
    cluster_features = cluster_base.merge(asset_cluster, on="event_cluster_id", how="left")

    first_rows = (
        returns_df.sort_values("timestamp_utc")
        .drop_duplicates(["event_cluster_id", "asset", "window_min"], keep="first")
        .copy()
    )
    cluster_df = first_rows.merge(cluster_features, on=["event_cluster_id", "asset"], how="left")
    cluster_df["cluster_abs_target_strength"] = pd.to_numeric(
        cluster_df["cluster_target_strength_conf_weighted"], errors="coerce"
    ).abs()
    return cluster_df


def one_sample_greater(values, center=0.0):
    arr = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 2:
        return np.nan, np.nan, np.nan, np.nan
    try:
        t_stat, p_t = stats.ttest_1samp(arr, popmean=center, alternative="greater")
    except TypeError:
        t_stat, p_two = stats.ttest_1samp(arr, popmean=center)
        p_t = p_two / 2 if t_stat > 0 else 1 - p_two / 2
    try:
        w_stat, p_w = stats.wilcoxon(arr - center, alternative="greater")
    except ValueError:
        w_stat, p_w = (np.nan, np.nan)
    return float(t_stat), float(p_t), float(w_stat) if pd.notna(w_stat) else np.nan, float(p_w) if pd.notna(p_w) else np.nan


def test_cluster_sentiment(cluster_df: pd.DataFrame):
    print("\n=== C1: cluster-level target sentiment vs realized direction ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub = cluster_df[
                (cluster_df["asset"] == asset)
                & (cluster_df["window_min"] == w)
                & cluster_df["target_delta_pct"].notna()
                & cluster_df["cluster_target_sentiment"].isin(["bull", "bear"])
                & (cluster_df["target_delta_pct"] != 0)
            ].copy()
            if len(sub) < 10:
                continue
            realized = np.where(sub["target_delta_pct"] > 0, "bull", "bear")
            correct = int((sub["cluster_target_sentiment"].to_numpy() == realized).sum())
            p_binom = stats.binomtest(correct, len(sub), p=0.5, alternative="greater").pvalue
            results.append({
                "asset": asset,
                "asset_target": target_label_for_asset(asset),
                "window_min": w,
                "n_clusters": len(sub),
                "correct": correct,
                "hit_rate": correct / len(sub),
                "mean_abs_cluster_strength": float(sub["cluster_abs_target_strength"].mean()),
                "p_binom_greater": float(p_binom),
            })
            print(f"  {asset:6s} +{w:3d}m: clusters={len(sub):4d} hit={correct/len(sub):.1%} p={p_binom:.4g}")
    return pd.DataFrame(results)


def test_range_outcomes(cluster_df: pd.DataFrame, baseline_pools, rng, baseline_per_event):
    print("\n=== C2: range/max move outcomes vs matched baseline ===")
    results = []
    metric_labels = {
        "range_pct": "high-low range",
        "max_abs_move_pct": "max absolute intrawindow move",
    }
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub = cluster_df[
                (cluster_df["asset"] == asset)
                & (cluster_df["window_min"] == w)
                & cluster_df["base_ts"].notna()
            ].copy()
            if len(sub) < 20:
                continue
            pool = baseline_pools.get((asset, w), pd.DataFrame())
            for metric, label in metric_labels.items():
                if metric not in sub.columns or metric not in pool.columns:
                    continue
                event_vals = pd.to_numeric(sub[metric], errors="coerce").dropna().to_numpy(dtype=float)
                baseline = sample_matched_baseline(
                    pool,
                    sub["timestamp_utc"].tolist(),
                    w,
                    rng,
                    baseline_per_event,
                    metric=metric,
                )
                if len(event_vals) < 20 or len(baseline) < 50:
                    continue
                t_stat, p_t = ttest_ind_greater(event_vals, baseline)
                u_stat, p_u = stats.mannwhitneyu(event_vals, baseline, alternative="greater")
                results.append({
                    "asset": asset,
                    "asset_target": target_label_for_asset(asset),
                    "window_min": w,
                    "metric": metric,
                    "metric_label": label,
                    "n_clusters": len(event_vals),
                    "n_baseline": len(baseline),
                    "mean_event": float(np.mean(event_vals)),
                    "mean_baseline": float(np.mean(baseline)),
                    "ratio": float(np.mean(event_vals) / np.mean(baseline)) if np.mean(baseline) > 0 else np.nan,
                    "t_stat": float(t_stat),
                    "p_ttest_greater": float(p_t),
                    "u_stat": float(u_stat),
                    "p_mwu_greater": float(p_u),
                })
                print(
                    f"  {asset:6s} +{w:3d}m {metric}: "
                    f"ratio={np.mean(event_vals)/np.mean(baseline):.2f}x p={p_u:.4g}"
                )
    return pd.DataFrame(results)


def test_abnormal_z_outcomes(cluster_df: pd.DataFrame):
    print("\n=== C3: standardized abnormal movement scores ===")
    results = []
    metric_labels = {
        "return_z": "signed close-to-close return z-score",
        "abs_return_z": "absolute close-to-close return z-score",
        "range_z": "high-low range z-score",
        "max_abs_move_z": "max absolute intrawindow move z-score",
    }
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub = cluster_df[(cluster_df["asset"] == asset) & (cluster_df["window_min"] == w)].copy()
            for metric, label in metric_labels.items():
                vals = pd.to_numeric(sub[metric], errors="coerce").dropna()
                if len(vals) < 20:
                    continue
                t_stat, p_t, w_stat, p_w = one_sample_greater(vals, center=0.0)
                results.append({
                    "asset": asset,
                    "asset_target": target_label_for_asset(asset),
                    "window_min": w,
                    "metric": metric,
                    "metric_label": label,
                    "n_clusters": len(vals),
                    "mean_z": float(vals.mean()),
                    "median_z": float(vals.median()),
                    "t_stat": t_stat,
                    "p_ttest_gt0": p_t,
                    "wilcoxon_stat": w_stat,
                    "p_wilcoxon_gt0": p_w,
                })
            if not sub.empty:
                mean_max = pd.to_numeric(sub["max_abs_move_z"], errors="coerce").mean()
                print(f"  {asset:6s} +{w:3d}m: mean max_abs_move_z={mean_max:+.3f}")
    return pd.DataFrame(results)


def test_targeted_categories(cluster_df: pd.DataFrame):
    print("\n=== C4: targeted category hypotheses ===")
    specs = []
    for category in ["central_bank", "politics", "geopolitical", "energy"]:
        for asset in ASSETS:
            specs.extend((category, asset, w) for w in [5, 15, 60])
    specs.extend(("corporate", "ndx", w) for w in [1, 5, 15, 60])

    results = []
    for category, asset, w in specs:
        sub = cluster_df[
            (cluster_df["asset"] == asset)
            & (cluster_df["window_min"] == w)
            & (cluster_df["dominant_category"] == category)
            & cluster_df["base_ts"].notna()
        ].copy()
        if len(sub) < 8:
            continue

        move_vals = pd.to_numeric(sub["max_abs_move_z"], errors="coerce").dropna()
        t_move, p_t_move, w_move, p_w_move = one_sample_greater(move_vals, center=0.0)

        directional = sub[
            sub["cluster_target_sentiment"].isin(["bull", "bear"])
            & sub["target_delta_pct"].notna()
            & (sub["target_delta_pct"] != 0)
        ].copy()
        if len(directional) >= 5:
            realized = np.where(directional["target_delta_pct"] > 0, "bull", "bear")
            correct = int((directional["cluster_target_sentiment"].to_numpy() == realized).sum())
            p_dir = stats.binomtest(correct, len(directional), p=0.5, alternative="greater").pvalue
            hit_rate = correct / len(directional)
        else:
            correct = np.nan
            p_dir = np.nan
            hit_rate = np.nan

        results.append({
            "hypothesis": f"{category}_{asset}_{w}m",
            "category": category,
            "asset": asset,
            "asset_target": target_label_for_asset(asset),
            "window_min": w,
            "n_clusters": len(sub),
            "n_directional": len(directional),
            "direction_correct": correct,
            "direction_hit_rate": hit_rate,
            "p_direction_binom_greater": float(p_dir) if pd.notna(p_dir) else np.nan,
            "mean_max_abs_move_z": float(move_vals.mean()) if len(move_vals) else np.nan,
            "median_max_abs_move_z": float(move_vals.median()) if len(move_vals) else np.nan,
            "t_max_abs_move_z": t_move,
            "p_max_abs_move_z_ttest_gt0": p_t_move,
            "wilcoxon_max_abs_move_z": w_move,
            "p_max_abs_move_z_wilcoxon_gt0": p_w_move,
        })
        print(
            f"  {category:<13s} {asset:6s} +{w:3d}m: n={len(sub):3d} "
            f"move_z={move_vals.mean() if len(move_vals) else np.nan:+.2f} "
            f"hit={hit_rate if pd.notna(hit_rate) else np.nan:.1%}"
        )
    return pd.DataFrame(results)


def test_pre_post_stability(cluster_df: pd.DataFrame, cutoff: pd.Timestamp = KNOWLEDGE_CUTOFF_TS):
    print("\n=== C5: pre/post cutoff stability ===")
    df = cluster_df.copy()
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df["sample_period"] = np.where(df["timestamp_utc"] < cutoff, "pre_cutoff", "post_cutoff")
    results = []
    for period in ["pre_cutoff", "post_cutoff"]:
        for asset in ASSETS:
            for w in WINDOWS_MIN:
                sub = df[
                    (df["sample_period"] == period)
                    & (df["asset"] == asset)
                    & (df["window_min"] == w)
                    & df["base_ts"].notna()
                ].copy()
                if len(sub) < 20:
                    continue
                abs_vals = pd.to_numeric(sub["abs_return_z"], errors="coerce").dropna()
                move_vals = pd.to_numeric(sub["max_abs_move_z"], errors="coerce").dropna()
                _, p_abs_t, _, p_abs_w = one_sample_greater(abs_vals, center=0.0)
                _, p_move_t, _, p_move_w = one_sample_greater(move_vals, center=0.0)
                directional = sub[
                    sub["cluster_target_sentiment"].isin(["bull", "bear"])
                    & sub["target_delta_pct"].notna()
                    & (sub["target_delta_pct"] != 0)
                ].copy()
                if len(directional) >= 5:
                    realized = np.where(directional["target_delta_pct"] > 0, "bull", "bear")
                    correct = int((directional["cluster_target_sentiment"].to_numpy() == realized).sum())
                    p_dir = stats.binomtest(correct, len(directional), p=0.5, alternative="greater").pvalue
                    hit_rate = correct / len(directional)
                else:
                    correct = np.nan
                    p_dir = np.nan
                    hit_rate = np.nan
                results.append({
                    "sample_period": period,
                    "cutoff_utc": str(cutoff),
                    "asset": asset,
                    "asset_target": target_label_for_asset(asset),
                    "window_min": w,
                    "n_clusters": len(sub),
                    "mean_abs_return_z": float(abs_vals.mean()) if len(abs_vals) else np.nan,
                    "p_abs_return_z_ttest_gt0": p_abs_t,
                    "p_abs_return_z_wilcoxon_gt0": p_abs_w,
                    "mean_max_abs_move_z": float(move_vals.mean()) if len(move_vals) else np.nan,
                    "p_max_abs_move_z_ttest_gt0": p_move_t,
                    "p_max_abs_move_z_wilcoxon_gt0": p_move_w,
                    "n_directional": len(directional),
                    "direction_correct": correct,
                    "direction_hit_rate": hit_rate,
                    "p_direction_binom_greater": float(p_dir) if pd.notna(p_dir) else np.nan,
                })
                print(
                    f"  {period:<11s} {asset:6s} +{w:3d}m: n={len(sub):4d} "
                    f"move_z={move_vals.mean() if len(move_vals) else np.nan:+.2f}"
                )
    return pd.DataFrame(results)


def test_multivariate_models(cluster_df: pd.DataFrame):
    print("\n=== C6: multivariate controls for category, surprise, length ===")
    results = []
    for asset in ASSETS:
        for w in [5, 15, 60]:
            base = cluster_df[
                (cluster_df["asset"] == asset)
                & (cluster_df["window_min"] == w)
                & cluster_df["base_ts"].notna()
            ].copy()
            if len(base) < 80:
                continue
            base["abs_cluster_strength"] = pd.to_numeric(base["cluster_abs_target_strength"], errors="coerce")
            base["log_n_headlines"] = np.log1p(pd.to_numeric(base["n_headlines"], errors="coerce"))
            base["pre_abs_target_delta_15"] = pd.to_numeric(base["pre_target_delta_pct_15"], errors="coerce").abs()
            numeric_features = [
                "abs_cluster_strength",
                "cluster_surprise_score_max",
                "cluster_magnitude_score_max",
                "cluster_confidence_mean",
                "log_n_headlines",
                "headline_length_mean",
                "pre_abs_target_delta_15",
            ]
            for outcome in ["abs_return_z", "max_abs_move_z"]:
                model_df = base[[outcome, "dominant_category"] + numeric_features].copy()
                for col in [outcome] + numeric_features:
                    model_df[col] = pd.to_numeric(model_df[col], errors="coerce")
                model_df = model_df.dropna(subset=[outcome] + numeric_features)
                if len(model_df) < 80:
                    continue
                X_num = model_df[numeric_features].astype(float)
                X_cat = pd.get_dummies(model_df["dominant_category"], prefix="cat", drop_first=True, dtype=float)
                X = pd.concat([X_num, X_cat], axis=1)
                X = sm.add_constant(X, has_constant="add").astype(float)
                y = model_df[outcome].astype(float)
                try:
                    model = fit_ols_robust(y, X)
                except Exception as exc:
                    print(f"  {asset:6s} +{w:3d}m {outcome}: OLS failed: {exc}")
                    continue
                for term in X.columns:
                    if term == "const":
                        continue
                    results.append({
                        "asset": asset,
                        "asset_target": target_label_for_asset(asset),
                        "window_min": w,
                        "outcome": outcome,
                        "term": term,
                        "n_clusters": len(model_df),
                        "r2": float(model.rsquared),
                        "cov_type": str(model.cov_type),
                        "coef": float(model.params[term]),
                        "se": float(model.bse[term]),
                        "p_value": float(model.pvalues[term]),
                    })
                strength_p = model.pvalues.get("abs_cluster_strength", np.nan)
                print(
                    f"  {asset:6s} +{w:3d}m {outcome}: n={len(model_df):4d} "
                    f"R2={model.rsquared:.3f} p_strength={strength_p:.4g}"
                )
    return pd.DataFrame(results)


def winsorize_values(values: pd.Series, lower=0.01, upper=0.99):
    vals = pd.to_numeric(values, errors="coerce").dropna()
    if vals.empty:
        return vals
    lo, hi = vals.quantile([lower, upper])
    return vals.clip(lo, hi)


def test_outlier_robustness(cluster_df: pd.DataFrame):
    print("\n=== C7: outlier robustness via 1% winsorization ===")
    results = []
    for asset in ASSETS:
        for w in WINDOWS_MIN:
            sub = cluster_df[(cluster_df["asset"] == asset) & (cluster_df["window_min"] == w)].copy()
            for metric in ["abs_return_z", "max_abs_move_z"]:
                raw = pd.to_numeric(sub[metric], errors="coerce").dropna()
                if len(raw) < 30:
                    continue
                win = winsorize_values(raw)
                _, p_raw_t, _, p_raw_w = one_sample_greater(raw, center=0.0)
                _, p_win_t, _, p_win_w = one_sample_greater(win, center=0.0)
                results.append({
                    "asset": asset,
                    "asset_target": target_label_for_asset(asset),
                    "window_min": w,
                    "metric": metric,
                    "n_clusters": len(raw),
                    "mean_raw": float(raw.mean()),
                    "mean_winsor_1pct": float(win.mean()),
                    "median_raw": float(raw.median()),
                    "p_raw_ttest_gt0": p_raw_t,
                    "p_raw_wilcoxon_gt0": p_raw_w,
                    "p_winsor_ttest_gt0": p_win_t,
                    "p_winsor_wilcoxon_gt0": p_win_w,
                })
            if not sub.empty:
                print(f"  {asset:6s} +{w:3d}m: robustness rows added")
    return pd.DataFrame(results)


def test_model_consensus(returns_df: pd.DataFrame, compare_csv: Path, cluster_dedupe=True):
    print("\n=== C8: Flash/Pro consensus subset ===")
    if compare_csv is None or not compare_csv.exists():
        print("  compare_models.csv not found; skipping consensus test")
        return pd.DataFrame()

    compare = pd.read_csv(compare_csv, parse_dates=["timestamp_utc"])
    compare["event_id"] = compare["id"].astype(str)
    rows = []
    for asset in ASSETS:
        sent_col = "sentiment_usd" if asset == "eurusd" else "sentiment_ndx"
        flash = f"flash_{sent_col}"
        pro = f"pro_{sent_col}"
        if flash not in compare.columns or pro not in compare.columns:
            continue
        agree = compare[
            (compare[flash] == compare[pro])
            & compare[flash].isin(["bull", "bear"])
        ][["event_id", flash]].copy()
        agree = agree.rename(columns={flash: "consensus_sentiment"})
        if agree.empty:
            continue
        base = returns_df[returns_df["asset"] == asset].copy()
        base["event_id"] = base["event_id"].astype(str)
        merged = base.merge(agree, on="event_id", how="inner")
        for w in WINDOWS_MIN:
            sub_raw = merged[
                (merged["window_min"] == w)
                & merged["target_delta_pct"].notna()
                & (merged["target_delta_pct"] != 0)
            ].copy()
            sub = first_per_cluster(sub_raw) if cluster_dedupe else sub_raw
            if len(sub) < 5:
                continue
            realized = np.where(sub["target_delta_pct"] > 0, "bull", "bear")
            correct = int((sub["consensus_sentiment"].to_numpy() == realized).sum())
            p_binom = stats.binomtest(correct, len(sub), p=0.5, alternative="greater").pvalue
            rows.append({
                "asset": asset,
                "asset_target": target_label_for_asset(asset),
                "window_min": w,
                "n_raw": len(sub_raw),
                "n_clusters": len(sub),
                "correct": correct,
                "hit_rate": correct / len(sub),
                "p_binom_greater": float(p_binom),
            })
            print(f"  {asset:6s} +{w:3d}m: consensus n={len(sub):3d} hit={correct/len(sub):.1%} p={p_binom:.4g}")
    return pd.DataFrame(rows)


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
        {"setting": "cluster_level_outputs", "value": "one outcome per event_cluster_id/asset/window using first cluster timestamp"},
        {"setting": "abnormal_return_standardization", "value": "z-scores vs matched baseline by asset/window/hour/day-of-week"},
        {"setting": "range_outcomes", "value": "high-low range and max absolute intrawindow move added for every window"},
        {"setting": "pre_post_cutoff_utc", "value": str(KNOWLEDGE_CUTOFF_TS)},
        {"setting": "multivariate_controls", "value": "category dummies, surprise, magnitude, confidence, cluster size, headline length, pre-event move"},
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
    parser.add_argument("--compare-models", default=None, help="Optional Flash/Pro comparison CSV for consensus tests")
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
    returns_df = attach_abnormal_scores(returns_df, baseline_pools)
    returns_path = out_dir / "event_study_windows.csv"
    returns_df.to_csv(returns_path, index=False)
    print(f"\nWrote {len(returns_df)} rows to {returns_path}")
    print(f"  rows with price returns: {int(returns_df['delta_pct'].notna().sum())}")
    print(f"  closed-period rows: {int(returns_df['is_in_closed_period'].sum())}")

    cluster_df = build_cluster_windows(events, returns_df)
    cluster_path = out_dir / "cluster_event_study_windows.csv"
    cluster_df.to_csv(cluster_path, index=False)
    print(f"  wrote {len(cluster_df)} cluster-window rows to {cluster_path}")

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

    c1 = test_cluster_sentiment(cluster_df)
    c2 = test_range_outcomes(cluster_df, baseline_pools, rng, args.baseline_per_event)
    c3 = test_abnormal_z_outcomes(cluster_df)
    c4 = test_targeted_categories(cluster_df)
    c5 = test_pre_post_stability(cluster_df)
    c6 = test_multivariate_models(cluster_df)
    c7 = test_outlier_robustness(cluster_df)
    compare_path = Path(args.compare_models) if args.compare_models else out_dir / "compare_models.csv"
    c8 = test_model_consensus(returns_df, compare_path, cluster_dedupe)

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
        "cluster_sentiment": c1,
        "range_outcomes": c2,
        "abnormal_z": c3,
        "targeted_category": c4,
        "pre_post_stability": c5,
        "multivariate": c6,
        "outlier_robustness": c7,
        "model_consensus": c8,
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
