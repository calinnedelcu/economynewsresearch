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
- rezultat central: miscari absolute peste baseline;
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

### 4.4 Matched Baseline

Baseline-ul se construieste din ferestre random valide, excluzand un buffer in jurul evenimentelor. Sampling-ul este matched pe:

- asset;
- durata ferestrei;
- ora UTC;
- ziua saptamanii, cand sunt destule observatii.

### 4.5 Hypothesis Tests

Ipotezele trebuie raportate conservator:

- H1: abs return event vs matched baseline, Welch one-sided + Mann-Whitney U.
- H2: target sentiment vs realized target direction, binomial one-sided.
- H3: OLS `abs_return ~ sentiment + prior_trend + sentiment x prior_trend`, covarianta clusterizata.
- H4: closed-period `target_gap_pct ~ aggregate_target_sentiment`, HC3 robust SE.
- H5/H7/H13: ANOVA + Kruskal-Wallis.
- H6: Brier score si reliability buckets.
- H8: pre-event drift vs matched baseline; formulare ca feed latency / information timing, nu dovada directa de front-running.
- H9: sign persistence +15m vs +4h.
- H10: volume proxy only.
- H11: hour/day effects.
- H12: bear vs bull asymmetry.
- H14: raportat atat EUR/USD vs NDX, cat si USD proxy vs NDX.

### 4.6 Multiple Testing

Toate p-value-urile din tabelele `h*_results.csv` primesc q-value Benjamini-Hochberg FDR. In paper, concluziile principale trebuie trase pe q-values, nu doar pe p-values.

## 5. Results

Structura recomandata:

1. H1 ca rezultat central.
2. H2/H3 ca teste despre utilitatea sentimentului.
3. H8/H9 ca discutie despre timing si persistenta.
4. H4/H14 ca market-structure / cross-asset.
5. H5-H7/H10-H13 ca analize exploratorii.

Evita formularea “all hypotheses were confirmed”. Foloseste verdict:

- robust;
- partial;
- mixed;
- weak;
- exploratory.

## 6. Discussion

Puncte de discutat:

- De ce H1 este mai puternic decat H2: stirile cresc volatilitatea mai clar decat prezic directia.
- De ce pre-event drift nu inseamna automat insider trading sau front-running.
- De ce confidence-ul LLM nu este calibrat.
- De ce volumul Dukascopy este proxy.
- De ce rezultatele NDX si EUR/USD difera.

## 7. Limitations

Include obligatoriu:

- un singur feed de stiri;
- timestamp Discord, nu timestamp sursa primara;
- perioada de preturi mai scurta decat exportul de stiri;
- doar doua active;
- NDX este CFD proxy, nu futures/ETF oficial;
- sentiment LLM nevalidat manual inca;
- multiple testing;
- evenimente suprapuse si clustere;
- volume proxy.

## 8. Conclusion

Concluzie recomandata:

Stirile neasteptate din feed-ul analizat sunt asociate robust cu miscari intraday peste baseline, dar sentimentul LLM ofera doar un edge directional modest. Cele mai valoroase contributii sunt masurarea reactiei de volatilitate, analiza timing-ului informatiei si evidenta ca feed latency trebuie tratata explicit in event studies pe stiri online.

## Appendix

Include:

- promptul LLM;
- schema output sentiment;
- setarile din `methodology_summary.csv`;
- link repo;
- comanda `validate_outputs.py`;
- tabelele H1-H14 complete.
