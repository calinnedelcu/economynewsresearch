#!/usr/bin/env python3
"""Download intraday OHLCV prices from Dukascopy for EUR/USD and Nasdaq-100.

Pulls 1-minute bars via dukascopy-python and writes CSVs ready for event study.
By default, downloads from the project start date through today's UTC date.

Usage:
    python download_prices.py --start 2025-03-24
    python download_prices.py --start 2025-03-24 --end 2026-04-21 --output-dir outputs
    python download_prices.py --start 2026-04-22 --merge-existing
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import dukascopy_python as d
import pandas as pd
from dukascopy_python.instruments import (
    INSTRUMENT_FX_MAJORS_EUR_USD,
    INSTRUMENT_IDX_AMERICA_E_NQ_100,
)

INSTRUMENTS = {
    "eurusd": INSTRUMENT_FX_MAJORS_EUR_USD,
    "ndx": INSTRUMENT_IDX_AMERICA_E_NQ_100,
}


def parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def download(name: str, instrument: str, start: datetime, end: datetime) -> "pd.DataFrame":
    print(f"  [{name}] fetching {start.date()} -> {end.date()} ...", flush=True)
    df = d.fetch(instrument, d.INTERVAL_MIN_1, d.OFFER_SIDE_BID, start, end)
    print(f"  [{name}] got {len(df):,} rows", flush=True)
    return df


def merge_with_existing(new_df: "pd.DataFrame", out_path: Path) -> "pd.DataFrame":
    """Merge newly downloaded rows with an existing CSV, de-duplicating timestamps."""
    if not out_path.exists():
        return new_df
    old = pd.read_csv(out_path, parse_dates=["timestamp"], index_col="timestamp")
    old.index = pd.to_datetime(old.index, utc=True)
    combined = pd.concat([old, new_df]).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", default="2025-03-24", help="UTC date YYYY-MM-DD (inclusive)")
    p.add_argument("--end", default=None, help="UTC date YYYY-MM-DD (inclusive); default=today UTC")
    p.add_argument("--output-dir", default="outputs", help="Where to write CSVs")
    p.add_argument("--merge-existing", action="store_true",
                   help="Merge downloaded rows into existing prices_*.csv instead of replacing them")
    p.add_argument(
        "--only",
        choices=list(INSTRUMENTS.keys()),
        help="Download only one instrument",
    )
    args = p.parse_args()

    start = parse_date(args.start)
    end_s = args.end or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    end = parse_date(end_s).replace(hour=23, minute=59)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    todo = {k: v for k, v in INSTRUMENTS.items() if (args.only is None or k == args.only)}

    for name, instrument in todo.items():
        df = download(name, instrument, start, end)
        if df.empty:
            print(f"  [{name}] WARNING: empty dataframe, skipping write")
            continue
        out_path = out_dir / f"prices_{name}.csv"
        if args.merge_existing:
            df = merge_with_existing(df, out_path)
        df.to_csv(out_path)
        print(f"  [{name}] wrote {out_path}  ({df.index.min()} -> {df.index.max()})")


if __name__ == "__main__":
    main()
