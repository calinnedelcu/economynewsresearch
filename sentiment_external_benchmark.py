#!/usr/bin/env python3
"""External benchmark validation on Financial PhraseBank.

Runs each of the three sentiment classifiers used in the paper
(DeepSeek-v4-flash, Loughran-McDonald dictionary, FinBERT-tone) on
the Financial PhraseBank dataset of @malo2014good and reports
accuracy, macro-F1, per-class F1, and Cohen's kappa against the
gold human-annotated labels.

This validates the *classifier* on the de facto standard finance
NLP benchmark (the same dataset used by FinBERT in @yang2020finbert),
not the specific labels on our event sample. It does so without
requiring any human annotation effort from the paper's authors.

The DeepSeek call uses a benchmark-adapted prompt that maps to
PhraseBank's three-class scheme (positive / negative / neutral) and
does not include the USD/NDX framing of the production prompt; this
isolates classifier capability from the prompt's domain conditioning.

Results are cached in a SQLite database (the same cache module used
in sentiment.py) so re-runs do not duplicate API costs.

Usage:
    python sentiment_external_benchmark.py
    python sentiment_external_benchmark.py --limit 100  # quick test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIError

CACHE_PATH = "outputs/sentiment_external_cache.sqlite"

BENCHMARK_SYSTEM_PROMPT = """You are a financial sentiment analyst. Classify each input sentence as having positive, negative, or neutral sentiment from the perspective of a retail investor.

Output STRICTLY a single JSON object with this schema:
{
  "sentiment": "positive" | "negative" | "neutral",
  "confidence": <float in [0.0, 1.0]>
}

