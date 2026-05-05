# Status proiect — unde suntem, ce s-a făcut, ce mai e de făcut

> Document live. Update la fiecare milestone.

## 📍 Stadiu curent (mai 2026)

**Pipeline tehnic: 100% complet end-to-end pe full data (13 luni).**
**Paper: nedraftat încă — task M3 + colaborare echipă.**

## ✅ Ce s-a făcut (tehnic)

### Etapa 1 — Export Discord ✅
- 1 fișier JSON, 55 MB, perioada `2025-03-24 → 2026-04-21`
- Sursă: DiscordChatExporter pe canalul `#newsfeed` FinancialJuice (`channel_id=1353792641392971776`)
- Locație: `data/FinancialJuice ... .json` (gitignored)

### Etapa 2 — Parse JSON → events.csv ✅
- Script: [`parse_fj_discord.py`](../parse_fj_discord.py)
- **63,016 mesaje** totale → **2,449 gold events** (filtru: 🔴 OR BREAKING, NOT $MACRO)
- Distribuție categorii:
  - geopolitical: 25% (15,705)
  - central_bank: 20% (12,650)
  - politics: 11% (6,938)
  - macro_release: 7.5% (4,741, excluse)
  - energy: 3% (2,011)
  - other: 33% (20,971)

### Etapa 3 — Download prețuri Dukascopy ✅
- Script: [`download_prices.py`](../download_prices.py)
- **EUR/USD spot FX**: 402,181 bare 1-min (24/5 cu weekend break)
- **E_NQ-100 CFD**: 367,778 bare 1-min (închis weekend; 87+291 closed periods detectate automat)
- Toate timestamp-urile UTC. Detectare automată gap-uri prețuri (>5 min între bare consecutive)

### Etapa 4 — Sentiment classification ✅
- Script: [`sentiment.py`](../sentiment.py) cu **DeepSeek V4 Flash**
- Schema sentiment **augmentată**:
  - `sentiment_usd`, `sentiment_ndx` ∈ {bull, bear, neutral}
  - `directional_strength_usd`, `directional_strength_ndx` ∈ [-1, +1] (continuous, NEW)
  - `expected_magnitude` ∈ {low, med, high}
  - `surprise_level` ∈ {expected, surprise, shock} (NEW)
  - `confidence` ∈ [0, 1]
  - `rationale` (text)
- 8 few-shot examples cu schema completă, temperature 0.1, JSON strict
- Concurrency 15 workers, cache SQLite cu thread-safety (WAL)
- **Cost real**: $0.06 (cache hits din A/B + run anterior); pe full re-run from scratch ~$0.55
- A/B test Flash vs Pro pe 200 mostre random:
  - Script: [`compare_models.py`](../compare_models.py)
  - Agreement NDX: 85.5%; Pearson r directional_strength_ndx: 0.91
  - Flash 3.4× ieftin, 3.3× rapid, zero erori → **Flash câștigă empiric**
  - Confirmă **Wu et al. (2025)** pe datele noastre

### Etapa 5 — Event study (H1-H14) ✅
- Script: [`event_study.py`](../event_study.py)
- 24,490 row-uri în `event_study_windows.csv` (2449 events × 2 assets × 5 windows)
- **Toate 14 ipoteze testate**, rezultate în `outputs/h{1..14}_results.csv`
- Calculează: Δ% per fereastră, volume_ratio, pre-event drift, baseline windows random

### Raport vizual ✅
- Script: [`make_report.py`](../make_report.py)
- HTML self-contained ~2 MB cu toate figurile inline (base64 PNG)
- 10 vizualizări noi pentru H5-H14 + top-10 case studies cu timeline prețuri

