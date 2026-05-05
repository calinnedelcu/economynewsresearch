#!/usr/bin/env python3
"""Classify sentiment of FJ news events with DeepSeek V4 Flash.

Reads events.csv (output of parse_fj_discord.py), filters is_gold=True,
calls DeepSeek API with structured JSON output for each event, writes
events_sentiment.csv with added columns.

Local SQLite cache keyed on hash(model + system_prompt + content) so
re-runs don't re-spend API credit during prompt iteration.

Usage:
    python sentiment.py outputs/events.csv -o outputs/events_sentiment.csv
    python sentiment.py outputs/events.csv -o outputs/test.csv --limit 5
"""

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIError

MODEL_FLASH = "deepseek-v4-flash"
MODEL_PRO = "deepseek-v4-pro"
DEFAULT_MODEL = MODEL_FLASH
CACHE_PATH = "outputs/sentiment_cache.sqlite"

SYSTEM_PROMPT = """You are a financial sentiment analyst. Classify how a news event likely affects the US Dollar (USD) and the Nasdaq-100 index (NDX) in the very short term (minutes to hours after publication).

Output STRICTLY a single JSON object with this exact schema:
{
  "sentiment_usd": "bull" | "bear" | "neutral",
  "sentiment_ndx": "bull" | "bear" | "neutral",
  "directional_strength_usd": <float in [-1.0, +1.0]>,
  "directional_strength_ndx": <float in [-1.0, +1.0]>,
  "expected_magnitude": "low" | "med" | "high",
  "surprise_level": "expected" | "surprise" | "shock",
  "confidence": <float in [0.0, 1.0]>,
  "rationale": "<one short sentence, max 25 words>"
}

Definitions:
- sentiment_usd / sentiment_ndx: discrete direction. "bull"=up, "bear"=down, "neutral"=no clear move.
- directional_strength_*: signed continuous score; -1.0 = strongly bearish, 0.0 = neutral, +1.0 = strongly bullish. Captures intensity, not just sign. Must be consistent with sentiment_* (bull → positive, bear → negative).
- expected_magnitude: low = a few basis points; med = ~0.1-0.3%; high = >0.3%.
- surprise_level:
    "expected" — scheduled or rumored news, broadly anticipated by markets (FOMC at consensus, planned summit).
    "surprise" — unscheduled but plausible (Trump tweet, Iran-US escalation announcement, central banker off-script comment).
    "shock" — extreme/tail event (military strike, bank run, leadership ousting, major terror).
- confidence: how sure you are about the direction call (NOT the magnitude).

Rules:
- Base your judgment STRICTLY on the text provided. Do NOT invent context.
- If the message is ambiguous, off-topic, or a pure data release without surprise, return neutral with low confidence (<0.4).
- USD and NDX are different assets; their sentiments can differ (e.g. risk-off events: bull USD, bear NDX).
- directional_strength values should respect sentiment direction: if sentiment_usd="bull", directional_strength_usd > 0.
- Return ONLY the JSON object, no preamble, no markdown fences."""

