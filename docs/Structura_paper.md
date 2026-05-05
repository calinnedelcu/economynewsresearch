# Structura research paper — plan detaliat

**Document intern pentru echipă · EN · 8–12 pagini · APA 7**

> Sursă originală: [Structura_paper.docx](Structura_paper.docx)

## Overview general

- **Lungime:** 8–12 pagini body (fără referințe + anexă).
- **Format:** A4, margini 2.5 cm, Times New Roman 12pt, spațiere 1.5, align justify.
- **Citări:** APA 7 în text "(Autor, An)" și listă References la final.

| # | Secțiune | Pagini | Citări | Conține figuri/tabele |
|---|---|---|---|---|
| — | Title page | 0.5 | 0 | — |
| — | Abstract | 0.5 | 0 | — |
| 1 | Introduction | 1.0–1.5 | 3–5 | — |
| 2 | Literature Review | 1.0–1.5 | 6–10 | 1 tabel sintetic opțional |
| 3 | Data & Methodology | 1.5–2.0 | 3–5 | 1 diagramă pipeline + 1 tabel surse |
| 4 | Descriptive Statistics | 0.75–1.0 | 0–1 | 1 tabel distribuție + 1 histogramă |
| 5 | Results | 2.0–2.5 | 1–2 | 1 tabel central + 4–5 grafice case study |
| 6 | Discussion | 0.75–1.0 | 3–5 | — |
| 7 | Conclusions | 0.5 | 0–1 | — |
| — | References | 0.5–1.0 | — | — |
| — | Appendix (opt.) | +1.0 | — | prompt LLM, formule, link GitHub |

## Title page

Pagină separată. Conține:

- **Titlu:** "The Impact of Unexpected Online News and Public Messages on Short-Term Exchange Rate and Equity Index Prices: An Event-Study Analysis of EUR/USD and Nasdaq (2025–2026)"
- Numele celor 3 autori + clasă + liceu
- Numele profesorului coordonator
- Data: lună + an
- Opțional: Keywords (5-6 termeni, pentru indexare)

## Abstract

**Lungime:** 200 cuvinte, 7 propoziții, exact structura din notițele inițiale:

1. **Propoziția 1** — ideea lucrării (tema + motivație scurtă)
2. **Propoziția 2–3** — obiectivul principal (ce testăm, pe ce piețe, în ce perioadă)
3. **Propoziția 4** — metoda de cercetare (event study + sentiment analysis cu LLM)
4. **Propoziția 5** — datele (Discord FJ, Dukascopy, N evenimente)
5. **Propoziția 6–7** — principalele rezultate obținute (H1/H2/H3 confirmate sau nu, numeric)

Scris la final, după ce rezultatele sunt gata. Unpersonal ("the study examines..."), timpul trecut pentru ce s-a făcut, prezent pentru ce înseamnă.

## 1. Introduction

**Scop:** setează context, definește termenii cheie, anunță obiectivele și cele 3 ipoteze.

### Structură pe paragrafe (5 paragrafe):

- **§1 Hook + context:** deschide cu un exemplu concret viu (ex: "On April 2, 2025, a single Truth Social post about tariffs moved EUR/USD by 80 pips in under 5 minutes"). Stabilește de ce contează tema.
- **§2 Problema de cercetare:** diferența dintre date macro programate și știri neașteptate; gap-ul din literatură (mai puțină atenție pe știri neprogramate intraday).
- **§3 Definire termeni:** event study, sentiment analysis, abnormal return, intraday — câte o propoziție definitorie pentru fiecare.
- **§4 Obiective:** enunță cele 3 ipoteze H1/H2/H3 explicit, numerotate.
- **§5 Roadmap:** "The remainder of the paper is organized as follows: Section 2 reviews... Section 3 describes... etc."

**Citări tipice:** 3–5, amestec între clasici (Fama 1970 despre efficient markets) și recenți (2018+ pe event study cu social media).

## 2. Literature Review

**Scop:** arată că îți cunoști domeniul; poziționează contribuția ta față de ce s-a făcut deja.

### Structură pe subsecțiuni (3 sub-secțiuni):

#### 2.1 News and high-frequency market reactions
2-3 articole clasice (Andersen, Bollerslev, Neely) care au demonstrat că știrile macroprogramate mișcă FX intraday.