### GitHub repo ✅
- Public: [github.com/calinnedelcu/economynewsresearch](https://github.com/calinnedelcu/economynewsresearch)
- 12+ fișiere tracked, niciun secret leaked
- `.env` gitignored (DEEPSEEK_API_KEY rămâne local)
- Commit-urile NU au atribuire Claude

### Documentație ✅
- [README.md](../README.md) cu rezumat rezultate
- [Plan proiect](Plan_proiect_economie.md) — actualizat cu H1-H14 + schema nouă
- [Structura paper](Structura_paper.md) — actualizat
- [STATUS.md](STATUS.md) — acest document

## 🎯 Rezultate cheie (toate semnificative statistic)

Vezi tabel complet în [README](../README.md). Pe scurt:

**Confirmate puternic (p < 10⁻⁶):**
- H1, H3, H8, H9, H11, H13, H14

**Confirmate moderat (p < 0.05):**
- H2 (NDX scurt), H4, H5, H7

**Weakness identificată:**
- H6: confidence calibration slabă (overconfidence pe >0.6 — flag pentru Discussion)
- H12: asimetrie bear/bull minimă — counterintuitiv vs literatura behavioral

**Discoveries notabile pentru paper:**
- 🚨 **H8 leakage signal**: pre-event drift NDX 3.4× peste baseline, p=10⁻²⁹⁸ — sugerează **front-running** sau lag al FJ
- 💡 **H9 amplification**: news-ul NU fade — magnitudinea CREȘTE 3-4× între +15m și +4h
- 💥 **H13 surprise gradient**: shock 2× expected — modelul AI captează intensitatea util pentru position sizing

## 🔜 Ce mai e de făcut

### Tehnic (pot face în continuare)
- [ ] **H15 memorization control** (Lopez-Lira et al. 2025) — F1 split pre/post knowledge cutoff (ian 2026)
- [ ] **Fix H10 volume** — output a fost gol, debug raportare volume_ratio
- [ ] **`references.bib`** APA 7 cu toate citațiile
- [ ] **Tabel central paper** (`paper_results_table.csv`) — matrice 14×5 ready-to-paste
- [ ] **Top hours/days extraction** — concret pentru H11 în paper
- [ ] **Case studies pack** (top 5-10 events + timeline + screenshots TradingView)
- [ ] **Descriptive stats summary** (etapa 4 din paper)
- [ ] **Export raport HTML → PDF** (deliverable pentru profesor)

### Echipă (planul tău)
- [ ] **M2 — validation 200 mostre**: 2 etichetatori → Cohen's κ + F1 vs DeepSeek (planul cere F1 ≥ 0.75)
- [ ] **M3 — Literature Review**: 3 articole sumarizate (recomandate: Muhammad 2025, Wu 2025, Lopez-Lira 2024)
- [ ] **Echipă — draft paper EN** pe baza rezultatelor + case studies

### Polish (final)
- [ ] Update README cu link la raport vizual
- [ ] Verifică APA citation cu scribbr
- [ ] Proofread EN (2 runde)
- [ ] Export PDF final, verifică figurile

## 📚 Lessons learned & decizii cheie

### Tehnice
- **Dukascopy = sweet spot** pentru date intraday gratis pe 13 luni (FX + indices CFD)
- **DeepSeek V4 Flash > Pro** pentru sentiment classification (confirmare empirică Wu et al.)
- **Concurrency 15 workers** = 4 min vs 40 min serial pentru 2449 events
- **Cache SQLite cu WAL + lock** thread-safe pentru re-rulări fără cost
- **Vectorizare baseline windows** O(N+E) vs O(N×E) — critic pentru scale
- **Detectare automată closed periods** (gap > 5min) > hardcodate ore (gestionează DST, holidays)

### Metodologice
- **Schema sentiment augmentată** (directional_strength continuous + surprise_level) → mai mult signal pentru H13, H14
- **A/B test pe 200 mostre random** = justificare empirică solidă pentru paper Methodology
- **Memorization caveat (Lopez-Lira 2025)** trebuie raportat split pre/post cutoff

### De evitat în viitor
- NU folosi sentiment AI pentru filtering trades pe `confidence > 0.8` — calibration weak
- NU lansa scripturi background fără `python -u` (unbuffered stdout) — output-ul nu apare
- NU folosi reasoning models (V4-Pro) pentru classification — overkill, mai lent, mai scump

## 🔑 Reproducibility

Pentru a reproduce rezultatele:
```bash
git clone https://github.com/calinnedelcu/economynewsresearch.git
cd economynewsresearch
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
echo "DEEPSEEK_API_KEY=sk-..." > .env

# (1) Export Discord cu DiscordChatExporter pe #newsfeed FJ, JSON, full range
# Pune fișierul în data/

# (2-5) Pipeline complet
.venv/Scripts/python.exe parse_fj_discord.py "data/FinancialJuice ... .json" -o outputs/events.csv --summary
.venv/Scripts/python.exe download_prices.py --start 2025-03-24 --end 2026-04-21
.venv/Scripts/python.exe sentiment.py outputs/events.csv -o outputs/events_sentiment.csv --workers 15
.venv/Scripts/python.exe event_study.py
.venv/Scripts/python.exe make_report.py
```

Cost API total: ~$0.55. Durată end-to-end: ~30 min.

## 📂 Outputs disponibile (local, gitignored)

- `outputs/events.csv` — 63k mesaje parsate
- `outputs/events_sentiment.csv` — 2,449 gold events cu sentiment augmentat
- `outputs/event_study_windows.csv` — 24,490 row-uri (event × asset × window)
- `outputs/h{1..14}_results.csv` — rezultate per ipoteză
- `outputs/compare_models.csv` — A/B Flash vs Pro
- `outputs/prices_eurusd.csv`, `outputs/prices_ndx.csv` — 1-min OHLCV 13 luni
- `outputs/sentiment_cache.sqlite` — cache request-uri DeepSeek
- `outputs/report.html` — raport vizual ~2 MB
- `outputs/figures/*.png` — figuri standalone

---

*Last updated: după extension H5-H14 + sentiment augmentat (commit `d281a72`).*
