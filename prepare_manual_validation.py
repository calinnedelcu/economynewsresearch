#!/usr/bin/env python3
"""Create a manual-labeling sample for sentiment validation.

The output CSV is meant for two human annotators. After they fill the blank
label columns, a separate scoring step can compute Cohen's kappa and F1
against the LLM labels.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


LABEL_COLUMNS = [
    "ann1_sentiment_usd",
    "ann1_sentiment_ndx",
    "ann1_expected_magnitude",
    "ann1_surprise_level",
    "ann2_sentiment_usd",
    "ann2_sentiment_ndx",
    "ann2_expected_magnitude",
    "ann2_surprise_level",
    "notes",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", default="outputs/events_sentiment.csv")
    parser.add_argument("-o", "--output", default="outputs/manual_validation_sample.csv")
    parser.add_argument("-n", "--n-samples", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    events = pd.read_csv(args.events, parse_dates=["timestamp_utc"])
    if "is_gold" in events.columns:
        events = events[events["is_gold"].astype(str) == "True"].copy()
    sample = events.sample(n=min(args.n_samples, len(events)), random_state=args.seed).copy()
    sample = sample.sort_values("timestamp_utc")

    keep = [
        "id",
        "timestamp_utc",
        "category",
        "content",
        "sentiment_usd",
        "sentiment_ndx",
        "expected_magnitude",
        "surprise_level",
        "confidence",
        "rationale",
    ]
    keep = [c for c in keep if c in sample.columns]
    sample = sample[keep].copy()
    for col in LABEL_COLUMNS:
        sample[col] = ""

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(out, index=False)
    print(f"Wrote {len(sample)} rows to {out}")
    print("Allowed labels:")
    print("  sentiment_*: bull, bear, neutral")
    print("  expected_magnitude: low, med, high")
    print("  surprise_level: expected, surprise, shock")


if __name__ == "__main__":
    main()
