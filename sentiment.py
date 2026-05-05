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
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIError

MODEL = "deepseek-v4-flash"
CACHE_PATH = "outputs/sentiment_cache.sqlite"

SYSTEM_PROMPT = """You are a financial sentiment analyst. Classify how a news event likely affects the US Dollar (USD) and the Nasdaq-100 index (NDX) in the very short term (minutes to hours after publication).

Output STRICTLY a single JSON object with this exact schema:
{
  "sentiment_usd": "bull" | "bear" | "neutral",
  "sentiment_ndx": "bull" | "bear" | "neutral",
  "expected_magnitude": "low" | "med" | "high",
  "confidence": <float between 0.0 and 1.0>,
  "rationale": "<one short sentence, max 25 words>"
}

Definitions:
- "bull" means the asset is expected to move UP in price after this news.
- "bear" means the asset is expected to move DOWN in price.
- "neutral" means no directional move expected, or text is too ambiguous.
- expected_magnitude: low = a few basis points; med = ~0.1-0.3%; high = >0.3%.
- confidence: how sure you are about the direction call (NOT the magnitude).

Rules:
- Base your judgment STRICTLY on the text provided. Do NOT invent context.
- If the message is ambiguous, off-topic, or a pure data release without surprise, return neutral with low confidence (<0.4).
- USD and NDX are different assets; their sentiments can differ (e.g. risk-off events: bull USD, bear NDX).
- Return ONLY the JSON object, no preamble, no markdown fences."""

FEW_SHOT_EXAMPLES = [
    {
        "event": "🔴 ⚠️ BREAKING: Trump: Highly unlikely I will extend ceasefire with Iran.",
        "output": {
            "sentiment_usd": "bull", "sentiment_ndx": "bear",
            "expected_magnitude": "med", "confidence": 0.75,
            "rationale": "Geopolitical escalation drives safe-haven demand for USD and risk-off in equities."
        }
    },
    {
        "event": "🔴 Fed's Powell: We are prepared to cut rates if labor market weakens further.",
        "output": {
            "sentiment_usd": "bear", "sentiment_ndx": "bull",
            "expected_magnitude": "high", "confidence": 0.85,
            "rationale": "Dovish Fed signal weakens USD and supports equities via lower discount rate."
        }
    },
    {
        "event": "🔴 ⚠️ BREAKING: ECB's Lagarde: Inflation risks have shifted to the upside, warranting tighter policy.",
        "output": {
            "sentiment_usd": "bear", "sentiment_ndx": "neutral",
            "expected_magnitude": "med", "confidence": 0.7,
            "rationale": "Hawkish ECB strengthens EUR (USD weaker on EUR/USD); NDX impact indirect."
        }
    },
    {
        "event": "🔴 US Treasury announces $30B emergency aid package to Ukraine.",
        "output": {
            "sentiment_usd": "neutral", "sentiment_ndx": "neutral",
            "expected_magnitude": "low", "confidence": 0.4,
            "rationale": "Aid package already partly priced in; mixed signal for risk assets."
        }
    },
    {
        "event": "🔴 ⚠️ BREAKING: NVIDIA reports earnings miss, stock down 8% after-hours.",
        "output": {
            "sentiment_usd": "neutral", "sentiment_ndx": "bear",
            "expected_magnitude": "high", "confidence": 0.85,
            "rationale": "Major NDX constituent miss directly drags index; FX impact minimal."
        }
    },
    {
        "event": "Iranian foreign ministry: We will respond proportionally to any aggression.",
        "output": {
            "sentiment_usd": "bull", "sentiment_ndx": "bear",
            "expected_magnitude": "low", "confidence": 0.5,
            "rationale": "Mild escalation rhetoric, modest safe-haven flow into USD, slight risk-off."
        }
    },
    {
        "event": "Norwegian fishing exports to UK rose 4% YoY in March.",
        "output": {
            "sentiment_usd": "neutral", "sentiment_ndx": "neutral",
            "expected_magnitude": "low", "confidence": 0.2,
            "rationale": "Off-topic for USD and NDX; no expected directional impact."
        }
    },
    {
        "event": "🔴 ⚠️ BREAKING: Reports indicate failed coup attempt in major OPEC member; oil up 5%.",
        "output": {
            "sentiment_usd": "bull", "sentiment_ndx": "bear",
            "expected_magnitude": "high", "confidence": 0.8,
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
    conn = sqlite3.connect(path)
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


def cache_get(conn, key):
    row = conn.execute("SELECT response_json FROM sentiment_cache WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def cache_put(conn, key, response, prompt_tokens, completion_tokens):
    conn.execute(
        "INSERT OR REPLACE INTO sentiment_cache (key, response_json, prompt_tokens, completion_tokens) VALUES (?,?,?,?)",
        (key, json.dumps(response), prompt_tokens, completion_tokens),
    )
    conn.commit()


def call_api(client: OpenAI, messages: list, max_retries: int = 3) -> tuple:
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
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
    if not isinstance(r, dict):
        return False
    if r.get("sentiment_usd") not in valid_sent:
        return False
    if r.get("sentiment_ndx") not in valid_sent:
        return False
    if r.get("expected_magnitude") not in valid_mag:
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
    args = p.parse_args()

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

    print(f"Processing {len(rows)} events with model={MODEL}")
    print(f"Cache: {args.cache}")
    print()

    out_rows = []
    total_in_tokens = 0
    total_out_tokens = 0
    cache_hits = 0
    api_calls = 0

    for i, row in enumerate(rows, 1):
        content = row["content"]
        key = cache_key(MODEL, SYSTEM_PROMPT, content)
        cached = cache_get(conn, key)
        if cached:
            sentiment = cached
            cache_hits += 1
            status = "[cache]"
        else:
            messages = build_messages(content)
            sentiment, ptok, ctok = call_api(client, messages)
            if not validate_response(sentiment):
                print(f"  [{i}] WARN invalid response, skipping: {sentiment}")
                continue
            cache_put(conn, key, sentiment, ptok, ctok)
            total_in_tokens += ptok
            total_out_tokens += ctok
            api_calls += 1
            status = f"[api {ptok}+{ctok}]"

        preview = content.splitlines()[0][:80]
        print(f"  [{i}/{len(rows)}] {status} {sentiment['sentiment_usd']:>7s}/{sentiment['sentiment_ndx']:>7s} conf={sentiment['confidence']:.2f} | {preview}")

        out_row = dict(row)
        out_row["sentiment_usd"] = sentiment["sentiment_usd"]
        out_row["sentiment_ndx"] = sentiment["sentiment_ndx"]
        out_row["expected_magnitude"] = sentiment["expected_magnitude"]
        out_row["confidence"] = sentiment["confidence"]
        out_row["rationale"] = sentiment["rationale"]
        out_row["sentiment_model"] = MODEL
        out_rows.append(out_row)

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
    cost = total_in_tokens * 0.14e-6 + total_out_tokens * 0.28e-6
    print(f"  est cost:     ${cost:.5f}")


if __name__ == "__main__":
    main()
