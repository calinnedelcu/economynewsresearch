# Studiu stiri online vs preturi intraday

Event-study pe stiri FinancialJuice Discord si preturi intraday EUR/USD + Nasdaq-100.

Perioada disponibila in exportul de stiri: `2025-03-24` -> `2026-05-05`.
Perioada comuna folosita in analiza curenta: `2025-03-24` -> `2026-05-05`.

## Status curent

Pipeline-ul tehnic este rulat end-to-end, dar rezultatele trebuie tratate ca rezultate de research corectate, nu ca versiunea initiala optimista.

Corectii metodologice aplicate:

- ferestrele post-event incep la primul minut complet dupa timestamp-ul stirii;
- evenimentele din afara intervalului comun de preturi sunt eliminate automat;
- `sentiment_usd` este evaluat contra unui proxy USD corect: `-EUR/USD`, nu direct contra EUR/USD;
- stirile apropiate sunt grupate in clustere de 15 minute, iar testele non-regresie folosesc primul eveniment per cluster;
- exista si output cluster-level explicit: un rand per `event_cluster_id` x asset x window;
- baseline-ul random este matched pe ora UTC si ziua saptamanii, cu buffer de excludere in jurul evenimentelor;
- fiecare fereastra include acum `range_pct`, `max_abs_move_pct` si z-score-uri anormale fata de baseline;
- exista teste pre/post `2026-01-15`, ca verificare impotriva obiectiei de memorization;
- exista teste targetate pe categorie si regresii multivariate cu controale pentru categorie, surprise, cluster size si lungime headline;
- exista robustete outlier prin winsorizare 1%;
- subsetul Flash/Pro consensus este testat separat pe `outputs/compare_models.csv`;
- regresiile folosesc erori robuste/clusterizate;
- toate p-value-urile din output primesc q-value Benjamini-Hochberg FDR;
- H10 include explicit caveat-ul ca volumul Dukascopy este proxy/tick volume.

Validator:

```bash
.venv/Scripts/python.exe validate_outputs.py
```

Output asteptat:

```text
OK: outputs passed methodology sanity checks
```

## Rezultate cheie dupa corectii

| H | Verdict curent | Interpretare scurta |
|---|---|---|
| H1 | robust | Evenimentele au miscari absolute peste baseline pe ambele active si toate ferestrele. |
| H2 | modest / mixed | Edge directional mic; dupa FDR ramane semnificativ doar un subset restrans. |
| H3 | partial | Interactiunea sentiment x trend ramane relevanta mai ales pe NDX +5m/+15m. |
| H4 | partial | NDX closed-period gap are semnal; EUR/USD este marginal/nesemnificativ. |
| H5 | slab / partial | `expected_magnitude` ajuta limitat, mai ales NDX +1m. |
| H6 | slab | `confidence` este overconfident; nu trebuie folosit ca probabilitate calibrata. |
| H7 | partial | Categoriile conteaza modest pentru EUR/USD, nu clar pentru NDX. |
| H8 | robust, dar caveat | Pre-event drift > baseline, dar poate indica lag al feed-ului, nu neaparat front-running. |
| H9 | robust | Miscarea tinde sa persiste intre +15m si +4h. |
| H10 | proxy evidence | Volumul proxy creste in jurul stirilor, dar sursa nu e volum consolidat. |
| H11 | partial | Time-of-day conteaza pentru EUR/USD; semnalul pe NDX este mai slab dupa clustering. |
| H12 | slab | Asimetria bear vs bull este mica. |
| H13 | slab / partial | `surprise_level` ajuta mai ales pentru NDX pe ferestre scurte. |
| H14 | robust, interpretare atenta | Corelatia EUR/USD vs NDX este negativa; USD proxy vs NDX este pozitiva prin conventie. |

Extensii noi pentru paper:

| Output | Verdict curent | Interpretare scurta |
|---|---|---|
| Cluster sentiment | partial | Agregarea pe cluster imbunatateste usor directia pe NDX +5m/+15m, dar nu transforma sentimentul intr-un predictor puternic. |
| Range/max move | foarte robust | Range-ul si miscarea maxima sunt peste baseline in toate activele/ferestrele; acesta este cel mai puternic rezultat nou. |
| Abnormal z-scores | robust | Miscarea anormala standardizata ramane pozitiva pe close-to-close, range si max move. |
| Targeted categories | util pentru paper | Central bank, geopolitical, politics, energy si corporate pot fi raportate separat; multe semnale sunt mai clare pe magnitudine decat directie. |
| Pre/post cutoff | robust | Efectul pe max move ramane pozitiv si dupa `2026-01-15`. |
| Multivariate controls | important ca aparare | Semnalul de miscare ramane modelabil peste categorie/surprise/lungime; pre-event move si cluster size sunt controale importante. |
| Outlier robustness | robust | Winsorizarea 1% nu elimina semnalul principal. |
| Flash/Pro consensus | exploratoriu | Consensus-ul da ferestre directionale interesante, dar esantionul de 200 este prea mic pentru concluzie centrala. |

