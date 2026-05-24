# Structura research paper

Document de lucru pentru varianta finala a paper-ului. Aceasta versiune reflecta metodologia corectata din `event_study.py`.

## Titlu propus

**Unexpected Online Financial News and Intraday Market Reactions: An Event-Study of EUR/USD and Nasdaq-100 Prices**

## Abstract

Scris la final, 180-220 cuvinte.

Include explicit:

- sursa stirilor: FinancialJuice Discord newsfeed;
- perioada stirilor si perioada comuna folosita cu preturile;
- active: EUR/USD si Nasdaq-100 CFD;
- metoda: event-study intraday + sentiment LLM;
- corectia importanta: `sentiment_usd` testat contra proxy USD `-EUR/USD`;
- rezultat central: miscari anormale de magnitudine/range/max-move peste baseline;
- rezultat secundar: edge directional modest, nu predictor puternic.

## 1. Introduction

Paragrafe recomandate:

1. Context: stirile online ajung in piete in timp real, dar feed-urile retail/profesionale pot avea latenta fata de sursa primara.
2. Research gap: multe studii analizeaza macro releases programate; mai putine testeaza stiri neprogramate pe ferestre intraday foarte scurte.
3. Obiectiv: masuram daca stirile FinancialJuice sunt asociate cu reactii de pret si daca sentimentul LLM adauga informatie directionala.
4. Contributii:
   - dataset intraday pe doua active;
   - event-study cu baseline matched;
   - control pentru clustere de stiri;
   - analiza explicita a pre-event drift / feed latency.

## 2. Literature Review

Subsectiuni:

- News and intraday price discovery.
- Event studies and market efficiency.
- Financial sentiment analysis with LLMs.
- Social media / online news and asset prices.

Atentie: citatiile din planul initial trebuie verificate manual inainte de paper. Nu folosi referinte neverificate doar pentru ca apar in notite.

## 3. Data

### 3.1 News Data

- Sursa: Discord FinancialJuice official newsfeed.
- Export: DiscordChatExporter JSON.
- Mesaje parsate: 63,016.
- Evenimente gold: 2,449.
- Filtru gold: `(red dot OR BREAKING) AND NOT $MACRO`.
- Categorii: `macro_release`, `central_bank`, `geopolitical`, `politics`, `energy`, `corporate`, `other`.

### 3.2 Price Data

- EUR/USD spot FX, Dukascopy 1-minute OHLCV.
- Nasdaq-100 proxy: Dukascopy `E_NQ-100` CFD 1-minute OHLCV.
- Preturile curente acopera exportul de stiri pana la `2026-05-05`.
- Toate timestamp-urile sunt UTC.

### 3.3 Final Analysis Sample

Raporteaza din `outputs/methodology_summary.csv`:

- common price start/end;
- evenimente eliminate in afara preturilor;
- evenimente folosite;
- numar de clustere;
- numar de bare per asset.

## 4. Methodology

### 4.1 Event-Time Alignment

Pentru a evita contaminarea ferestrei de event:

- fereastra post-event incepe la primul minut complet dupa timestamp-ul stirii;
- fereastra pre-event se termina la ultimul minut complet inainte de timestamp;
- aceasta regula este mai conservatoare decat folosirea `floor(timestamp)`.

### 4.2 Return Definitions

Pentru fiecare event `i`, asset `a` si fereastra `w`:

```text
price_return_i,a,w = (close_end - open_start) / open_start * 100
```

Outcome-uri suplimentare, mai robuste pentru paper:

```text
range_i,a,w = (max(high_window) - min(low_window)) / open_start * 100
max_abs_move_i,a,w = max(abs(max_up), abs(max_down))
abnormal_z_i,a,w = (outcome_i,a,w - matched_baseline_mean_a,w,h,d) / matched_baseline_sd_a,w,h,d
```

Pentru NDX:

```text
target_return = price_return
```

Pentru EUR/USD, deoarece sentimentul este etichetat pentru USD:

```text
target_return = -price_return_EURUSD
```

Aceasta conventie este esentiala pentru H2/H3/H4/H14.

### 4.3 Event Clustering

Stirile apropiate temporal nu sunt independente. Evenimentele sunt grupate in clustere daca distanta dintre ele este de cel mult 15 minute. Testele non-regresie folosesc primul eveniment per cluster; regresiile folosesc erori clusterizate.

Extensia noua construieste si un tabel cluster-level separat:

```text
cluster_event_study_windows.csv = event_cluster_id x asset x window
```

Pentru fiecare cluster se agrega sentimentul, surprise, expected magnitude, categoria dominanta, numarul de headline-uri si lungimea medie a headline-ului.

### 4.4 Matched Baseline

