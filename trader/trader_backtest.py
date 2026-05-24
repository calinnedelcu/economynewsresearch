#!/usr/bin/env python3
"""Backtest trader playbook rules on existing EUR/USD and NDX data.

This is intentionally separate from the academic event-study pipeline. It reads
the existing cluster-level outputs plus 1-minute OHLC data and writes new files:

  * outputs/trader_backtest_trades.csv
  * outputs/trader_backtest_summary.csv
  * outputs/trader_backtest.md

Rules are designed to avoid lookahead bias:

  * naive hold enters at the first full minute after the news timestamp;
  * 1m/5m confirmation strategies enter only after the confirmation window;
  * breakout strategies observe an initial range, then enter only if a later
    bar breaks that range;
  * stop/target simulation uses conservative same-bar ordering.

The backtest is research, not financial advice.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

import numpy as np
import pandas as pd


ASSETS = ["eurusd", "ndx"]
TARGET_SIGN = {"bull": 1, "bear": -1}


def read_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing input file: {path}")
    return pd.read_csv(path, **kwargs)


def post_event_start(event_ts: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(event_ts).ceil("min")


def price_side(asset: str, target_sentiment: str) -> int | None:
    """Return price direction: +1 long price, -1 short price.

    EUR/USD is inverted because cluster sentiment is expressed as USD proxy.
    """
    if target_sentiment not in TARGET_SIGN:
        return None
    target_dir = TARGET_SIGN[target_sentiment]
    return -target_dir if asset == "eurusd" else target_dir


def side_label(side: int) -> str:
    return "long" if side > 0 else "short"


def load_prices(results_dir: Path) -> dict[str, pd.DataFrame]:
    prices = {}
    for asset in ASSETS:
        path = results_dir / f"prices_{asset}.csv"
        df = read_csv(path, parse_dates=["timestamp"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp").sort_index()
        prices[asset] = df
    return prices


def has_full_window(prices: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    if start not in prices.index or end not in prices.index:
        return False
    expected = int((end - start) / pd.Timedelta(minutes=1)) + 1
    return len(prices.loc[start:end]) == expected


def get_window(prices: pd.DataFrame, start: pd.Timestamp, minutes: int) -> pd.DataFrame | None:
    end = start + pd.Timedelta(minutes=minutes - 1)
    if minutes <= 0 or not has_full_window(prices, start, end):
        return None
    return prices.loc[start:end]


def apply_costs(entry: float, exit_price: float, side: int, cost_bps_per_side: float) -> float:
    cost = cost_bps_per_side / 10000.0
    if side > 0:
        adj_entry = entry * (1 + cost)
        adj_exit = exit_price * (1 - cost)
        return (adj_exit - adj_entry) / adj_entry * 100.0
    adj_entry = entry * (1 - cost)
    adj_exit = exit_price * (1 + cost)
    return (adj_entry - adj_exit) / adj_entry * 100.0


def risk_pct(entry: float, stop: float) -> float:
    if entry <= 0:
        return np.nan
    return abs(entry - stop) / entry * 100.0


def simulate_stop_target(
    prices: pd.DataFrame,
    entry_time: pd.Timestamp,
    timeout_end: pd.Timestamp,
    side: int,
    entry: float,
    stop: float,
    target: float,
    cost_bps_per_side: float,
) -> dict | None:
    if entry_time not in prices.index or timeout_end not in prices.index:
        return None
    window = prices.loc[entry_time:timeout_end]
    if window.empty:
        return None

    exit_time = timeout_end
    exit_price = float(window.iloc[-1]["close"])
    exit_reason = "timeout"

    for ts, bar in window.iterrows():
        high = float(bar["high"])
        low = float(bar["low"])
        if side > 0:
            stop_hit = low <= stop
            target_hit = high >= target
            # Conservative same-bar ordering: stop first if both are touched.
            if stop_hit:
                exit_time = ts
                exit_price = stop
                exit_reason = "stop"
                break
            if target_hit:
                exit_time = ts
                exit_price = target
                exit_reason = "target"
                break
        else:
            stop_hit = high >= stop
            target_hit = low <= target
            if stop_hit:
                exit_time = ts
                exit_price = stop
                exit_reason = "stop"
                break
            if target_hit:
                exit_time = ts
                exit_price = target
                exit_reason = "target"
                break

    net = apply_costs(entry, exit_price, side, cost_bps_per_side)
    r_pct = risk_pct(entry, stop)
    return {
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "net_return_pct": net,
        "risk_pct": r_pct,
        "r_multiple": net / r_pct if r_pct and pd.notna(r_pct) and r_pct > 0 else np.nan,
    }


def fixed_hold_trade(
    prices: pd.DataFrame,
    event_start: pd.Timestamp,
    side: int,
    hold_min: int,
    cost_bps_per_side: float,
) -> dict | None:
    entry_time = event_start
    exit_time = event_start + pd.Timedelta(minutes=hold_min - 1)
    if entry_time not in prices.index or exit_time not in prices.index:
        return None
    if not has_full_window(prices, entry_time, exit_time):
        return None
    entry = float(prices.loc[entry_time, "open"])
    exit_price = float(prices.loc[exit_time, "close"])
    net = apply_costs(entry, exit_price, side, cost_bps_per_side)
    return {
        "entry_time": entry_time,
        "entry_price": entry,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": f"hold_{hold_min}m",
        "net_return_pct": net,
        "risk_pct": np.nan,
        "r_multiple": np.nan,
    }


def sentiment_breakout_trade(
    prices: pd.DataFrame,
    event_start: pd.Timestamp,
    side: int,
    observe_min: int,
    wait_until_min: int,
    horizon_min: int,
    r_target: float,
    min_risk_pct: float,
    cost_bps_per_side: float,
) -> dict | None:
    setup = get_window(prices, event_start, observe_min)
    if setup is None:
        return None
    setup_high = float(setup["high"].max())
    setup_low = float(setup["low"].min())
    trigger = setup_high if side > 0 else setup_low
    stop = setup_low if side > 0 else setup_high
    r_pct = risk_pct(trigger, stop)
    if pd.isna(r_pct) or r_pct < min_risk_pct:
        return None

    target = trigger + (trigger - stop) * r_target if side > 0 else trigger - (stop - trigger) * r_target
    search_start = event_start + pd.Timedelta(minutes=observe_min)
    search_end = event_start + pd.Timedelta(minutes=wait_until_min - 1)
    timeout_end = event_start + pd.Timedelta(minutes=horizon_min - 1)
    if search_start not in prices.index or search_end not in prices.index or timeout_end not in prices.index:
        return None
    if not has_full_window(prices, search_start, search_end):
        return None

    for ts, bar in prices.loc[search_start:search_end].iterrows():
        if side > 0 and float(bar["high"]) >= trigger:
            result = simulate_stop_target(prices, ts, timeout_end, side, trigger, stop, target, cost_bps_per_side)
            if result is None:
                return None
            result.update({
                "entry_time": ts,
                "entry_price": trigger,
                "stop_price": stop,
                "target_price": target,
                "setup_high": setup_high,
                "setup_low": setup_low,
            })
            return result
        if side < 0 and float(bar["low"]) <= trigger:
            result = simulate_stop_target(prices, ts, timeout_end, side, trigger, stop, target, cost_bps_per_side)
            if result is None:
                return None
            result.update({
                "entry_time": ts,
                "entry_price": trigger,
                "stop_price": stop,
                "target_price": target,
                "setup_high": setup_high,
                "setup_low": setup_low,
            })
            return result
    return None


def volatility_breakout_trade(
    prices: pd.DataFrame,
    event_start: pd.Timestamp,
    observe_min: int,
    wait_until_min: int,
    horizon_min: int,
    r_target: float,
    min_risk_pct: float,
    cost_bps_per_side: float,
) -> dict | None:
    setup = get_window(prices, event_start, observe_min)
    if setup is None:
        return None
    setup_high = float(setup["high"].max())
    setup_low = float(setup["low"].min())
    setup_range_pct = risk_pct(setup_high, setup_low)
    if pd.isna(setup_range_pct) or setup_range_pct < min_risk_pct:
        return None

    search_start = event_start + pd.Timedelta(minutes=observe_min)
    search_end = event_start + pd.Timedelta(minutes=wait_until_min - 1)
    timeout_end = event_start + pd.Timedelta(minutes=horizon_min - 1)
    if search_start not in prices.index or search_end not in prices.index or timeout_end not in prices.index:
        return None
    if not has_full_window(prices, search_start, search_end):
        return None

    for ts, bar in prices.loc[search_start:search_end].iterrows():
        high_break = float(bar["high"]) >= setup_high
        low_break = float(bar["low"]) <= setup_low
        if high_break and low_break:
            # Unknown sequence: skip rather than inventing a direction.
            return None
        if high_break:
            side = 1
            entry = setup_high
            stop = setup_low
            target = entry + (entry - stop) * r_target
        elif low_break:
            side = -1
            entry = setup_low
            stop = setup_high
            target = entry - (stop - entry) * r_target
        else:
            continue
        result = simulate_stop_target(prices, ts, timeout_end, side, entry, stop, target, cost_bps_per_side)
        if result is None:
            return None
        result.update({
            "entry_time": ts,
            "entry_price": entry,
            "stop_price": stop,
            "target_price": target,
            "setup_high": setup_high,
            "setup_low": setup_low,
            "breakout_side": side_label(side),
        })
        return result
    return None


def followthrough_after_5m_trade(
    prices: pd.DataFrame,
    event_start: pd.Timestamp,
    side: int,
    horizon_min: int,
    r_target: float,
    min_risk_pct: float,
    cost_bps_per_side: float,
) -> dict | None:
    first5 = get_window(prices, event_start, 5)
    if first5 is None:
        return None
    entry_time = event_start + pd.Timedelta(minutes=5)
    timeout_end = event_start + pd.Timedelta(minutes=horizon_min - 1)
    if entry_time not in prices.index or timeout_end not in prices.index:
        return None
    entry = float(prices.loc[entry_time, "open"])
    stop = float(first5["low"].min()) if side > 0 else float(first5["high"].max())
    r_pct = risk_pct(entry, stop)
    if pd.isna(r_pct) or r_pct < min_risk_pct:
        return None
    target = entry + (entry - stop) * r_target if side > 0 else entry - (stop - entry) * r_target
    result = simulate_stop_target(prices, entry_time, timeout_end, side, entry, stop, target, cost_bps_per_side)
    if result is None:
        return None
    result.update({
        "entry_time": entry_time,
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "setup_high": float(first5["high"].max()),
        "setup_low": float(first5["low"].min()),
    })
    return result


def one_min_confirmed_trade(
    prices: pd.DataFrame,
    event_start: pd.Timestamp,
    side: int,
    horizon_min: int,
    r_target: float,
    min_risk_pct: float,
    cost_bps_per_side: float,
) -> dict | None:
    first1 = get_window(prices, event_start, 1)
    if first1 is None:
        return None
    entry_time = event_start + pd.Timedelta(minutes=1)
    timeout_end = event_start + pd.Timedelta(minutes=horizon_min - 1)
    if entry_time not in prices.index or timeout_end not in prices.index:
        return None
    entry = float(prices.loc[entry_time, "open"])
    stop = float(first1["low"].min()) if side > 0 else float(first1["high"].max())
    r_pct = risk_pct(entry, stop)
    if pd.isna(r_pct) or r_pct < min_risk_pct:
        return None
    target = entry + (entry - stop) * r_target if side > 0 else entry - (stop - entry) * r_target
    result = simulate_stop_target(prices, entry_time, timeout_end, side, entry, stop, target, cost_bps_per_side)
    if result is None:
        return None
    result.update({
        "entry_time": entry_time,
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "setup_high": float(first1["high"].max()),
        "setup_low": float(first1["low"].min()),
    })
    return result


def first_headlines(events_path: Path) -> pd.DataFrame:
    if not events_path.exists():
        return pd.DataFrame(columns=["event_cluster_id", "headline"])
    events = read_csv(events_path, parse_dates=["timestamp_utc"])
    events["timestamp_utc"] = pd.to_datetime(events["timestamp_utc"], utc=True)
    if "is_gold" in events.columns:
        events = events[events["is_gold"].astype(str).str.lower().eq("true")].copy()
    if "event_cluster_id" not in events.columns:
        gap = pd.Timedelta(minutes=15)
        events = events.sort_values("timestamp_utc").copy()
        starts = events["timestamp_utc"].diff().isna() | (events["timestamp_utc"].diff() > gap)
        events["event_cluster_id"] = starts.cumsum().astype(int)
    events["headline"] = events["content"].astype(str).str.replace(r"\s+", " ", regex=True).str.slice(0, 220)
    return events.sort_values("timestamp_utc").groupby("event_cluster_id").agg(headline=("headline", "first")).reset_index()


def add_trade(
    trades: list[dict],
    strategy: str,
    cluster_row: pd.Series,
    side: int,
    trade_result: dict | None,
    extra: dict | None = None,
) -> None:
    if trade_result is None:
        return
    row = {
        "strategy": strategy,
        "event_cluster_id": int(cluster_row["event_cluster_id"]),
        "asset": cluster_row["asset"],
        "asset_target": cluster_row.get("asset_target", ""),
        "cluster_start_ts": cluster_row.get("cluster_start_ts", ""),
        "dominant_category": cluster_row.get("dominant_category", ""),
        "n_headlines": cluster_row.get("n_headlines", np.nan),
        "cluster_target_sentiment": cluster_row.get("cluster_target_sentiment", ""),
        "cluster_target_strength_conf_weighted": cluster_row.get("cluster_target_strength_conf_weighted", np.nan),
        "cluster_sentiment_agreement_share": cluster_row.get("cluster_sentiment_agreement_share", np.nan),
        "pre_abs_target_delta_15": abs(float(cluster_row.get("pre_target_delta_pct_15", np.nan))),
        "side": side_label(side),
        "entry_time": trade_result.get("entry_time"),
        "exit_time": trade_result.get("exit_time"),
        "entry_price": trade_result.get("entry_price"),
        "exit_price": trade_result.get("exit_price"),
        "stop_price": trade_result.get("stop_price", np.nan),
        "target_price": trade_result.get("target_price", np.nan),
        "exit_reason": trade_result.get("exit_reason"),
        "net_return_pct": trade_result.get("net_return_pct"),
        "risk_pct": trade_result.get("risk_pct", np.nan),
        "r_multiple": trade_result.get("r_multiple", np.nan),
        "setup_high": trade_result.get("setup_high", np.nan),
        "setup_low": trade_result.get("setup_low", np.nan),
    }
    if extra:
        row.update(extra)
    trades.append(row)


def run_backtest(args) -> pd.DataFrame:
    results_dir = Path(args.results_dir)
    cluster = read_csv(
        results_dir / "cluster_event_study_windows.csv",
        parse_dates=["timestamp_utc", "cluster_start_ts", "cluster_end_ts"],
    )
    cluster["timestamp_utc"] = pd.to_datetime(cluster["timestamp_utc"], utc=True)
    cluster["cluster_start_ts"] = pd.to_datetime(cluster["cluster_start_ts"], utc=True)
    cluster = cluster[cluster["asset"].isin(ASSETS)].copy()
    cluster["pre_abs_15"] = pd.to_numeric(cluster["pre_target_delta_pct_15"], errors="coerce").abs()

    anchor = cluster[cluster["window_min"] == 5].copy()
    anchor["pre_abs_rank"] = anchor.groupby("asset")["pre_abs_15"].rank(pct=True)
    rank_map = anchor.set_index(["event_cluster_id", "asset"])["pre_abs_rank"].to_dict()

    prices = load_prices(results_dir)
    cost_map = {"eurusd": args.eurusd_cost_bps, "ndx": args.ndx_cost_bps}
    trades: list[dict] = []

    rows_by_cluster_asset = {
        (cid, asset): group.sort_values("window_min")
        for (cid, asset), group in cluster.groupby(["event_cluster_id", "asset"])
    }

    for (cid, asset), group in rows_by_cluster_asset.items():
        by_w = {int(row["window_min"]): row for _, row in group.iterrows()}
        base = by_w.get(5) if 5 in by_w else next(iter(by_w.values()))
        sentiment = str(base.get("cluster_target_sentiment", ""))
        side = price_side(asset, sentiment)
        if side is None:
            continue

        event_start = post_event_start(pd.Timestamp(base["cluster_start_ts"]))
        price_df = prices[asset]
        cost_bps = cost_map[asset]
        pre_rank = rank_map.get((cid, asset), np.nan)
        not_late = pd.notna(pre_rank) and pre_rank <= args.max_pre_move_percentile
        agreement = float(base.get("cluster_sentiment_agreement_share", np.nan))
        strength = abs(float(base.get("cluster_target_strength_conf_weighted", np.nan)))
        coherent = (pd.isna(agreement) or agreement >= args.min_agreement) and (pd.isna(strength) or strength >= args.min_abs_strength)

        for hold in [15, 60]:
            result = fixed_hold_trade(price_df, event_start, side, hold, cost_bps)
            add_trade(trades, f"naive_sentiment_hold_{hold}m", base, side, result, {"pre_abs_rank": pre_rank})
            if not_late:
                result = fixed_hold_trade(price_df, event_start, side, hold, cost_bps)
                add_trade(trades, f"no_chase_filtered_hold_{hold}m", base, side, result, {"pre_abs_rank": pre_rank})

        if not_late and coherent:
            for horizon in [15, 60]:
                result = sentiment_breakout_trade(
                    price_df,
                    event_start,
                    side,
                    observe_min=args.breakout_observe_min,
                    wait_until_min=args.breakout_wait_until_min,
                    horizon_min=horizon,
                    r_target=args.breakout_r_target,
                    min_risk_pct=args.min_risk_pct,
                    cost_bps_per_side=cost_bps,
                )
                add_trade(
                    trades,
                    f"fresh_sentiment_breakout_{horizon}m",
                    base,
                    side,
                    result,
                    {"pre_abs_rank": pre_rank},
                )

            result = volatility_breakout_trade(
                price_df,
                event_start,
                observe_min=args.breakout_observe_min,
                wait_until_min=args.breakout_wait_until_min,
                horizon_min=15,
                r_target=args.breakout_r_target,
                min_risk_pct=args.min_risk_pct,
                cost_bps_per_side=cost_bps,
            )
            if result is not None:
                vol_side = 1 if result.get("breakout_side") == "long" else -1
                add_trade(
                    trades,
                    "volatility_breakout_15m",
                    base,
                    vol_side,
                    result,
                    {"pre_abs_rank": pre_rank},
                )

        if asset == "ndx" and not_late and coherent and 5 in by_w:
            target_delta_5 = float(by_w[5].get("target_delta_pct", np.nan))
            target_dir = TARGET_SIGN.get(sentiment)
            if target_dir is not None and pd.notna(target_delta_5) and target_delta_5 * target_dir > 0:
                result = followthrough_after_5m_trade(
                    price_df,
                    event_start,
                    side,
                    horizon_min=60,
                    r_target=args.followthrough_r_target,
                    min_risk_pct=args.min_risk_pct,
                    cost_bps_per_side=cost_bps,
                )
                add_trade(trades, "ndx_cluster_followthrough_60m", base, side, result, {"pre_abs_rank": pre_rank})

        if asset == "eurusd" and not_late and coherent and 1 in by_w:
            target_delta_1 = float(by_w[1].get("target_delta_pct", np.nan))
            target_dir = TARGET_SIGN.get(sentiment)
            if target_dir is not None and pd.notna(target_delta_1) and target_delta_1 * target_dir > 0:
                result = one_min_confirmed_trade(
                    price_df,
                    event_start,
                    side,
                    horizon_min=15,
                    r_target=args.confirmed_r_target,
                    min_risk_pct=args.min_risk_pct,
                    cost_bps_per_side=cost_bps,
                )
                add_trade(trades, "eurusd_usd_1m_confirmed_15m", base, side, result, {"pre_abs_rank": pre_rank})

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        headlines = first_headlines(results_dir / "events_sentiment.csv")
        trades_df = trades_df.merge(headlines, on="event_cluster_id", how="left")
        trades_df = trades_df.sort_values(["entry_time", "strategy", "asset"]).reset_index(drop=True)
    return trades_df


def max_drawdown(series: pd.Series) -> float:
    if series.empty:
        return np.nan
    equity = series.cumsum()
    peak = equity.cummax()
    drawdown = equity - peak
    return float(drawdown.min())


def summarize_trades(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if trades.empty:
        return pd.DataFrame()
    for keys, group in trades.groupby(["strategy", "asset"], dropna=False):
        strategy, asset = keys
        ret = pd.to_numeric(group["net_return_pct"], errors="coerce").dropna()
        wins = ret[ret > 0]
        losses = ret[ret < 0]
        rows.append({
            "strategy": strategy,
            "asset": asset,
            "n_trades": int(len(ret)),
            "win_rate": float((ret > 0).mean()) if len(ret) else np.nan,
            "avg_return_pct": float(ret.mean()) if len(ret) else np.nan,
            "median_return_pct": float(ret.median()) if len(ret) else np.nan,
            "total_return_pct_sum": float(ret.sum()) if len(ret) else np.nan,
            "avg_win_pct": float(wins.mean()) if len(wins) else np.nan,
            "avg_loss_pct": float(losses.mean()) if len(losses) else np.nan,
            "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and abs(losses.sum()) > 0 else np.nan,
            "max_drawdown_pct_sum": max_drawdown(ret),
            "avg_r_multiple": float(pd.to_numeric(group["r_multiple"], errors="coerce").mean()),
            "target_exit_rate": float((group["exit_reason"] == "target").mean()),
            "stop_exit_rate": float((group["exit_reason"] == "stop").mean()),
        })
    return pd.DataFrame(rows).sort_values(["avg_return_pct", "profit_factor"], ascending=[False, False])


def markdown_table(df: pd.DataFrame, columns: list[str] | None = None, max_rows: int | None = None) -> str:
    if df.empty:
        return "_No rows._"
    show = df.copy()
    if columns:
        show = show[columns]
    if max_rows:
        show = show.head(max_rows)
    for col in show.columns:
        show[col] = show[col].map(lambda v: "" if pd.isna(v) else str(v).replace("|", "\\|"))
    header = "| " + " | ".join(show.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(show.columns)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in show.astype(str).to_numpy()]
    return "\n".join([header, sep] + body)


def write_report(trades: pd.DataFrame, summary: pd.DataFrame, output: Path, args) -> None:
    best = summary.sort_values("avg_return_pct", ascending=False).head(12) if not summary.empty else pd.DataFrame()
    by_exit = trades.groupby(["strategy", "exit_reason"]).size().reset_index(name="count") if not trades.empty else pd.DataFrame()
    lines = [
        "# Trader Backtest",
        "",
        "Research backtest for the FinancialJuice trader playbook. Assets are unchanged: EUR/USD and NDX.",
        "",
        "## Assumptions",
        "",
        f"- EUR/USD cost per side: {args.eurusd_cost_bps} bps.",
        f"- NDX cost per side: {args.ndx_cost_bps} bps.",
        f"- No-chase filter: pre-move percentile <= {args.max_pre_move_percentile:.0%}.",
        f"- Breakout observes first {args.breakout_observe_min}m and waits until minute {args.breakout_wait_until_min}.",
        f"- Breakout target: {args.breakout_r_target}R. Follow-through target: {args.followthrough_r_target}R.",
        "- Same-bar stop/target ambiguity is handled conservatively: stop first.",
        "",
        "## Best Strategy/Asset Rows By Average Return",
        "",
        markdown_table(
            best,
            [
                "strategy", "asset", "n_trades", "win_rate", "avg_return_pct",
                "median_return_pct", "profit_factor", "max_drawdown_pct_sum",
                "target_exit_rate", "stop_exit_rate",
            ],
        ),
        "",
        "## Full Summary",
        "",
        markdown_table(summary),
        "",
        "## Exit Reason Counts",
        "",
        markdown_table(by_exit),
        "",
        "## Important Limitation",
        "",
        "This is still a research backtest. It uses minute OHLC bars, not tick data. Intrabar ordering is unknown, so the simulator uses conservative stop-first logic when stop and target are touched in the same candle.",
        "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def fmt_pct(value, digits=3) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}%"


def fmt_rate(value) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value) * 100:.1f}%"


def fmt_num(value, digits=2) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def html_table(df: pd.DataFrame, columns: list[str], formats: dict[str, str] | None = None, max_rows: int | None = None) -> str:
    if df.empty:
        return "<p class='empty'>No rows.</p>"
    formats = formats or {}
    show = df[columns].copy()
    if max_rows:
        show = show.head(max_rows)

    def render_cell(col: str, value) -> str:
        if pd.isna(value):
            text = ""
        elif formats.get(col) == "rate":
            text = fmt_rate(value)
        elif formats.get(col) == "pct":
            text = fmt_pct(value)
        elif formats.get(col) == "num":
            text = fmt_num(value)
        else:
            text = str(value)
        cls = ""
        if col in {"avg_return_pct", "median_return_pct", "total_return_pct_sum", "max_drawdown_pct_sum"}:
            val = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
            if pd.notna(val):
                cls = " pos" if val > 0 else " neg" if val < 0 else ""
        return f"<td class='{cls.strip()}'>{html.escape(text)}</td>"

    heads = "".join(f"<th>{html.escape(col)}</th>" for col in columns)
    rows = []
    for _, row in show.iterrows():
        rows.append("<tr>" + "".join(render_cell(col, row[col]) for col in columns) + "</tr>")
    return f"<table><thead><tr>{heads}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def build_html_report(trades: pd.DataFrame, summary: pd.DataFrame, output: Path, args) -> None:
    nocost_path = Path(args.nocost_summary_input)
    nocost = pd.DataFrame()
    if nocost_path.exists():
        nocost = read_csv(nocost_path)

    best_costed = summary.sort_values("avg_return_pct", ascending=False).head(8) if not summary.empty else pd.DataFrame()
    best_nocost = nocost.sort_values("avg_return_pct", ascending=False).head(8) if not nocost.empty else pd.DataFrame()
    by_exit = trades.groupby(["strategy", "exit_reason"]).size().reset_index(name="count") if not trades.empty else pd.DataFrame()
    total_trades = len(trades)
    positive_costed = int((pd.to_numeric(summary["avg_return_pct"], errors="coerce") > 0).sum()) if not summary.empty else 0
    positive_nocost = int((pd.to_numeric(nocost["avg_return_pct"], errors="coerce") > 0).sum()) if not nocost.empty else 0
    best_row = best_costed.iloc[0] if not best_costed.empty else None
    best_nocost_row = best_nocost.iloc[0] if not best_nocost.empty else None

    conclusion = "Cu costurile asumate, niciun strategy/asset row nu are expectancy pozitiv."
    if positive_costed > 0:
        conclusion = "Cu costurile asumate exista cel putin un row pozitiv, dar trebuie verificata robustetea."

    columns_main = [
        "strategy", "asset", "n_trades", "win_rate", "avg_return_pct",
        "median_return_pct", "profit_factor", "max_drawdown_pct_sum",
        "target_exit_rate", "stop_exit_rate",
    ]
    formats = {
        "win_rate": "rate",
        "avg_return_pct": "pct",
        "median_return_pct": "pct",
        "profit_factor": "num",
        "max_drawdown_pct_sum": "pct",
        "target_exit_rate": "rate",
        "stop_exit_rate": "rate",
    }

    css = """