#### 2.2 Sentiment analysis in finance
2-3 articole recente. Candidați actualizați (verificat 2025/2026):
- **Muhammad et al. (2025)** — Benchmarking LLMs for Target-Based Financial Sentiment Analysis (CLiC-it 2025)
- **Wu et al. (2025)** — "Reasoning or Overthinking" pe sentiment financiar (arXiv:2506.04574)
- **Teles & Figueiredo (2025)** — Comparing LLMs for Sentiment Analysis in Financial Market News (arXiv:2510.15929)
- **FinBERT (Araci, 2019)** ca clasic transformer pentru finance

#### 2.3 Social media and asset prices
2-3 articole specifice pe tweets/social posts:
- **Ranco et al. (2015)** — Twitter sentiment & stock returns
- **Ge, Kurov, Wolfe (2019)** — Trump tweets pe stocks
- **Lopez-Lira & Tang (2024)** — ChatGPT forecast stock movements (arXiv:2304.07619)
- **Du et al. (2025)** — Event-Aware Sentiment Factors from LLM-Augmented Financial Tweets (arXiv:2508.07408)

Încheie cu un paragraf de poziționare: "To our knowledge, no prior work combines... Our contribution is..."

**Stil de citare:** "Smith (2020) found that...", sau "Studies have shown that news events drive intraday volatility (Smith, 2020; Jones, 2021)."

## 3. Data & Methodology

**Scop:** reproductibilitate. Cineva care citește ar trebui să poată replica studiul.

### 3.1 Data sources
- **Știri:** Discord FinancialJuice official, canal #newsfeed, extracție cu DiscordChatExporter. Intervalul exact: 2025-03-24 → 2026-04-21.
- **Prețuri EUR/USD:** Dukascopy Historical Data Feed, agregat la 1 minut OHLCV.
- **Prețuri Nasdaq-100:** Dukascopy E_NQ-100 CFD, 1 minut OHLCV.
- **Toate timpurile convertite la UTC.**

**Tabel 1:** surse de date (din planul intern, reutilizat).

### 3.2 Event identification
Filtrul aplicat: mesaje FJ marcate cu 🔴 (market-moving alert), excluzând tag-ul `$MACRO` (date programate). Rezultat: N = ~1000 evenimente neașteptate (gold). Categorizare automată: `geopolitical / politics / central_bank / energy / corporate / other`, prin regex pe keyword-uri.

### 3.3 Sentiment classification
Fiecare eveniment procesat prin **DeepSeek V4 Flash** API, zero-shot cu 8 exemple few-shot. Output JSON augmentat:
- `sentiment_usd`, `sentiment_ndx` ∈ {bull, bear, neutral} — direcție discretă
- `directional_strength_usd`, `directional_strength_ndx` ∈ [-1, +1] — intensitate continuă
- `expected_magnitude` ∈ {low, med, high} — magnitudine predicted
- `surprise_level` ∈ {expected, surprise, shock} — cât de neașteptată e știrea
- `confidence` ∈ [0, 1] — încredere model
- `rationale` (text scurt)

**Justificare model:** Muhammad et al. (2025) demonstrează că DeepSeek family ranks among top performers pentru TBFSA. Wu et al. (2025) arată că reasoning models nu îmbunătățesc sentiment classification → folosim Flash variant. Open weights asigură reproducibility.

**Validare:** 200 evenimente etichetate manual, Cohen's kappa între 2 etichetatori, F1 LLM vs consens uman. Pre/post-cutoff F1 split (per Lopez-Lira et al. 2025) pentru a controla memorization.

### 3.4 Event study framework
Pentru fiecare eveniment t:
- `r_t(Δ) = (P_{t+Δ} - P_t) / P_t` — returnul în fereastra Δ ∈ {1m, 5m, 15m, 1h, 4h}
- `volume_ratio_t(Δ) = V_{t..t+Δ} / V_baseline(Δ)` — raport de volum vs baseline (medie pe 30 zile)
- `abnormal_return_t(Δ) = r_t(Δ) − E[r(Δ)]` — unde E[r(Δ)] se estimează pe ferestre random din zile fără evenimente

Detectare automată a perioadelor de piață închisă: gap-uri > 5 min între bare consecutive în feed-ul Dukascopy (gestionează DST, weekend, holidays).

