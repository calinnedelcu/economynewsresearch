#!/usr/bin/env python3
"""FinBERT-tone sentiment baseline for event headlines.

Runs the @yang2020finbert FinBERT model (yiyanghkust/finbert-tone) over
the gold event corpus and assigns a discrete bull/bear/neutral label
per headline. Complements the Loughran-McDonald dictionary baseline
in sentiment_baseline.py with a modern neural baseline that the LLM
must also beat.

Like the LM baseline, FinBERT is a single-output classifier and cannot
differentiate USD vs NDX sentiment. The cross-asset disagreement that
the LLM produces (USD != NDX on 73.5% of events) is therefore
out-of-scope for this baseline by construction.

Usage:
    python sentiment_finbert.py outputs/events_sentiment.csv \\
        -o outputs/events_sentiment_finbert.csv

First run downloads the model (~440 MB) from Hugging Face Hub and
caches it under the user's ~/.cache/huggingface. Subsequent runs are
local.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_NAME = "yiyanghkust/finbert-tone"
LABEL_MAP = {"Positive": "bull", "Negative": "bear", "Neutral": "neutral"}
BATCH_SIZE = 32


def load_model():
    print(f"Loading {MODEL_NAME} (first run will download ~440 MB) ...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    model.eval()
    return tokenizer, model


@torch.no_grad()
def classify_batch(tokenizer, model, texts):
    inputs = tokenizer(texts, return_tensors="pt", padding=True,
                       truncation=True, max_length=128)
    outputs = model(**inputs)
    probs = torch.softmax(outputs.logits, dim=-1).cpu().numpy()
    labels = [model.config.id2label[int(i)] for i in probs.argmax(axis=-1)]
    return labels, probs


def annotate_events(events: pd.DataFrame) -> pd.DataFrame:
    tokenizer, model = load_model()
    n = len(events)
    print(f"Classifying {n} events in batches of {BATCH_SIZE} on CPU ...")

    texts = events["content"].fillna("").astype(str).tolist()
    all_labels = []
    all_pos = []
    all_neu = []
    all_neg = []

    for start in range(0, n, BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        if not batch:
            continue
        labels, probs = classify_batch(tokenizer, model, batch)
        all_labels.extend(labels)
        for p in probs:
            label_to_prob = {model.config.id2label[i]: float(p[i])
                             for i in range(len(p))}
            all_pos.append(label_to_prob.get("Positive", 0.0))
            all_neu.append(label_to_prob.get("Neutral", 0.0))
            all_neg.append(label_to_prob.get("Negative", 0.0))
        if (start // BATCH_SIZE) % 10 == 0:
            print(f"  batch {start // BATCH_SIZE + 1}/{(n + BATCH_SIZE - 1) // BATCH_SIZE} done")

    finbert_labels = [LABEL_MAP.get(lbl, "neutral") for lbl in all_labels]
    annotations = pd.DataFrame({
        "finbert_raw_label": all_labels,
        "sentiment_usd_finbert": finbert_labels,
        "sentiment_ndx_finbert": finbert_labels,
        "prob_positive_finbert": all_pos,
        "prob_neutral_finbert": all_neu,
        "prob_negative_finbert": all_neg,
    }, index=events.index)
    return pd.concat([events, annotations], axis=1)


def print_summary(df: pd.DataFrame):
    n = len(df)
    print(f"\nClassified {n} events with FinBERT.")
    counts = df["sentiment_usd_finbert"].value_counts()
    print(f"\n  [FinBERT] distribution:")
    for label in ["bull", "bear", "neutral"]:
        c = int(counts.get(label, 0))
        print(f"    {label:>7s}: {c:5d}  ({c/n:5.1%})")

    if "sentiment_usd" in df.columns:
        agree_usd = (df["sentiment_usd"] == df["sentiment_usd_finbert"]).sum()
        agree_ndx = (df["sentiment_ndx"] == df["sentiment_ndx_finbert"]).sum()
        print(f"\n  Agreement LLM vs FinBERT (sentiment_usd): "
              f"{agree_usd}/{n} = {agree_usd/n:5.1%}")
        print(f"  Agreement LLM vs FinBERT (sentiment_ndx): "
              f"{agree_ndx}/{n} = {agree_ndx/n:5.1%}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Input CSV (with content column)")
    parser.add_argument("-o", "--output", default="outputs/events_sentiment_finbert.csv")
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
