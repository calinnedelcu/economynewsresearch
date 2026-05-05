#!/usr/bin/env python3
"""Parse FinancialJuice Discord channel JSON exports into structured events CSV.

Input: DiscordChatExporter JSON for the FJ #newsfeed channel.
Output: CSV with one row per non-empty message plus parsed flags.
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone

RED_DOT = "\U0001F534"
WARNING = "⚠"
BREAKING_RE = re.compile(r"\bBREAKING\b")
MACRO_RE = re.compile(r"\$MACRO\b")
URL_ONLY_RE = re.compile(r"^\s*<?https?://\S+>?\s*$")

KEYWORDS_CB = [
    "fed", "fomc", "powell", "ecb", "lagarde", "boj", "ueda", "boe", "bailey",
    "snb", "boc", "macklem", "pboc", "rba", "rbnz", "riksbank", "central bank",
    "interest rate", "rate decision", "rate hike", "rate cut",
]
KEYWORDS_POLITICS = [
    "trump", "biden", "harris", "putin", "zelensky", "xi jinping", "macron",
    "scholz", "merz", "starmer", "sunak", "netanyahu", "white house",
    "congress", "senate", "house of representatives", "election",
]
KEYWORDS_GEOPOLITICAL = [
    "iran", "israel", "russia", "ukraine", "china", "north korea", "taiwan",
    "syria", "gaza", "hamas", "hezbollah", "houthi", "missile", "ceasefire",
    "war ", "attack", "strike", "military", "nato", "un security council",
    "sanctions",
]
KEYWORDS_ENERGY = [
    "opec", "oil ", "crude", "brent", "wti", "natural gas", "lng", "barrel",
    "saudi aramco",
]


def classify(content: str, is_macro: bool) -> str:
    if is_macro:
        return "macro_release"
    text = content.lower()

    def hit(words):
        for w in words:
            if w.endswith(" "):
                if w in text:
                    return True
            elif re.search(r"\b" + re.escape(w) + r"\b", text):
                return True
        return False

    if hit(KEYWORDS_CB):
        return "central_bank"
    if hit(KEYWORDS_GEOPOLITICAL):
        return "geopolitical"
    if hit(KEYWORDS_POLITICS):
        return "politics"
    if hit(KEYWORDS_ENERGY):
        return "energy"
    return "other"


def to_utc_iso(ts: str) -> str:
    dt = datetime.fromisoformat(ts)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_message(msg: dict) -> dict:
    content = (msg.get("content") or "").strip()
    has_red = RED_DOT in content
    has_warn = WARNING in content
    is_breaking = bool(BREAKING_RE.search(content))
    is_macro = bool(MACRO_RE.search(content))
    is_url_only = bool(URL_ONLY_RE.match(content))
    category = classify(content, is_macro)
    is_gold = (has_red or is_breaking) and not is_macro
    return {
        "id": msg.get("id", ""),
        "timestamp_utc": to_utc_iso(msg["timestamp"]),
        "author": (msg.get("author") or {}).get("name", ""),
        "content": content,
        "has_red_dot": has_red,
        "has_warning": has_warn,
        "is_breaking": is_breaking,
        "is_macro": is_macro,
        "is_url_only": is_url_only,
        "category": category,
        "is_gold": is_gold,
    }


def print_summary(rows):
    c = Counter()
    for r in rows:
        for k in ("has_red_dot", "has_warning", "is_breaking", "is_macro", "is_url_only", "is_gold"):
            if r[k]:
                c[k] += 1
    cat = Counter(r["category"] for r in rows)
    print("\n=== Flag counts ===")
    for k in ("has_red_dot", "has_warning", "is_breaking", "is_macro", "is_url_only", "is_gold"):
        print(f"  {k:14s}: {c[k]}")
    print("\n=== Categories ===")
    for k, v in cat.most_common():
        print(f"  {k:16s}: {v}")
    gold = [r for r in rows if r["is_gold"]]
    if gold:
        print(f"\n=== First 5 gold events ===")
        for r in gold[:5]:
            preview = r["content"].splitlines()[0][:140]
            print(f"  [{r['timestamp_utc']}] ({r['category']}) {preview}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="DiscordChatExporter JSON file")
    p.add_argument("-o", "--output", required=True, help="Output CSV path")
    p.add_argument("--summary", action="store_true", help="Print summary stats")
    args = p.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    messages = data.get("messages", [])
    rows = [parse_message(m) for m in messages if (m.get("content") or "").strip()]

    if not rows:
        print("No non-empty messages found.", file=sys.stderr)
        sys.exit(1)

    fieldnames = list(rows[0].keys())
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {args.output}")
    if args.summary:
        print_summary(rows)


if __name__ == "__main__":
    main()