### 3.5 Hypothesis tests (14 ipoteze)

**Ipoteze principale (event study core):**
- **H1:** Mann-Whitney U + t-test pe |Δ%| events vs random baseline windows (one-sided greater).
- **H2:** 3×3 matrice confuzie (sentiment × direcție observată), binomial test one-sided pentru rejection of chance (50%).
- **H3:** OLS `|Δ%| ~ sentiment + trend_zi + sentiment×trend_zi`. Test β₃ (interacțiune).
- **H4:** OLS `gap_pct ~ aggregate_sentiment` pe closed periods (auto-detectate prin gap-uri >5min în feed-ul de prețuri).

**Ipoteze suplimentare (model & market structure):**
- **H5:** ANOVA `|Δ%| ~ expected_magnitude` (validează model-ul de magnitude).
- **H6:** Reliability diagram + Brier score pentru calibrarea `confidence`.
- **H7:** ANOVA `|Δ%| ~ category`; identifică categorii dominante.
- **H8:** Pre-event drift `|Δ%[-15m,0]|` events vs random baseline (information leakage test).
- **H9:** Sign agreement |Δ%[+15m]| vs |Δ%[+4h]| (persistență vs decay).
- **H10:** Wilcoxon signed-rank pe `volume_ratio` events vs 1 (one-sided greater).
- **H11:** ANOVA pe `hour_utc` + `day_of_week` (time-of-day effects).
- **H12:** `|Δ%|_bear` vs `|Δ%|_bull` (asimetrie / loss aversion).
- **H13:** ANOVA `|Δ%| ~ surprise_level` (folosește câmp nou de sentiment).
- **H14:** Pearson + Spearman correlation NDX × EUR/USD (cross-asset spillover).

**Methodology control (Lopez-Lira, Tang & Zhu, 2025):** raportăm F1-score split pe pre/post knowledge cutoff (ian 2026) pentru a controla memorization risk.

**Robustness:** A/B comparison Flash vs Pro pe 200 mostre; raportăm agreement rate + Pearson r pe directional_strength + Brier score per model. Justificare empirică pentru alegerea Flash (per Wu et al., 2025).

**Figura 1:** diagramă bloc a pipeline-ului (Discord → parser → sentiment → event study → teste).

## 4. Descriptive Statistics

**Scop:** "înainte să trecem la teste, iată cum arată datele".

- Număr total evenimente extrase, număr după filtre, distribuție pe categorii (tabel).
- Histogramă: distribuția evenimentelor pe ore/zile săptămânii.
- Validare sentiment: F1 LLM vs manual, per categorie, inter-rater kappa între etichetatori umani.
- Statistici de preț: volatilitate medie EUR/USD / Nasdaq în perioada studiată.

**Tabel 2:** descriptive stats.
**Figura 2:** distribuția evenimentelor pe categorii și timp.

## 5. Results

**Scop:** secțiunea centrală. Răspunde la fiecare ipoteză cu numere + vizualizare.

### 5.1 H1 — do unexpected events move the market?
Tabelul principal cu |abnormal_return| mediu per fereastră × per categorie × per activ, plus p-values. Interpretare scurtă: "we reject H0 for [categories] at the 1% level."

### 5.2 H2 — does sentiment predict direction?
Matrice confuzie 3×3 pentru `sentiment_usd × direcție EUR/USD` în fereastra 15min. Accuracy globală + per categorie. Benchmark 50% random (excluzând neutral). Binomial p-value.

### 5.3 H3 — does daily trend moderate?
Output regresie: tabel cu coeficienți β₀..β₃, SE, t-stat, p-value, R². Plot scatter `|Δ%| vs sentiment`, colorat pe trendul zilei.

### 5.4 H4 — closed-period gap regression
Output regresie pentru weekend FX gaps + overnight NDX gaps. Aggregate sentiment (confidence-weighted) → gap_pct.

### 5.5 Case studies (4–5 zoom-ins)
Pentru fiecare caz: 1 paragraf naratic + 1 screenshot TradingView (timeline-ul știrii pe grafic) + 1 tabel mic cu numerele din fereastră. Candidați:
- Trump tweet tarife 2 aprilie 2025 — mișcare mare EUR/USD
- Escaladare Iran-SUA aprilie 2026 — spike Nasdaq
- Un caz de "fals pozitiv" — AI a prezis mișcare, n-a fost
- Un caz unde trendul zilei a dominat
- O declarație Fed surpriză (ex: un discurs Powell non-programat)

