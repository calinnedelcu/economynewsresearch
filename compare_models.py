#!/usr/bin/env python3
"""A/B test: DeepSeek V4 Flash vs Pro on a random sample of gold events.

Methodology:
  1. Random-sample N events (default 200) from is_gold=True rows.
  2. Run both models with the SAME prompt + few-shot in parallel.
  3. Report agreement rates, divergence cases, cost, latency.
  4. Save side-by-side results to outputs/compare_models.csv.

Used to empirically validate the choice of Flash over Pro for the
methodology section (per Wu et al. 2025: reasoning models do not
improve financial sentiment classification).
"""

import argparse
import csv
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from sentiment import (
    SYSTEM_PROMPT, FEW_SHOT_EXAMPLES, MODEL_FLASH, MODEL_PRO,
    build_messages, call_api, validate_response, cache_key, open_cache, cache_get, cache_put,
)

PRICING = {
    MODEL_FLASH: (0.14e-6, 0.28e-6),
    MODEL_PRO:   (0.145e-6, 1.74e-6),
}


def run_model_on_event(client, model, content):
    """Returns (sentiment_dict, prompt_tokens, completion_tokens, latency_sec)."""
    messages = build_messages(content)
    t0 = time.time()
    sentiment, ptok, ctok = call_api(client, messages, model)
    latency = time.time() - t0
    return sentiment, ptok, ctok, latency


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", default="outputs/events.csv")
    p.add_argument("-o", "--output", default="outputs/compare_models.csv")
    p.add_argument("-n", "--n-samples", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--workers", type=int, default=10, help="Concurrent workers per model")
    p.add_argument("--cache", default="outputs/sentiment_cache.sqlite")
    args = p.parse_args()

    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not in .env", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    conn = open_cache(args.cache)

    with open(args.events, "r", encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("is_gold") == "True"]

    rng = random.Random(args.seed)
    sample = rng.sample(rows, min(args.n_samples, len(rows)))
    print(f"Sampled {len(sample)} events from {len(rows)} gold events (seed={args.seed})")
    print(f"A/B testing {MODEL_FLASH} vs {MODEL_PRO} ...")
    print()

    from concurrent.futures import ThreadPoolExecutor
    import threading

    cnt_lock = threading.Lock()
    counters = {
        MODEL_FLASH: {"in": 0, "out": 0, "latency": 0.0, "errors": 0},
        MODEL_PRO:   {"in": 0, "out": 0, "latency": 0.0, "errors": 0},
    }

    def process_one(event_row):
        content = event_row["content"]
        results_per_model = {}
        for model in (MODEL_FLASH, MODEL_PRO):
            ck = cache_key(model, SYSTEM_PROMPT, content)
            cached = cache_get(conn, ck)
            if cached:
                results_per_model[model] = (cached, 0, 0, 0.0)
                continue
            try:
                sent, p_tok, c_tok, lat = run_model_on_event(client, model, content)
                if not validate_response(sent):
                    raise ValueError("invalid schema")
                cache_put(conn, ck, sent, p_tok, c_tok)
                results_per_model[model] = (sent, p_tok, c_tok, lat)
                with cnt_lock:
                    counters[model]["in"] += p_tok
                    counters[model]["out"] += c_tok
                    counters[model]["latency"] += lat
            except Exception as e:
                with cnt_lock:
                    counters[model]["errors"] += 1
                results_per_model[model] = (None, 0, 0, 0.0)
        return event_row, results_per_model

    out_rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, (ev, per_model) in enumerate(ex.map(process_one, sample), 1):
            f_sent, _, _, _ = per_model[MODEL_FLASH]
            p_sent, _, _, _ = per_model[MODEL_PRO]
            row = {
                "id": ev["id"],
                "timestamp_utc": ev["timestamp_utc"],
                "category": ev.get("category", ""),
                "content": ev["content"].splitlines()[0][:160],
            }
            for prefix, sent in [("flash", f_sent), ("pro", p_sent)]:
                if sent is None:
                    for fld in ("sentiment_usd","sentiment_ndx","directional_strength_usd",
                                "directional_strength_ndx","expected_magnitude","surprise_level",
                                "confidence","rationale"):
                        row[f"{prefix}_{fld}"] = ""
                else:
                    for fld in ("sentiment_usd","sentiment_ndx","directional_strength_usd",
                                "directional_strength_ndx","expected_magnitude","surprise_level",
                                "confidence","rationale"):
                        row[f"{prefix}_{fld}"] = sent.get(fld, "")
            out_rows.append(row)
            if i % 25 == 0 or i == len(sample):
                f_cost = counters[MODEL_FLASH]["in"] * PRICING[MODEL_FLASH][0] + counters[MODEL_FLASH]["out"] * PRICING[MODEL_FLASH][1]
                p_cost = counters[MODEL_PRO]["in"] * PRICING[MODEL_PRO][0] + counters[MODEL_PRO]["out"] * PRICING[MODEL_PRO][1]
                print(f"  [{i:3d}/{len(sample)}]  Flash ${f_cost:.4f}  Pro ${p_cost:.4f}", flush=True)

    fieldnames = list(out_rows[0].keys()) if out_rows else []
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    # ---- Summary statistics ----
    print()
    print("=" * 70)
    print("A/B TEST SUMMARY")
    print("=" * 70)

    valid_pairs = [r for r in out_rows if r["flash_sentiment_usd"] and r["pro_sentiment_usd"]]
    n = len(valid_pairs)
    print(f"\nValid response pairs: {n}/{len(out_rows)}")

    if n == 0:
        print("No valid pairs to analyze.")
        return

    # Agreement on categorical fields
    cat_fields = ["sentiment_usd", "sentiment_ndx", "expected_magnitude", "surprise_level"]
    print(f"\n=== Categorical agreement ===")
    for fld in cat_fields:
        agree = sum(1 for r in valid_pairs if r[f"flash_{fld}"] == r[f"pro_{fld}"])
        print(f"  {fld:25s}: {agree}/{n} = {agree/n:.1%}")

    # Continuous correlation
    import statistics
    print(f"\n=== Continuous fields (Pearson r) ===")
    for fld in ["directional_strength_usd", "directional_strength_ndx", "confidence"]:
        try:
            xs = [float(r[f"flash_{fld}"]) for r in valid_pairs]
            ys = [float(r[f"pro_{fld}"]) for r in valid_pairs]
            n_xy = len(xs)
            mx, my = sum(xs)/n_xy, sum(ys)/n_xy
            num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
            denx = (sum((x-mx)**2 for x in xs))**0.5
            deny = (sum((y-my)**2 for y in ys))**0.5
            r = num / (denx*deny) if denx*deny > 0 else float('nan')
            mae = sum(abs(x-y) for x,y in zip(xs,ys)) / n_xy
            print(f"  {fld:30s}: r={r:.3f}  mean|diff|={mae:.3f}")
        except Exception as e:
            print(f"  {fld}: error {e}")

    # Cost & latency
    print(f"\n=== Cost & latency ===")
    for m in (MODEL_FLASH, MODEL_PRO):
        c = counters[m]
        cost = c["in"] * PRICING[m][0] + c["out"] * PRICING[m][1]
        avg_lat = c["latency"] / max(n, 1)
        print(f"  {m:25s}: cost=${cost:.4f}  in={c['in']:>6d}  out={c['out']:>6d}  avg_latency={avg_lat:.2f}s  errors={c['errors']}")

    # Disagreement examples
    print(f"\n=== First 5 disagreements (sentiment_usd or sentiment_ndx) ===")
    disagrees = [r for r in valid_pairs
                 if r["flash_sentiment_usd"] != r["pro_sentiment_usd"]
                 or r["flash_sentiment_ndx"] != r["pro_sentiment_ndx"]]
    for r in disagrees[:5]:
        print(f"  [{r['timestamp_utc']}] {r['content']}")
        print(f"    Flash: USD={r['flash_sentiment_usd']:>7s}/NDX={r['flash_sentiment_ndx']:>7s}  surp={r['flash_surprise_level']}")
        print(f"    Pro:   USD={r['pro_sentiment_usd']:>7s}/NDX={r['pro_sentiment_ndx']:>7s}  surp={r['pro_surprise_level']}")

    print(f"\nFull comparison written to {args.output}")


if __name__ == "__main__":
    main()
