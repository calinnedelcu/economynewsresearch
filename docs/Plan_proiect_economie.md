# Plan proiect — știri online vs. prețuri

**EUR/USD + Nasdaq-100 · 24 mar 2025 – 21 apr 2026 · intraday (min–ore)**

> Sursă originală: [Plan_proiect_economie.docx](Plan_proiect_economie.docx)

## Scope

- **Active:** EUR/USD (FX) + Nasdaq-100 (NQ futures sau QQQ ETF)
- **Perioadă:** 24 mar 2025 → prezent (limitat de istoricul Discord FJ)
- **Orizont:** intraday — ferestre [0, +1m], [0, +5m], [0, +15m], [0, +1h], [0, +4h]
- **Evenimente incluse:** tweets Trump, breaking geopolitic, declarații Fed/BCE surpriză, alte mesaje publice neașteptate
- **Evenimente EXCLUSE:** date macro programate (`$MACRO` + pattern ACTUAL/FORECAST) — sunt în calendarul economic

## Ce testăm (14 ipoteze)

### Ipoteze principale (H1-H4)

**H1** — Evenimentele neașteptate produc mișcări semnificative statistic peste volatilitatea normală.
*Test:* t-test + Mann-Whitney U pe |Δ%| events vs random baseline windows.

**H2** — Direcția sentimentului se corelează cu direcția prețului peste nivelul de hazard (>50%).
*Test:* matrice confuzie 3×3 + test binomial.

**H3** — Trendul zilei moderează impactul știrii (interacțiune sentiment × trend).
*Test:* OLS `|Δ%| = β₀ + β₁·sentiment + β₂·trend_zi + β₃·(sentiment × trend_zi) + ε`; testăm β₃.

**H4** — Sentimentul agregat al știrilor în perioadele de piață închisă prezice direcția gap-ului de redeschidere.
*Test:* OLS `gap_pct ~ aggregate_sentiment` per-asset (weekend FX + overnight NDX).

### Ipoteze suplimentare (H5-H14)

**H5** — `expected_magnitude` (low/med/high) corelează cu |Δ%| realizat.
*Test:* ANOVA + post-hoc Tukey.

**H6** — Modelul are confidence calibrat (probabilitatea spusă coincide cu hit rate observat).
*Test:* Brier score + reliability diagram (buckets de confidence).

**H7** — Categoriile diferite produc magnitudini diferite.
*Test:* ANOVA `|Δ%| ~ category` + per-category mean ranking.

**H8** — Pre-event drift / market efficiency: există mișcare anticipativă (information leakage)?
*Test:* `|Δ%[-15m, 0]|` events vs random baseline (paired t-test + MWU).

**H9** — News impact persistă vs decade — half-life analysis.
*Test:* sign agreement între ferestre +15m și +4h, ratio magnitudine.

**H10** — Volume reaction la events (volume_ratio events vs baseline).
*Test:* Wilcoxon signed-rank vs ratio=1 (one-sided greater).

**H11** — Time-of-day moderează impactul.
*Test:* ANOVA pe `hour_utc` + `day_of_week`.

**H12** — Asimetrie bear vs bull (loss aversion / fear premium).
*Test:* `|Δ%|_bear` vs `|Δ%|_bull` (t-test + MWU one-sided).

**H13** — `surprise_level` (expected/surprise/shock) corelează cu magnitudinea.
*Test:* ANOVA `|Δ%| ~ surprise_level`.

**H14** — Cross-asset spillover NDX × EUR/USD.
*Test:* per-event Pearson + Spearman correlation; sign-match rate (binomial test).

**Methodology control (Lopez-Lira et al. 2025):** F1 split pre-cutoff (înainte ian 2026) vs post-cutoff. Raportat în Methodology pentru a controla memorization risk.

## Surse de date

