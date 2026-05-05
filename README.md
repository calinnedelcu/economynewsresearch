# Studiu știri online vs prețuri (EUR/USD + Nasdaq-100)

Plan complet în `Plan_proiect_economie.docx`. Perioada: 24 mar 2025 → 21 apr 2026, intraday.

## Structură

```
parse_fj_discord.py     # etapa 2: JSON Discord → events.csv
download_prices.py      # etapa 3: Dukascopy → prices_eurusd.csv, prices_ndx.csv
sentiment.py            # etapa 4: DeepSeek V4 Flash → events_sentiment.csv
event_study.py          # etapa 5: H1/H2/H3/H4 tests → results CSVs + figures
data/                   # JSON-uri Discord (gitignored)
outputs/                # CSV-uri, cache, figures (gitignored)
```

## Setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # Linux/Mac
```

## Cum rulezi

### Etapa 2 — parse export Discord
```bash
python parse_fj_discord.py "data/FinancialJuice ... .json" -o outputs/events.csv --summary
```

Coloane în `events.csv`:

| coloană | ce e |
|---|---|
| `id` | Discord message ID |
| `timestamp_utc` | UTC ISO-8601 |
| `author` | nume autor |
| `content` | text complet |
| `has_red_dot` | conține 🔴 |
| `has_warning` | conține ⚠ |
| `is_breaking` | conține "BREAKING" |
| `is_macro` | conține `$MACRO` (date programate) |
| `is_url_only` | doar URL în mesaj |
| `category` | macro_release / central_bank / geopolitical / politics / energy / other |
| `is_gold` | `(has_red_dot OR is_breaking) AND NOT is_macro` — filtru pentru event study |

### Etapa 3 — download prețuri (Dukascopy)
```bash
.venv/Scripts/python.exe download_prices.py --start 2026-04-15 --end 2026-04-21
```

Scrie `outputs/prices_eurusd.csv` și `outputs/prices_ndx.csv` cu OHLCV 1-minut.

Instrumentele Dukascopy folosite:
- **EUR/USD** spot FX (24/5, weekend break vineri seara)
- **E_NQ-100** CFD index (închis weekend; corespunde futures NQ)

Note timezone: toate timestamp-urile sunt **UTC** la sursă, fără conversie locală.

### Etapa 4 — sentiment classification (DeepSeek V4 Flash)

Necesită cheie API DeepSeek în `.env`:
```
DEEPSEEK_API_KEY=sk-...
```

Rulare:
```bash
.venv/Scripts/python.exe sentiment.py outputs/events.csv -o outputs/events_sentiment.csv
```

Adaugă la fiecare eveniment:
- `sentiment_usd`, `sentiment_ndx` ∈ {bull, bear, neutral}
- `expected_magnitude` ∈ {low, med, high}
- `confidence` ∈ [0, 1]
- `rationale` — propoziție scurtă

Cache local SQLite (`outputs/sentiment_cache.sqlite`) — re-rularea pe aceleași evenimente nu re-cheltuiește credit API.

**Justificare model** (pentru paper Methodology):
- Muhammad et al. (2025) — DeepSeek-R1 ranks among top performers on Target-Based Financial Sentiment Analysis
- Wu et al. (2025) — reasoning models nu îmbunătățesc sentiment financiar → folosim Flash, nu Pro
- Open weights → reproducibility academic
- Cost ~$0.20 pentru 1000 events vs $20+ pentru frontier closed-source

### Etapa 5 — event study + teste statistice
```bash
.venv/Scripts/python.exe event_study.py
```

Rulează 4 ipoteze pe ferestrele [0,+1m], [0,+5m], [0,+15m], [0,+1h], [0,+4h]:

- **H1**: |Δ%| events vs distribuție null random (t-test + Mann-Whitney U)
- **H2**: sentiment-direction agreement (matrice confuzie + binomial test)
- **H3**: regresie OLS `|Δ%| ~ sentiment + trend + sentiment×trend`
- **H4**: gap regression pe closed-periods (weekend FX, overnight NDX) cu sentiment agregat

Output:
- `outputs/event_study_windows.csv` — un rând per event × asset × fereastră
- `outputs/h1_results.csv`, `h2_results.csv`, `h3_results.csv`, `h4_results.csv`
- `outputs/figures/*.png`

Detecție automată closed periods (gap-uri > 5 min între bare consecutive în prețuri) — funcționează indiferent de DST, holidays, schedule changes.
