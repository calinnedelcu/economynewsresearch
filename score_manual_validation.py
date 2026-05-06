#!/usr/bin/env python3
"""Score the manual validation CSV after two annotators fill labels."""

from __future__ import annotations

import argparse
from collections import Counter

import pandas as pd


FIELDS = ["sentiment_usd", "sentiment_ndx", "expected_magnitude", "surprise_level"]


def cohen_kappa(a: list[str], b: list[str]) -> float:
    labels = sorted(set(a) | set(b))
    if not labels:
        return float("nan")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca = Counter(a)
    cb = Counter(b)
    expected = sum((ca[l] / n) * (cb[l] / n) for l in labels)
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    labels = sorted(set(y_true) | set(y_pred))
    scores = []
    for lab in labels:
        tp = sum(t == lab and p == lab for t, p in zip(y_true, y_pred))
        fp = sum(t != lab and p == lab for t, p in zip(y_true, y_pred))
        fn = sum(t == lab and p != lab for t, p in zip(y_true, y_pred))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        scores.append(f1)
    return sum(scores) / len(scores) if scores else float("nan")


def consensus(a: str, b: str) -> str:
    return a if a == b else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="outputs/manual_validation_sample.csv")
    args = parser.parse_args()

    df = pd.read_csv(args.input).fillna("")
    rows = []
    for field in FIELDS:
        a_col = f"ann1_{field}"
        b_col = f"ann2_{field}"
        llm_col = field
        if not all(c in df.columns for c in [a_col, b_col, llm_col]):
            continue
        sub = df[(df[a_col] != "") & (df[b_col] != "")].copy()
        if sub.empty:
            rows.append({"field": field, "n_labeled": 0})
            continue
        a = sub[a_col].astype(str).tolist()
        b = sub[b_col].astype(str).tolist()
        sub["consensus"] = [consensus(x, y) for x, y in zip(a, b)]
        agreed = sub[sub["consensus"] != ""]
        row = {
            "field": field,
            "n_labeled": len(sub),
            "human_agreement": sum(x == y for x, y in zip(a, b)) / len(sub),
            "cohen_kappa": cohen_kappa(a, b),
            "n_consensus": len(agreed),
        }
        if not agreed.empty:
            row["llm_accuracy_vs_consensus"] = (agreed[llm_col].astype(str) == agreed["consensus"]).mean()
            row["llm_macro_f1_vs_consensus"] = macro_f1(
                agreed["consensus"].astype(str).tolist(),
                agreed[llm_col].astype(str).tolist(),
            )
        rows.append(row)

    out = pd.DataFrame(rows)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
