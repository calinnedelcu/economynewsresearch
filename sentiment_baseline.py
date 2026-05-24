#!/usr/bin/env python3
"""Loughran-McDonald dictionary sentiment baseline.

Provides a reference baseline that the LLM-based sentiment classifier
must beat to justify the methodological choice. LM is the de facto
standard in finance NLP since Loughran & McDonald (2011, Journal of
Finance) introduced a finance-specific sentiment dictionary that
outperformed the general-purpose Harvard IV-4 lexicon on financial
text.

LM produces a single polarity per document. It cannot differentiate
USD vs NDX sentiment the way the LLM does (e.g., risk-off geopolitical
events produce bull USD + bear NDX simultaneously). That asymmetric
behaviour is exactly the comparison we want to surface in the paper:
the LLM captures cross-asset directionality the dictionary cannot.

Usage:
    python sentiment_baseline.py outputs/events_sentiment.csv \\
        -o outputs/events_sentiment_baseline.csv

Adds columns:
    sentiment_<asset>_lm   bull / bear / neutral (same for USD and NDX
                           by construction; LM has no asset awareness)
    polarity_lm             continuous polarity in [-1, +1]
    pos_count_lm            raw positive word count
    neg_count_lm            raw negative word count

Threshold for direction: |polarity| >= POLARITY_THRESHOLD -> bull/bear,
else neutral. Default 0.1 matches the LLM's behaviour of returning
neutral on weak signals (see sentiment.py system prompt).

Note on HIV4: pysentiment2's Harvard IV-4 loader is incompatible with
recent pandas (categorical dtype concat error). We deliberately use only
LM, which is the finance-domain standard anyway. If a Harvard baseline
is later required, fix the loader upstream or rebuild from raw lists.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import pysentiment2 as ps

POLARITY_THRESHOLD = 0.1


def classify(polarity: float, threshold: float = POLARITY_THRESHOLD) -> str:
    if polarity >= threshold:
        return "bull"
    if polarity <= -threshold:
        return "bear"
    return "neutral"


def score_with(model, text: str):
    """Return (positive_count, negative_count, polarity) for a single text."""
    if not isinstance(text, str) or not text.strip():
        return 0, 0, 0.0
    tokens = model.tokenize(text)
    scores = model.get_score(tokens)
    pos = int(scores.get("Positive", 0))
    neg = int(scores.get("Negative", 0))
    polarity = float(scores.get("Polarity", 0.0))
    return pos, neg, polarity


def annotate_events(events: pd.DataFrame) -> pd.DataFrame:
    lm = ps.LM()

    rows = []
    for text in events["content"].fillna(""):
        pos, neg, pol = score_with(lm, text)
        rows.append({
            "pos_count_lm": pos,
            "neg_count_lm": neg,
            "polarity_lm": pol,
            "sentiment_usd_lm": classify(pol),
            "sentiment_ndx_lm": classify(pol),
        })

    annotations = pd.DataFrame(rows, index=events.index)
    return pd.concat([events, annotations], axis=1)


def print_summary(df: pd.DataFrame):
    n = len(df)
    print(f"\nClassified {n} events with LM baseline.")
    counts = df["sentiment_usd_lm"].value_counts()
    print(f"\n  [LM] distribution (sentiment_usd_lm):")
    for label in ["bull", "bear", "neutral"]:
        c = int(counts.get(label, 0))
        print(f"    {label:>7s}: {c:5d}  ({c/n:5.1%})")

    if "sentiment_usd" in df.columns:
        agree_usd = (df["sentiment_usd"] == df["sentiment_usd_lm"]).sum()
        print(f"\n  Agreement LLM vs LM (sentiment_usd): "
              f"{agree_usd}/{n} = {agree_usd/n:5.1%}")

        if "sentiment_ndx" in df.columns:
            agree_ndx = (df["sentiment_ndx"] == df["sentiment_ndx_lm"]).sum()
            print(f"  Agreement LLM vs LM (sentiment_ndx): "
                  f"{agree_ndx}/{n} = {agree_ndx/n:5.1%}")

            cross_diff_llm = (df["sentiment_usd"] != df["sentiment_ndx"]).sum()
            cross_diff_lm = (df["sentiment_usd_lm"] != df["sentiment_ndx_lm"]).sum()
            print(f"\n  Cross-asset disagreement (sentiment_usd != sentiment_ndx):")
            print(f"    LLM: {cross_diff_llm}/{n} = {cross_diff_llm/n:5.1%}")
            print(f"    LM : {cross_diff_lm}/{n} = {cross_diff_lm/n:5.1%}  "
                  f"(by construction = 0; LM is single-polarity)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Input CSV (events with content column)")
    parser.add_argument("-o", "--output", default="outputs/events_sentiment_baseline.csv")
    parser.add_argument("--limit", type=int, default=0, help="Process only N rows (testing)")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"ERROR: input file not found: {in_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(in_path)
    if args.limit > 0:
        df = df.head(args.limit).copy()
    if "content" not in df.columns:
        print(f"ERROR: input must have a 'content' column", file=sys.stderr)
        sys.exit(1)

    df = annotate_events(df)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\nWrote {len(df)} rows to {out_path}")
    print_summary(df)


if __name__ == "__main__":
    main()