Rules:
- "positive": the news is favourable for the firm or the broader market.
- "negative": the news is unfavourable.
- "neutral": the sentence is factual, balanced, or has no clear directional implication.
- Return ONLY the JSON object, no preamble, no markdown fences."""


def cache_get(conn, key):
    with _CACHE_LOCK:
        cur = conn.execute("SELECT value FROM cache WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else None


def cache_set(conn, key, value):
    with _CACHE_LOCK:
        conn.execute(
            "INSERT OR REPLACE INTO cache(key, value, created_at) VALUES (?, ?, ?)",
            (key, value, int(time.time())),
        )
        conn.commit()


_CACHE_LOCK = __import__("threading").Lock()


def init_cache():
    Path(CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_PATH, timeout=60, check_same_thread=False)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT, created_at INTEGER)"
    )
    return conn


def make_cache_key(model, prompt, content):
    h = hashlib.sha256()
    h.update(f"{model}\n{prompt}\n{content}".encode("utf-8"))
    return h.hexdigest()


def classify_one(client, model, content, conn, max_retries=4):
    key = make_cache_key(model, BENCHMARK_SYSTEM_PROMPT, content)
    cached = cache_get(conn, key)
    if cached:
        try:
            return json.loads(cached).get("sentiment", "neutral")
        except json.JSONDecodeError:
            pass

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": BENCHMARK_SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                temperature=0.0,
                max_tokens=120,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content
            cache_set(conn, key, raw)
            parsed = json.loads(raw)
            return parsed.get("sentiment", "neutral")
        except (RateLimitError, APIError) as e:
            if attempt == max_retries - 1:
                print(f"  ERROR after retries: {e}", file=sys.stderr)
                return None
            time.sleep(2 ** attempt)
        except json.JSONDecodeError:
            return None
    return None


def run_deepseek(sentences, model_name, workers=10):
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY not in .env; skipping DeepSeek", file=sys.stderr)
        return [None] * len(sentences)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    conn = init_cache()
    results = [None] * len(sentences)
    print(f"Running DeepSeek ({model_name}) on {len(sentences)} sentences (workers={workers}) ...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(classify_one, client, model_name, s, conn): i
                   for i, s in enumerate(sentences)}
        for n, fut in enumerate(as_completed(futures), 1):
            i = futures[fut]
            results[i] = fut.result()
            if n % 200 == 0:
                print(f"  {n}/{len(sentences)} done")
    conn.close()
    return results


def run_lm_dictionary(sentences):
    import pysentiment2 as ps
    lm = ps.LM()
    print(f"Running Loughran-McDonald on {len(sentences)} sentences ...")
    results = []
    for s in sentences:
        if not isinstance(s, str) or not s.strip():
            results.append("neutral")
            continue
        tokens = lm.tokenize(s)
        scores = lm.get_score(tokens)
        polarity = float(scores.get("Polarity", 0.0))
        if polarity >= 0.1:
            results.append("positive")
        elif polarity <= -0.1:
            results.append("negative")
        else:
            results.append("neutral")
    return results


def run_finbert(sentences, batch_size=32):
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    print(f"Running FinBERT-tone on {len(sentences)} sentences ...")
    tokenizer = AutoTokenizer.from_pretrained("yiyanghkust/finbert-tone")
    model = AutoModelForSequenceClassification.from_pretrained("yiyanghkust/finbert-tone")
    model.eval()
    label_map = {"Positive": "positive", "Negative": "negative", "Neutral": "neutral"}
    results = []
    n = len(sentences)
    for start in range(0, n, batch_size):
        batch = sentences[start:start + batch_size]
        with torch.no_grad():
            inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=128)
            out = model(**inputs)
            preds = out.logits.argmax(dim=-1).tolist()
        for p in preds:
            raw = model.config.id2label[p]
            results.append(label_map.get(raw, "neutral"))
        if (start // batch_size) % 10 == 0:
            print(f"  batch {start // batch_size + 1}/{(n + batch_size - 1) // batch_size}")
    return results


def compute_metrics(gold, pred, labels=("positive", "negative", "neutral")):
    gold = np.array(gold)
    pred = np.array(pred)
    valid = pred != None  # noqa
    gold = gold[valid]
    pred = pred[valid]
    n = len(gold)
    if n == 0:
        return {}

    # Overall accuracy
    accuracy = float((gold == pred).mean())

    # Per-class precision, recall, F1
    out = {"n": int(n), "accuracy": accuracy}
    f1s = []
    for c in labels:
        tp = int(((gold == c) & (pred == c)).sum())
        fp = int(((gold != c) & (pred == c)).sum())
        fn = int(((gold == c) & (pred != c)).sum())
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        out[f"precision_{c}"] = prec
        out[f"recall_{c}"] = rec
        out[f"f1_{c}"] = f1
        f1s.append(f1)
    out["macro_f1"] = float(np.mean(f1s))

    # Cohen's kappa (manual implementation)
    po = accuracy
    counts_gold = pd.Series(gold).value_counts(normalize=True)
    counts_pred = pd.Series(pred).value_counts(normalize=True)
    pe = sum(counts_gold.get(c, 0) * counts_pred.get(c, 0) for c in labels)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 0.0
    out["cohens_kappa"] = float(kappa)

    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="lmassaron/FinancialPhraseBank",
                        help="HuggingFace dataset name")
    parser.add_argument("--model", default="deepseek-chat", help="DeepSeek model name")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only N sentences (for testing)")
    parser.add_argument("--skip-deepseek", action="store_true")
    parser.add_argument("--skip-finbert", action="store_true")
    parser.add_argument("-o", "--output", default="outputs/external_benchmark_results.csv")
    parser.add_argument("--metrics-output", default="outputs/external_benchmark_metrics.csv")
    args = parser.parse_args()

    from datasets import load_dataset
    print(f"Loading {args.dataset} ...")
    ds = load_dataset(args.dataset)
    all_rows = list(ds["train"]) + list(ds["validation"]) + list(ds["test"])
    if args.limit > 0:
        all_rows = all_rows[:args.limit]
    sentences = [r["sentence"] for r in all_rows]
    gold = [r["sentiment"] for r in all_rows]
    print(f"  loaded {len(sentences)} sentences")
    print(f"  gold distribution: {dict(pd.Series(gold).value_counts())}")
    print()

    df = pd.DataFrame({"sentence": sentences, "gold": gold})

    if not args.skip_deepseek:
        df["deepseek"] = run_deepseek(sentences, args.model, workers=args.workers)
    df["lm"] = run_lm_dictionary(sentences)
    if not args.skip_finbert:
        df["finbert"] = run_finbert(sentences)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"\nWrote per-sentence predictions to {args.output}")

    # Compute metrics
    rows = []
    for src in ["deepseek", "lm", "finbert"]:
        if src not in df.columns:
            continue
        m = compute_metrics(df["gold"].tolist(), df[src].tolist())
        m["classifier"] = src
        rows.append(m)
    metrics = pd.DataFrame(rows)
    metrics.to_csv(args.metrics_output, index=False)
    print(f"Wrote metrics to {args.metrics_output}\n")

    # Print summary
    print("=" * 80)
    print(f"{'Classifier':<12} {'N':>5} {'Acc':>6} {'Macro-F1':>9} {'kappa':>7} "
          f"{'F1-pos':>7} {'F1-neg':>7} {'F1-neu':>7}")
    print("=" * 80)
    for _, r in metrics.iterrows():
        print(f"{r['classifier']:<12} {int(r['n']):>5} {r['accuracy']:>6.3f} "
              f"{r['macro_f1']:>9.3f} {r['cohens_kappa']:>7.3f} "
              f"{r['f1_positive']:>7.3f} {r['f1_negative']:>7.3f} {r['f1_neutral']:>7.3f}")


if __name__ == "__main__":
    main()