Raportul HTML curent este generat din CSV-uri, fara rezultate hardcodate:

- `outputs/report.html`
- `docs/report.html`

## Structura proiect

```text
parse_fj_discord.py     # DiscordChatExporter JSON -> outputs/events.csv
download_prices.py      # Dukascopy EUR/USD + E_NQ-100 1m -> outputs/prices_*.csv
sentiment.py            # DeepSeek-compatible API -> outputs/events_sentiment.csv
compare_models.py       # Flash vs Pro A/B agreement sample
event_study.py          # event-study core, H1-H14, cluster tests, z-scores, FDR q-values
make_report.py          # HTML report generated from current outputs
validate_outputs.py     # sanity checks for methodology-sensitive outputs
prepare_manual_validation.py  # 200-row sample for human annotation
score_manual_validation.py    # Cohen's kappa + F1 after labels are filled
data/                   # local raw JSON exports, gitignored
outputs/                # generated CSVs, figures, report, cache, gitignored
docs/                   # project notes and copied report
```

## Setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Sentiment classification necesita `.env`:

```text
DEEPSEEK_API_KEY=sk-...
```

## Rulare pipeline

```bash
# 1. Parse Discord export
.venv/Scripts/python.exe parse_fj_discord.py "data/FinancialJuice ... .json" -o outputs/events.csv --summary

# 2. Preturi. Default: 2025-03-24 -> azi UTC
.venv/Scripts/python.exe download_prices.py --start 2025-03-24 --merge-existing

# 3. Sentiment LLM, cu cache SQLite
.venv/Scripts/python.exe sentiment.py outputs/events.csv -o outputs/events_sentiment.csv --workers 15

# 4. Event study core
.venv/Scripts/python.exe event_study.py

# 5. Validare output-uri
.venv/Scripts/python.exe validate_outputs.py

# 6. Raport HTML
.venv/Scripts/python.exe make_report.py --also-copy docs/report.html

# 7. Esantion pentru validare manuala
.venv/Scripts/python.exe prepare_manual_validation.py

# Dupa ce etichetatorii completeaza CSV-ul:
.venv/Scripts/python.exe score_manual_validation.py
```

## Output-uri principale

- `outputs/events.csv`: toate mesajele parsate;
- `outputs/events_sentiment.csv`: evenimente gold cu sentiment LLM;
- `outputs/event_study_windows.csv`: event x asset x window;
- `outputs/cluster_event_study_windows.csv`: cluster x asset x window;
- `outputs/h1_results.csv` ... `outputs/h14_results.csv`: rezultate per ipoteza;
- `outputs/cluster_sentiment_results.csv`: directie pe sentiment agregat la nivel de cluster;
- `outputs/range_outcomes_results.csv`: range si max-move vs baseline;
- `outputs/abnormal_z_results.csv`: z-score-uri anormale standardizate;
- `outputs/targeted_category_results.csv`: ipoteze targetate pe categorii;
- `outputs/pre_post_stability_results.csv`: stabilitate inainte/dupa `2026-01-15`;
- `outputs/multivariate_results.csv`: regresii multivariate cu controale;
- `outputs/outlier_robustness_results.csv`: robustete la winsorizare 1%;
- `outputs/model_consensus_results.csv`: subset Flash/Pro consensus;
- `outputs/h4_periods.csv`: perioade inchise folosite pentru H4;
- `outputs/methodology_summary.csv`: setarile metodologice efective;
- `outputs/report.html`: raport vizual curent.
- `outputs/manual_validation_sample.csv`: sample pentru validare umana.

## Pentru paper

Nu formula concluziile ca “toate ipotezele au fost confirmate”. Varianta defensabila este:

1. stiri neasteptate sunt asociate cu volatilitate intraday anormala;
2. sentimentul LLM ofera un edge directional mic, nu un predictor puternic;
3. pre-event drift-ul sugereaza fie latenta feed-ului, fie informatie deja incorporata de piata;
4. rezultatele cele mai solide sunt max-move/range, magnitudinea anormala, drift-ul pre-event si persistenta;
5. rezultatele bazate pe volum, confidence, surprise-level si consensus sample trebuie raportate ca exploratorii.
