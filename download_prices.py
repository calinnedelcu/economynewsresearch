#!/usr/bin/env python3
"""Download intraday OHLCV prices from Dukascopy for EUR/USD and Nasdaq-100.

Pulls 1-minute bars via dukascopy-python and writes CSVs ready for event study.
Defaults to the pilot window (2026-04-15 -> 2026-04-21).

Usage:
    python download_prices.py --start 2026-04-15 --end 2026-04-21
    python download_prices.py --start 2025-03-24 --end 2026-04-21 --output-dir outputs
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import dukascopy_python as d
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


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", default="2026-04-15", help="UTC date YYYY-MM-DD (inclusive)")
    p.add_argument("--end", default="2026-04-21", help="UTC date YYYY-MM-DD (inclusive)")
    p.add_argument("--output-dir", default="outputs", help="Where to write CSVs")
    p.add_argument(
        "--only",
        choices=list(INSTRUMENTS.keys()),
        help="Download only one instrument",
    )
    args = p.parse_args()

    start = parse_date(args.start)
    end = parse_date(args.end).replace(hour=23, minute=59)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    todo = {k: v for k, v in INSTRUMENTS.items() if (args.only is None or k == args.only)}

    for name, instrument in todo.items():
        df = download(name, instrument, start, end)
        if df.empty:
            print(f"  [{name}] WARNING: empty dataframe, skipping write")
            continue
        out_path = out_dir / f"prices_{name}.csv"
        df.to_csv(out_path)
        print(f"  [{name}] wrote {out_path}  ({df.index.min()} -> {df.index.max()})")


if __name__ == "__main__":
    main()