Baseline-ul se construieste din ferestre random valide, excluzand un buffer in jurul evenimentelor. Sampling-ul este matched pe:

- asset;
- durata ferestrei;
- ora UTC;
- ziua saptamanii, cand sunt destule observatii.

### 4.5 Hypothesis Tests

Ipotezele sunt impartite explicit in main results, robustness checks, appendix si limitations. Codul ruleaza toate testele pentru reproducibility, dar paper-ul prioritizeaza ipotezele cu verdict non-trivial.

**Main results (raportate in Section 5)**:

- H1: abs return event vs matched baseline, primary test = Mann-Whitney U one-sided (Welch t-test in appendix robustness).
- H2: target sentiment vs realized target direction, binomial one-sided. Raportat cu hit rate si CI 95%.
- H3: OLS `abs_return ~ sentiment + prior_trend + sentiment x prior_trend`, covarianta clusterizata.
- H4: closed-period `target_gap_pct ~ aggregate_target_sentiment`, HC3 robust SE.
- H8: pre-event drift vs matched baseline; formulare ca feed latency / information timing, nu dovada directa de front-running.
- H9: sign persistence +15m vs +4h.
- H11: hour/day effects (subsectiune scurta, focus EUR/USD).
- H14: raportat atat EUR/USD vs NDX, cat si USD proxy vs NDX.

**Extensii principale C1-C7 (in Section 5)**:

- C1: cluster-level target sentiment vs realized target direction.
- C2: range si max-absolute-move vs matched baseline. **Rezultatul cel mai puternic nou**.
- C3: abnormal z-scores pentru return, abs return, range si max move.
- C4: ipoteze targetate pe categorii (`central_bank`, `geopolitical`, `politics`, `energy`, `corporate`). Inlocuieste H7 (ANOVA pe categorii) care e redundant.
- C5: stabilitate pre/post `2026-01-15`.
- C6: regresii multivariate cu controale pentru categorie, surprise, magnitude, confidence, cluster size, headline length si pre-event move.
- C7: robustete la outlieri prin winsorizare 1%.

**Auxiliary LLM labels (consolidare H5+H13)**:

- O singura subsectiune "LLM auxiliary labels (magnitude, surprise)" cu ANOVA + Kruskal-Wallis pe ambele label-uri. Tabel combinat. Verdict: util explorator, nu predictor robust.

**Limitations (o propozitie/paragraf, nu subsection in Results)**:

- H6: LLM confidence is uncalibrated (Brier > naive baseline); not used as a probability. Tabelele in appendix.
- H10: Volume proxy only (Dukascopy tick volume, nu consolidated). Mentionat in Limitations, tabelele in appendix.
- H12: No robust bear/bull asymmetry detected. O propozitie.
- C8: Flash/Pro consensus exploratory on n=200, underpowered for main paper. Mentionat in footnote sau Limitations.

**Window strategy**:

- **Primary windows reported in Section 5 tables**: 5m, 15m, 60m.
- **Appendix robustness**: 1m (bid-ask bounce concerns) si 240m (margin of "intraday").
- Aceasta reduce dimensiunea tabelelor principale cu ~40% fara a pierde concluzii.

### 4.6 Multiple Testing

Toate p-value-urile din tabelele `h*_results.csv` primesc q-value Benjamini-Hochberg FDR. In paper, concluziile principale trebuie trase pe q-values, nu doar pe p-values.

## 5. Results

Structura curatata, 6 subsectiuni (in loc de 22 unitati de raportare initiale):

1. **§5.1 Volatility and magnitude (central)**: H1 + C2 + C3. Raportat pe ferestre 5/15/60m. Acesta e rezultatul central al paper-ului.
2. **§5.2 Direction (modest edge)**: H2 + C1 + backtest cu costuri. Operationalizeaza "edge < costuri".
3. **§5.3 Heterogeneity by category and time**: C4 (categorii) + H11 (time-of-day, scurt).
4. **§5.4 Timing and persistence**: H8 (pre-event drift cu caveat feed latency) + H9 (persistence).
5. **§5.5 Market structure**: H4 (closed-period gap) + H14 (cross-asset, scurt).
6. **§5.6 Robustness defense**: C5 (pre/post cutoff) + C6 (multivariate controls) + C7 (winsorization). Plus subsectiune scurta "LLM auxiliary labels" (H5+H13 consolidat).

**Cut din main results, mentionate doar in Limitations**: H6, H10, H12, C8.

**Cut total din raportare**: H7 (suprapus cu C4).

Evita formularea "all hypotheses were confirmed". Foloseste verdict:

- robust;
- partial;
- mixed;
- weak;
- exploratory.

## 6. Discussion

Puncte de discutat:

- De ce H1 este mai puternic decat H2: stirile cresc volatilitatea mai clar decat prezic directia.
- De ce range/max-move este un outcome mai stabil decat directia close-to-close.
- De ce split-ul post-cutoff ajuta la discutia despre memorization, dar nu inlocuieste validarea manuala.
- De ce pre-event drift nu inseamna automat insider trading sau front-running.
- De ce confidence-ul LLM nu este calibrat.
- De ce volumul Dukascopy este proxy.
- De ce rezultatele NDX si EUR/USD difera.

## 7. Limitations

Include obligatoriu:

- un singur feed de stiri (FinancialJuice Discord);
- timestamp Discord, nu timestamp sursa primara;
- perioada de preturi mai scurta decat exportul de stiri;
- doar doua active;
- NDX este CFD proxy (Dukascopy `E_NQ-100`), nu futures/ETF oficial;
- sentiment LLM nevalidat manual inca (in lucru: 200-event sample cu doi etichetatori, Cohen's kappa);
- multiple testing addressed via BH-FDR, dar number of tested hypotheses ramane mare;
- evenimente suprapuse si clustere (addressed via cluster dedupe + clustered SE);
- volume proxy (Dukascopy tick volume nu este consolidated volume; H10 mutat in appendix din cauza asta);
- **LLM confidence is uncalibrated** (H6 finding); cannot be used as probability of correctness;
- **No robust bear/bull asymmetry detected** (H12); reaction is symmetric in our sample;
- **Flash/Pro model consensus exploratory** (C8) tested only on n=200 subsample due to API cost, underpowered for main inference;
- absence of baseline comparison cu metode standard (dictionary Loughran-McDonald, FinBERT) este o limitare cunoscuta; in lucru ca extension.

## 8. Conclusion

Concluzie recomandata:

Stirile neasteptate din feed-ul analizat sunt asociate robust cu miscari intraday peste baseline, dar sentimentul LLM ofera doar un edge directional modest. Cele mai valoroase contributii sunt masurarea reactiei de volatilitate, analiza timing-ului informatiei si evidenta ca feed latency trebuie tratata explicit in event studies pe stiri online.

## Appendix

Include:

- promptul LLM si few-shot examples;
- schema output sentiment;
- setarile din `methodology_summary.csv`;
- link repo;
- comanda `validate_outputs.py`;
- tabelele H1-H14 complete (inclusiv H6, H10, H12 cu rezultate null si C8 cu n=200);
- ferestre 1m si 240m (robustness);
- Welch t-test ca robustness check pentru H1 (MWU este primary).

## Pre-submission TODO

Inainte de submission, urmatoarele trebuie completate. In ordinea impactului:

**Blocking pentru credibilitate**:

1. **Validare manuala sentiment** (200 evenimente, 2 etichetatori):
   - Sample-ul exista in `outputs/manual_validation_sample.csv` (generat de `prepare_manual_validation.py`).
   - Scoring exista in `score_manual_validation.py` (Cohen's kappa + F1 LLM vs consens).
   - Split pre/post `2026-01-15` pentru memorization risk argument.
   - Fara aceasta, claim-urile despre LLM sentiment nu sunt falsifiable pentru reviewer.

**Strong nice-to-have**:

2. **Baseline comparison cu FinBERT si Loughran-McDonald dictionary**:
   - Script nou (~1-2 zile) care ruleaza ambele baseline pe acelasi corpus.
   - Permite fraza tip "our LLM beats dictionary baseline by X pp on hit rate, matches FinBERT".
   - Raspunde direct la "why LLM and not standard methods?" din referee report.

3. **Case studies cu timestamp verificat la sursa primara**:
   - 5-10 stiri reprezentative, verificate manual fata de Bloomberg/Reuters/oficial source.
   - Intareste interpretarea H8 (feed latency vs front-running).

**Formatting / submission**:

4. **`references.bib` in APA 7 verificat manual**:
   - Nu folosi citatii neverificate din notitele initiale.
   - Lista de checat: Tetlock 2007, Loughran-McDonald 2011, Andersen-Bollerslev-Diebold-Vega 2003, Calomiris-Mamaysky 2019, Heston-Sinha 2017, FinBERT (Yang et al. 2020).

5. **Reproducibility statement**:
   - Link repo public.
   - Seed (`42`), versiuni in `requirements.txt`.
   - Comanda `validate_outputs.py`.

6. **Pre-registration / ethics**:
   - Daca journal-ul cere: declaratie ca ipotezele initiale (H1-H14) au fost specificate inainte de cleanup-ul rezultatelor.
   - Mentionare ca H6/H10/H12 raman raportate in appendix chiar daca verdict null.