FEW_SHOT_EXAMPLES = [
    {
        "event": "🔴 ⚠️ BREAKING: Trump: Highly unlikely I will extend ceasefire with Iran.",
        "output": {
            "sentiment_usd": "bull", "sentiment_ndx": "bear",
            "directional_strength_usd": 0.55, "directional_strength_ndx": -0.65,
            "expected_magnitude": "med", "surprise_level": "surprise",
            "confidence": 0.75,
            "rationale": "Geopolitical escalation drives safe-haven demand for USD and risk-off in equities."
        }
    },
    {
        "event": "🔴 Fed's Powell: We are prepared to cut rates if labor market weakens further.",
        "output": {
            "sentiment_usd": "bear", "sentiment_ndx": "bull",
            "directional_strength_usd": -0.7, "directional_strength_ndx": 0.8,
            "expected_magnitude": "high", "surprise_level": "surprise",
            "confidence": 0.85,
            "rationale": "Dovish Fed signal weakens USD and supports equities via lower discount rate."
        }
    },
    {
        "event": "🔴 ⚠️ BREAKING: ECB's Lagarde: Inflation risks have shifted to the upside, warranting tighter policy.",
        "output": {
            "sentiment_usd": "bear", "sentiment_ndx": "neutral",
            "directional_strength_usd": -0.5, "directional_strength_ndx": -0.1,
            "expected_magnitude": "med", "surprise_level": "surprise",
            "confidence": 0.7,
            "rationale": "Hawkish ECB strengthens EUR (USD weaker on EUR/USD); NDX impact indirect."
        }
    },
    {
        "event": "🔴 US Treasury announces $30B emergency aid package to Ukraine.",
        "output": {
            "sentiment_usd": "neutral", "sentiment_ndx": "neutral",
            "directional_strength_usd": 0.05, "directional_strength_ndx": 0.0,
            "expected_magnitude": "low", "surprise_level": "expected",
            "confidence": 0.4,
            "rationale": "Aid package already partly priced in; mixed signal for risk assets."
        }
    },
    {
        "event": "🔴 ⚠️ BREAKING: NVIDIA reports earnings miss, stock down 8% after-hours.",
        "output": {
            "sentiment_usd": "neutral", "sentiment_ndx": "bear",
            "directional_strength_usd": 0.05, "directional_strength_ndx": -0.85,
            "expected_magnitude": "high", "surprise_level": "shock",
            "confidence": 0.85,
            "rationale": "Major NDX constituent miss directly drags index; FX impact minimal."
        }
    },
    {
        "event": "Iranian foreign ministry: We will respond proportionally to any aggression.",
        "output": {
            "sentiment_usd": "bull", "sentiment_ndx": "bear",
            "directional_strength_usd": 0.25, "directional_strength_ndx": -0.3,
            "expected_magnitude": "low", "surprise_level": "expected",
            "confidence": 0.5,
            "rationale": "Mild escalation rhetoric, modest safe-haven flow into USD, slight risk-off."
        }
    },
    {
        "event": "Norwegian fishing exports to UK rose 4% YoY in March.",
        "output": {
            "sentiment_usd": "neutral", "sentiment_ndx": "neutral",
            "directional_strength_usd": 0.0, "directional_strength_ndx": 0.0,
            "expected_magnitude": "low", "surprise_level": "expected",
            "confidence": 0.2,
            "rationale": "Off-topic for USD and NDX; no expected directional impact."
        }
    },
    {
        "event": "🔴 ⚠️ BREAKING: Reports indicate failed coup attempt in major OPEC member; oil up 5%.",
        "output": {
            "sentiment_usd": "bull", "sentiment_ndx": "bear",
            "directional_strength_usd": 0.7, "directional_strength_ndx": -0.75,
            "expected_magnitude": "high", "surprise_level": "shock",
            "confidence": 0.8,
            "rationale": "Oil supply shock fuels inflation fears, USD safe-haven, equities risk-off."
        }
    },
]