## 6. Discussion

**Scop:** interpretare economică, nu doar "rezultatul a fost X". De ce? Ce înseamnă?

- **§1 — Principalele rezultate rezumate:** legați H1/H2/H3/H4 de o narațiune coerentă.
- **§2 — Comparație cu literatura:** "consistent with Smith (2020) who found...", sau "contrasts with Jones (2021), possibly because..."
- **§3 — Implicații:** pentru traderi (cât de repede trebuie să reacționezi), pentru economiști (cât de eficientă e piața pe termen foarte scurt).
- **§4 — Limitări:** perioadă limitată (13 luni), două active doar, AI de sentiment imperfect, posibile biasuri de selecție, nu distingem știri suprapuse, memorization risk în model (Lopez-Lira et al. 2025).

## 7. Conclusions

**Scop:** închidere. Scurt.

- **§1 — Ce am făcut:** 1-2 propoziții care reamintesc metoda și scopul.
- **§2 — Ce am găsit:** răspuns direct la H1, H2, H3, H4 în ordine. O propoziție per ipoteză.
- **§3 — Direcții viitoare:** perioadă mai lungă, mai multe active, modele predictive, date order book.

## References

**Stil:** APA 7. Ordonate alfabetic după primul autor. Hanging indent 1.27 cm.

**Template articol de revistă:**
```
Autor, A. A., & Autor, B. B. (Anul). Titlul articolului în minuscule (doar prima literă + cele după ':'). Numele Revistei cu Fiecare Cuvânt Capitalizat, Volum(număr), paginile. https://doi.org/xxx
```

**Exemplu:**
```
Ge, Q., Kurov, A., & Wolfe, M. H. (2019). Stock market reactions to presidential statements: Evidence from company-specific tweets. Journal of Corporate Finance, 58, 125–148. https://doi.org/10.1016/j.jcorpfin.2019.04.009
```

**Citare în text:** "(Ge, Kurov, & Wolfe, 2019)" prima dată, apoi "(Ge et al., 2019)". Dacă autorul e în propoziție: "Ge et al. (2019) showed that...".

**Website / raport:**
```
Autor / Instituție. (Anul, lună ziua). Titlul. URL
```

## Convenții de scriere

- **Timp verbal:** past pentru ce ai făcut tu ("we collected", "the model classified"). Present pentru ce spun datele sau literatura ("the data show", "Smith argues").
- **Voce:** mai degrabă activă ("we test...") decât pasivă, dar acceptabil pasiv când subiectul contează mai puțin ("the sample was split into...").
- **Persoană:** "we" e acceptat în economie modernă. Alternativ: third-person ("this study", "the authors").
- **Numere:** în propoziții scrie în litere până la 9, cifre de la 10 încolo. În tabele/rezultate: întotdeauna cifre. p-values: dacă e sub 0.001 scrie "p < 0.001", altfel 3 zecimale.
- **Abrevieri:** expandează la prima apariție: "Foreign Exchange (FX) market".
- **Figuri și tabele:** toate numerotate și cu caption. Referite în text: "as shown in Figure 2...".
- **Cuvinte interzise:** "prove", "always", "never", "huge", "amazing" — prea absolute pentru știință. Înlocuiește cu "suggest", "typically", "substantial".
- **Lungime propoziții:** max 25 cuvinte. Dacă depășești, sparge în două.

## Checklist înainte de predare

- [ ] Fiecare ipoteză are răspuns numeric + interpretare
- [ ] Fiecare număr din paper poate fi reprodus din `events_with_metrics.csv`
- [ ] Fiecare citare din text apare în References și invers
- [ ] Toate figurile au captions + referite în text
- [ ] Abstract-ul respectă cele 7 propoziții
- [ ] Cuvinte total: 3000–5000 (fără references + appendix)
- [ ] Proofread EN minim 2 runde, pe 2 persoane diferite
- [ ] Grammarly sau LanguageTool pass
- [ ] APA 7 verificat cu scribbr.com/apa-citation-generator
- [ ] PDF export, verificat că figurile nu-s tăiate