:root {
  --bg: #111310;
  --paper: #f2efe5;
  --panel: #fbf8ef;
  --ink: #171916;
  --muted: #77736a;
  --line: #d8cfbd;
  --red: #a93e32;
  --green: #1f7454;
  --amber: #a87924;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: Aptos, "Segoe UI", sans-serif;
}
.shell {
  width: min(1320px, calc(100% - 36px));
  margin: 0 auto;
}
header {
  color: var(--paper);
  padding: 34px 0 26px;
}
h1 {
  margin: 0;
  font-family: Georgia, Cambria, serif;
  font-size: 44px;
  line-height: 1;
  letter-spacing: 0;
}
.dek {
  max-width: 860px;
  margin: 12px 0 0;
  color: #c9c1b3;
}
.verdict {
  background: var(--paper);
  border-top: 4px solid var(--red);
  padding: 18px;
  margin-bottom: 16px;
}
.verdict strong {
  display: block;
  font-size: 20px;
  margin-bottom: 6px;
}
.kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  background: #3a352d;
  margin-bottom: 16px;
}
.kpi {
  background: var(--panel);
  padding: 16px;
}
.kpi b {
  display: block;
  font-family: Georgia, Cambria, serif;
  font-size: 30px;
  line-height: 1;
}
.kpi span {
  display: block;
  margin-top: 7px;
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: .08em;
}
section {
  background: var(--paper);
  margin-bottom: 16px;
  padding: 18px;
}
h2 {
  margin: 0 0 14px;
  font-size: 18px;
  text-transform: uppercase;
  letter-spacing: .08em;
}
.split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
  font-size: 12px;
}
th, td {
  text-align: left;
  padding: 9px 10px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
th {
  background: #e7dfcf;
  text-transform: uppercase;
  letter-spacing: .06em;
  font-size: 11px;
}
.pos { color: var(--green); font-weight: 700; }
.neg { color: var(--red); font-weight: 700; }
.callout {
  border: 1px solid var(--line);
  background: var(--panel);
  padding: 14px;
  color: #34332f;
}
.callout p { margin: 8px 0 0; }
.empty { color: var(--muted); }
@media (max-width: 900px) {
  .kpis, .split { grid-template-columns: 1fr; }
  h1 { font-size: 34px; }
}
"""

    best_costed_text = "n/a"
    if best_row is not None:
        best_costed_text = (
            f"{best_row['strategy']} / {best_row['asset']} "
            f"({fmt_pct(best_row['avg_return_pct'])} avg)"
        )
    best_nocost_text = "n/a"
    if best_nocost_row is not None:
        best_nocost_text = (
            f"{best_nocost_row['strategy']} / {best_nocost_row['asset']} "
            f"({fmt_pct(best_nocost_row['avg_return_pct'])} avg)"
        )

    document = f"""<!doctype html>
<html lang="ro">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trader Backtest Report</title>
  <style>{css}</style>
</head>
<body>
  <header>
    <div class="shell">
      <h1>Trader Backtest Report</h1>
      <p class="dek">Backtest separat pentru regulile din playbook FinancialJuice. Activele raman EUR/USD si Nasdaq/NDX. Raportul compara rezultatele cu costuri si, daca exista fisierul, varianta zero-cost.</p>
    </div>
  </header>
  <main class="shell">
    <div class="verdict">
      <strong>{html.escape(conclusion)}</strong>
      <div>Interpretare: semnalul brut exista in unele variante zero-cost, dar este prea mic pentru costurile de executie setate in backtestul principal.</div>
    </div>

    <div class="kpis">
      <div class="kpi"><b>{total_trades:,}</b><span>costed trades</span></div>
      <div class="kpi"><b>{positive_costed}</b><span>positive costed rows</span></div>
      <div class="kpi"><b>{positive_nocost}</b><span>positive zero-cost rows</span></div>
      <div class="kpi"><b>{args.eurusd_cost_bps}/{args.ndx_cost_bps}</b><span>bps per side EU/NQ</span></div>
    </div>

    <section>
      <h2>Executive Read</h2>
      <div class="split">
        <div class="callout">
          <strong>Best costed row</strong>
          <p>{html.escape(best_costed_text)}</p>
          <p>Costed results are the realistic default view.</p>
        </div>
        <div class="callout">
          <strong>Best zero-cost row</strong>
          <p>{html.escape(best_nocost_text)}</p>
          <p>Zero-cost helps separate raw signal from execution drag.</p>
        </div>
      </div>
    </section>

    <section>
      <h2>Costed Results</h2>
      {html_table(summary.sort_values('avg_return_pct', ascending=False), columns_main, formats)}
    </section>

    <section>
      <h2>Zero-Cost Comparison</h2>
      {html_table(nocost.sort_values('avg_return_pct', ascending=False), columns_main, formats) if not nocost.empty else "<p class='empty'>Run the no-cost command to generate outputs/trader_backtest_summary_nocost.csv.</p>"}
    </section>

    <section>
      <h2>Exit Reason Counts</h2>
      {html_table(by_exit, ['strategy', 'exit_reason', 'count'])}
    </section>

    <section>
      <h2>Assumptions</h2>
      <div class="callout">
        <p>EUR/USD cost per side: {args.eurusd_cost_bps} bps. NDX cost per side: {args.ndx_cost_bps} bps.</p>
        <p>No-chase filter: pre-move percentile <= {args.max_pre_move_percentile:.0%}. Breakout observes first {args.breakout_observe_min}m and waits until minute {args.breakout_wait_until_min}.</p>
        <p>Minute OHLC bars do not reveal intrabar order. If stop and target are both touched in the same candle, the simulator assumes stop first.</p>
      </div>
    </section>
  </main>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default="outputs")
    parser.add_argument("--trades-output", default="outputs/trader_backtest_trades.csv")
    parser.add_argument("--summary-output", default="outputs/trader_backtest_summary.csv")
    parser.add_argument("--report-output", default="outputs/trader_backtest.md")
    parser.add_argument("--html-output", default="outputs/trader_backtest.html")
    parser.add_argument("--nocost-summary-input", default="outputs/trader_backtest_summary_nocost.csv")
    parser.add_argument("--eurusd-cost-bps", type=float, default=0.8)
    parser.add_argument("--ndx-cost-bps", type=float, default=2.0)
    parser.add_argument("--max-pre-move-percentile", type=float, default=0.75)
    parser.add_argument("--min-agreement", type=float, default=0.55)
    parser.add_argument("--min-abs-strength", type=float, default=0.05)
    parser.add_argument("--min-risk-pct", type=float, default=0.005)
    parser.add_argument("--breakout-observe-min", type=int, default=2)
    parser.add_argument("--breakout-wait-until-min", type=int, default=10)
    parser.add_argument("--breakout-r-target", type=float, default=1.0)
    parser.add_argument("--followthrough-r-target", type=float, default=1.5)
    parser.add_argument("--confirmed-r-target", type=float, default=1.0)
    args = parser.parse_args()

    trades = run_backtest(args)
    summary = summarize_trades(trades)

    trades_path = Path(args.trades_output)
    summary_path = Path(args.summary_output)
    report_path = Path(args.report_output)
    html_path = Path(args.html_output)
    trades_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    trades.to_csv(trades_path, index=False)
    summary.to_csv(summary_path, index=False)
    write_report(trades, summary, report_path, args)
    build_html_report(trades, summary, html_path, args)

    print(f"Wrote {len(trades):,} trades to {trades_path}")
    print(f"Wrote {len(summary):,} summary rows to {summary_path}")
    print(f"Wrote report to {report_path}")
    print(f"Wrote HTML report to {html_path}")


if __name__ == "__main__":
    main()