def build_messages(event_text: str) -> list:
    """Build chat messages with system + few-shot + user query."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for ex in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": f"Event: {ex['event']}"})
        messages.append({"role": "assistant", "content": json.dumps(ex["output"])})
    messages.append({"role": "user", "content": f"Event: {event_text}"})
    return messages


def cache_key(model: str, system: str, content: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"\x00")
    h.update(system.encode())
    h.update(b"\x00")
    h.update(content.encode())
    return h.hexdigest()


def open_cache(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_cache (
            key TEXT PRIMARY KEY,
            response_json TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


_cache_lock = threading.Lock()


def cache_get(conn, key):
    with _cache_lock:
        row = conn.execute("SELECT response_json FROM sentiment_cache WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def cache_put(conn, key, response, prompt_tokens, completion_tokens):
    with _cache_lock:
        conn.execute(
            "INSERT OR REPLACE INTO sentiment_cache (key, response_json, prompt_tokens, completion_tokens) VALUES (?,?,?,?)",
            (key, json.dumps(response), prompt_tokens, completion_tokens),
        )
        conn.commit()


def call_api(client: OpenAI, messages: list, model: str, max_retries: int = 3) -> tuple:
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            content = resp.choices[0].message.content
            parsed = json.loads(content)
            return parsed, resp.usage.prompt_tokens, resp.usage.completion_tokens
        except RateLimitError:
            wait = 2 ** attempt
            print(f"    rate limited, waiting {wait}s ...", flush=True)
            time.sleep(wait)
        except (APIError, json.JSONDecodeError) as e:
            if attempt == max_retries - 1:
                raise
            print(f"    error ({type(e).__name__}), retry {attempt + 1}/{max_retries} ...", flush=True)
            time.sleep(1)
    raise RuntimeError("max retries exceeded")


def validate_response(r: dict) -> bool:
    """Check that response has all required fields with valid values."""
    valid_sent = {"bull", "bear", "neutral"}
    valid_mag = {"low", "med", "high"}
    valid_surprise = {"expected", "surprise", "shock"}
    if not isinstance(r, dict):
        return False
    if r.get("sentiment_usd") not in valid_sent:
        return False
    if r.get("sentiment_ndx") not in valid_sent:
        return False
    if r.get("expected_magnitude") not in valid_mag:
        return False
    if r.get("surprise_level") not in valid_surprise:
        return False
    for fld in ("directional_strength_usd", "directional_strength_ndx"):
        v = r.get(fld)
        if not isinstance(v, (int, float)) or not (-1.0 <= v <= 1.0):
            return False
    conf = r.get("confidence")
    if not isinstance(conf, (int, float)) or not (0 <= conf <= 1):
        return False
    if not isinstance(r.get("rationale"), str):
        return False
    return True


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_csv", help="Path to events.csv (from parse_fj_discord.py)")
    p.add_argument("-o", "--output", required=True, help="Output CSV path")
    p.add_argument("--limit", type=int, default=None, help="Process only first N gold events (for testing)")
    p.add_argument("--all", action="store_true", help="Process ALL events, not only is_gold")
    p.add_argument("--cache", default=CACHE_PATH, help="SQLite cache path")
    p.add_argument("--workers", type=int, default=1, help="Concurrent API workers (1=serial)")
    p.add_argument("--model", choices=[MODEL_FLASH, MODEL_PRO], default=DEFAULT_MODEL,
                   help="DeepSeek model variant")
    args = p.parse_args()
    model = args.model
    out_pricing = (0.14e-6, 0.28e-6) if model == MODEL_FLASH else (0.145e-6, 1.74e-6)

    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not in .env", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    conn = open_cache(args.cache)

    with open(args.input_csv, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not args.all:
        rows = [r for r in rows if r.get("is_gold") == "True"]

    if args.limit:
        rows = rows[: args.limit]

    print(f"Processing {len(rows)} events with model={model}")
    print(f"Cache: {args.cache}")
    print()

    counters = {"cache_hits": 0, "api_calls": 0, "in_tok": 0, "out_tok": 0, "done": 0, "skipped": 0}
    counters_lock = threading.Lock()
    results = [None] * len(rows)
    progress_every = max(1, len(rows) // 40)

    def process(idx, row):
        content = row["content"]
        key = cache_key(model, SYSTEM_PROMPT, content)
        cached = cache_get(conn, key)
        if cached:
            sentiment = cached
            with counters_lock:
                counters["cache_hits"] += 1
        else:
            messages = build_messages(content)
            try:
                sentiment, ptok, ctok = call_api(client, messages, model)
            except Exception:
                with counters_lock:
                    counters["skipped"] += 1
                return None
            if not validate_response(sentiment):
                with counters_lock:
                    counters["skipped"] += 1
                return None
            cache_put(conn, key, sentiment, ptok, ctok)
            with counters_lock:
                counters["api_calls"] += 1
                counters["in_tok"] += ptok
                counters["out_tok"] += ctok

        out_row = dict(row)
        out_row["sentiment_usd"] = sentiment["sentiment_usd"]
        out_row["sentiment_ndx"] = sentiment["sentiment_ndx"]
        out_row["directional_strength_usd"] = sentiment["directional_strength_usd"]
        out_row["directional_strength_ndx"] = sentiment["directional_strength_ndx"]
        out_row["expected_magnitude"] = sentiment["expected_magnitude"]
        out_row["surprise_level"] = sentiment["surprise_level"]
        out_row["confidence"] = sentiment["confidence"]
        out_row["rationale"] = sentiment["rationale"]
        out_row["sentiment_model"] = model

        with counters_lock:
            counters["done"] += 1
            done = counters["done"]
            if done % progress_every == 0 or done == len(rows):
                cost = counters["in_tok"] * out_pricing[0] + counters["out_tok"] * out_pricing[1]
                preview = content.splitlines()[0][:60]
                print(f"  [{done:4d}/{len(rows)}] cache={counters['cache_hits']} api={counters['api_calls']} cost=${cost:.4f}  {sentiment['sentiment_usd'][:4]}/{sentiment['sentiment_ndx'][:4]} surp={sentiment['surprise_level'][:4]} | {preview}", flush=True)
        return idx, out_row

    if args.workers > 1:
        print(f"Running with {args.workers} concurrent workers ...\n")
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = [ex.submit(process, i, row) for i, row in enumerate(rows)]
            for fut in as_completed(futures):
                res = fut.result()
                if res is not None:
                    idx, out_row = res
                    results[idx] = out_row
    else:
        for i, row in enumerate(rows):
            res = process(i, row)
            if res is not None:
                idx, out_row = res
                results[idx] = out_row

    out_rows = [r for r in results if r is not None]
    cache_hits = counters["cache_hits"]
    api_calls = counters["api_calls"]
    total_in_tokens = counters["in_tok"]
    total_out_tokens = counters["out_tok"]

    if not out_rows:
        print("No rows produced.", file=sys.stderr)
        sys.exit(1)

    fieldnames = list(out_rows[0].keys())
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    print()
    print(f"Wrote {len(out_rows)} rows to {args.output}")
    print(f"  cache hits:   {cache_hits}")
    print(f"  API calls:    {api_calls}")
    print(f"  in tokens:    {total_in_tokens:,}")
    print(f"  out tokens:   {total_out_tokens:,}")
    cost = total_in_tokens * out_pricing[0] + total_out_tokens * out_pricing[1]
    print(f"  est cost:     ${cost:.5f}")


if __name__ == "__main__":
    main()
