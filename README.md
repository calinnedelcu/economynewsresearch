# Studiu știri online vs prețuri (EUR/USD + Nasdaq-100)

Plan complet în `Plan_proiect_economie.docx`. Perioada: 24 mar 2025 → 21 apr 2026, intraday.

## Structură

```
parse_fj_discord.py     # etapa 2: JSON Discord → events.csv
data/                   # JSON-uri Discord (gitignored)
outputs/                # events.csv, prices_*.csv, rezultate (gitignored)
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