| Ce | De unde | Cum | Cost |
|---|---|---|---|
| Știri | Discord FJ oficial, canal #newsfeed | DiscordChatExporter → JSON | 0 |
| Trump (backup) | trumpstruth.org | scrape HTML Python | 0 |
| EUR/USD | Dukascopy Historical Feed | dukascopy-python → CSV 1min | 0 |
| Nasdaq-100 | **Dukascopy E_NQ-100 CFD** (decis ulterior) | dukascopy-python → CSV 1min | 0 |
| Screenshots case studies | TradingView Pro (contul tău) | manual PNG | deja plătit |

## Pipeline (5 etape)

### 1. Export Discord
- Rulează DiscordChatExporter GUI (deja instalat)
- Canal: `#newsfeed` oficial FinancialJuice
- Format: JSON · After: `2025-03-24` · Before: gol
- Export → fișier ~50-150 MB

### 2. Parsare JSON
```bash
python parse_fj_discord.py export.json -o events.csv --summary
```
- Output: `events.csv` cu ~60k rânduri, flag-uri `is_red_alert` / `is_breaking` / `is_scheduled_macro` / `category`
- Filtru pentru event study: `is_red_alert=True AND is_scheduled_macro=False` → ~4000 evenimente gold

### 3. Descărcare prețuri
- EUR/USD: script Python cu `dukascopy-python`, range `2025-03-24 → azi`, resample la 1min OHLCV
- Nasdaq-100: dukascopy `E_NQ-100` CFD, 1min OHLCV
- Output: `prices_eurusd.csv`, `prices_ndx.csv` — timestamp UTC, OHLCV
- Validare: pentru 3 evenimente cunoscute, verificăm că spike-ul e vizibil în CSV față de TradingView

### 4. Sentiment cu LLM API
- Script Python cu OpenAI SDK (DeepSeek-compatible); model `deepseek-v4-flash`
- Prompt: rol analist FX + definiții clase + 8 exemple few-shot + output JSON strict
- Per eveniment (schemă extinsă):
  - `sentiment_usd`, `sentiment_ndx` ∈ {bull, bear, neutral}
  - `directional_strength_usd`, `directional_strength_ndx` ∈ [-1, +1] (continuous, captures intensitate)
  - `expected_magnitude` ∈ {low, med, high}
  - `surprise_level` ∈ {expected, surprise, shock}
  - `confidence` ∈ [0, 1]
  - `rationale` (text)
- Caching local SQLite pe hash(text+system+model) pentru rerulare ieftină
- **Cost estimat: ~$0.20 pentru toate ~1000 evenimentele gold**
- Validare: 200 evenimente etichetate manual de 2 membri → calcul F1 vs LLM; accept dacă F1 ≥ 0.75

### 5. Event study + teste
- Script Python cu pandas: pentru fiecare eveniment calculează Δ% și volum ratio în ferestrele definite, pe ambele active
- Baseline: 30 zile anterioare, ferestre random de aceeași lungime pentru distribuția nulă
- Detectare automată closed periods (gap > 5min între bare consecutive)
- Rulează testele H1 (t-test), H2 (matrice confuzie + binomial), H3 (regresie statsmodels cu interacțiune), H4 (gap regression)
- Output: `rezultate.csv` + `figures/*.png` (distribuții, scatter, bar charts)

## Stack tehnic

| Etapă | Librării |
|---|---|
| Extragere | DiscordChatExporter GUI |
| Parsare | python3 stdlib (json, csv, re, argparse) |
| Prețuri | dukascopy-python |
| Sentiment | openai SDK + DeepSeek V4 Flash |
| Analiză | pandas, numpy, scipy.stats, statsmodels |
| Grafice | matplotlib + screenshots TradingView Pro pentru case studies |
| Repo | Git + GitHub public, requirements.txt, README cu comenzi de rulare |

## Model AI pentru sentiment

**Principal:** DeepSeek V4 Flash zero-shot. Nu antrenăm nimic de la zero — doar prompt + few-shot.

