# Plan proiect economie

Tema: impactul stirilor financiare online neasteptate asupra preturilor intraday EUR/USD si Nasdaq-100.

Acest plan inlocuieste varianta initiala optimista. Versiunea curenta este orientata spre un research paper defensabil.

## Intrebarea de cercetare

Sunt stirile neprogramate dintr-un feed financiar online asociate cu miscari intraday anormale ale EUR/USD si Nasdaq-100? In plus, sentimentul generat de un LLM adauga informatie directionala sau doar ajuta la explicarea magnitudinii?

## Date

- Stiri: FinancialJuice Discord newsfeed, export DiscordChatExporter.
- Preturi:
  - EUR/USD Dukascopy 1-minute OHLCV;
  - `E_NQ-100` Dukascopy CFD ca proxy Nasdaq-100 1-minute OHLCV.
- Toate timestamp-urile sunt UTC.
- Analiza foloseste doar intervalul comun intre stiri si preturi.

## Pipeline

1. `parse_fj_discord.py`
   - parseaza JSON-ul;
   - marcheaza red-dot / BREAKING / MACRO;
   - creeaza categorii: central bank, geopolitical, politics, energy, corporate, other.

2. `download_prices.py`
   - descarca preturi Dukascopy;
   - poate face merge cu CSV-urile existente;
   - default start: `2025-03-24`.

3. `sentiment.py`
   - ruleaza clasificare DeepSeek-compatible;
   - foloseste cache SQLite;
   - output: sentiment USD, sentiment NDX, strength, magnitude, surprise, confidence.

4. `event_study.py`
   - filtreaza la intervalul comun;
   - calculeaza ferestre post/pre cu aliniere conservatoare;
   - corecteaza conventia USD vs EUR/USD;
   - grupeaza evenimente in clustere;
   - construieste baseline matched;
   - ruleaza H1-H14;
   - adauga FDR q-values.

5. `validate_outputs.py`
   - verifica output-urile metodologic sensibile.

6. `make_report.py`
   - genereaza raport HTML din CSV-uri, fara text hardcodat.

## Ipoteze

### Core

- H1: stirile sunt asociate cu miscari absolute peste baseline.
- H2: sentimentul LLM prezice directia peste hazard.
- H3: trendul anterior modereaza impactul stirii.
- H4: sentimentul agregat in perioade inchise prezice gap-ul de redeschidere.

### Exploratorii

- H5: expected magnitude vs magnitudine realizata.
- H6: calibrarea confidence.
- H7: diferenta intre categorii.
- H8: pre-event drift / feed latency / information timing.
- H9: persistenta vs decay.
- H10: volum proxy.
- H11: time-of-day / day-of-week.
- H12: bear vs bull asymmetry.
- H13: surprise level.
- H14: cross-asset spillover.

## Standarde metodologice

- Foloseste q-values FDR pentru concluzii.
- Nu interpreta p-value-uri foarte mici fara discutia dependentei intre evenimente.
- Nu folosi `confidence` LLM ca probabilitate calibrata.
- Nu prezenta H8 ca dovada directa de front-running.
- Nu prezenta volumul Dukascopy ca volum real CME/interbank.
- Nu spune “toate ipotezele sunt confirmate”.

## Ce trebuie finalizat pentru paper

- Validare manuala sentiment pe 200 evenimente:
  - doi etichetatori;
  - Cohen's kappa;
  - F1 vs consens;
  - split pre/post cutoff pentru memorization risk.
- Bibliografie APA 7 verificata.
- Tabel central cu verdict pe ipoteze.
- 4-6 case studies cu timestamp verificat fata de sursa primara a stirii.
- Actualizare preturi pana la finalul exportului sau justificare a filtrarii.

## Verdict asteptat

Paper-ul ar trebui sa sustina o concluzie nuantata:

> Unexpected online news is robustly associated with elevated intraday absolute returns, but LLM sentiment provides only a modest directional edge. Feed latency and clustered news arrivals are central methodological challenges in high-frequency news event studies.