**Justificare academică (pentru paper Methodology):**
- Muhammad et al. (2025) — DeepSeek-R1 ranks among top performers on Target-Based Financial Sentiment Analysis
- Wu et al. (2025) — reasoning models nu îmbunătățesc sentiment financiar → folosim Flash, nu Pro
- Open weights → reproducibility academic

**De ce nu training:** 200 exemple manual nu ajung pentru fine-tuning robust; LLM zero-shot deja bate modele fine-tuned pe date puține; complexitate în plus fără beneficiu.

**Validare:** 200 mostre etichetate manual de 2 membri (inter-rater: Cohen's kappa). Calculăm F1 vs LLM. Dacă F1 < 0.75 pe o categorie, rafinăm promptul.

**Baseline opțional:** FinBERT (ProsusAI/finbert de pe Hugging Face) rulat pe 1000 evenimente pentru comparație în discuție. Se face dacă timpul permite.

## Echipa (3 persoane)

| Membru | Ce face | Etape |
|---|---|---|
| **M1 — Data eng** | Export Discord, parser, prețuri, aliniere timezone, setup Git repo | Etapele 1, 2, 3 |
| **M2 — Analyst** | Prompt LLM + rulare sentiment, validare manuală, calcule event study, testare H1/H2/H3/H4 | Etapele 4, 5 |
| **M3 — Writer** | Review literatură (3 articole), draft paper EN, case studies + screenshots TV, bibliografie APA | Paralel cu 1-5 |

## Timeline (8 săpt)

| Săpt | Milestone | De făcut |
|---|---|---|
| 1 | Plan aprobat intern + export Discord full | Citirea documentului ăsta + ok. Rulare DiscordChatExporter pe tot 2025-03-24 → azi. Setup GitHub repo. |
| 2 | events.csv + prețuri descărcate | Parser rulat pe exportul complet. Script Python download EUR/USD + NDX Dukascopy. |
| 3 | Literatură citită (3 articole) | Căutare Google Scholar, selectare + citire + notițe. Draft secțiune „Literature Review". În paralel: prompt LLM v1. |
| 4 | Sentiment rulat + validat | Rulare DeepSeek API pe toate evenimentele gold. Etichetare manuală 200 mostre. Calcul F1 + rafinare prompt. |
| 5 | Event study complet | Calcul Δ%, volum ratio, abnormal returns pentru toate evenimentele × toate ferestrele × ambele active. |
| 6 | Rezultate H1/H2/H3/H4 | Rulare teste statistice. Generare grafice. Interpretare echipă. |
| 7 | Draft paper complet | Redactare toate secțiunile EN. Selectare 4-5 case studies + screenshots TV. Integrare figuri. |
| 8 | Final | Peer-review intern 3×. Fact-check numere. Proofread EN. Verificare APA. Export PDF. Predare. |

## Riscuri + plan B

| Risc | Plan B |
|---|---|
| Discord invalidează tokenul în timpul exportului | Re-obținem token nou, reluăm de unde s-a oprit (DCE suportă date range). |
| Rate limits Alpha Vantage pe Nasdaq | Folosim Dukascopy E_NQ-100 CFD în loc (decis: am ales Dukascopy pentru ambele). |
| LLM API cost depășește bugetul | Caching pe hash; DeepSeek V4 Flash e ~$0.20 total — mult sub buget. |
| Aliniere timezone greșită | Validare vizuală pe 10 evenimente cunoscute (NFP, CPI) — verificăm vs grafic TradingView. |
| Toate 4 ipotezele sunt respinse | Rezultat null este valid — paper spune onest de ce (piețe prea eficiente, sentiment greu de captat, etc). |

## Next steps imediate

- M1 rulează exportul complet Discord (`2025-03-24 → azi`). ~30 min.
- M2 pregătește prompt LLM v1 cu 8 exemple din pilot-ul deja extras.
- M3 caută pe Google Scholar 3 articole candidate pt literatură (keywords în doc).
- Toți 3 setup GitHub repo + invitare reciprocă.
- Sync următor: final săpt 1.
